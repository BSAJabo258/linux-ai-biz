#!/usr/bin/env bash
# Turn on automatic updates on a desktop installed before they existed (docs/UPDATES.md).
# Run once, as root, on the installed desktop:
#   sudo bash bau-update-first.sh
# It fetches the newest BAU that passed every check on main, checks its SHA-256, installs it,
# turns automatic updates on and runs the first one (which restarts Mission Control, checks it
# answers and goes back to the stick's own build if it does not).
set -euo pipefail

URL="https://github.com/BSAJabo258/linux-ai-biz/releases/download/bau-update"
say() { printf '%s\n' "$*"; }

if [[ $(id -u) -ne 0 ]]; then
  say "Run it with sudo: sudo bash $0"; exit 1
fi
if [[ -d /run/live/medium ]]; then
  say "This is the live stick: it is rebuilt, not updated. Run this on the installed desktop."
  exit 1
fi
[[ -x /opt/bau/venv/bin/pip ]] || { say "BAU is not installed here (/opt/bau/venv)."; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
say "1/3 The newest tested build..."
curl -fsSL --retry 3 -o "${work}/bau-update.json" "${URL}/bau-update.json"
read -r wheel sha < <(python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1]));
print(m["wheel"], m["sha256"])' "${work}/bau-update.json")
[[ ${wheel} =~ ^bau-[0-9][0-9A-Za-z.+]*-py3-none-any\.whl$ && ${sha} =~ ^[0-9a-f]{64}$ ]] \
  || { say "The update record looks wrong: stopping"; exit 1; }
curl -fsSL --retry 3 -o "${work}/${wheel}" "${URL}/${wheel}"
echo "${sha}  ${work}/${wheel}" | sha256sum -c --quiet \
  || { say "The download does not match its SHA-256: stopping"; exit 1; }

say "2/3 Installing it..."
/opt/bau/venv/bin/pip install --quiet --no-index --no-deps --force-reinstall "${work}/${wheel}"
# The same two files as installer/payload/systemd/ (a test keeps them equal).
cat > /etc/systemd/system/bau-update.service <<'UNIT'
[Unit]
Description=BAU automatic update (only when the owner chose: sudo bau update auto)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
# Root, because pip writes /opt/bau/venv and the kept builds live in root-owned /opt/bau/update.
Environment=BAU_HOME=/var/lib/bau
Environment=BAU_AUDIT_KEY=/etc/bau/audit.key
ExecStart=/opt/bau/venv/bin/bau update now
UMask=0007
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
UNIT
cat > /etc/systemd/system/bau-update.timer <<'UNIT'
[Unit]
Description=Check for a tested BAU update every night

[Timer]
OnCalendar=*-*-* 03:17:00
RandomizedDelaySec=1800
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now bau-update.timer >/dev/null

say "3/3 Automatic updates on, and the first one now..."
export BAU_HOME=/var/lib/bau BAU_AUDIT_KEY=/etc/bau/audit.key
/usr/local/bin/bau update auto >/dev/null
/usr/local/bin/bau update now
say "Done. BAU now updates itself each night; see it with: bau update status"
