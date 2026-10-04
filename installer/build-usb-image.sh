#!/usr/bin/env bash
# USB #1 - build the BAU base-OS installer image.
#
# Downloads the official Debian netinst ISO for the current stable release,
# verifies the Debian CD signing key's signature over SHA512SUMS and the
# ISO's hash, then remasters it with:
#   * a "BAU install" boot entry that loads preseed/bau.preseed
#   * /bau/ on the ISO (first-boot notice + baseline hardening)
# Boot records are replayed unchanged, so UEFI Secure Boot (shim) still works.
#
# The preseed NEVER selects or confirms the target disk: the Debian
# partitioner shows the disk and asks for confirmation. Run `bau wipe-gate`
# on the old system before booting this stick (see docs/INSTALL.md).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${HERE}/lib/common.sh"

MIRROR="https://cdimage.debian.org/debian-cd/current"
ARCH="amd64"
OUT_DIR="${HERE}/../dist"
ISO_IN=""
# Debian CD signing keys. Confirm at https://www.debian.org/CD/verify before first use.
KEY_FPRS=("DF9B9C49EAA9298432589D76DA87E80D6294BE9B" "10460DAD76165AD81FBC0CE9988021A964E6EA7D")
KEYSERVER="hkps://keyring.debian.org"

usage() {
  cat <<EOF
usage: $0 [--arch amd64] [--out DIR] [--iso LOCAL_NETINST.iso --sums SHA512SUMS --sig SHA512SUMS.sign]

  --iso/--sums/--sig  use files you already downloaded (offline build); all three required
  --mirror URL        default ${MIRROR}
EOF
}

SUMS_IN="" SIG_IN=""
while (($#)); do
  case $1 in
    --arch) ARCH=$2; shift 2 ;;
    --out) OUT_DIR=$2; shift 2 ;;
    --mirror) MIRROR=$2; shift 2 ;;
    --iso) ISO_IN=$2; shift 2 ;;
    --sums) SUMS_IN=$2; shift 2 ;;
    --sig) SIG_IN=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "unknown argument $1" ;;
  esac
done

need xorriso gpg sha512sum sha256sum
mkdir -p "${OUT_DIR}"
OUT_DIR="$(cd "${OUT_DIR}" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT
export GNUPGHOME="${WORK}/gnupg"
mkdir -m 700 "${GNUPGHOME}"

base="${MIRROR}/${ARCH}/iso-cd"
if [[ -n "${ISO_IN}" ]]; then
  [[ -n "${SUMS_IN}" && -n "${SIG_IN}" ]] || die "--iso needs --sums and --sig"
  cp "${SUMS_IN}" "${WORK}/SHA512SUMS"
  cp "${SIG_IN}" "${WORK}/SHA512SUMS.sign"
else
  need curl
  log "fetching checksums from ${base}"
  curl -fsSL --proto '=https' "${base}/SHA512SUMS" -o "${WORK}/SHA512SUMS"
  curl -fsSL --proto '=https' "${base}/SHA512SUMS.sign" -o "${WORK}/SHA512SUMS.sign"
fi

log "verifying SHA512SUMS signature"
if ! gpg --batch --quiet --keyserver "${KEYSERVER}" --recv-keys "${KEY_FPRS[@]}" 2>/dev/null; then
  # Keyserver protocol blocked (proxies often are): fetch the same keys over HTTPS.
  need curl
  for f in "${KEY_FPRS[@]}"; do
    curl -fsSL --proto '=https' "https://keyring.debian.org/pks/lookup?op=get&search=0x${f}" \
      | gpg --batch --quiet --import || die "could not fetch Debian CD signing key ${f}"
  done
fi
status="$(gpg --batch --status-fd 1 --verify "${WORK}/SHA512SUMS.sign" "${WORK}/SHA512SUMS" 2>/dev/null || true)"
signer="$(awk '/^\[GNUPG:\] VALIDSIG/ {print $NF}' <<<"${status}")"
ok=0
for f in "${KEY_FPRS[@]}"; do [[ "${signer}" == "${f}" ]] && ok=1; done
((ok)) || die "SHA512SUMS is not validly signed by a pinned Debian CD key (got '${signer}')"

