#!/usr/bin/env bash
# Her face on paid levels 2 and 3 (the owner's choice 2026-11-18, docs/PICTURES.md): train a
# LoRA of the creator's face for Chroma1-HD on this computer, from the pictures
# `bau creator face dataset` drew (clothed, from her locked face, each with a caption).
# Run as root, after the explicit setup and after you have looked at the dataset:
#   sudo bash bau-lora-train.sh aria
# The first run installs the trainer (about 8 GB): kohya-ss/sd-scripts (Apache-2.0, pinned
# commit), its own Python with PyTorch's CUDA 12.6 build, and the plain fp8 T5 text encoder
# (the picture maker's "scaled" one cannot be read by the trainer). Facts, read 2026-11-18 in
# sd-scripts docs/flux_train_network.md at the pinned commit: --model_type=chroma,
# --guidance_scale=0.0, --timestep_sampling=sigmoid, --apply_t5_attn_mask; for a 12 GB card
# --fp8_base, --blocks_to_swap 16 and 8-bit AdamW. sd-scripts is tested on Python 3.10-3.12;
# this computer has 3.13, so the first run is also the test of that.
# While it trains (a few hours), the chat model and the picture maker are stopped: this
# computer's memory cannot hold all three. They are started again when it ends, also on failure.
set -euo pipefail

CID="${1:-}"
BAU_HOME=/var/lib/bau        # fixed: never taken from the caller's environment
COMFY="/usr/local/comfyui/ComfyUI"
MODELS="${COMFY}/models"
APP=/usr/local/bau-lora
SRC="${APP}/sd-scripts"
VENV="${APP}/venv"
WORK="${APP}/work"
SD_REPO=https://github.com/kohya-ss/sd-scripts.git
SD_COMMIT=cb70b96858477e716a2096292ab8aab433277f38            # 2026-11-10
TORCH_INDEX=https://download.pytorch.org/whl/cu126
TORCH_VERSION=2.14.1                                           # the picture maker's
T5_NAME=t5xxl_fp8_e4m3fn.safetensors
T5_SUM=7d330da4816157540d6bb7838bf63a0f02f573fc48ca4d8de34bb0cbfd514f09
T5_URL=https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/6af2a98e3f615bdfa612fbd85da93d1ed5f69ef5/${T5_NAME}
MIN_PICTURES=10
STEPS=1000

say() { printf '%s\n' "$*"; }
# Every file step below runs as comfyui, never as root, in folders comfyui or the bau group
# can change: a planted link must not make root read or write a file it should not.
as_comfy() { runuser -u comfyui -- "$@"; }
# The dataset is the bau group's: the bau service user reads it, never root, so a link planted
# anywhere on its path reaches nothing bau could not already read.
as_bau() { runuser -u bau -- "$@"; }

if [[ $(id -u) -ne 0 ]]; then
  say "Run it with sudo: sudo bash $0 CREATOR"; exit 1
fi
if [[ ! ${CID} =~ ^[a-z0-9][a-z0-9_-]{0,60}$ ]]; then
  say "Say which creator: sudo bash $0 aria   (her profile's id)"; exit 1
fi
DATA="${BAU_HOME}/creators/faces/dataset/${CID}"
if [[ ! -f ${MODELS}/diffusion_models/Chroma1-HD.safetensors ]] || ! id comfyui >/dev/null 2>&1; then
  say "Chroma is not installed yet. Run the explicit setup first:"
  say "  sudo bash bau-explicit-setup.sh"
  exit 1
fi
if ! as_bau test -d "${DATA}"; then
  say "No dataset folder at ${DATA}. Draw it first: bau creator face dataset"; exit 1
fi
count=$(as_bau find "${DATA}" -maxdepth 1 -type f -name '*.png' | wc -l)
if (( count < MIN_PICTURES )); then
  say "Only ${count} dataset picture(s) in ${DATA}; at least ${MIN_PICTURES} are needed."
  say "Draw them first: bau creator face dataset"
  exit 1
fi
while IFS= read -r -d '' png; do
  as_bau test -f "${png%.png}.txt" \
    || { say "No caption for ${png}; draw it again or delete it."; exit 1; }
done < <(as_bau find "${DATA}" -maxdepth 1 -type f -name '*.png' -print0)

say "1/4 the trainer (sd-scripts ${SD_COMMIT:0:8})..."
install -d -o comfyui -g comfyui "${APP}"   # its own folder, in root's /usr/local: safe
as_comfy mkdir -p "${WORK}"                  # inside it, comfyui's: never root (2026-11-21)
if [[ ! -d ${SRC}/.git ]]; then
  runuser -u comfyui -- git clone --quiet "${SD_REPO}" "${SRC}"
fi
runuser -u comfyui -- git -C "${SRC}" fetch --quiet origin "${SD_COMMIT}" || true
runuser -u comfyui -- git -C "${SRC}" -c advice.detachedHead=false checkout --quiet "${SD_COMMIT}"
[[ $(runuser -u comfyui -- git -C "${SRC}" rev-parse HEAD) == "${SD_COMMIT}" ]] \
  || { say "sd-scripts is not the pinned commit: stopping"; exit 1; }
