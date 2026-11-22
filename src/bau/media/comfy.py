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

Clips (the owner's ask 2026-11-21, levels 2 and 3, Fanvue only, solo only): Wan 2.2 TI2V-5B
(Wan-AI/Wan2.2-TI2V-5B, Apache-2.0) animates one of her pictures that already passed the age
check, in ComfyUI's own Wan 2.2 5B workflow (docs.comfy.org/tutorials/video/wan/wan2_2 and the
template video_wan2_2_5B_ti2v.json, read 2026-11-21): UNETLoader(weight_dtype default) ->
ModelSamplingSD3(shift 8); CLIPLoader(type "wan"); VAELoader; LoadImage ->
Wan22ImageToVideoLatent(width, height, length 4k+1, start_image); KSampler(20 steps, cfg 5,
uni_pc, simple); VAEDecode; CreateVideo(fps 24); SaveVideo, whose result is listed under
"images" in /history like a picture (comfy_api/latest/_ui.py PreviewVideo). Every node was
checked in ComfyUI commit 17ff1dc on 2026-11-21; SaveVideo's nested inputs are named with dots
("format.codec", _io.py finalize_prefix). ComfyUI says the 5B "should fit well on 8GB vram
with the ComfyUI native offloading" (their claim; measured on this card before the defaults
below are trusted). Files (installer/bau-video-setup.sh, SHA-256 pinned): Comfy-Org/Wan-2.2
wan2.2_ti2v_5B_fp16.safetensors and wan2.2_vae.safetensors, Comfy-Org/Wan-2.1
umt5_xxl_fp8_e4m3fn_scaled.safetensors, all Apache-2.0. Fanvue's rules (read 2026-11-21,
examples/platform-fanvue.yaml) ban bodily fluids and need ID and consent for anyone else shown,
so a clip prompt naming a second person, fluids or a banned act is refused (SOLO_ONLY). Every
frame of every clip passes the same age check (one run of the age model for all of them), or
nothing is kept.

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
# The face lock (the owner's choice 2026-11-18; installed by bau-face-setup.sh): IP-Adapter
# Plus Face for SDXL (h94/IP-Adapter, Apache-2.0, commit 018e4027) through the
# ComfyUI_IPAdapter_plus nodes (GPL-3.0, commit a0f451a5, run by ComfyUI, not imported here).
# Read in that commit 2026-11-18: IPAdapterUnifiedLoader(model, preset "PLUS FACE (portraits)")
# -> MODEL, IPADAPTER, finding the files by name in models/ipadapter and models/clip_vision;
# IPAdapterAdvanced(model, ipadapter, image, weight, weight_type, combine_embeds, start_at,
# end_at, embeds_scaling) -> MODEL. The face picture goes to ComfyUI with POST /upload/image.
# Only the safe-for-work lane: there is no IP-Adapter for Chroma (the explicit lane).
COMFY_APP = Path("/usr/local/comfyui/ComfyUI")
FACE_FILES = (COMFY_APP / "custom_nodes" / "ComfyUI_IPAdapter_plus" / "IPAdapterPlus.py",
              COMFY_APP / "models" / "ipadapter" / "ip-adapter-plus-face_sdxl_vit-h.safetensors",
              COMFY_APP / "models" / "clip_vision" / "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors")
FACE_WEIGHT = 0.8
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
                          str(AGE_DIR), str(path)], capture_output=True, text=True, timeout=600)
    if run.returncode != 0:
        raise OSError((run.stderr or run.stdout).strip()[-300:] or "the age model did not run")
    return json.loads(run.stdout)


def age_scores_many(paths: list[Path]) -> list[dict[str, float]]:
    """The age model on many pictures in one run (a clip's frames): one list, same order."""
    if not paths:
        return []
    run = subprocess.run([str(AGE_PYTHON), "-I", str(Path(__file__).with_name("agecheck_run.py")),
                          str(AGE_DIR), *map(str, paths)],
                         capture_output=True, text=True, timeout=1800)
    if run.returncode != 0:
        raise OSError((run.stderr or run.stdout).strip()[-300:] or "the age model did not run")
    got = json.loads(run.stdout)
    got = got if isinstance(got, list) else [got]
    if len(got) != len(paths):
        raise OSError(f"the age model scored {len(got)} of {len(paths)} frames")
    return got


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


def face_ready() -> bool:
    """The face nodes and both face models are installed on this computer."""
    return all(f.is_file() for f in FACE_FILES)


