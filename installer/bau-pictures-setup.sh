#!/usr/bin/env bash
# Local pictures for the creator (docs/PICTURES.md): ComfyUI on this computer only,
# 127.0.0.1:8188, drawing with Stable Diffusion XL on the NVIDIA card. Run once, as root, on
# the installed desktop after NVIDIA's driver (sudo bau-gpu-setup):
#   sudo bash bau-pictures-setup.sh
# Facts, read 2026-11-01:
#   ComfyUI (GPL-3.0) pinned below; --listen defaults to 127.0.0.1 (comfy/cli_args.py).
#   PyTorch's CUDA 12.6 build (download.pytorch.org/whl/cu126, torch 2.14.1 for Python 3.13):
#   NVIDIA's table says CUDA 12.x runs on driver >= 525, so driver 550 is enough
#   (docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html).
#   SDXL base 1.0 (CreativeML Open RAIL++-M, commercial use allowed under its use
#   restrictions), 6,938,078,334 bytes, SHA-256 pinned below.
# BAU_PICTURES_CPU=1 uses the processor instead (very slow; for testing only).
# BAU_PICTURES_MODEL=/path/to/sd_xl_base_1.0.safetensors uses a copy you already have
# (the BAU Pack); otherwise the file is downloaded from Hugging Face. Either way it is checked.
set -euo pipefail

COMFY_COMMIT="17ff1dcce963bd9f23095ec9b28febbfc4db8388"   # 2026-11-01
MODEL_FILE="sd_xl_base_1.0.safetensors"
MODEL_SHA256="31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b"
MODEL_URL="https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/${MODEL_FILE}"
HOME_DIR=/usr/local/comfyui
SRC="${HOME_DIR}/ComfyUI"
VENV="${HOME_DIR}/venv"
UNIT=/etc/systemd/system/bau-pictures.service

say() { printf '%s\n' "$*"; }

if [[ $(id -u) -ne 0 ]]; then
  say "Run it with sudo: sudo bash $0"; exit 1
fi
if [[ -d /run/live/medium && ${BAU_PICTURES_ALLOW_LIVE:-} != 1 ]]; then
  say "This is the live stick: an install here lands in memory and is gone at restart."
  say "Install BAU to a disk first (menu: Install BAU to a disk), then run this again."
  exit 1
fi
TORCH_INDEX="https://download.pytorch.org/whl/cu126"
EXTRA=()
if [[ ${BAU_PICTURES_CPU:-} == 1 ]]; then
  TORCH_INDEX="https://download.pytorch.org/whl/cpu"
  EXTRA=(--cpu)
  say "Processor only (BAU_PICTURES_CPU=1): pictures will take minutes each."
elif ! nvidia-smi >/dev/null 2>&1; then
  say "NVIDIA's driver is not running. Install it first: sudo bau-gpu-setup, then restart."
  exit 1
fi

say "1/5 Packages (Debian)..."
apt-get install -y python3-venv git curl >/dev/null

say "2/5 The comfyui account (no login, no password)..."
id comfyui >/dev/null 2>&1 || useradd --shell /usr/sbin/nologin --system \
  --home-dir "${HOME_DIR}" --comment 'Local pictures for BAU' comfyui
install -d -o comfyui -g comfyui "${HOME_DIR}"
id -nG comfyui | grep -qw video || usermod -aG video,render comfyui 2>/dev/null || true

say "3/5 ComfyUI ${COMFY_COMMIT:0:9} (checking the exact version)..."
if [[ ! -d ${SRC}/.git ]]; then
  runuser -u comfyui -- git clone --quiet https://github.com/Comfy-Org/ComfyUI "${SRC}"
fi
runuser -u comfyui -- git -C "${SRC}" fetch --quiet origin
runuser -u comfyui -- git -C "${SRC}" checkout --quiet "${COMFY_COMMIT}"
[[ $(runuser -u comfyui -- git -C "${SRC}" rev-parse HEAD) == "${COMFY_COMMIT}" ]] \
  || { say "ComfyUI is not the pinned version: stopping"; exit 1; }

say "4/5 Its Python parts and PyTorch (several GB, takes a while)..."
runuser -u comfyui -- python3 -m venv "${VENV}"
runuser -u comfyui -- "${VENV}/bin/pip" install --quiet -U pip
runuser -u comfyui -- "${VENV}/bin/pip" install --quiet --index-url "${TORCH_INDEX}" \
  torch torchvision torchaudio
runuser -u comfyui -- "${VENV}/bin/pip" install --quiet -r "${SRC}/requirements.txt"

say "5/5 The picture model (6.9 GB, checked), the service (this computer only)..."
DEST="${SRC}/models/checkpoints/${MODEL_FILE}"
if [[ ! -f ${DEST} ]]; then
  if [[ -n ${BAU_PICTURES_MODEL:-} ]]; then
    install -o comfyui -g comfyui -m 0644 "${BAU_PICTURES_MODEL}" "${DEST}.part"
  else
    runuser -u comfyui -- curl -fL --retry 3 -o "${DEST}.part" "${MODEL_URL}"
  fi
  echo "${MODEL_SHA256}  ${DEST}.part" | sha256sum -c --quiet \
    || { rm -f "${DEST}.part"; say "The model file is not the pinned one: stopping"; exit 1; }
  mv "${DEST}.part" "${DEST}"
fi

cat > "${UNIT}" <<EOF
[Unit]
Description=Local pictures for BAU (ComfyUI on 127.0.0.1:8188)
After=network.target

[Service]
User=comfyui
Group=comfyui
SupplementaryGroups=video render
WorkingDirectory=${SRC}
ExecStart=${VENV}/bin/python ${SRC}/main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch ${EXTRA[*]}
Restart=on-failure
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
  systemctl enable --now bau-pictures.service
  for _ in $(seq 120); do
    curl -fs -o /dev/null http://127.0.0.1:8188/system_stats && break
    sleep 1
  done
  if curl -fs -o /dev/null http://127.0.0.1:8188/system_stats; then
    say "Local pictures are running on 127.0.0.1:8188."
  else
    say "It did not answer yet: sudo systemctl status bau-pictures"
  fi
else
  say "Installed. Start it with: systemctl enable --now bau-pictures.service"
fi
