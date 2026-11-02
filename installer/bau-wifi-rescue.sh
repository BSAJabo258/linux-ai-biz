#!/usr/bin/env bash
# Wi-Fi rescue for the desktop's MediaTek MT7921 card (docs/WIFI-RESCUE.md). Works with no
# internet: it tries one fix after another, checks the Wi-Fi after each, and stops at the
# first that works, saying which one it was. With --install it also stays on duty and
# repeats the ladder whenever the Wi-Fi drops.
#
#   sudo bash bau-wifi-rescue.sh              # try every fix now
#   sudo bash bau-wifi-rescue.sh --install    # and keep watching (a service)
#
# Facts, read 2026-11-02:
#   The card: PCI 14c3:7961, driver mt7921e (docs/DESKTOP.md, the owner's laptop check).
#   Firmware: Debian 13 package firmware-mediatek 20250410-2 [non-free-firmware]
#     (packages.debian.org/trixie/firmware-mediatek), file list includes
#     /usr/lib/firmware/mediatek/WIFI_RAM_CODE_MT7961_1.bin and
#     /usr/lib/firmware/mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin;
#     firmware-mediatek_20250410-2_all.deb, 19598740 bytes, SHA-256 below
#     (packages.debian.org/trixie/all/firmware-mediatek/download).
#   mt7921e: module_param_named(disable_aspm, ...) "disable PCI ASPM support" (Linux
#     drivers/net/wireless/mediatek/mt76/mt7921/pci.c); used only if `modinfo -p` lists it.
#   Power saving off: NetworkManager wifi.powersave=2 (see the stick's
#     bau-mt7921-powersave.conf).
set -uo pipefail

PCI_ID="14c3:7961"
DRIVER="mt7921e"
ETC=${BAU_WIFI_ETC:-/etc}                  # tests point these into a scratch folder
FW_DIR=${BAU_WIFI_FW_DIR:-/usr/lib/firmware/mediatek}
FW_FILES=(WIFI_RAM_CODE_MT7961_1.bin WIFI_MT7961_patch_mcu_1_2_hdr.bin)
FW_DEB="firmware-mediatek_20250410-2_all.deb"
FW_SHA256="957f82d72d413f4577f45bfad03237b1dd6f8693eddc226ac452f9c5d4187012"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG=${BAU_WIFI_LOG:-/var/log/bau-wifi-rescue.log}
WAIT=${BAU_WIFI_WAIT:-45}

say() { printf '%s\n' "$*"; printf '%s %s\n' "$(date -Is)" "$*" >> "${LOG}" 2>/dev/null || true; }

if [[ $(id -u) -ne 0 ]]; then
  echo "Run it with sudo: sudo bash $0"; exit 1
fi

wifi_ok() {   # a Wi-Fi device connected and something on the network answering
  nmcli -t -f TYPE,STATE device 2>/dev/null | grep -q '^wifi:connected$' || return 1
  local gw
  gw="$(ip route show default 2>/dev/null | awk '/dev/ {print $3; exit}')"
  [[ -n ${gw} ]] && ping -c 1 -W 3 "${gw}" >/dev/null 2>&1
}

wait_for_wifi() {
  local i
  for ((i = 0; i < WAIT; i += 5)); do
    wifi_ok && return 0
    sleep 5
  done
  return 1
}

reload_driver() {
  modprobe -r "${DRIVER}" 2>/dev/null
  sleep 2
  modprobe "${DRIVER}"
  sleep 3
}

restart_nm() { systemctl restart NetworkManager; sleep 5; }

# ------------------------------------------------------------------ the fixes, in order
fix_radio() {          # 1. Wi-Fi switched off in software
  rfkill unblock wifi 2>/dev/null
  nmcli radio wifi on
}

fix_firmware() {       # 2. the card's firmware missing: install it from the kit, offline
  local f missing=0
  for f in "${FW_FILES[@]}"; do [[ -f ${FW_DIR}/${f} ]] || missing=1; done
  if ((missing == 0)); then say "   firmware is already there"; return 0; fi
  local deb="${HERE}/${FW_DEB}"
  if [[ ! -f ${deb} ]]; then
    say "   firmware missing and ${FW_DEB} is not next to this script; get the full kit"
    return 0
  fi
  echo "${FW_SHA256}  ${deb}" | sha256sum -c --quiet \
    || { say "   ${FW_DEB} does not match its SHA-256: not installing it"; return 0; }
  dpkg -i "${deb}" && reload_driver
}

