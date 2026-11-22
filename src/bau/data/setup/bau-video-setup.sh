#!/usr/bin/env bash
# Short video clips for paid levels 2 and 3 (the owner's ask 2026-11-21, docs/PICTURES.md): Wan
# 2.2 TI2V-5B inside the ComfyUI that bau-pictures-setup.sh installed (127.0.0.1:8188, this
# computer only). A clip starts from one of her pictures that already passed the age check.
# Run once, as root, after the pictures setup:
#   sudo bash bau-video-setup.sh
# Facts, read 2026-11-21: the three files are those of ComfyUI's own Wan 2.2 5B workflow
# (docs.comfy.org/tutorials/video/wan/wan2_2, template video_wan2_2_5B_ti2v.json), from
# Comfy-Org/Wan-2.2 (revision 5df3a4a) and Comfy-Org/Wan-2.1 (revision d625832) on Hugging
# Face, both Apache-2.0; SHA-256 from the Hugging Face API. Wan 2.2 itself is Apache-2.0
# (Wan-AI/Wan2.2-TI2V-5B). Every node it needs is in ComfyUI commit 17ff1dc.
# About 18 GB is downloaded into ComfyUI's models folder.
# BAU_VIDEO_DIR=/path/with/the/three/files uses copies you already have; either way each is
# checked against its pinned SHA-256 before it is used.
set -euo pipefail

HOME_DIR=/usr/local/comfyui
MODELS="${HOME_DIR}/ComfyUI/models"
FILES=(
  "diffusion_models wan2.2_ti2v_5B_fp16.safetensors 456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e https://huggingface.co/Comfy-Org/Wan-2.2/resolve/5df3a4a3ed0628002308022198249dbbbd045d09/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"
  "text_encoders umt5_xxl_fp8_e4m3fn_scaled.safetensors c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68 https://huggingface.co/Comfy-Org/Wan-2.1/resolve/d6258323e18f14c60d37899da97ca555f3118259/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
  "vae wan2.2_vae.safetensors e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156 https://huggingface.co/Comfy-Org/Wan-2.2/resolve/5df3a4a3ed0628002308022198249dbbbd045d09/split_files/vae/wan2.2_vae.safetensors"
)
NEED_KB=$((20 * 1024 * 1024))

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
  say "about 20 GB needed. Run the Make room step first (docs/MAKE-ROOM.md), then this again."
  exit 1
fi

# Everything inside ComfyUI's models folder is done as the comfyui account, never as root: that
# account owns the folder, so root following a link planted there could change a system file
# (security review, 2026-11-21). Root only opens a local copy and hands its bytes over.
as_comfy() { runuser -u comfyui -- "$@"; }

n=0
for entry in "${FILES[@]}"; do
  read -r dir name sum url <<<"${entry}"
  n=$((n + 1))
  dest="${MODELS}/${dir}/${name}"
  as_comfy mkdir -p "${MODELS}/${dir}"
  if as_comfy test -f "${dest}"; then
    say "${n}/3 ${name}: already here."
    continue
  fi
  say "${n}/3 ${name} (checked against its pinned SHA-256)..."
  if [[ -n ${BAU_VIDEO_DIR:-} ]]; then
    as_comfy tee "${dest}.part" >/dev/null <"${BAU_VIDEO_DIR}/${name}"
  else
    as_comfy curl -fL --retry 3 -C - -o "${dest}.part" "${url}"
  fi
  echo "${sum}  ${dest}.part" | as_comfy sha256sum -c --quiet \
    || { as_comfy rm -f "${dest}.part"; say "${name} is not the pinned file: stopping"; exit 1; }
  as_comfy mv "${dest}.part" "${dest}"
done

say "Done. Wan 2.2 is ready for short clips on levels 2 and 3; every clip still goes through the"
say "age check, frame by frame, before it is kept."
