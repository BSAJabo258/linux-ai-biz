#!/usr/bin/env bash
# The creator's face lock (the owner's choice 2026-11-18, docs/PICTURES.md): IP-Adapter Plus
# Face for SDXL inside the ComfyUI that bau-pictures-setup.sh installed, so every safe-for-work
# picture of a creator is drawn from her one locked reference face.
# Run once, as root, after the pictures setup:
#   sudo bash bau-face-setup.sh
# Facts, read 2026-11-18:
#   github.com/cubiq/ComfyUI_IPAdapter_plus  GPL-3.0, commit a0f451a5 (2025-04-14): the nodes.
#     It runs inside ComfyUI as its own program; BAU only sends it jobs over 127.0.0.1.
#   huggingface.co/h94/IP-Adapter  Apache-2.0, commit 018e4027: the face adapter and its image
#     encoder (OpenCLIP ViT-H-14). No InsightFace (its models are for non-commercial use only).
# About 3.4 GB is downloaded; each file is checked against its pinned SHA-256.
set -euo pipefail

HOME_DIR=/usr/local/comfyui
APP="${HOME_DIR}/ComfyUI"
MODELS="${APP}/models"
NODE_REPO=https://github.com/cubiq/ComfyUI_IPAdapter_plus.git
NODE_COMMIT=a0f451a5113cf9becb0847b92884cb10cbdec0ef
NODE_DIR="${APP}/custom_nodes/ComfyUI_IPAdapter_plus"
HF=https://huggingface.co/h94/IP-Adapter/resolve/018e402774aeeddd60609b4ecdb7e298259dc729
FILES=(
  "ipadapter ip-adapter-plus-face_sdxl_vit-h.safetensors 677ad8860204f7d0bfba12d29e6c31ded9beefdf3e4bbd102518357d31a292c1 ${HF}/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors"
  "clip_vision CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors 6ca9667da1ca9e0b0f75e46bb030f7e011f44f86cbfb8d5a36590fcd7507b030 ${HF}/models/image_encoder/model.safetensors"
)
NEED_KB=$((4 * 1024 * 1024))

say() { printf '%s\n' "$*"; }

if [[ $(id -u) -ne 0 ]]; then
  say "Run it with sudo: sudo bash $0"; exit 1
fi
if [[ ! -d ${MODELS} ]] || ! id comfyui >/dev/null 2>&1; then
  say "The picture maker is not installed yet. Run the pictures setup first:"
  say "  sudo bash bau-pictures-setup.sh"
  exit 1
fi
free_kb=$(df -Pk "${MODELS}" | awk 'NR==2 {print $4}')
if (( free_kb < NEED_KB )); then
  say "Not enough room: $((free_kb / 1024 / 1024)) GB free where ComfyUI keeps its models,"
  say "about 4 GB needed. Run the Make room step first (docs/MAKE-ROOM.md), then this again."
  exit 1
fi

say "1/3 the IP-Adapter nodes (commit ${NODE_COMMIT:0:8})..."
if [[ ! -d ${NODE_DIR}/.git ]]; then
  install -d -o comfyui -g comfyui "${APP}/custom_nodes"
  runuser -u comfyui -- git clone --quiet "${NODE_REPO}" "${NODE_DIR}"
fi
runuser -u comfyui -- git -C "${NODE_DIR}" fetch --quiet origin "${NODE_COMMIT}" || true
runuser -u comfyui -- git -C "${NODE_DIR}" -c advice.detachedHead=false checkout --quiet "${NODE_COMMIT}"
[[ $(runuser -u comfyui -- git -C "${NODE_DIR}" rev-parse HEAD) == "${NODE_COMMIT}" ]] \
  || { say "the IP-Adapter nodes are not the pinned commit: stopping"; exit 1; }

n=1
for entry in "${FILES[@]}"; do
  read -r dir name sum url <<<"${entry}"
  n=$((n + 1))
  dest="${MODELS}/${dir}/${name}"
  install -d -o comfyui -g comfyui "${MODELS}/${dir}"
  if [[ -f ${dest} ]] && echo "${sum}  ${dest}" | sha256sum -c --quiet 2>/dev/null; then
    say "${n}/3 ${name}: already here."
    continue
  fi
  say "${n}/3 ${name} (checked against its pinned SHA-256)..."
  runuser -u comfyui -- curl -fL --retry 3 -C - -o "${dest}.part" "${url}"
  echo "${sum}  ${dest}.part" | sha256sum -c --quiet \
    || { rm -f "${dest}.part"; say "${name} is not the pinned file: stopping"; exit 1; }
  mv "${dest}.part" "${dest}"
done

say "Restarting the picture maker so it loads the face nodes..."
systemctl restart bau-pictures.service || true
say "Done. Next, at your terminal:"
say "  bau creator face draw     # a few candidate faces for your creator"
say "  bau creator face pick N   # lock the one you like"
