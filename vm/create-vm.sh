#!/usr/bin/env bash
# Build a VirtualBox "test laptop" with both BAU sticks plugged in, so the whole two-stick
# install can be rehearsed on this computer before touching the real laptop.
#
#   bash vm/create-vm.sh [--usb1 FILE.iso] [--payload FILE.iso] [--name BAU-Test]
#                        [--memory-mb N] [--cpus N] [--disk-gb 60]
#
# If the VM already exists, it is resized instead: safe memory and CPUs for this computer,
# disk first in the boot order. Its disk and anything installed on it are kept.
#
# Without --usb1/--payload it looks for bau-debian-*.iso and BAU-PAYLOAD-*.iso (from the
# GitHub release) in the current folder and ~/Downloads, and checks them against
# SHA256SUMS.txt when that file sits next to them. Needs VirtualBox 7 on Linux or an
# Intel Mac (Apple-silicon Macs: use the Docker test drive instead, see docker/README.md).
set -euo pipefail

NAME=BAU-Test
MEM=0      # 0 = half of this computer's RAM, 4-8 GB
CPUS=0     # 0 = half of this computer's cores, at most 4
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
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done

die() { echo "create-vm: $*" >&2; exit 1; }
# Size the VM from this computer so the host keeps enough memory: a VM that takes too
# much RAM makes the whole computer swap and freeze.
if [[ -r /proc/meminfo ]]; then host_mb=$(( $(awk '/^MemTotal:/ {print $2}' /proc/meminfo) / 1024 ))
else host_mb=$(( $(sysctl -n hw.memsize) / 1048576 )); fi
cores="$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
# At most 60% of RAM and at least 4 GB left for the computer itself.
max_mb=$(( host_mb * 6 / 10 )); ((max_mb > host_mb - 4096)) && max_mb=$(( host_mb - 4096 ))
max_mb=$(( max_mb - max_mb % 1024 )); ((max_mb < 2048)) && max_mb=2048
if ((MEM <= 0)); then
  MEM=$(( host_mb / 2 - (host_mb / 2) % 1024 )); ((MEM > 8192)) && MEM=8192
  ((MEM > max_mb)) && MEM=$max_mb; ((MEM < 2048)) && MEM=2048
fi
if ((CPUS <= 0)); then CPUS=$(( cores / 2 )); ((CPUS < 1)) && CPUS=1; ((CPUS > 4)) && CPUS=4; fi
if ((MEM > max_mb)); then
  echo "create-vm: ${MEM} MB for the VM is too much for this computer's ${host_mb} MB (it would freeze) - use --memory-mb ${max_mb} or less" >&2; exit 1
fi
command -v VBoxManage >/dev/null || die "VirtualBox not found - install it from virtualbox.org"
ask() { local a; read -r -p "$1 (y/N) " a; [[ $a =~ ^[Yy]([Ee][Ss])?$ ]]; }

if VBoxManage showvminfo "$NAME" >/dev/null 2>&1; then
  # Fix the existing VM instead of building a new one; its disk is left alone.
  state="$(VBoxManage showvminfo "$NAME" --machinereadable | sed -n 's/^VMState="\(.*\)"$/\1/p')"
  case $state in
    running|paused|stuck)
      ask "$NAME is running. Power it off now to fix its memory? Unsaved work inside it is lost" ||
        die "left $NAME as it is - shut it down, then run this again"
      VBoxManage controlvm "$NAME" poweroff ||
        die "could not power off $NAME - close its window, choose Power off, then run this again" ;;
    saved)
      ask "$NAME was saved while running. Discard that saved moment so its memory can be fixed? (like pulling the plug)" ||
        die "left $NAME as it is - start it, shut it down from inside, then run this again"
      VBoxManage discardstate "$NAME" ;;
  esac
  # Right after a power-off VirtualBox keeps the VM locked for a few seconds.
  for ((i = 0; i < 15; i++)); do
    VBoxManage modifyvm "$NAME" --memory "$MEM" --cpus "$CPUS" \
      --boot1 disk --boot2 dvd --boot3 none --boot4 none && break
    sleep 2
  done
  ((i < 15)) || die "could not change $NAME - close VirtualBox completely, then run this again"
  echo
  echo "VM \"$NAME\" fixed: ${MEM} MB RAM, ${CPUS} CPUs (safe for this computer's ${host_mb} MB). Its disk and everything installed are kept."
  echo "Start it:   VBoxManage startvm \"$NAME\" --type gui     (or double-click it in VirtualBox)"
  exit 0
fi

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

base="$(VBoxManage list systemproperties | sed -n 's/^Default machine folder: *//p')"
disk="$base/$NAME/$NAME.vdi"

VBoxManage createvm --name "$NAME" --ostype Debian_64 --register
VBoxManage modifyvm "$NAME" --memory "$MEM" --cpus "$CPUS" --firmware efi64 \
  --graphicscontroller vmsvga --vram 128 --nic1 nat \
  --boot1 disk --boot2 dvd --boot3 none --boot4 none
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
