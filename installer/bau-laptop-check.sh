#!/usr/bin/env bash
# BAU laptop check (Linux, from the My Jarvis stick). Shows what Linux really does with
# this laptop: which drivers load, which firmware is missing, whether Wi-Fi is blocked.
# Read only: it changes nothing. Works without sudo; with sudo it sees a little more.
#   bash bau-laptop-check.sh [OUTPUT_DIR]      (default: ./BAU-Laptop-Check)
# Writes BAU-LAPTOP-SUMMARY-LINUX.txt (safe to share: no names, network addresses or
# serial numbers) and BAU-LAPTOP-FULL-LINUX.txt (everything; keep it private).
set -uo pipefail
OUT="${1:-./BAU-Laptop-Check}"
mkdir -p "${OUT}"
FULL="${OUT}/BAU-LAPTOP-FULL-LINUX.txt"
SUM="${OUT}/BAU-LAPTOP-SUMMARY-LINUX.txt"
have() { command -v "$1" >/dev/null 2>&1; }

# Every command may be missing or refused; the check carries on either way.
run() {
  echo "### $*"
  if have "$1"; then "$@" 2>&1 || true; else echo "(not available)"; fi
  echo
}

kernel_log() {
  dmesg 2>/dev/null || journalctl -k -b --no-pager 2>/dev/null || true
}

# MAC addresses, IPs and serial-looking fields never reach the summary.
scrub() {
  sed -E -e 's/([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}/<mac>/g' \
         -e 's/\b([0-9]{1,3}\.){3}[0-9]{1,3}\b/<ip>/g' \
         -e 's/(serial[^:=]*[:=]\s*).*/\1<hidden>/I'
}

{
  echo "BAU LAPTOP CHECK (Linux) - FULL, PRIVATE: contains names, addresses and serials"
  echo "collected: $(date -u +%Y-%m-%dT%H:%M:%SZ)  as uid $(id -u)"
  echo
  run uname -a
  run cat /etc/os-release
  run cat /sys/class/dmi/id/sys_vendor /sys/class/dmi/id/product_name \
          /sys/class/dmi/id/product_serial /sys/class/dmi/id/bios_version
  run lscpu
  run free -h
  run ls /sys/firmware/efi
  run mokutil --sb-state
  run lsblk -o NAME,MODEL,SERIAL,SIZE,TYPE,TRAN,FSTYPE,MOUNTPOINT
  run lspci -nnk
  run lsusb
  run ip -brief link
  run ip -brief address
  run rfkill list
  run nmcli device status
  run nmcli radio all
  run upower -d
  echo "### kernel messages about firmware or drivers"
  kernel_log | grep -iE "firmware|failed|error" | tail -n 200
} > "${FULL}" 2>&1

memory() {
  awk '/MemTotal/ {printf "  %.1f GB (BAU needs 8 GB or more)\n", $2/1048576}' /proc/meminfo
}

firmware() {
  if [[ -d /sys/firmware/efi ]]; then echo "  started in UEFI mode"
  else echo "  started in legacy BIOS mode (UEFI is better for installing)"; fi
  if have mokutil; then echo "  $(mokutil --sb-state 2>&1 | head -n 1)"; fi
  echo "  laptop: $(cat /sys/class/dmi/id/sys_vendor 2>/dev/null) $(cat /sys/class/dmi/id/product_name 2>/dev/null)"
  echo "  cpu: $(awk -F': ' '/model name/ {print $2; exit}' /proc/cpuinfo) ($(nproc) threads)"
}

# Network, graphics, audio and similar: each one with the driver Linux loaded, or a clear
# "NO DRIVER" when none did.
devices() {
  if ! have lspci; then echo "  (lspci not available)"; return; fi
  lspci -nnk | awk '
    /^[0-9a-f]/ { if (dev != "") report(); dev = $0; drv = ""; next }
    /Kernel driver in use:/ { sub(/.*in use: /, ""); drv = $0 }
    END { if (dev != "") report() }
    function report() {
      if (dev ~ /Network|Ethernet|VGA|3D|Display|Audio|Bluetooth|Camera|Multimedia|Wireless/)
        printf "  %s\n      driver: %s\n", dev, (drv == "" ? "NO DRIVER LOADED" : drv)
    }'
  if have lsusb; then
    lsusb | grep -iE "wireless|wi-fi|wlan|bluetooth|camera|webcam|802\.11" | sed 's/^/  usb: /'
  fi
}

missing_firmware() {
  local found
  found="$(kernel_log | grep -iE "failed to load firmware|firmware: failed|direct firmware load .* failed|firmware.*not found" \
           | sed -E 's/^\[[^]]*\] //' | sort -u | tail -n 30)"
  if [[ -n "${found}" ]]; then awk '{print "  " $0}' <<< "${found}"
  elif kernel_log | grep -q .; then echo "  none reported"
  else echo "  could not read kernel messages: run again with sudo to see them"; fi
}

radios() {
  if have rfkill; then rfkill list 2>&1 | sed 's/^/  /'; else echo "  (rfkill not available)"; fi
  if have nmcli; then nmcli -t -f TYPE,STATE device 2>/dev/null | sed 's/^/  /'; fi
}

disks() {
  if have lsblk; then lsblk -d -o NAME,MODEL,SIZE,TRAN,TYPE 2>/dev/null | sed 's/^/  /'
  else echo "  (lsblk not available)"; fi
}

{
  echo "BAU LAPTOP CHECK (Linux) - safe to share (no names, network addresses or serial numbers)"
  echo
  echo "Memory:"; memory; echo
  echo "Firmware and processor:"; firmware; echo
  echo "Disks:"; disks; echo
  echo "Devices and their drivers:"; devices; echo
  echo "Missing firmware:"; missing_firmware; echo
  echo "Radios (Wi-Fi / Bluetooth, blocked or not):"; radios; echo
  echo "A device with NO DRIVER LOADED, or a line under Missing firmware, is what to ask about."
} 2>&1 | scrub > "${SUM}"

cat "${SUM}"
echo
echo "Share this one:    ${SUM}"
echo "Keep this private: ${FULL}"
