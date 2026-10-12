#!/usr/bin/env bash
# Finishes a laptop installed from the full stick: opens by itself at login (autostart
# written by firstboot-setup.sh) and runs BAU's own setup, /opt/bau-payload/install.sh.
# The owner types the bauadmin password for sudo and chooses the approval-key passphrase;
# this script never sees either. install.sh removes the autostart once BAU is installed,
# so until then this window comes back at every login.
set -u
P="${BAU_PAYLOAD:-/opt/bau-payload}"
[[ -f "${P}/install.sh" ]] || exit 0

echo "Last step: install BAU on this laptop (about 10 minutes)."
echo "It needs the internet once, to add a few packages."
echo
until getent hosts deb.debian.org >/dev/null 2>&1; do
  echo "Not online yet. Connect to Wi-Fi (network icon, top right)."
  read -r -p "Then press Enter, or type q to do this at the next login: " answer || exit 0
  [[ "${answer}" == q ]] && { echo "OK. This window opens again at the next login."; exit 0; }
done

echo "Online. Type your bauadmin password when asked (it does not show while you type)."
echo "BAU then asks you to choose a passphrase for your approval key: remember it."
echo
if sudo bash "${P}/install.sh"; then
  echo
  echo "BAU is installed. Log out and log in again once; then Jarvis is in the menu."
else
  echo
  echo "Something went wrong (details: /var/log/bau-install.log)."
  echo "Nothing is lost: this window opens again at the next login to try again."
fi
read -r -p "Press Enter to close this window. " _ || true