def graph(prompt: str, seed: int, width: int = 1024, height: int = 1024, steps: int = 30,
          negative: str = NEGATIVE, ckpt: str = MODEL, face: str | None = None,
          face_weight: float = FACE_WEIGHT) -> dict[str, Any]:
    """The smallest text-to-picture job, in ComfyUI's API format (node id -> node). With
    ``face`` (a picture already uploaded to ComfyUI) the model is drawn from that face."""
    g = _sdxl(prompt, seed, width, height, steps, negative, ckpt)
    if face:
        g["8"] = {"class_type": "LoadImage", "inputs": {"image": face}}
        g["9"] = {"class_type": "IPAdapterUnifiedLoader",
                  "inputs": {"model": ["1", 0], "preset": "PLUS FACE (portraits)"}}
        g["10"] = {"class_type": "IPAdapterAdvanced",
                   "inputs": {"model": ["9", 0], "ipadapter": ["9", 1], "image": ["8", 0],
                              "weight": float(face_weight), "weight_type": "linear",
                              "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                              "embeds_scaling": "V only"}}
        g["5"]["inputs"]["model"] = ["10", 0]
    return g


def _sdxl(prompt: str, seed: int, width: int, height: int, steps: int, negative: str,
          ckpt: str) -> dict[str, Any]:
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


LORA_STRENGTH = 0.9


def chroma_graph(prompt: str, seed: int, negative: str = NEGATIVE, width: int = 1152,
                 height: int = 1152, lora: str | None = None,
                 lora_strength: float = LORA_STRENGTH) -> dict[str, Any]:
    """The Chroma1-HD model card's ComfyUI workflow, in ComfyUI's API format. With ``lora``
    (a file in ComfyUI's loras folder: the creator's face) ComfyUI's own LoraLoaderModelOnly
    sits between the model and its sampling (nodes.py, read 2026-11-18 in ComfyUI 0.43.0)."""
    g = _chroma(prompt, seed, negative, width, height)
    if lora:
        g["15"] = {"class_type": "LoraLoaderModelOnly",
                   "inputs": {"model": ["1", 0], "lora_name": lora,
                              "strength_model": float(lora_strength)}}
        g["2"]["inputs"]["model"] = ["15", 0]
    return g


def _chroma(prompt: str, seed: int, negative: str, width: int, height: int) -> dict[str, Any]:
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


def upload_face(opener: Any, base: str, face: Path, prefix: str = "bau-face-") -> str:
    """Send a picture (the locked face, or a clip's start) to ComfyUI's input folder; returns
    the name it uses."""
    data = face.read_bytes()
    name = prefix + hashlib.sha256(data).hexdigest()[:16] + ".png"
    boundary = "bau" + hashlib.sha256(data[:64] + name.encode()).hexdigest()[:24]
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n").encode() + data + \
        f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(base + "/upload/image", data=body, method="POST", headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with opener(req, timeout=60) as r:
        got = json.loads(r.read() or b"{}")
    if not got.get("name"):
        raise ComfyError("ComfyUI did not take the face picture")
    return got["name"] if not got.get("subfolder") else f"{got['subfolder']}/{got['name']}"


def _call(opener: Any, url: str, body: dict[str, Any] | None = None, raw: bool = False,
          timeout: int = 60) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    with opener(req, timeout=timeout) as r:
        got = r.read()
    return got if raw else json.loads(got or b"{}")


# How long one picture may take once ComfyUI is drawing it, and how long it may wait in
# ComfyUI's line before that. Chroma on the desktop's RTX 3060 took 9 to 33 minutes a picture
# (bau-pictures journal, 2026-11-20: 548.97 s to 00:32:47); the old 15 minutes for everything,
# counted from the moment the job was sent, gave up on every Chroma picture and on any picture
# that waited in line, and left the job running for nobody: the line grew to 15.
DRAW_SFW, DRAW_EXPLICIT, IN_LINE = 900.0, 2700.0, 3600.0


def _cancel(opener: Any, base: str, pid: str) -> None:
    """Take our own job back from ComfyUI: out of the line if it waits, stopped if it is being
    drawn. Only ever this ``pid`` (server.py's POST /queue delete and POST /interrupt with a
    prompt_id, read 2026-11-20 in /usr/local/comfyui/ComfyUI/server.py). Best effort: the reason
    we gave up is what the caller hears."""
    try:
        q = _call(opener, f"{base}/queue")
        if any(item[1] == pid for item in q.get("queue_pending", [])):
            _call(opener, f"{base}/queue", {"delete": [pid]})
        elif any(item[1] == pid for item in q.get("queue_running", [])):
            _call(opener, f"{base}/interrupt", {"prompt_id": pid})
    except Exception:  # noqa: BLE001 - ComfyUI gone: nothing is left to take back
        pass


def _await(opener: Any, base: str, pid: str, wait: float, max_draw: float,
           max_line: float) -> dict[str, Any]:
    """Wait for one job's picture. Time in ComfyUI's line counts against ``max_line``, time
    being drawn against ``max_draw``."""
    in_line = drawing = 0.0
    step = max(wait, 0.001)
    while True:
        hist = _call(opener, f"{base}/history/{urllib.parse.quote(pid)}").get(pid)
        if hist and hist.get("outputs"):
            return hist
        if hist and (hist.get("status") or {}).get("status_str") == "error":
            raise ComfyError(f"ComfyUI failed the job: {hist['status']}")
        q = _call(opener, f"{base}/queue")
        if any(item[1] == pid for item in q.get("queue_pending", [])):
            in_line += step
            if in_line >= max_line:
                raise ComfyError(f"still waiting in ComfyUI's line after {int(max_line)} s "
                                 "(other pictures ahead); it was taken out of the line")
        else:
            drawing += step
            if drawing >= max_draw:
                raise ComfyError(f"no picture after {int(max_draw)} s of drawing; "
                                 "the job was stopped")
        time.sleep(wait)


def draw(home: Path, prompt: str, name: str, seed: int | None = None, base: str = BASE,
         opener: Any = None, wait: float = 2.0, max_wait: float | None = None,
         max_line: float = IN_LINE,
         checker: Any = None, negative: str = NEGATIVE, lane: str = "sfw",
         face: Path | None = None, lora: str | None = None, **size: int) -> dict[str, Any]:
    """Draw one picture into BAU_HOME/artifacts/media/NAME.png and record where it came from.
    ``face``: the creator's locked face picture, used on the safe-for-work lane. ``max_wait``:
    seconds of drawing (by lane when not given); ``max_line``: seconds in ComfyUI's line."""
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
    face_sha = None
    if face is not None and lane == "sfw":
        face_sha = hashlib.sha256(Path(face).read_bytes()).hexdigest()
        face_name = upload_face(opener, base, Path(face))
    g = (chroma_graph(prompt, seed, negative=negative, lora=lora, **size) if lane == "explicit"
         else graph(prompt, seed, negative=negative,
                    face=face_name if face_sha else None, **size))
    job = _call(opener, base + "/prompt", {"prompt": g})
    if not job.get("prompt_id"):
        err = job.get("error")
        why = err.get("message") if isinstance(err, dict) else err
        raise ComfyError(f"ComfyUI refused the job: {why or job.get('node_errors')}")
    pid = job["prompt_id"]
    if max_wait is None:
        max_wait = DRAW_EXPLICIT if lane == "explicit" else DRAW_SFW
    try:
        hist = _await(opener, base, pid, wait, max_wait, max_line)
    except BaseException:                   # gave up, or stopped (Ctrl-C): never left behind
        _cancel(opener, base, pid)
        raise
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
            "face_lock": ({"adapter": "ip-adapter-plus-face_sdxl_vit-h", "face_sha256": face_sha,
                           "weight": FACE_WEIGHT} if face_sha else None),
            "lora": ({"file": lora, "strength": LORA_STRENGTH}
                     if lora and lane == "explicit" else None),
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "file_sha256": hashlib.sha256(png).hexdigest(),
            "age_check": {"passed": True, "under_20": young, "max": MAX_UNDER_20,
                          "model": AGE_MODEL, "revision": AGE_REVISION},
            "created": dt.datetime.now(dt.UTC).isoformat()}
    (media / f"{name}.png.provenance.json").write_text(json.dumps(prov, indent=1))
    audit.append("media.drawn", "bau", {"file": out.name, "model": model, "seed": seed,
                                        "under_20": young, "file_sha256": prov["file_sha256"]})
    return {"file": out.name, "seed": seed, "bytes": len(png)}


# ---------------------------------------------------------------- clips (Wan 2.2 TI2V-5B)
WAN = "wan2.2_ti2v_5B_fp16.safetensors"
WAN_TEXT = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
WAN_VAE = "wan2.2_vae.safetensors"
WAN_FILES = (COMFY_APP / "models" / "diffusion_models" / WAN,
             COMFY_APP / "models" / "text_encoders" / WAN_TEXT,
             COMFY_APP / "models" / "vae" / WAN_VAE)
# Cautious until measured on the desktop's card: portrait, 3 seconds at 24 a second.
CLIP_WIDTH, CLIP_HEIGHT, CLIP_FRAMES, CLIP_FPS = 704, 1280, 73, 24
DRAW_CLIP = 3600.0
CLIP_NEGATIVE = NEGATIVE + (", another person, man, partner, couple, bodily fluids, "
                            "static, frozen, blurry, distorted face, extra limbs")
# Solo only, and nothing Fanvue bans (community guidelines C.6, read 2026-11-21): a second
# person, fluids, choking, sleep, family roles, non-consent, blood. Refused, never sent.
SOLO_ONLY = re.compile(
    r"\b(man|men|male|guy|boyfriend|husband|partner|couple|threesome|two people|"
    r"another (?:person|woman|girl)|second person|penis|cock|dick|ejaculat\w*|cum|cums|"
    r"cumshot\w*|creampie\w*|facial|squirt\w*|gush\w*|semen|sperm|urinat\w*|pee|piss\w*|"
    r"chok\w*|strangl\w*|asleep|sleeping|unconscious|incest|step(?:mom|mother|sister|dad|"
    r"father|brother|daughter|son)|rape|forced|non-?consent\w*|blood\w*)\b", re.I)


def wan_ready() -> bool:
    return all(f.is_file() for f in WAN_FILES)


def wan_graph(start: str, prompt: str, seed: int, negative: str = CLIP_NEGATIVE,
              width: int = CLIP_WIDTH, height: int = CLIP_HEIGHT,
              frames: int = CLIP_FRAMES, fps: int = CLIP_FPS) -> dict[str, Any]:
    """ComfyUI's own Wan 2.2 5B workflow in its API format, starting from ``start`` (a picture
    already in ComfyUI's input folder)."""
    if frames % 4 != 1:
        raise ComfyError("a clip's length is 4k+1 frames (Wan22ImageToVideoLatent)")
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": WAN, "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": WAN_TEXT, "type": "wan", "device": "default"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["3", 0]}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": WAN_VAE}},
        "7": {"class_type": "LoadImage", "inputs": {"image": start}},
        "8": {"class_type": "Wan22ImageToVideoLatent",
              "inputs": {"vae": ["6", 0], "width": width, "height": height, "length": frames,
                         "batch_size": 1, "start_image": ["7", 0]}},
        "9": {"class_type": "KSampler",
              "inputs": {"model": ["2", 0], "seed": seed, "steps": 20, "cfg": 5,
                         "sampler_name": "uni_pc", "scheduler": "simple",
                         "positive": ["4", 0], "negative": ["5", 0],
                         "latent_image": ["8", 0], "denoise": 1}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["6", 0]}},
        "11": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "fps": fps}},
        "12": {"class_type": "SaveVideo",
               "inputs": {"video": ["11", 0], "filename_prefix": "bau/clip", "format": "mp4",
                          "format.codec": "auto"}},
    }


