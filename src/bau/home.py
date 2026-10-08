"""BAU_HOME: the canonical runtime state directory (spec §91 `.bau/`).

Shipped defaults live inside the package (`bau/data`). `bau init` copies
them into BAU_HOME, where the regulation watcher and human reviewers
update them under the lifecycle in spec §93. Memory is not authority:
canonical state is whatever is in BAU_HOME, verified by the audit chain.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

LAYOUT = [
    "config", "policies", "schemas", "registry", "memory", "history", "compliance",
    "regulations", "ip", "tax", "data", "security", "audit", "evidence", "jobs",
    "checkpoints", "artifacts", "tests", "benchmarks", "snapshots", "reports",
    "consent", "suppression", "dsr", "approvals", "economics", "artifacts/drafts",
    "artifacts/media_inbox", "artifacts/exports", "constitution",
]


def bau_home() -> Path:
    env = os.environ.get("BAU_HOME")
    if env:
        return Path(env)
    system = Path("/var/lib/bau")
    if system.is_dir() and os.access(system, os.W_OK):
        return system
    return Path.home() / ".bau"


def shipped_data() -> Path:
    return Path(str(resources.files("bau") / "data"))


def init_home(home: Path | None = None, overwrite_data: bool = False) -> Path:
    home = home or bau_home()
    if not home.exists():
        # Created by us: private. An existing dir (the installer makes /var/lib/bau
        # 2770 bau:bau so the admin and the agent account share it) is left alone.
        home.mkdir(parents=True, mode=0o750)
    for sub in LAYOUT:
        (home / sub).mkdir(parents=True, exist_ok=True)
    # Copied only when missing, so the owner's edits (e.g. to the constitution) survive.
    for sub in ("regulations", "policies", "schemas", "constitution"):
        src = shipped_data() / sub
        if not src.is_dir():
            continue
        for f in src.iterdir():
            dst = home / sub / f.name
            if overwrite_data or not dst.exists():
                shutil.copy2(f, dst)
    bs = home / "reports" / "build_state.yaml"
    if not bs.exists():
        shutil.copy2(shipped_data() / "build_state.yaml", bs)
    return home


def data_dir(sub: str, home: Path | None = None) -> Path:
    """Prefer BAU_HOME copies (reviewed, updatable); fall back to shipped data."""
    home = home or bau_home()
    local = home / sub
    if local.is_dir() and any(local.iterdir()):
        return local
    return shipped_data() / sub


def atomic_write_json(path: Path, obj: Any) -> None:
    """Write-then-rename with fsync so a crash never leaves half a file (spec §87-88)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    os.fchmod(fd, 0o660)  # mkstemp is 0600; state is shared by the bau group
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
