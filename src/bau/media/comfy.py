"""Local pictures for the creator: ComfyUI on this computer draws them (docs/PICTURES.md).

The owner's choice (2026-11-01): pictures are made on his own desktop (RTX 3060, 12 GB), not
by a paid service. ComfyUI (GPL-3.0, github.com/Comfy-Org/ComfyUI) runs as its own program on
127.0.0.1:8188; BAU only talks to its local API, so ComfyUI's code is never imported here.

Facts read 2026-11-01 in ComfyUI's code (commit 17ff1dc):
  server.py   POST /prompt {"prompt": graph} -> {"prompt_id", "number", "node_errors"};
              GET /history/{prompt_id} -> {id: {"status", "outputs": {node: {"images":
              [{"filename", "subfolder", "type"}]}}}}; GET /view?filename=&subfolder=&type=
  cli_args.py --listen defaults to 127.0.0.1, --port to 8188
  nodes.py    CheckpointLoaderSimple(ckpt_name) -> MODEL, CLIP, VAE; CLIPTextEncode(text, clip);
              EmptyLatentImage(width, height, batch_size); KSampler(model, seed, steps, cfg,
              sampler_name, scheduler, positive, negative, latent_image, denoise);
              VAEDecode(samples, vae); SaveImage(images, filename_prefix)

The model: Stable Diffusion XL base 1.0 (huggingface.co/stabilityai/stable-diffusion-xl-base-1.0,
CreativeML Open RAIL++-M, commercial use allowed under its use restrictions, which include never
harming minors; file sd_xl_base_1.0.safetensors, 6,938,078,334 bytes, SHA-256 31e35c80fc4829d1
4f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b; read 2026-11-01).

The explicit lane (the owner's choice 2026-11-09, levels 2 and 3, Fanvue only): Chroma1-HD
(huggingface.co/lodestones/Chroma1-HD, Apache-2.0: "anyone can use, modify, and build upon it";
"has not been aligned with a specific safety filter"; 8.9B, based on FLUX.1-schnell), drawn
with the model card's own ComfyUI workflow (ComfyUI_Chroma1-HD_T2I-workflow.json, read
2026-11-09): UNETLoader -> ModelSamplingAuraFlow(shift 1) -> CFGGuider(cfg 3.8) with
CLIPLoader(type "chroma") + CLIPTextEncode, KSamplerSelect(euler), BetaSamplingScheduler(26,
0.45, 0.45), RandomNoise, EmptySD3LatentImage(1152), SamplerCustomAdvanced, VAELoader,
VAEDecode, SaveImage. The full bf16 file is loaded with UNETLoader weight_dtype fp8_e4m3fn
(ComfyUI's own conversion) so it can fit the 12 GB card; that fit is not yet measured. Every
node and the "chroma" type were checked in ComfyUI commit 17ff1dc on 2026-11-09. Files and
SHA-256 (Hugging Face API, 2026-11-09), all Apache-2.0:
  lodestones/Chroma1-HD  Chroma1-HD.safetensors  17,800,038,288 bytes  d446d969...642a
  comfyanonymous/flux_text_encoders  t5xxl_fp8_e4m3fn_scaled.safetensors
                                     5,157,348,688 bytes  a498f048...557a
  Comfy-Org/Lumina-Image-2  split_files/vae/ae.safetensors  335,304,388  afc8e282...9e38
The age check below runs on these pictures exactly as on every other.

Every picture: the prompt is checked for anything about minors first (never sent if so), the
file lands in BAU_HOME/artifacts/media with a provenance record (AI-generated, model, seed,
prompt hash), and the audit chain gets a media.drawn row.

Nothing childlike (the owner, 2026-11-01): every picture is looked at by an age model before it
is kept - dima806/fairface_age_image_detection (Apache-2.0 on its page, a ViT on FairFace age
groups), revision 4e02ab8, run by agecheck_run.py inside ComfyUI's own Python (BAU never loads
PyTorch). If the three youngest groups (0-2, 3-9, 10-19) add up to more than MAX_UNDER_20, the
picture is moved to artifacts/rejected and never used; if the check cannot run, it is not kept.
Sandbox test 2026-11-01 (agecheck_run.py on the pinned model, all nine groups) on two
real SDXL pictures: 0.25 for one that read young (rejected), 0.05 for a clearly adult one
(kept). A second guard: the owner still looks at every picture.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..audit import AuditLog
from ..virtual_creator import MINOR_REFERENCE

BASE = "http://127.0.0.1:8188"
MODEL = "sd_xl_base_1.0.safetensors"
MODEL_SHA256 = "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b"
CHROMA = "Chroma1-HD.safetensors"
CHROMA_T5 = "t5xxl_fp8_e4m3fn_scaled.safetensors"
CHROMA_VAE = "ae.safetensors"
CHROMA_FILES = Path("/usr/local/comfyui/ComfyUI/models/diffusion_models") / CHROMA
LOCAL = re.compile(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$")
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,80}$")
AGE_MODEL = "dima806/fairface_age_image_detection"
AGE_REVISION = "4e02ab8057ea7fd74b1670940995c5dfda3e6ec0"
AGE_PYTHON = Path("/usr/local/comfyui/venv/bin/python")
AGE_DIR = Path("/usr/local/comfyui/age-model")
YOUNG_GROUPS = ("0-2", "3-9", "10-19")
MAX_UNDER_20 = 0.10
NEGATIVE = ("child, childlike, minor, teen, young-looking, school uniform, cartoon, anime, "
            "illustration, character sheet, color swatches, real person, celebrity, text, "
            "watermark, logo")


class ComfyError(RuntimeError):
    pass


def under_20(scores: dict[str, float]) -> float:
    """How likely the face is to read under 20: the three youngest FairFace groups."""
    return round(sum(float(scores.get(g, 0.0)) for g in YOUNG_GROUPS), 6)


def age_scores(path: Path) -> dict[str, float]:
    """Run the age model in ComfyUI's Python on the desktop (no PyTorch inside BAU)."""
    run = subprocess.run([str(AGE_PYTHON), "-I", str(Path(__file__).with_name("agecheck_run.py")),
                          str(AGE_DIR), str(path)], capture_output=True, text=True, timeout=300)
    if run.returncode != 0:
        raise OSError((run.stderr or run.stdout).strip()[-300:] or "the age model did not run")
    return json.loads(run.stdout)


