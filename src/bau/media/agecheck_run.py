"""Run by ComfyUI's own Python on the desktop, never imported by BAU (src/bau/media/comfy.py):
python -I agecheck_run.py MODEL_DIR PICTURE prints the age model's scores per FairFace group
as JSON. With several pictures (a clip's frames, 2026-11-21) it prints a JSON list, one entry
per picture in the same order, so the model loads once. The model files are local
(bau-pictures-setup.sh); nothing is downloaded here."""

import json
import os
import sys

os.environ["HF_HUB_OFFLINE"] = "1"      # local files only; set before the import reads it
# The processor, never the graphics card: with the chat model and the face-lock models loaded
# the card was full and every check failed with CUDA out of memory (2026-11-18), so every
# picture was thrown away. The age model is small; on the processor it takes about a second.
os.environ["CUDA_VISIBLE_DEVICES"] = ""
from transformers import pipeline  # noqa: E402

classify = pipeline("image-classification", model=sys.argv[1], device="cpu")
every = len(classify.model.config.id2label)   # all groups: a young one must never drop off
pictures = sys.argv[2:]
scores = [{r["label"]: round(float(r["score"]), 6) for r in classify(p, top_k=every)}
          for p in pictures]
print(json.dumps(scores[0] if len(pictures) == 1 else scores))
