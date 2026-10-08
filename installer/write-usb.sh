#!/usr/bin/env bash
# Write an image to a USB stick, then read it back and verify the hash.
#
# Refuses: non-whole-disk targets, the disk holding the running system, and
# non-USB/non-removable disks (unless --allow-non-usb). Requires typing the
# stick's serial number. Writes <image>.installer-record.json, which
# `bau wipe-gate --installer-record` requires before any wipe.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${HERE}/lib/common.sh"

ALLOW_NON_USB=0
args=()
while (($#)); do
  case $1 in
    --allow-non-usb) ALLOW_NON_USB=1; shift ;;
    -h|--help) echo "usage: $0 IMAGE.iso /dev/sdX [--allow-non-usb]"; exit 0 ;;
    *) args+=("$1"); shift ;;
  esac
done
((${#args[@]} == 2)) || die "usage: $0 IMAGE.iso /dev/sdX"
IMG=${args[0]} DEV=${args[1]}

require_root
need lsblk dd sha256sum stat blockdev
[[ -f "${IMG}" ]] || die "image not found: ${IMG}"
[[ -b "${DEV}" ]] || die "not a block device: ${DEV}"

# One lsblk call per field: robust to spaces in model names and empty columns.
field() { lsblk -dn -b -o "$1" "${DEV}" | sed 's/^ *//; s/ *$//'; }
TYPE=$(field TYPE) TRAN=$(field TRAN) RM=$(field RM) SIZE=$(field SIZE)
MODEL=$(field MODEL) SERIAL=$(field SERIAL)
[[ "${TYPE}" == "disk" ]] || die "${DEV} is a ${TYPE}, not a whole disk"

# lsblk lists the whole tree under DEV (partitions, LUKS, LVM), so this also
# catches an encrypted/LVM root that lives on the device.
if lsblk -ln -o MOUNTPOINT "${DEV}" | grep -qxE '/|/boot|/boot/efi|/home|/usr|/var'; then
  die "${DEV} holds the running system - refusing"
fi
if [[ "${TRAN}" != "usb" && "${RM}" != "1" ]] && ((ALLOW_NON_USB == 0)); then
  die "${DEV} is not a USB/removable disk (TRAN=${TRAN} RM=${RM}); use --allow-non-usb if you are sure"
fi
img_size=$(stat -c %s "${IMG}")
((SIZE >= img_size)) || die "stick too small: ${SIZE} < ${img_size} bytes"

echo "TARGET  ${DEV}"
echo "MODEL   ${MODEL}"
echo "SERIAL  ${SERIAL}"
echo "SIZE    ${SIZE} bytes"
echo "Everything on ${DEV} will be destroyed."
if [[ -n "${SERIAL}" ]]; then
  confirm_typed "Type the stick's serial number (${SERIAL}) to continue" "${SERIAL}"
else
  confirm_typed "No serial reported; type the device path (${DEV}) to continue" "${DEV}"
fi

while read -r part; do
  if [[ -n "${part}" ]]; then
    umount "/dev/${part}" 2>/dev/null || true
  fi
done < <(lsblk -ln -o NAME "${DEV}" | tail -n +2)

log "writing ${IMG} -> ${DEV}"
dd if="${IMG}" of="${DEV}" bs=4M conv=fsync oflag=direct status=progress
sync
blockdev --flushbufs "${DEV}" || true

log "verifying by reading the stick back"
want="$(sha256sum "${IMG}" | cut -d' ' -f1)"
got="$(head -c "${img_size}" "${DEV}" | sha256sum | cut -d' ' -f1)"
verified=false
[[ "${want}" == "${got}" ]] && verified=true

rec="${IMG}.installer-record.json"
cat > "${rec}" <<EOF
{"image": "$(basename "${IMG}")", "sha256": "${want}", "readback_sha256": "${got}",
 "verified": ${verified}, "device_model": "${MODEL}", "device_serial": "${SERIAL}",
 "written_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF
[[ "${verified}" == true ]] || die "read-back hash mismatch - do not use this stick"
log "verified. record: ${rec}"