def creator_prompt(profile: dict[str, Any], theme: str, shot: str) -> str:
    """Short visual facts for a picture model, from the creator profile. The batch's
    instruction-style prompt drew a character sheet in the sandbox run (2026-11-01)."""
    age = int(profile.get("age") or 0)
    if age < 21:
        raise ComfyError("the creator must be a fictional adult of 21 or over")
    parts = [f"photo of a {age}-year-old adult woman", *profile.get("appearance", []),
             str(profile.get("style", "")), theme, f"{shot} shot",
             "realistic photograph, natural skin, sharp focus"]
    return ", ".join(p.strip() for p in parts if p and p.strip())


def graph(prompt: str, seed: int, width: int = 1024, height: int = 1024, steps: int = 30,
          negative: str = NEGATIVE, ckpt: str = MODEL) -> dict[str, Any]:
    """The smallest text-to-picture job, in ComfyUI's API format (node id -> node)."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "seed": seed, "steps": steps, "cfg": 7.0,
                         "sampler_name": "euler", "scheduler": "normal", "positive": ["2", 0],
                         "negative": ["3", 0], "latent_image": ["4", 0], "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "bau"}},
    }


def chroma_graph(prompt: str, seed: int, negative: str = NEGATIVE, width: int = 1152,
                 height: int = 1152) -> dict[str, Any]:
    """The Chroma1-HD model card's ComfyUI workflow, in ComfyUI's API format."""
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": CHROMA, "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CHROMA_T5, "type": "chroma", "device": "default"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["3", 0]}},
        "6": {"class_type": "CFGGuider", "inputs": {"model": ["2", 0], "positive": ["4", 0],
                                                    "negative": ["5", 0], "cfg": 3.8}},
        "7": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "8": {"class_type": "BetaSamplingScheduler",
              "inputs": {"model": ["2", 0], "steps": 26, "alpha": 0.45, "beta": 0.45}},
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "10": {"class_type": "EmptySD3LatentImage",
               "inputs": {"width": width, "height": height, "batch_size": 1}},
        "11": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["9", 0], "guider": ["6", 0], "sampler": ["7", 0],
                          "sigmas": ["8", 0], "latent_image": ["10", 0]}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": CHROMA_VAE}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["12", 0]}},
        "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0],
                                                     "filename_prefix": "bau"}},
    }


def chroma_ready() -> bool:
    return CHROMA_FILES.is_file()


def _call(opener: Any, url: str, body: dict[str, Any] | None = None, raw: bool = False,
          timeout: int = 60) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    with opener(req, timeout=timeout) as r:
        got = r.read()
    return got if raw else json.loads(got or b"{}")


def draw(home: Path, prompt: str, name: str, seed: int | None = None, base: str = BASE,
         opener: Any = None, wait: float = 2.0, max_wait: float = 900.0,
         checker: Any = None, negative: str = NEGATIVE, lane: str = "sfw",
         **size: int) -> dict[str, Any]:
    """Draw one picture into BAU_HOME/artifacts/media/NAME.png and record where it came from."""
    if not LOCAL.match(base):
        raise ComfyError("pictures are drawn only by a model server on this computer")
    if not NAME.match(name or ""):
        raise ComfyError("a picture name is lowercase letters, digits, dot, dash")
    if m := MINOR_REFERENCE.search(prompt):
        raise ComfyError(f"refers to minors ({m.group(0)!r}); BAU never draws that")
    opener = opener or urllib.request.urlopen
    seed = random.randrange(2**32) if seed is None else int(seed)
    if lane not in ("sfw", "explicit"):
        raise ComfyError("the lane is sfw or explicit")
    g = (chroma_graph(prompt, seed, negative=negative, **size) if lane == "explicit"
         else graph(prompt, seed, negative=negative, **size))
    job = _call(opener, base + "/prompt", {"prompt": g})
    if not job.get("prompt_id"):
        err = job.get("error")
        why = err.get("message") if isinstance(err, dict) else err
        raise ComfyError(f"ComfyUI refused the job: {why or job.get('node_errors')}")
    pid, waited = job["prompt_id"], 0.0
    while True:
        hist = _call(opener, f"{base}/history/{urllib.parse.quote(pid)}").get(pid)
        if hist and hist.get("outputs"):
            break
        if hist and (hist.get("status") or {}).get("status_str") == "error":
            raise ComfyError(f"ComfyUI failed the job: {hist['status']}")
        if waited >= max_wait:
            raise ComfyError(f"no picture after {int(max_wait)} s")
        time.sleep(wait)
        waited += max(wait, 0.001)
    images = [i for o in hist["outputs"].values() for i in o.get("images", [])]
    if not images:
        raise ComfyError("ComfyUI finished without a picture")
    q = urllib.parse.urlencode({k: images[0].get(k, "") for k in ("filename", "subfolder",
                                                                   "type")})
    png = _call(opener, f"{base}/view?{q}", raw=True)
    audit = AuditLog(home / "audit" / "chain.jsonl")
    rejected = home / "artifacts" / "rejected"
    rejected.mkdir(parents=True, exist_ok=True)
    held = rejected / f"{name}.png"                 # stays here unless the age check passes
    held.write_bytes(png)
    try:
        young = under_20((checker or age_scores)(held))
    except Exception as e:  # noqa: BLE001 - any failure means the picture is not kept
        audit.append("media.rejected", "bau", {"file": held.name, "why": "age check failed"})
        raise ComfyError(f"the age check could not run ({e}); the picture was not kept") from e
    if young > MAX_UNDER_20:
        audit.append("media.rejected", "bau", {"file": held.name, "under_20": young})
        raise ComfyError(f"the picture could pass for under 20 ({young:.2f}); it was moved to "
                         "artifacts/rejected and will not be used")
    media = home / "artifacts" / "media"
    media.mkdir(parents=True, exist_ok=True)
    out = media / f"{name}.png"
    shutil.move(held, out)
    model = CHROMA if lane == "explicit" else MODEL
    prov = {"ai_generated": True, "generator": "ComfyUI (local)", "model": model, "lane": lane,
            "seed": seed,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "file_sha256": hashlib.sha256(png).hexdigest(),
            "age_check": {"passed": True, "under_20": young, "max": MAX_UNDER_20,
                          "model": AGE_MODEL, "revision": AGE_REVISION},
            "created": dt.datetime.now(dt.UTC).isoformat()}
    (media / f"{name}.png.provenance.json").write_text(json.dumps(prov, indent=1))
    audit.append("media.drawn", "bau", {"file": out.name, "model": model, "seed": seed,
                                        "under_20": young, "file_sha256": prov["file_sha256"]})
    return {"file": out.name, "seed": seed, "bytes": len(png)}
