"""The creator's locked face: the same woman in every safe-for-work picture (docs/PICTURES.md).

The owner's choice (2026-11-18, "all consistent model per page"): BAU draws a few candidate
faces of the creator, the owner picks one, and from then on each safe-for-work picture is drawn
from that face with IP-Adapter Plus Face (media/comfy.py; installed by bau-face-setup.sh).

The pick is the owner's, at a terminal: a model never chooses or changes the face. The lock is
a small file next to the faces, BAU_HOME/creators/faces/<id>.lock.json, holding the picture's
SHA-256, so the owner's hand-written profile is never rewritten. A face whose file no longer
matches its lock is not used.

Not covered yet: the explicit lane (Chroma). There is no IP-Adapter for it; a face there needs
a LoRA trained on the locked pictures, the next step.
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
    return {"creator": cid, "installed": comfy.face_ready(),
            "locked": str(face) if face else None,
            "changed_since_lock": tampered,
            "candidates": [p.name for p in candidates(home, prof)],
            "explicit_lane": "not locked yet: needs a LoRA trained on her locked pictures",
            "next": ("sudo bash bau-face-setup.sh" if not comfy.face_ready() else
                     "bau creator face draw" if not candidates(home, prof) and not face else
                     "bau creator face pick N" if not face else
                     "every safe-for-work picture now uses her face")}