if [[ ! -x ${VENV}/bin/accelerate ]]; then
  runuser -u comfyui -- python3 -m venv "${VENV}"
  runuser -u comfyui -- "${VENV}/bin/pip" install --quiet "torch==${TORCH_VERSION}" torchvision \
    --index-url "${TORCH_INDEX}"
  (cd "${SRC}" && runuser -u comfyui -- "${VENV}/bin/pip" install --quiet -r requirements.txt)
fi
runuser -u comfyui -- "${VENV}/bin/python" -c \
  'import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)' \
  || { say "The trainer's PyTorch cannot see the graphics card: stopping"; exit 1; }

say "2/4 the plain text encoder (checked against its pinned SHA-256)..."
T5="${MODELS}/text_encoders/${T5_NAME}"
if ! { [[ -f ${T5} ]] && echo "${T5_SUM}  ${T5}" | as_comfy sha256sum -c --quiet 2>/dev/null; }; then
  runuser -u comfyui -- curl -fL --retry 3 -C - -o "${T5}.part" "${T5_URL}"
  echo "${T5_SUM}  ${T5}.part" | as_comfy sha256sum -c --quiet \
    || { as_comfy rm -f "${T5}.part"; say "${T5_NAME} is not the pinned file: stopping"; exit 1; }
  as_comfy mv "${T5}.part" "${T5}"
fi

say "3/4 her ${count} pictures..."
as_comfy rm -rf "${WORK:?}/${CID}"
as_comfy mkdir -p -m 0700 "${WORK}/${CID}"
as_comfy mkdir -p -m 0700 "${WORK}/${CID}/img" "${WORK}/${CID}/out"
# comfyui cannot read the dataset: bau reads each regular file (no link followed at the end)
# and comfyui writes the copy. Root reads none of it.
while IFS= read -r -d '' f; do
  as_bau dd if="${f}" iflag=nofollow status=none \
    | as_comfy tee "${WORK}/${CID}/img/${f##*/}" >/dev/null
done < <(as_bau find "${DATA}" -maxdepth 1 -type f \( -name '*.png' -o -name '*.txt' \) -print0)
as_comfy tee "${WORK}/${CID}/dataset.toml" >/dev/null <<TOML
[general]
caption_extension = ".txt"
shuffle_caption = false

[[datasets]]
resolution = 768
batch_size = 1
enable_bucket = true

  [[datasets.subsets]]
  image_dir = "${WORK}/${CID}/img"
  num_repeats = 10
TOML

restart=()
for unit in bau-llm.service bau-pictures.service; do
  if systemctl is-active --quiet "${unit}"; then restart+=("${unit}"); fi
done
back() { for unit in "${restart[@]}"; do systemctl start "${unit}" || true; done; }
trap back EXIT
if (( ${#restart[@]} )); then
  say "Stopping ${restart[*]} while she trains (started again at the end)..."
  systemctl stop "${restart[@]}"
fi

say "4/4 training ${STEPS} steps (a few hours; the card works hard, that is normal)..."
cd "${SRC}"
runuser -u comfyui -- env HOME="${WORK}" "${VENV}/bin/accelerate" launch \
  --num_cpu_threads_per_process 1 --num_processes 1 --num_machines 1 \
  --mixed_precision bf16 --dynamo_backend no \
  flux_train_network.py \
  --pretrained_model_name_or_path="${MODELS}/diffusion_models/Chroma1-HD.safetensors" \
  --model_type=chroma \
  --t5xxl="${T5}" \
  --ae="${MODELS}/vae/ae.safetensors" \
  --dataset_config="${WORK}/${CID}/dataset.toml" \
  --output_dir="${WORK}/${CID}/out" \
  --output_name="bau-${CID}-chroma" \
  --save_model_as=safetensors \
  --network_module=networks.lora_flux \
  --network_dim=16 --network_alpha=16 \
  --learning_rate=1e-4 --optimizer_type=AdamW8bit --lr_scheduler=constant \
  --max_train_steps="${STEPS}" \
  --mixed_precision=bf16 --fp8_base --sdpa --gradient_checkpointing \
  --blocks_to_swap=16 \
  --guidance_scale=0.0 --timestep_sampling=sigmoid --model_prediction_type=raw \
  --apply_t5_attn_mask \
  --cache_latents_to_disk --cache_text_encoder_outputs_to_disk \
  --seed=42

out="${WORK}/${CID}/out/bau-${CID}-chroma.safetensors"
[[ -f ${out} && ! -L ${out} ]] || { say "Training ended without a LoRA file: nothing was changed."; exit 1; }
as_comfy mkdir -p "${MODELS}/loras"
as_comfy install -m 0644 "${out}" "${MODELS}/loras/"
say "Done: ${MODELS}/loras/bau-${CID}-chroma.safetensors"
say "Next, at your terminal: look at a test picture of her, then lock it:"
say "  bau creator face use-lora"
