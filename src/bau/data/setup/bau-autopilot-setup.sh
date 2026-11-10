#!/usr/bin/env bash
# Turn on the autopilot timer on an installed desktop (docs/AUTOPILOT.md). Run by the Jarvis
# setup pop-up, or by hand: sudo bash bau-autopilot-setup.sh
# The same two unit files as installer/payload/systemd/ (a test keeps them equal).
set -euo pipefail
[[ $(id -u) -eq 0 ]] || { echo "Run it with sudo: sudo bash $0"; exit 1; }
cat > /etc/systemd/system/bau-autopilot.service <<'UNIT'
[Unit]
Description=BAU autopilot (Jarvis works through his queue: scan, inspect, vote; asks the owner for money, posting and legal)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=bau
Group=bau
Environment=BAU_HOME=/var/lib/bau
Environment=BAU_AUDIT_KEY=/etc/bau/audit.key
# An optional GITHUB_TOKEN (no scopes) only raises GitHub's rate limit.
EnvironmentFile=-/etc/bau/models.env
ExecStart=/usr/local/bin/bau autopilot run --steps 20
UMask=0007
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/bau
CapabilityBoundingSet=
UNIT
cat > /etc/systemd/system/bau-autopilot.timer <<'UNIT'
[Unit]
Description=Run the BAU autopilot every 30 minutes

[Timer]
OnBootSec=10min
OnUnitActiveSec=30min
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now bau-autopilot.timer
echo "The autopilot runs every 30 minutes now. See it with: bau autopilot status"
