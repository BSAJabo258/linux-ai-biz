#!/usr/bin/env bash
# Pictures for paid levels 2 and 3 (the owner's choice 2026-11-09, docs/PICTURES.md): Chroma1-HD
# inside the ComfyUI that bau-pictures-setup.sh installed (127.0.0.1:8188, this computer only).
# Run once, as root, after the pictures setup:
#   sudo bash bau-explicit-setup.sh
# Facts, read 2026-11-09 on Hugging Face (model cards and the files API), all Apache-2.0:
#   lodestones/Chroma1-HD: 8.9B, "has not been aligned with a specific safety filter".
#   The model card's ComfyUI workflow needs these three files; SHA-256 pinned below.
# About 23 GB is downloaded into ComfyUI's models folder. If "/" is short of room, run the Make
# room step first (docs/MAKE-ROOM.md): it moves ComfyUI onto the big encrypted part.
# BAU_EXPLICIT_DIR=/path/with/the/three/files uses copies you already have; either way each is
# checked against its pinned SHA-256 before it is used.
set -euo pipefail

HOME_DIR=/usr/local/comfyui
MODELS="${HOME_DIR}/ComfyUI/models"
FILES=(
  "diffusion_models Chroma1-HD.safetensors d446d9695d08276f61e53653e025289dd96f7a489c27982a1fa54ecabc06642a https://huggingface.co/lodestones/Chroma1-HD/resolve/0e0c60ece1e82b17cb7f77342d765ba5024c40c0/Chroma1-HD.safetensors"
  "text_encoders t5xxl_fp8_e4m3fn_scaled.safetensors a498f0485dc9536735258018417c3fd7758dc3bccc0a645feaa472b34955557a https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/6af2a98e3f615bdfa612fbd85da93d1ed5f69ef5/t5xxl_fp8_e4m3fn_scaled.safetensors"
  "vae ae.safetensors afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38 https://huggingface.co/Comfy-Org/Lumina-Image-2/resolve/5b072540ef86570fecb8249c505f23d5bdeb88cd/split_files/vae/ae.safetensors"
)
NEED_KB=$((25 * 1024 * 1024))

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
  say "about 25 GB needed. Run the Make room step first (docs/MAKE-ROOM.md), then this again."
  exit 1
fi

n=0
for entry in "${FILES[@]}"; do
  read -r dir name sum url <<<"${entry}"
  n=$((n + 1))
  dest="${MODELS}/${dir}/${name}"
  install -d -o comfyui -g comfyui "${MODELS}/${dir}"
  if [[ -f ${dest} ]]; then
    say "${n}/3 ${name}: already here."
    continue
  fi
  say "${n}/3 ${name} (checked against its pinned SHA-256)..."
  if [[ -n ${BAU_EXPLICIT_DIR:-} ]]; then
    install -o comfyui -g comfyui -m 0644 "${BAU_EXPLICIT_DIR}/${name}" "${dest}.part"
  else
    runuser -u comfyui -- curl -fL --retry 3 -C - -o "${dest}.part" "${url}"
  fi
  echo "${sum}  ${dest}.part" | sha256sum -c --quiet \
    || { rm -f "${dest}.part"; say "${name} is not the pinned file: stopping"; exit 1; }
  mv "${dest}.part" "${dest}"
done

say "Done. Chroma is ready for levels 2 and 3; every picture still goes through the age check"
say "and waits for your Accept in Jarvis."
