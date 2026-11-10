"""Run by ComfyUI's own Python on the desktop, never imported by BAU (src/bau/media/comfy.py):
python -I agecheck_run.py MODEL_DIR PICTURE prints the age model's scores per FairFace group
as JSON. The model files are local (bau-pictures-setup.sh); nothing is downloaded here."""

import json
import os
import sys

os.environ["HF_HUB_OFFLINE"] = "1"      # local files only; set before the import reads it
from transformers import pipeline  # noqa: E402

classify = pipeline("image-classification", model=sys.argv[1])
every = len(classify.model.config.id2label)   # all groups: a young one must never drop off
print(json.dumps({r["label"]: round(float(r["score"]), 6)
                  for r in classify(sys.argv[2], top_k=every)}))