def video_frames(clip: Path, out: Path) -> list[Path]:
    """Every frame of the clip as a picture for the age check (ffmpeg, no frame skipped: the
    security review of 2026-11-21 found one a second left most frames unchecked)."""
    out.mkdir(parents=True, exist_ok=True)
    run = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip),
                          "-fps_mode", "passthrough", str(out / "f%05d.png")],
                         capture_output=True, text=True, timeout=600)
    if run.returncode != 0:
        raise OSError((run.stderr or "ffmpeg failed").strip()[-300:])
    frames = sorted(out.glob("f*.png"))
    if not frames:
        raise OSError("ffmpeg found no frames in the clip")
    return frames


def animate(home: Path, picture: str, prompt: str, name: str, seed: int | None = None,
            base: str = BASE, opener: Any = None, wait: float = 5.0,
            max_wait: float = DRAW_CLIP, max_line: float = IN_LINE, checker: Any = None,
            frames_of: Any = None, negative: str = CLIP_NEGATIVE, **size: int) -> dict[str, Any]:
    """Make one clip, BAU_HOME/artifacts/media/NAME.mp4, from ``picture``: one of her pictures
    in artifacts/media that already passed the age check. Every frame of the clip is
    age-checked again; one failing, a frame missing, or the check not running keeps nothing."""
    if not LOCAL.match(base):
        raise ComfyError("clips are made only by a model server on this computer")
    if not NAME.match(name or ""):
        raise ComfyError("a clip name is lowercase letters, digits, dot, dash")
    if m := MINOR_REFERENCE.search(prompt):
        raise ComfyError(f"refers to minors ({m.group(0)!r}); BAU never makes that")
    if m := SOLO_ONLY.search(prompt):
        raise ComfyError(f"clips are her alone and within Fanvue's rules ({m.group(0)!r} is "
                         "not); never sent")
    media = home / "artifacts" / "media"
    start = media / Path(picture).name
    try:
        prov = json.loads((media / f"{start.name}.provenance.json").read_text())
    except (OSError, ValueError):
        prov = {}
    if start.suffix != ".png" or not start.is_file() or \
            not (prov.get("age_check") or {}).get("passed"):
        raise ComfyError(f"{picture} is not one of her kept pictures (age-checked)")
    opener = opener or urllib.request.urlopen
    seed = random.randrange(2**32) if seed is None else int(seed)
    first = upload_face(opener, base, start, prefix="bau-clip-")
    job = _call(opener, base + "/prompt",
                {"prompt": wan_graph(first, prompt, seed, negative=negative, **size)})
    if not job.get("prompt_id"):
        err = job.get("error")
        why = err.get("message") if isinstance(err, dict) else err
        raise ComfyError(f"ComfyUI refused the job: {why or job.get('node_errors')}")
    pid = job["prompt_id"]
    try:
        hist = _await(opener, base, pid, wait, max_wait, max_line)
    except BaseException:
        _cancel(opener, base, pid)
        raise
    made = [i for o in hist["outputs"].values() for i in o.get("images", [])]
    if not made:
        raise ComfyError("ComfyUI finished without a clip")
    q = urllib.parse.urlencode({k: made[0].get(k, "") for k in ("filename", "subfolder",
                                                                 "type")})
    data = _call(opener, f"{base}/view?{q}", raw=True, timeout=300)
    audit = AuditLog(home / "audit" / "chain.jsonl")
    rejected = home / "artifacts" / "rejected"
    rejected.mkdir(parents=True, exist_ok=True)
    held = rejected / f"{name}.mp4"                  # stays here unless every frame passes
    held.write_bytes(data)
    look = rejected / f".frames-{name}"
    expected = int(size.get("frames", CLIP_FRAMES))
    try:
        frames = (frames_of or video_frames)(held, look)
        if len(frames) != expected:          # every frame, or the clip is not kept
            raise OSError(f"{len(frames)} frames decoded, {expected} made")
        found = [checker(f) for f in frames] if checker else age_scores_many(frames)
        scores = [under_20(x) for x in found]
    except Exception as e:  # noqa: BLE001 - any failure means the clip is not kept
        audit.append("media.rejected", "bau", {"file": held.name, "why": "age check failed"})
        raise ComfyError(f"the age check could not run ({e}); the clip was not kept") from e
    finally:
        shutil.rmtree(look, ignore_errors=True)
    if not scores or max(scores) > MAX_UNDER_20:
        audit.append("media.rejected", "bau", {"file": held.name, "under_20": max(scores or [1])})
        raise ComfyError(f"a frame could pass for under 20 ({max(scores or [1]):.2f}); the "
                         "clip was moved to artifacts/rejected and will not be used")
    out = media / f"{name}.mp4"
    shutil.move(held, out)
    w, h, n = (size.get("width", CLIP_WIDTH), size.get("height", CLIP_HEIGHT),
               size.get("frames", CLIP_FRAMES))
    clip_prov = {"ai_generated": True, "generator": "ComfyUI (local)", "model": WAN,
                 "lane": prov.get("lane", "explicit"), "seed": seed, "kind": "clip",
                 "start": {"file": start.name, "file_sha256": prov.get("file_sha256")},
                 "size": [w, h], "frames": n, "fps": CLIP_FPS,
                 "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                 "file_sha256": hashlib.sha256(data).hexdigest(),
                 "age_check": {"passed": True, "under_20": max(scores), "frames": len(scores),
                               "of_frames": expected, "max": MAX_UNDER_20, "model": AGE_MODEL,
                               "revision": AGE_REVISION},
                 "created": dt.datetime.now(dt.UTC).isoformat()}
    (media / f"{name}.mp4.provenance.json").write_text(json.dumps(clip_prov, indent=1))
    audit.append("media.animated", "bau", {"file": out.name, "start": start.name, "seed": seed,
                                           "under_20": max(scores), "frames": len(scores),
                                           "file_sha256": clip_prov["file_sha256"]})
    return {"file": out.name, "seed": seed, "bytes": len(data)}

