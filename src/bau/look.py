"""The BAU look (`bau look`, docs/LOOK.md): which art sits behind Jarvis and Mission Control,
and whether it is gently alive.

The art is still images: the stick's own (``moon``, ``light``) and any the owner adds with
``bau look add``. "Alive" is light CSS animation in the page (a slow breathing glow, a
pulse rising along the art's centre line, faster while Jarvis thinks), not a video, so it
costs almost nothing on an 8 GB laptop and stops for reduced-motion users.
"""

from __future__ import annotations

import re
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

from .home import bau_home
from .store import YamlStore

SHIPPED = {"moon": "moon.jpg", "light": "light.jpg"}
DEFAULT = "moon"
MAX_BYTES = 15 * 1024 * 1024
TYPES = {b"\xff\xd8\xff": (".jpg", "image/jpeg"), b"\x89PNG\r\n\x1a\n": (".png", "image/png")}


def _store(home: Path) -> YamlStore:
    return YamlStore(home / "config" / "look.yaml")


def _own(home: Path) -> dict[str, Path]:
    d = home / "art"
    return {p.stem: p for p in sorted(d.glob("*")) if p.suffix in (".jpg", ".png")} \
        if d.is_dir() else {}


def show(home: Path | None = None) -> dict[str, Any]:
    home = home or bau_home()
    saved = _store(home).load() or {}
    return {"art": saved.get("art", DEFAULT), "alive": saved.get("alive", True),
            "choices": [*SHIPPED, *_own(home), "none"]}


def brief(home: Path | None = None) -> dict[str, Any]:
    """What a page needs: the art's name (None when off) and whether it is alive."""
    s = show(home)
    return {"art": None if s["art"] == "none" else s["art"], "alive": s["alive"]}


def set_look(home: Path | None = None, art: str | None = None,
             alive: bool | None = None) -> dict[str, Any]:
    home = home or bau_home()
    saved = _store(home).load() or {}
    if art is not None:
        if art not in show(home)["choices"]:
            raise ValueError(f"no art called {art!r}; have {', '.join(show(home)['choices'])}")
        saved["art"] = art
    if alive is not None:
        saved["alive"] = bool(alive)
    _store(home).save(saved)
    return show(home)


def _kind(head: bytes) -> tuple[str, str] | None:
    return next((v for magic, v in TYPES.items() if head.startswith(magic)), None)


def add(home: Path | None, path: Path | str, name: str | None = None) -> str:
    """Bring in one of the owner's images (JPEG or PNG, checked by content) and use it."""
    home = home or bau_home()
    src = Path(path)
    if src.stat().st_size > MAX_BYTES:
        raise ValueError(f"{src.name} is too big (over {MAX_BYTES // 1024 // 1024} MB)")
    with src.open("rb") as f:
        kind = _kind(f.read(8))
    if kind is None:
        raise ValueError(f"{src.name} is not a JPEG or PNG image")
    slug = re.sub(r"[^a-z0-9]+", "-", (name or src.stem).lower()).strip("-")[:40]
    if not slug or slug in (*SHIPPED, "none"):
        slug = f"my-{slug or 'art'}"
    dest = home / "art" / f"{slug}{kind[0]}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    old = _own(home).get(slug)
    if old is not None and old != dest:            # same name, other type: replace it
        old.unlink()
    shutil.copyfile(src, dest)
    set_look(home, art=slug)
    return slug


def art_file(home: Path | None = None) -> tuple[Any, str] | None:
    """The current art (a readable file) and its content type; None when switched off."""
    home = home or bau_home()
    art = show(home)["art"]
    if art in SHIPPED:
        return resources.files("bau.ui") / "art" / SHIPPED[art], "image/jpeg"
    own = _own(home).get(art)
    if own is None:
        return None
    with own.open("rb") as f:
        kind = _kind(f.read(8))
    return (own, kind[1]) if kind else None
