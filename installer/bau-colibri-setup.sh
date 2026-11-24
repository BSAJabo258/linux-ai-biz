#!/usr/bin/env bash
# Colibri on this laptop (docs/COLIBRI.md, the owner's ask 2026-11-24: "update the laptop
# install using colibri to be able to run my system"). Colibri (github.com/JustVugg/colibri,
# Apache-2.0) runs big "mixture of experts" models with only part of them in memory: the
# rest stays on the disk and is read when needed. On an 8 GB laptop it runs
# Qwen3-Coder-30B-A3B (Apache-2.0, tool calls) as Jarvis's model, on 127.0.0.1:8000.
#   sudo bash bau-colibri-setup.sh
# Facts, read 2026-11-24 in Colibri's v2.2.0 (commit below): README (Apache-2.0, 8 GB RAM and
# 22 GB free disk at least, server on 127.0.0.1:8000, OpenAI-compatible /v1/chat/completions
# with tool calls); c/setup_catalog.py (Qwen3-Coder-30B-A3B: 19.4 GB, ram_min_gb 8);
# docs/qwen36.md ("coli serve --model qwen3-coder-i4 --cap 32  # 6.5 GB resident", about
# 5 tokens a second on an 8-core desktop, "a request whose tool block makes the prompt about
# 500 tokens takes around two minutes from a cold cache"); c/coli (serve --host defaults to
# 127.0.0.1, refuses another address without an API key). The model files are pinned to one
# commit of huggingface.co/Justvugg/Qwen3-Coder-30B-A3B-colibri-int4 and checked one by one
# (colibri/qwen3-coder-30b.sha256 for the big files, .gitoid for the small ones).
set -euo pipefail

COLIBRI_COMMIT="e479104ae01bdc40ce81e675299b1d230891b321"   # v2.2.0, 2026-11-22
MODEL_REPO="Justvugg/Qwen3-Coder-30B-A3B-colibri-int4"
MODEL_COMMIT="d839110a17d31b4e6fa9f3d973b751f779b6b9c6"     # 2026-10-02
MODEL_ID="qwen3-coder-30b-a3b-colibri"                       # the gateway's own model id
SRC=/opt/colibri
MODELS=/var/lib/bau/models/colibri
DIR="${MODELS}/qwen3-coder-30b"
ENV_FILE=/etc/bau/colibri.env
UNIT=/etc/systemd/system/bau-colibri.service
HERE="$(cd "$(dirname "$0")" && pwd)"
SUMS="${HERE}/colibri/qwen3-coder-30b.sha256"
OIDS="${HERE}/colibri/qwen3-coder-30b.gitoid"

say() { printf '%s\n' "$*"; }

if [[ $(id -u) -ne 0 ]]; then
  say "Run it with sudo: sudo bash $0"; exit 1
fi
if [[ -d /run/live/medium && ${BAU_COLIBRI_ALLOW_LIVE:-} != 1 ]]; then
  say "This is the live stick: 19 GB of model would land in memory and be gone at restart."
  say "Install BAU to a disk first (menu: Install BAU to a disk), then run this again."
  exit 1
fi
[[ -f ${SUMS} && -f ${OIDS} ]] || { say "The checksum lists are missing next to $0"; exit 1; }

say "1/6 This computer..."
ram_kb=$(awk '/MemTotal/{print $2}' /proc/meminfo)
# 8 GB laptops report a little under 8 GB (the firmware keeps some): 7.3 GiB and up
if (( ram_kb < 7300000 )); then
  say "Colibri needs 8 GB of memory; this computer has $((ram_kb / 1024)) MB. Stopping."
  exit 1
fi
install -d -o bau -g bau -m 0750 "${MODELS}"
free_kb=$(df --output=avail -k "${MODELS}" | tail -1)
have_kb=0
[[ -d ${DIR} ]] && have_kb=$(du -sk "${DIR}" | cut -f1)
if (( free_kb + have_kb < 22000000 )); then
  say "Colibri needs 22 GB free for the model; $(( free_kb / 1048576 )) GB free in ${MODELS}."
  exit 1
fi
say "  memory $((ram_kb / 1048576)) GB, disk free $((free_kb / 1048576)) GB: enough"

say "2/6 Packages to build it (Debian)..."
apt-get install -y build-essential git curl python3 >/dev/null

say "3/6 Colibri ${COLIBRI_COMMIT:0:9} (checking the exact version)..."
if [[ ! -d ${SRC}/.git ]]; then
  git clone --quiet https://github.com/JustVugg/colibri "${SRC}"
