"""Local only: the owner's switch that keeps every model call on this computer.

``bau privacy local-only`` turns it on: Claude, OpenAI-compatible hosted models (Z.ai,
NVIDIA) and any model server on another computer are refused where every model is built
(``models.providers.build``), so Jarvis, the agents, the specialist, the double-check and
the benchmark all stay local. ``bau privacy cloud`` turns it off. Owner only, typed at a
terminal; there is no default (CLAUDE.md: privacy choices never come from a model).

Web research (``web_search``, ``read_page``) still reaches the internet when used: it reads
public pages, it does not hand BAU's data to a model.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .home import bau_home
from .store import YamlStore

MODES = ("local-only", "cloud")
LOCAL_ADAPTERS = ("local_http", "scripted")


def _store(home: Path) -> YamlStore:
    return YamlStore(home / "config" / "privacy.yaml")


def mode(home: Path | None = None) -> str | None:
    """'local-only', 'cloud', or None while the owner hasn't chosen."""
    return (_store(home or bau_home()).load() or {}).get("models")


def set_mode(home: Path | None, choice: str, by: str, audit: Any = None) -> dict[str, Any]:
    if not by.startswith("human:"):
        raise PermissionError("only the owner chooses where models run")
    if choice not in MODES:
        raise ValueError(f"choose one of {', '.join(MODES)}")
    home = home or bau_home()
    (home / "config").mkdir(parents=True, exist_ok=True)
    rec = {"models": choice, "set_by": by,
           "set_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    _store(home).save(rec)
    if audit is not None:
        audit.append("privacy.set", by, {"models": choice})
    return rec


def _loopback(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_local(record: dict[str, Any]) -> bool:
    """Runs on this computer: a local adapter talking to 127.0.0.1 / ::1 / localhost, or the
    test drive's model container (BAU_LLM_ENDPOINT, used only for deployment: local)."""
    kind = record.get("adapter", "local_http")
    if kind not in LOCAL_ADAPTERS:
        return False
    if kind == "scripted":
        return True
    if record.get("deployment") == "local" and os.environ.get("BAU_LLM_ENDPOINT"):
        return True
    return _loopback(record.get("endpoint", "http://127.0.0.1:8080"))


def check(record: dict[str, Any], home: Path | None = None) -> None:
    """Refuse a model that would send data off this computer while local only is on."""
    if mode(home) == "local-only" and not is_local(record):
        raise PermissionError(
            f"{record.get('model_id', 'this model')} runs off this computer and local only "
            "is on (`bau privacy` to see, `bau privacy cloud` to allow cloud models)")
