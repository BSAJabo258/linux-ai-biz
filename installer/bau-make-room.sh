#!/usr/bin/env bash
# Make room for Jarvis (docs/MAKE-ROOM.md). The installer gave the system part of the disk ("/")
# a small share and /home the rest, but BAU's big files (local models, the picture maker, the
# CUDA engine) all live under "/", so "/" fills up while /home stays nearly empty.
#
# This moves those big folders into a folder on the bigger, encrypted part (default
# /home/bau-data, or a second encrypted drive you name) and links each one back to where BAU
# expects it (a bind mount in /etc/fstab), so nothing else changes. Copied first, checked, and
# only then is the old copy removed. Run as root:
#
#   sudo bash bau-make-room.sh                 # move into /home/bau-data
#   sudo bash bau-make-room.sh /mnt/big/bau    # or into another encrypted drive's folder
#   sudo bash bau-make-room.sh --undo          # put everything back (needs the room on "/")
#
# Never moves BAU's keys, data or audit log: only the three big program/model folders.
set -uo pipefail

R=${BAU_ROOM_ROOT:-}                       # tests point these into a scratch folder
FSTAB=${BAU_ROOM_FSTAB:-/etc/fstab}
BIG=("${R}/var/lib/bau/models" "${R}/usr/local/comfyui" "${R}/opt/llama.cpp-cuda")
SERVICES=(bau-llm.service bau-pictures.service bau-jarvis.service bau-ui.service)
MARK="# bau-make-room"
say() { printf '%s\n' "$*"; }

if [[ $(id -u) -ne 0 ]]; then say "Run it with sudo: sudo bash $0"; exit 1; fi
if [[ -d ${R}/run/live/medium ]]; then
  say "This is the live stick: install BAU on the computer first."; exit 1
fi

undo=0
if [[ ${1:-} == --undo ]]; then undo=1; shift; fi
TARGET=${1:-${R}/home/bau-data}

free_bytes() { df --output=avail -B1 "$1" 2>/dev/null | tail -1 | tr -d ' '; }
fs_of() { df --output=target "$1" 2>/dev/null | tail -1; }
encrypted() {   # the target's disk sits on LUKS (dm-crypt), like the rest of BAU's install
  local src; src="$(findmnt -no SOURCE --target "$1" 2>/dev/null)"
  [[ -n ${src} ]] && lsblk -s -no TYPE "${src}" 2>/dev/null | grep -qx crypt
}

active=()
stop_services() {
  local u
  for u in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$u" 2>/dev/null; then active+=("$u"); systemctl stop "$u"; fi
  done
}
start_services() { local u; for u in "${active[@]}"; do systemctl start "$u" || true; done; }
trap start_services EXIT

say "Before:"; df -h "${R}/" "$(dirname "${TARGET}")" 2>/dev/null | sed 's/^/  /'

if ((undo)); then
  stop_services
  for dir in "${BIG[@]}"; do
    dest="${TARGET}/$(echo "${dir#"${R}"}" | tr / _)"
    grep -qF "${dest} ${dir} none bind" "${FSTAB}" || continue
    need=$(du -sb "${dest}" | cut -f1)
    if (( $(free_bytes "${R}/") < need + (1 << 30) )); then
      say "Not enough room on / to bring back ${dir}; left where it is."; continue
    fi
    umount "${dir}" && cp -a "${dest}/." "${dir}/" \
      && grep -vF "${dest} ${dir} none bind" "${FSTAB}" > "${FSTAB}.bau-new" \
      && cat "${FSTAB}.bau-new" > "${FSTAB}" && rm -f "${FSTAB}.bau-new" && rm -rf "${dest}" \
      && say "Back on /: ${dir}"
  done
  say "After:"; df -h "${R}/" 2>/dev/null | sed 's/^/  /'
  exit 0
fi

mkdir -p "${TARGET}"
chmod 755 "${TARGET}"
if [[ "$(fs_of "${TARGET}")" == "$(fs_of "${R}/")" ]]; then
  say "${TARGET} is on the same part of the disk as /: moving there frees nothing."
  say "Name a folder on /home or on a second drive: sudo bash $0 /path/to/folder"
  exit 1
fi
if ! encrypted "${TARGET}"; then
  say "${TARGET} is not on an encrypted disk. BAU keeps everything encrypted: format the drive"
  say "with encryption first (Disks > Format > Encrypted), mount it, then run this again."
  exit 1
fi

stop_services
moved=0
for dir in "${BIG[@]}"; do
  [[ -d ${dir} ]] || continue
  if mountpoint -q "${dir}"; then say "Already moved: ${dir}"; continue; fi
  dest="${TARGET}/$(echo "${dir#"${R}"}" | tr / _)"
  size=$(du -sb "${dir}" | cut -f1)
  if (( $(free_bytes "${TARGET}") < size + (1 << 30) )); then
    say "Not enough room in ${TARGET} for ${dir} ($((size >> 20)) MB); skipped."; continue
  fi
  say "Moving ${dir} ($((size >> 20)) MB)..."
  rm -rf "${dest}"
  if ! cp -a "${dir}" "${dest}"; then say "  copy failed; ${dir} left as it was"; rm -rf "${dest}"; continue; fi
  if [[ "$(find "${dir}" | wc -l)" != "$(find "${dest}" | wc -l)" ]]; then
    say "  the copy does not match; ${dir} left as it was"; rm -rf "${dest}"; continue
  fi
  owner=$(stat -c %u:%g "${dir}"); mode=$(stat -c %a "${dir}")
  mv "${dir}" "${dir}.bau-old" && mkdir -p "${dir}" && chown "${owner}" "${dir}" && chmod "${mode}" "${dir}"
  if ! mount --bind "${dest}" "${dir}"; then
    say "  could not link it back; restoring"; rmdir "${dir}"; mv "${dir}.bau-old" "${dir}"; continue
  fi
  grep -qF "${dest} ${dir} none bind" "${FSTAB}" \
    || printf '%s %s none bind 0 0 %s\n' "${dest}" "${dir}" "${MARK}" >> "${FSTAB}"
  rm -rf "${dir}.bau-old"
  moved=$((moved + 1))
  say "  done: ${dir} now lives in ${dest}"
done

say "After:"; df -h "${R}/" "${TARGET}" 2>/dev/null | sed 's/^/  /'
say "Moved ${moved} folder(s). Jarvis's services are starting again."
