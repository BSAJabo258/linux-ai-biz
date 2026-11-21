#!/usr/bin/env bash
# The graphics card watchdog (docs/GPU.md, "When the card falls off the bus"). The desktop's
# RTX 3060 dropped off its PCI Express link at the end of each of the four boots from
# 2026-11-19 to 2026-11-21 (kernel: "NVRM: Xid (PCI:0000:05:00): 79, ... GPU has fallen off the
# bus"); after each, the pictures, the local model and the agents stayed dead until a person
# restarted the computer, once for more than three hours.
#
#   sudo bash bau-gpu-watch.sh              # read only: past crashes and the card's link now
#   sudo bash bau-gpu-watch.sh --install    # keep watching (a service): restart when it falls
#
# Facts, read 2026-11-21:
#   NVIDIA, Xid catalog (docs.nvidia.com/deploy/xid-errors, r555 section 4.9): Xid 79 "is logged
#   when the GPU driver attempts to access the GPU over its PCI Express connection and finds
#   that the GPU is not accessible ... often caused by hardware failures on the PCI Express
#   link ... may also be cause[d] by failing GPU hardware or other driver issues". The catalog's
#   immediate action is a restart. The kernel asks for nvidia-bug-report.sh "before the NVIDIA
#   kernel module is unloaded": the watchdog saves it before restarting.
#   This desktop (sysfs, 2026-11-21): the card links at 8 GT/s x4 through the chipset's root
#   port 00:1c.4, while it can do 16 GT/s x16; the processor's own graphics port shows no card.
# It never restarts more than MAX_RESTARTS times in WINDOW_H hours: after that it only records,
# so a card that is gone for good cannot keep the computer restarting.
set -euo pipefail

LOG_DIR=${BAU_GPU_LOG:-/var/log/bau-gpu}
MAX_RESTARTS=3
WINDOW_H=6
CRASH='NVRM: Xid \([^)]*\): 79,|GPU has fallen off the bus'

say() { printf '%s\n' "$*"; }

is_crash() { grep -qE "${CRASH}" <<<"$1"; }

restarts_lately() {
  local since
  since=$(date -d "-${WINDOW_H} hours" +%s)
  [[ -f ${LOG_DIR}/restarts ]] || { echo 0; return; }
  awk -v s="${since}" '$1 >= s' "${LOG_DIR}/restarts" | wc -l
}

report() {
  say "The card's link now:"
  local dev
  for dev in /sys/bus/pci/devices/*; do
    [[ $(cat "${dev}/vendor" 2>/dev/null) == 0x10de && $(cat "${dev}/class") == 0x03* ]] || continue
    say "  $(basename "${dev}"): $(cat "${dev}/current_link_speed") x$(cat "${dev}/current_link_width")" \
        "(it can do $(cat "${dev}/max_link_speed") x$(cat "${dev}/max_link_width"))"
  done
  say "Crashes (Xid 79) at the end of earlier boots:"
  local b n
  for b in $(journalctl --list-boots --no-pager 2>/dev/null | awk 'NR > 1 {print $1}'); do
    n=$(journalctl -k -b "${b}" --no-pager 2>/dev/null | grep -E "${CRASH}" | head -1 || true)
    [[ -n ${n} ]] && say "  boot ${b}: ${n}"
  done
  [[ -f ${LOG_DIR}/restarts ]] && say "Restarts by this watchdog: $(wc -l <"${LOG_DIR}/restarts")"
  return 0
}

on_crash() {
  local line=$1 stamp
  stamp=$(date +%Y%m%d-%H%M%S)
  mkdir -p "${LOG_DIR}"
  say "${stamp} ${line}" >>"${LOG_DIR}/crashes"
  logger -t bau-gpu-watch "the graphics card fell off the bus: ${line}"
  # NVIDIA's report, as the kernel asks, before the driver is gone (bounded: it can hang).
  (cd "${LOG_DIR}" && timeout 180 nvidia-bug-report.sh --safe-mode \
     --output-file "${LOG_DIR}/nvidia-bug-report-${stamp}.log" >/dev/null 2>&1) || true
  if (( $(restarts_lately) >= MAX_RESTARTS )); then
    logger -t bau-gpu-watch "not restarting: ${MAX_RESTARTS} restarts in ${WINDOW_H} hours already"
    return 0
  fi
  date +%s >>"${LOG_DIR}/restarts"
  logger -t bau-gpu-watch "restarting the computer in 60 seconds to bring the card back"
  sleep 60
  systemctl reboot
}

case "${1:-}" in
  --install)
    [[ $(id -u) -eq 0 ]] || { say "Run it with sudo: sudo bash $0 --install"; exit 1; }
    install -m 0755 "$0" /usr/local/sbin/bau-gpu-watch
    cat >/etc/systemd/system/bau-gpu-watch.service <<'UNIT'
[Unit]
Description=BAU graphics card watchdog: restarts when the card falls off the bus (docs/GPU.md)
After=systemd-journald.service

[Service]
ExecStart=/usr/local/sbin/bau-gpu-watch --watch
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable --now bau-gpu-watch.service
    say "Installed: if the card falls off the bus again, its report is saved in ${LOG_DIR}"
    say "and the computer restarts by itself (at most ${MAX_RESTARTS} times in ${WINDOW_H} hours)."
    ;;
  --watch)
    journalctl -k -f -n 0 -o cat --no-pager | while IFS= read -r line; do
      if is_crash "${line}"; then
        on_crash "${line}"
      fi
    done
    ;;
  --is-crash)                       # for the tests: is this kernel line a crash?
    is_crash "$2"
    ;;
  *)
    report
    ;;
esac
