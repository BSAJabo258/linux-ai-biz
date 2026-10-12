"""Brains: which model drafts each workspace stage.

The files-and-folders system (workspaces) does the work; a stage folder only says which
kind of brain it needs (its `## Brain` section):

- ``small``: the free local model, for routine steps (pitches, metadata, lists). When no
  local model is approved yet, the strong brain does it and the result says so.
- ``strong``: Claude, or whatever model Jarvis thinks with, for steps that need
  judgement. The owner may name a different approved model.
- ``content``: a local uncensored (abliterated) model in the sealed content lane. It drafts
  text only: no tools, local only, only the content jobs its registry record lists, never
  in a kids workspace, and never chosen for the owner.

The owner picks once which model each brain means (``bau ws brains``); only a person can.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .home import bau_home
from .registry import CONTENT_LANE, ROUTABLE, CapabilityRegistry
from .store import YamlStore
from .workspace import BRAINS, for_kids

WHAT = {"small": "free local model for routine steps",
        "strong": "Claude or Jarvis's best model, for steps that need judgement",
        "content": "local uncensored model, sealed content lane: text only, no tools, "
                   "never kids"}


def _models(home: Path) -> dict[str, dict[str, Any]]:
    return CapabilityRegistry(home / "registry" / "capabilities.yaml").data["model"]


def _store(home: Path) -> YamlStore:
    return YamlStore(home / "config" / "brains.yaml")


def config(home: Path | None = None) -> dict[str, str | None]:
    """The owner's choices; the small brain defaults to the first approved local model.
    Strong defaults to Jarvis's own model (None here); content is never defaulted."""
    home = home or bau_home()
    saved = _store(home).load() or {}
    small = saved.get("small") or next(
        (mid for mid, r in _models(home).items() if r.get("deployment") == "local"
         and r.get("status") in ROUTABLE and r.get("lane") != CONTENT_LANE), None)
    return {"small": small, "strong": saved.get("strong"), "content": saved.get("content")}


def choose(home: Path | None, by: str, audit: Any = None, **ids: str | None
           ) -> dict[str, str | None]:
    """The owner names the model behind one or more brains. Human only."""
    home = home or bau_home()
    if not by.startswith("human:"):
        raise PermissionError("only the owner chooses which model each brain is")
    models = _models(home)
    for brain, mid in ids.items():
        if brain not in BRAINS:
            raise ValueError(f"no brain {brain!r}; have {', '.join(BRAINS)}")
        if mid is None:
            continue
        rec = models.get(mid)
        if rec is None:
            raise ValueError(f"model {mid} is not registered (bau registry list)")
        sealed = rec.get("lane") == CONTENT_LANE
        if brain == "content" and not sealed:
            raise ValueError(f"{mid} is not in the content lane; only a content lane model "
                             "can be the content brain")
        if brain != "content" and sealed:
            raise ValueError(f"{mid} is a content lane model; it can only be the content "
                             "brain")
    saved = _store(home).load() or {}
    saved.update({k: v for k, v in ids.items() if v is not None})
    saved.update(set_by=by, set_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"))
    (home / "config").mkdir(parents=True, exist_ok=True)
    _store(home).save(saved)
    if audit is not None:
        audit.append("brains.chosen", by, {k: v for k, v in ids.items() if v is not None})
    return config(home)


def resolve(brain: str, home: Path | None, ws: Path, jarvis: tuple[Any, dict[str, Any]],
            factory: Callable[..., tuple[Any, dict[str, Any]]] | None = None,
            kind: str = "") -> dict[str, Any]:
    """The provider and model record for a brain in this workspace, with a note when a
    fallback was used. ``jarvis`` is Jarvis's own (provider, record)."""
    from .runtime import provider_for
    home = home or bau_home()
    factory = factory or provider_for
    cfg = config(home)
    if brain not in BRAINS:
        raise ValueError(f"no brain {brain!r}; have {', '.join(BRAINS)}")

    def strong(note: str = "") -> dict[str, Any]:
        if cfg["strong"]:
            p, rec = factory(cfg["strong"], home)
            return {"brain": "strong", "provider": p, "model": {**rec, "id": cfg["strong"]},
                    "note": note}
        if jarvis[0] is None:
            raise ValueError("no approved model to draft with (bau models bench ...)")
        return {"brain": "strong", "provider": jarvis[0], "model": jarvis[1], "note": note}

    if brain == "strong":
        return strong()
    if brain == "small":
        if cfg["small"]:
            try:
                p, rec = factory(cfg["small"], home)
                return {"brain": "small", "provider": p,
                        "model": {**rec, "id": cfg["small"]}, "note": ""}
            except (KeyError, PermissionError, ImportError) as e:
                return strong(f"small brain {cfg['small']} not usable ({e}); the strong "
                              "brain drafted it")
        return strong("no small local model approved yet; the strong brain drafted it")
    if for_kids(ws):
        raise ValueError("the content brain is never used in a kids workspace")
    if not cfg["content"]:
        raise ValueError("no content brain chosen: the owner picks one with "
                         "`bau ws brains --content MODEL`")
    if not kind:
        raise ValueError("say which content job this stage is (its Brain line, e.g. "
                         "'content lyrics')")
    p, rec = factory(cfg["content"], home)
    if rec.get("lane") != CONTENT_LANE:
        raise ValueError(f"{cfg['content']} is not in the content lane")
    if kind not in (rec.get("use_for") or []):
        raise ValueError(f"{kind!r} is not in {cfg['content']}'s use_for "
                         f"({', '.join(rec.get('use_for') or [])})")
    return {"brain": "content", "provider": p, "model": {**rec, "id": cfg["content"]},
            "note": ""}
