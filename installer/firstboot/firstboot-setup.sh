#!/bin/sh
# Runs inside the freshly installed system (debian-installer late_command, chroot).
# Applies the baseline firewall so the machine is default-deny inbound from its
# first boot, and leaves instructions for installing BAU: from USB #2, or from
# /opt/bau-payload when the one-stick image carried it. In that case BAU's setup also
# opens by itself in a window at login (finish-install.sh) until install.sh has run.
set -eu

B=/opt/bau-bootstrap
install -m 0644 "$B/hardening/nftables.conf" /etc/nftables.conf
systemctl enable nftables.service >/dev/null 2>&1 || true
install -m 0644 "$B/hardening/99-bau-sysctl.conf" /etc/sysctl.d/99-bau.conf

if [ -f /opt/bau-payload/install.sh ]; then
  cat >> /etc/motd <<'EOF'

  BAU base OS installed.  Next step - install the BAU control plane.
  It is already on this computer (one-stick install), no second stick needed:
    sudo bash /opt/bau-payload/install.sh
  It also opens by itself in a window when you log in to the desktop.
  See /opt/bau-payload/docs/INSTALL.md. This notice is removed by install.sh.

EOF
  install -d /etc/xdg/autostart
  cat > /etc/xdg/autostart/bau-finish-install.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Finish installing BAU
Exec=xfce4-terminal --title "Finish installing BAU" -x bash $B/finish-install.sh
Terminal=false
EOF
else
  cat >> /etc/motd <<'EOF'

  BAU base OS installed.  Next step - install the BAU control plane:
    1. Insert USB #2 (BAU-PAYLOAD) and open a terminal.
    2. cd /media/$USER/<usb-label>/BAU-PAYLOAD
    3. sudo ./install.sh --wipe-gate-record /path/to/BAU-WIPE-GATE.json
  See docs/INSTALL.md on the payload stick. This notice is removed by install.sh.

EOF
fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$B/installed_at"
