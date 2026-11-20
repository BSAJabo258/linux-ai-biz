"""The creator's locked face: the same woman in every safe-for-work picture (docs/PICTURES.md).

The owner's choice (2026-11-18, "all consistent model per page"): BAU draws a few candidate
faces of the creator, the owner picks one, and from then on each safe-for-work picture is drawn
from that face with IP-Adapter Plus Face (media/comfy.py; installed by bau-face-setup.sh).

The pick is the owner's, at a terminal: a model never chooses or changes the face. The lock is
a small file next to the faces, BAU_HOME/creators/faces/<id>.lock.json, holding the picture's
SHA-256, so the owner's hand-written profile is never rewritten. A face whose file no longer
matches its lock is not used.

The explicit lane (Chroma) has no IP-Adapter, so her face there is a LoRA (2026-11-18):
``draw_dataset`` draws her in many clothed scenes from the locked face, each with a caption that
names her trigger word; the owner deletes any that do not look like her; the owner trains with
installer/bau-lora-train.sh (kohya-ss/sd-scripts, Apache-2.0, on this computer); and the owner
locks the result with ``use_lora`` (SHA-256, like the face). Levels 2 and 3 are then drawn with
it. The LoRA learns her face from clothed pictures only; what each level shows comes from the
level's own prompt and the owner's explicit limits, as before.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from .home import atomic_write_json

ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")
HEADSHOT = ("neutral light grey studio background, soft even light, looking straight at the "
            "camera, calm natural expression, face clearly visible")
HEADSHOT_SHOT = "close-up head and shoulders"
MAX_CANDIDATES = 8
MAX_DATASET = 40
# Clothed scenes that vary the angle, light, clothes and place, so the LoRA learns her face and
# nothing else (the trainer's own advice: varied pictures of one subject).
DATASET_SCENES = (
    "close-up portrait, soft window light, white t-shirt",
    "head and shoulders, smiling, outdoor cafe, daylight",
    "three-quarter view, black turtleneck, studio light",
    "profile view, golden hour light, linen shirt",
    "waist-up, laughing, city street at dusk, denim jacket",
    "close-up, looking over her shoulder, warm lamp light",
    "medium shot, sitting by a window, knit sweater, morning light",
    "portrait, hair tied back, plain grey background, soft light",
    "waist-up, red evening dress, restaurant, candle light",
    "close-up, wet hair after a swim, beach, sun",
    "medium shot, reading a book on a sofa, cozy room",
    "portrait, looking up, overcast daylight, trench coat",
    "head and shoulders, neutral expression, bright studio",
    "waist-up, gym clothes, sports hall, even light",
    "close-up, slight smile, autumn park, scarf",
    "three-quarter view, silk blouse, office, daylight",
    "medium shot, cooking in a kitchen, apron, warm light",
    "portrait, hair down, night city lights behind her, coat",
    "close-up, eyes closed, sunlight on her face",
    "waist-up, summer dress, garden, dappled light",
    "head and shoulders, glasses, library, soft light",
    "profile view, looking out to sea, windy, sweater",
    "medium shot, leaning on a wall, leather jacket, street",
    "portrait, serious expression, black background, rim light",
)


class FaceError(ValueError):
    pass


def _id(prof: dict[str, Any]) -> str:
    cid = str(prof.get("id") or "")
    if not ID.match(cid):
        raise FaceError(f"the creator profile needs a simple id (got {cid!r})")
    return cid


def faces_dir(home: Path) -> Path:
    return home / "creators" / "faces"


def candidates(home: Path, prof: dict[str, Any]) -> list[Path]:
    cid = _id(prof)
    d = faces_dir(home) / "candidates"
    return sorted(d.glob(f"{cid}-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1])) \
        if d.is_dir() else []


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def draw_candidates(home: Path, prof: dict[str, Any], count: int = 4,
                    drawer: Any = None) -> list[dict[str, Any]]:
    """Draw ``count`` candidate headshots (age-checked, as every picture). They are moved out
    of artifacts/media at once: the Fanvue queue picks from there, and these are never posted."""
    from .media import comfy
    cid = _id(prof)
    if not 1 <= int(count) <= MAX_CANDIDATES:
        raise FaceError(f"draw 1 to {MAX_CANDIDATES} candidates")
    out_dir = faces_dir(home) / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    have = [int(p.stem.rsplit("-", 1)[1]) for p in candidates(home, prof)]
    start = max(have, default=0) + 1
    prompt = comfy.creator_prompt(prof, HEADSHOT, HEADSHOT_SHOT)
    media = home / "artifacts" / "media"
    done = []
    for n in range(start, start + int(count)):
        name = f"face-{cid}-{n}"
        try:
            (drawer or comfy.draw)(home, prompt, name, width=896, height=1152)
        except (comfy.ComfyError, OSError) as e:
            done.append({"number": n, "result": f"not drawn: {e}"})
            continue
        dest = out_dir / f"{cid}-{n}.png"
        (media / f"{name}.png").replace(dest)
        prov = media / f"{name}.png.provenance.json"
        if prov.exists():
            prov.replace(out_dir / f"{cid}-{n}.png.provenance.json")
        done.append({"number": n, "result": "drawn", "file": str(dest)})
    return done


def trigger(prof: dict[str, Any]) -> str:
    """Her trigger word: a made-up token the LoRA ties to her face."""
    return "bau" + re.sub(r"[^a-z0-9]", "", _id(prof))


def dataset_dir(home: Path, prof: dict[str, Any]) -> Path:
    return faces_dir(home) / "dataset" / _id(prof)


def draw_dataset(home: Path, prof: dict[str, Any], count: int = 20,
                 drawer: Any = None) -> list[dict[str, Any]]:
    """Draw her in ``count`` clothed scenes from the locked face, each with its caption, for
    the LoRA. Never in artifacts/media; numbers already there are kept, never overwritten."""
    from .media import comfy
    face = locked(home, prof)
    if face is None:
        raise FaceError("lock her face first: bau creator face pick N")
    if not 1 <= int(count) <= MAX_DATASET:
        raise FaceError(f"draw 1 to {MAX_DATASET} dataset pictures")
    out_dir = dataset_dir(home, prof)
    out_dir.mkdir(parents=True, exist_ok=True)
    have = [int(p.stem) for p in out_dir.glob("*.png") if p.stem.isdigit()]
    start = max(have, default=0) + 1
    word = trigger(prof)
    media = home / "artifacts" / "media"
    done = []
    for n in range(start, start + int(count)):
        scene = DATASET_SCENES[(n - 1) % len(DATASET_SCENES)]
        name = f"lora-{_id(prof)}-{n}"
        try:
            (drawer or comfy.draw)(home, comfy.creator_prompt(prof, scene, "portrait"), name,
                                   face=face, width=896, height=1152)
        except (comfy.ComfyError, OSError) as e:
            done.append({"number": n, "result": f"not drawn: {e}"})
            continue
        (media / f"{name}.png").replace(out_dir / f"{n:02d}.png")
        prov = media / f"{name}.png.provenance.json"
        if prov.exists():
            prov.replace(out_dir / f"{n:02d}.png.provenance.json")
        (out_dir / f"{n:02d}.txt").write_text(f"photo of {word} woman, {scene}\n")
        done.append({"number": n, "result": "drawn", "scene": scene})
    return done


def lora_file(prof: dict[str, Any]) -> Path:
    """Where bau-lora-train.sh writes her LoRA, in ComfyUI's loras folder."""
    from .media import comfy
    return comfy.COMFY_APP / "models" / "loras" / f"bau-{_id(prof)}-chroma.safetensors"


