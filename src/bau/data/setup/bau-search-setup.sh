#!/usr/bin/env bash
# Private web search for Jarvis (docs/RESEARCH.md): SearXNG on this computer only,
# 127.0.0.1:8888, JSON answers switched on. It asks public search engines on your behalf
# without an account or tracking cookies. Run once, as root, on a laptop where BAU is
# installed on a disk (on the live stick it would only fill memory):
#   sudo bash bau-search-setup.sh
# Follows SearXNG's own step-by-step install (docs.searxng.org, checked 2026-10-21) and runs
# it the way its official container does (granian searx.webapp:app). SearXNG is AGPL-3.0:
# fine to run unchanged for yourself. Pinned to the release the BAU tests used.
set -euo pipefail

SEARXNG_COMMIT="81371861f67226091d1c4df2e3908a11d3b54eb9"   # 2026.10.19
HOME_DIR=/usr/local/searxng
SRC="${HOME_DIR}/searxng-src"
VENV="${HOME_DIR}/searx-pyenv"
CONF=/etc/searxng/settings.yml
UNIT=/etc/systemd/system/bau-search.service

say() { printf '%s\n' "$*"; }

if [[ $(id -u) -ne 0 ]]; then
  say "Run it with sudo: sudo bash $0"; exit 1
fi
if [[ -d /run/live/medium && ${BAU_SEARCH_ALLOW_LIVE:-} != 1 ]]; then
  say "This is the live stick: an install here lands in memory and is gone at restart."
  say "Install BAU to a disk first (menu: Install BAU to a disk), then run this again."
  exit 1
fi

say "1/5 Packages (Debian)..."
apt-get install -y python3-dev python3-babel python3-venv git build-essential \
  libxslt-dev zlib1g-dev libffi-dev libssl-dev openssl >/dev/null

say "2/5 The searxng account (no login, no password)..."
id searxng >/dev/null 2>&1 || useradd --shell /usr/sbin/nologin --system \
  --home-dir "${HOME_DIR}" --comment 'Private search for Jarvis' searxng
install -d -o searxng -g searxng "${HOME_DIR}"

say "3/5 SearXNG ${SEARXNG_COMMIT:0:9} (checking the exact version)..."
if [[ ! -d ${SRC}/.git ]]; then
  runuser -u searxng -- git clone --quiet https://github.com/searxng/searxng "${SRC}"
fi
runuser -u searxng -- git -C "${SRC}" fetch --quiet origin
runuser -u searxng -- git -C "${SRC}" checkout --quiet "${SEARXNG_COMMIT}"
[[ $(runuser -u searxng -- git -C "${SRC}" rev-parse HEAD) == "${SEARXNG_COMMIT}" ]] \
  || { say "SearXNG is not the pinned version: stopping"; exit 1; }

say "4/5 Its Python parts (a few minutes)..."
runuser -u searxng -- python3 -m venv "${VENV}"
runuser -u searxng -- "${VENV}/bin/pip" install --quiet -U pip setuptools wheel pyyaml \
  msgspec typing-extensions pybind11
runuser -u searxng -- sh -c "cd '${SRC}' && '${VENV}/bin/pip' install --quiet \
  --use-pep517 --no-build-isolation -e ."
runuser -u searxng -- "${VENV}/bin/pip" install --quiet granian

say "5/5 Settings (this computer only) and the service..."
install -d -m 0755 /etc/searxng
if [[ ! -f ${CONF} ]]; then
  umask 077
  cat > "${CONF}" <<EOF
# Written by bau-search-setup.sh. Only this computer can reach it.
use_default_settings: true
server:
  secret_key: "$(openssl rand -hex 32)"
  bind_address: "127.0.0.1"
  port: 8888
  limiter: false
  image_proxy: false
search:
  formats:
    - html
    - json
EOF
  chown root:searxng "${CONF}"
  chmod 0640 "${CONF}"
fi

cat > "${UNIT}" <<EOF
[Unit]
Description=Private web search for Jarvis (SearXNG on 127.0.0.1:8888)
After=network-online.target
Wants=network-online.target

[Service]
User=searxng
Group=searxng
WorkingDirectory=${SRC}
Environment=SEARXNG_SETTINGS_PATH=${CONF}
Environment=GRANIAN_INTERFACE=wsgi
Environment=GRANIAN_HOST=127.0.0.1
Environment=GRANIAN_PORT=8888
Environment=GRANIAN_BLOCKING_THREADS=4
ExecStart=${VENV}/bin/granian searx.webapp:app
Restart=on-failure
MemoryMax=512M
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${HOME_DIR}

[Install]
WantedBy=multi-user.target
EOF

if [[ -d /run/systemd/system ]]; then
  systemctl daemon-reload
  systemctl enable --now bau-search.service
  for _ in $(seq 30); do
    curl -fs -o /dev/null http://127.0.0.1:8888/healthz && break
    sleep 1
  done
  if curl -fs -o /dev/null http://127.0.0.1:8888/healthz; then
    say "Private search is running on 127.0.0.1:8888. Jarvis can search the web now."
  else
    say "It did not answer yet: sudo systemctl status bau-search"
  fi
else
  say "Installed. Start it with: systemctl enable --now bau-search.service"
fi