fix_powersave() {      # 3. the card's power saving drops the connection
  install -d "${ETC}/NetworkManager/conf.d"
  printf '[connection-bau-mt7921]\nmatch-device=driver:%s\nwifi.powersave=2\n' "${DRIVER}" \
    > "${ETC}/NetworkManager/conf.d/bau-mt7921-powersave.conf"
  restart_nm
}

fix_reload() {         # 4. the driver in a bad state: start it again
  reload_driver
  restart_nm
}

fix_aspm() {           # 5. PCI power saving (ASPM) makes the card hang
  if ! modinfo -p "${DRIVER}" 2>/dev/null | grep -q '^disable_aspm:'; then
    say "   this kernel's ${DRIVER} has no disable_aspm option; skipped"; return 0
  fi
  install -d "${ETC}/modprobe.d"
  echo "options ${DRIVER} disable_aspm=1" > "${ETC}/modprobe.d/bau-mt7921.conf"
  reload_driver
  restart_nm
}

fix_mac() {            # 6. some routers refuse the random address used while scanning
  printf '[device-bau-mt7921]\nmatch-device=driver:%s\nwifi.scan-rand-mac-address=no\n' \
    "${DRIVER}" > "${ETC}/NetworkManager/conf.d/bau-mt7921-mac.conf"
  restart_nm
}

fix_region() {         # 7. the wrong country's channels
  if command -v iw >/dev/null; then iw reg set US; fi
  restart_nm
}

fix_full_restart() {   # 8. everything once more from cold
  systemctl restart wpa_supplicant 2>/dev/null
  reload_driver
  restart_nm
}

FIXES=(fix_radio fix_firmware fix_powersave fix_reload fix_aspm fix_mac fix_region
       fix_full_restart)
NAMES=("switch the Wi-Fi radio on" "install the card's firmware (offline)"
       "turn the card's power saving off" "restart the driver"
       "turn PCI power saving (ASPM) off for the card" "stop random scan addresses"
       "set the US region" "restart everything")

ladder() {
  local i
  if wifi_ok; then say "The Wi-Fi works."; return 0; fi
  for i in "${!FIXES[@]}"; do
    say "Trying $((i + 1))/${#FIXES[@]}: ${NAMES[$i]}..."
    "${FIXES[$i]}"
    if wait_for_wifi; then
      say "Fixed: the Wi-Fi works after \"${NAMES[$i]}\"."
      return 0
    fi
  done
  say "Still no Wi-Fi after every fix. Next steps (docs/WIFI-RESCUE.md):"
  say " - plug in the cable once, or a supported USB Wi-Fi adapter;"
  say " - send the file ${LOG} so the next fix can be made for this exact card."
  return 1
}

# ------------------------------------------------------------------ start
if ! lspci -nn 2>/dev/null | grep -qi "${PCI_ID}"; then
  say "No MediaTek MT7921 card (${PCI_ID}) found in this computer; this rescue is for that card."
  exit 1
fi
if [[ -t 0 ]] && ! nmcli -t -f NAME,TYPE connection show 2>/dev/null \
    | grep -q ':802-11-wireless$'; then
  say "No Wi-Fi network saved yet. Type it once:"
  read -r -p "Wi-Fi name: " ssid
  read -r -s -p "Password: " pass; echo
  nmcli radio wifi on
  nmcli device wifi connect "${ssid}" password "${pass}" >/dev/null 2>&1 || true
  unset pass
fi

case "${1:-}" in
  --install)
    install -m 0755 "$0" /usr/local/sbin/bau-wifi-rescue
    [[ -f ${HERE}/${FW_DEB} ]] && install -D -m 0644 "${HERE}/${FW_DEB}" \
      "/usr/local/share/bau-wifi/${FW_DEB}"
    cat > /etc/systemd/system/bau-wifi-rescue.service <<'UNIT'
[Unit]
Description=BAU Wi-Fi rescue: keeps the MT7921 Wi-Fi working (docs/WIFI-RESCUE.md)
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Environment=BAU_WIFI_HOME=/usr/local/share/bau-wifi
ExecStart=/usr/local/sbin/bau-wifi-rescue --watch
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable --now bau-wifi-rescue.service
    say "Installed: the rescue now watches the Wi-Fi and fixes it whenever it drops."
    ;;
  --watch)
    HERE=${BAU_WIFI_HOME:-${HERE}}
    while true; do
      wifi_ok || ladder || true
      sleep 120
    done
    ;;
  *)
    ladder
    ;;
esac