iso_name="$(awk '{print $2}' "${WORK}/SHA512SUMS" | grep -E "^debian-[0-9.]+-${ARCH}-netinst\.iso$" | head -n1)"
[[ -n "${iso_name}" ]] || die "no netinst ISO listed in SHA512SUMS"
if [[ -n "${ISO_IN}" ]]; then
  [[ "$(basename "${ISO_IN}")" == "${iso_name}" ]] || die "ISO name does not match SHA512SUMS (${iso_name})"
  cp "${ISO_IN}" "${WORK}/${iso_name}"
else
  log "downloading ${iso_name}"
  curl -fL --proto '=https' "${base}/${iso_name}" -o "${WORK}/${iso_name}"
fi
(cd "${WORK}" && grep " ${iso_name}\$" SHA512SUMS | sha512sum -c -) || die "ISO checksum mismatch"
log "official ISO verified: ${iso_name}"

# Stage the files we add to the image.
STAGE="${WORK}/stage"
mkdir -p "${STAGE}/preseed" "${STAGE}/bau/hardening"
cp "${HERE}/preseed/bau.preseed" "${STAGE}/preseed/bau.preseed"
cp "${HERE}/firstboot/firstboot-setup.sh" "${STAGE}/bau/firstboot-setup.sh"
cp "${HERE}/payload/hardening/"* "${STAGE}/bau/hardening/"

xorriso -osirrox on -indev "${WORK}/${iso_name}" \
  -extract /boot/grub/grub.cfg "${STAGE}/grub.cfg" 2>/dev/null \
  || die "ISO has no /boot/grub/grub.cfg"
chmod u+w "${STAGE}/grub.cfg"
entry="menuentry --hotkey=b 'BAU install (encrypted disk, you confirm the target)' {
    set background_color=black
    linux    /install.amd/vmlinuz auto=true file=/cdrom/preseed/bau.preseed vga=788 --- quiet
    initrd   /install.amd/initrd.gz
}
"
# Insert our entry before the first stock menuentry so it is the default.
awk -v e="${entry}" 'BEGIN{done=0} /^menuentry/ && !done {printf "%s\n", e; done=1} {print}' \
  "${STAGE}/grub.cfg" > "${STAGE}/grub.cfg.new"
mv "${STAGE}/grub.cfg.new" "${STAGE}/grub.cfg"

maps=(-map "${STAGE}/preseed" /preseed -map "${STAGE}/bau" /bau
      -map "${STAGE}/grub.cfg" /boot/grub/grub.cfg)
# Legacy BIOS menu, when present.
if xorriso -osirrox on -indev "${WORK}/${iso_name}" -extract /isolinux/txt.cfg \
     "${STAGE}/txt.cfg" 2>/dev/null; then
  chmod u+w "${STAGE}/txt.cfg"
  {
    printf 'default bau\nlabel bau\n\tmenu label ^BAU install (encrypted disk)\n'
    printf '\tkernel /install.amd/vmlinuz\n'
    printf '\tappend auto=true file=/cdrom/preseed/bau.preseed vga=788 initrd=/install.amd/initrd.gz --- quiet\n'
    grep -v '^default ' "${STAGE}/txt.cfg"
  } > "${STAGE}/txt.cfg.new"
  mv "${STAGE}/txt.cfg.new" "${STAGE}/txt.cfg"
  maps+=(-map "${STAGE}/txt.cfg" /isolinux/txt.cfg)
fi

out="${OUT_DIR}/bau-${iso_name}"
rm -f "${out}"
xorriso -indev "${WORK}/${iso_name}" -outdev "${out}" "${maps[@]}" -boot_image any replay \
  >/dev/null 2>&1 || die "xorriso remaster failed"
sha256sum "${out}" > "${out}.sha256"
cat > "${out}.json" <<EOF
{"image": "$(basename "${out}")", "base_iso": "${iso_name}", "base_iso_signer": "${signer}",
 "sha256": "$(cut -d' ' -f1 "${out}.sha256")", "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF
log "built ${out}"
log "next: sudo installer/write-usb.sh ${out} /dev/sdX"
