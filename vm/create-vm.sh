#!/usr/bin/env bash
# Build a VirtualBox "test laptop" with both BAU sticks plugged in, so the whole two-stick
# install can be rehearsed on this computer before touching the real laptop.
#
#   bash vm/create-vm.sh [--usb1 FILE.iso] [--payload FILE.iso] [--name BAU-Test]
#                        [--memory-mb 8192] [--cpus 4] [--disk-gb 60]
#
# Without --usb1/--payload it looks for bau-debian-*.iso and BAU-PAYLOAD-*.iso (from the
# GitHub release) in the current folder and ~/Downloads, and checks them against
# SHA256SUMS.txt when that file sits next to them. Needs VirtualBox 7 on Linux or an
# Intel Mac (Apple-silicon Macs: use the Docker test drive instead, see docker/README.md).
set -euo pipefail

NAME=BAU-Test
MEM=8192
CPUS=4
DISK_GB=60
USB1=""
PAYLOAD=""
while (($#)); do
  case $1 in
    --usb1) USB1=$2; shift 2 ;;
    --payload) PAYLOAD=$2; shift 2 ;;
    --name) NAME=$2; shift 2 ;;
    --memory-mb) MEM=$2; shift 2 ;;
    --cpus) CPUS=$2; shift 2 ;;
    --disk-gb) DISK_GB=$2; shift 2 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done

die() { echo "create-vm: $*" >&2; exit 1; }
command -v VBoxManage >/dev/null || die "VirtualBox not found - install it from virtualbox.org"

find_one() {  # newest file matching the pattern $1 in . or ~/Downloads
  local f="" c
  # shellcheck disable=SC2086  # $1 is a wildcard pattern and is meant to expand
  for c in ./$1 "$HOME"/Downloads/$1; do
    [[ -f "$c" ]] || continue
    if [[ -z "$f" || "$c" -nt "$f" ]]; then f="$c"; fi
  done
  [[ -n "$f" ]] || die "no $1 found here or in ~/Downloads - download it from the GitHub release"
  echo "$f"
}
[[ -n "$USB1" ]] || USB1="$(find_one 'bau-debian-*.iso')"
[[ -n "$PAYLOAD" ]] || PAYLOAD="$(find_one 'BAU-PAYLOAD-*.iso')"
[[ -f "$USB1" && -f "$PAYLOAD" ]] || die "image not found: $USB1 / $PAYLOAD"

for img in "$USB1" "$PAYLOAD"; do
  sums="$(dirname "$img")/SHA256SUMS.txt"
  if [[ -f "$sums" ]]; then
    want="$(grep " $(basename "$img")\$" "$sums" | cut -d' ' -f1 || true)"
    [[ -n "$want" ]] || die "$(basename "$img") is not listed in $sums"
    got="$(sha256sum "$img" 2>/dev/null || shasum -a 256 "$img")"
    [[ "${got%% *}" == "$want" ]] || die "checksum mismatch for $img - download it again"
    echo "verified $(basename "$img")"
  else
    echo "WARNING: no SHA256SUMS.txt next to $(basename "$img"); checksum not verified"
  fi
done

if VBoxManage showvminfo "$NAME" >/dev/null 2>&1; then
  die "a VM called $NAME already exists (delete it in VirtualBox or use --name)"
fi
base="$(VBoxManage list systemproperties | sed -n 's/^Default machine folder: *//p')"
disk="$base/$NAME/$NAME.vdi"

VBoxManage createvm --name "$NAME" --ostype Debian_64 --register
VBoxManage modifyvm "$NAME" --memory "$MEM" --cpus "$CPUS" --firmware efi64 \
  --graphicscontroller vmsvga --vram 128 --nic1 nat \
  --boot1 dvd --boot2 disk --boot3 none --boot4 none
VBoxManage createmedium disk --filename "$disk" --size $((DISK_GB * 1024)) --format VDI
VBoxManage storagectl "$NAME" --name SATA --add sata --controller IntelAhci --portcount 3
VBoxManage storageattach "$NAME" --storagectl SATA --port 0 --device 0 --type hdd --medium "$disk"
VBoxManage storageattach "$NAME" --storagectl SATA --port 1 --device 0 --type dvddrive \
  --medium "$USB1"
VBoxManage storageattach "$NAME" --storagectl SATA --port 2 --device 0 --type dvddrive \
  --medium "$PAYLOAD"

cat <<EOF

VM "$NAME" is ready: ${MEM} MB RAM, ${CPUS} CPUs, ${DISK_GB} GB disk, USB #1 and USB #2 inserted.
Start it:   VBoxManage startvm "$NAME" --type gui     (or double-click it in VirtualBox)
Then follow vm/README.md: install from USB #1, log in, and run USB #2's install.sh.
EOF