def use_lora(home: Path, prof: dict[str, Any], by: str, audit: Any = None,
             path: Path | None = None) -> dict[str, Any]:
    """The owner locks the trained LoRA (after looking at its test pictures)."""
    if not str(by).startswith("human:"):
        raise PermissionError("only the owner locks the creator's LoRA")
    cid = _id(prof)
    f = path or lora_file(prof)
    if not f.is_file():
        raise FaceError(f"no LoRA at {f}: train it first (sudo bash bau-lora-train.sh {cid})")
    face = locked(home, prof)
    lock = {"creator": cid, "file": f.name, "sha256": _sha(f), "trigger": trigger(prof),
            "face_sha256": _sha(face) if face else None, "locked_by": by,
            "locked_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    atomic_write_json(faces_dir(home) / f"{cid}.lora.json", lock)
    if audit is not None:
        audit.append("creator.lora_locked", by, {"creator": cid, "sha256": lock["sha256"]})
    return lock


def locked_lora(home: Path, prof: dict[str, Any],
                path: Path | None = None) -> dict[str, Any] | None:
    """The locked LoRA's ComfyUI name and trigger word, only while the file matches its lock."""
    try:
        cid = _id(prof)
        lock = json.loads((faces_dir(home) / f"{cid}.lora.json").read_text())
    except (FaceError, OSError, ValueError):
        return None
    f = path or lora_file(prof)
    if not f.is_file() or _sha(f) != lock.get("sha256"):
        return None
    return {"name": f.name, "trigger": lock["trigger"], "sha256": lock["sha256"]}


def _lock_path(home: Path, cid: str) -> Path:
    return faces_dir(home) / f"{cid}.lock.json"


def pick(home: Path, prof: dict[str, Any], number: int, by: str,
         audit: Any = None) -> dict[str, Any]:
    """The owner locks candidate ``number`` as the creator's face."""
    if not str(by).startswith("human:"):
        raise PermissionError("only the owner picks the creator's face")
    cid = _id(prof)
    src = faces_dir(home) / "candidates" / f"{cid}-{int(number)}.png"
    if not src.is_file():
        have = [p.stem.rsplit("-", 1)[1] for p in candidates(home, prof)]
        raise FaceError(f"no candidate {number}; have {', '.join(have) or 'none'} "
                        "(bau creator face draw)")
    dest = faces_dir(home) / f"{cid}.png"
    shutil.copy2(src, dest)
    lock = {"creator": cid, "file": dest.name, "sha256": _sha(dest), "from": src.name,
            "picked_by": by, "picked_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    atomic_write_json(_lock_path(home, cid), lock)
    if audit is not None:
        audit.append("creator.face_locked", by, {"creator": cid, "sha256": lock["sha256"]})
    return lock


def locked(home: Path, prof: dict[str, Any]) -> Path | None:
    """The locked face picture, only while it still matches its lock."""
    try:
        cid = _id(prof)
        lock = json.loads(_lock_path(home, cid).read_text())
    except (FaceError, OSError, ValueError):
        return None
    f = faces_dir(home) / f"{cid}.png"
    return f if f.is_file() and _sha(f) == lock.get("sha256") else None


def status(home: Path, prof: dict[str, Any]) -> dict[str, Any]:
    from .media import comfy
    cid = _id(prof)
    face = locked(home, prof)
    tampered = face is None and _lock_path(home, cid).exists()
    lora = locked_lora(home, prof)
    data = sorted(dataset_dir(home, prof).glob("*.png")) if face else []
    return {"creator": cid, "installed": comfy.face_ready(),
            "locked": str(face) if face else None,
            "changed_since_lock": tampered,
            "candidates": [p.name for p in candidates(home, prof)],
            "explicit_lane": (f"locked: {lora['name']} (trigger {lora['trigger']})" if lora
                              else f"not locked yet: {len(data)} dataset picture(s); "
                                   "bau creator face dataset, then sudo bash "
                                   f"bau-lora-train.sh {cid}, then bau creator face use-lora"),
            "next": ("sudo bash bau-face-setup.sh" if not comfy.face_ready() else
                     "bau creator face draw" if not candidates(home, prof) and not face else
                     "bau creator face pick N" if not face else
                     "every safe-for-work picture now uses her face")}