fi
git -C "${SRC}" fetch --quiet origin
git -C "${SRC}" -c advice.detachedHead=false checkout --quiet "${COLIBRI_COMMIT}"
[[ $(git -C "${SRC}" rev-parse HEAD) == "${COLIBRI_COMMIT}" ]] \
  || { say "Colibri is not the pinned version: stopping"; exit 1; }

say "4/6 Building its engine for this processor (a minute or two)..."
make -s -C "${SRC}/c" qwen36 ARCH=native
[[ -x ${SRC}/c/qwen36 ]] || { say "The engine did not build: stopping"; exit 1; }

say "5/6 The model, 19 GB, checked file by file (safe to stop; run again to continue)..."
install -d -o bau -g bau -m 0750 "${DIR}"
base="https://huggingface.co/${MODEL_REPO}/resolve/${MODEL_COMMIT}"
fetch() {   # $1 = file name; resumes a part already there
  runuser -u bau -- curl -fL --retry 5 --retry-delay 5 -C - -o "${DIR}/$1.part" \
    "${base}/$1" || return 1
  mv "${DIR}/$1.part" "${DIR}/$1"
}
n=0
total=$(( $(wc -l < "${SUMS}") + $(wc -l < "${OIDS}") ))
while read -r sum name; do
  n=$((n + 1))
  if [[ -f ${DIR}/${name} ]] && echo "${sum}  ${DIR}/${name}" | sha256sum -c --quiet - \
      2>/dev/null; then
    continue
  fi
  rm -f "${DIR}/${name}"
  say "  ${n}/${total} ${name}"
  fetch "${name}"
  echo "${sum}  ${DIR}/${name}" | sha256sum -c --quiet - \
    || { rm -f "${DIR}/${name}"; say "${name} is not the pinned file: stopping"; exit 1; }
done < "${SUMS}"
while read -r oid name; do
  n=$((n + 1))
  [[ -f ${DIR}/${name} && $(git hash-object "${DIR}/${name}") == "${oid}" ]] && continue
  rm -f "${DIR}/${name}"
  fetch "${name}"
  [[ $(git hash-object "${DIR}/${name}") == "${oid}" ]] \
    || { rm -f "${DIR}/${name}"; say "${name} is not the pinned file: stopping"; exit 1; }
done < "${OIDS}"
say "  all ${total} files match"

say "6/6 The service (this computer only, no network)..."
if [[ ! -f ${ENV_FILE} ]]; then
  install -d -m 0755 /etc/bau
  # Experts kept in memory per layer: 32 is Colibri's measured 6.5 GB (docs/qwen36.md).
  # Lower it (16) if the laptop runs short of memory; higher answers faster.
  printf 'COLI_CAP=32\n' > "${ENV_FILE}"
fi
cat > "${UNIT}" <<EOF
[Unit]
Description=Jarvis's model on this laptop (Colibri, Qwen3-Coder-30B-A3B, 127.0.0.1:8000)
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
User=bau
Group=bau
EnvironmentFile=${ENV_FILE}
ExecStart=/usr/bin/python3 ${SRC}/c/coli serve --model ${DIR} --cap \${COLI_CAP} \\
  --host 127.0.0.1 --port 8000 --model-id ${MODEL_ID}
Restart=on-failure
RestartSec=10
# When memory runs out, Linux stops this model first instead of the desktop or Jarvis.
OOMScoreAdjust=500
UMask=0007
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
# The engine keeps which experts it used in <model>/.coli_usage (c/route_trace.h), so the
# model folder stays writable; the program itself is read-only.
ReadOnlyPaths=${SRC}
ReadWritePaths=${DIR}
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
IPAddressDeny=any
IPAddressAllow=localhost
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
EOF

if [[ -d /run/systemd/system ]]; then
  systemctl daemon-reload
  # Two models do not fit in 8 GB: the stick's llama.cpp model gives way.
  if systemctl is-active --quiet bau-llm.service; then
    say "  stopping the stick's small model (bau-llm): both do not fit in 8 GB"
    systemctl disable --now bau-llm.service
  fi
  systemctl enable --now bau-colibri.service
  say "  loading the model (a minute or more)..."
  for _ in $(seq 120); do
    curl -fs -o /dev/null http://127.0.0.1:8000/v1/models && break
    sleep 2
  done
  if curl -fs -o /dev/null http://127.0.0.1:8000/v1/models; then
    say "Colibri answers on 127.0.0.1:8000. Next: measure it (docs/COLIBRI.md step 3):"
    say "  sudo bau models bench qwen3-coder-30b-colibri"
  else
    say "It did not answer yet: sudo systemctl status bau-colibri"
  fi
else
  say "Installed. Start it with: systemctl enable --now bau-colibri.service"
fi
