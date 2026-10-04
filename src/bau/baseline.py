"""Golden baseline and controlled updates (spec §90, §104-105).

``create`` freezes a known-good state: package version, file hashes of the
installed code and of BAU_HOME registries/policies/memory/compliance, and a
backup bundle of that state (never secrets or keys). ``verify`` reports drift.
Updates move TEST -> CANARY -> VALIDATE -> PROMOTE, or ROLLBACK; no step skips.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import tarfile
from pathlib import Path
from typing import Any

from . import __version__
from .home import bau_home
from .store import JsonlStore

STATE_DIRS = ["regulations", "policies", "registry", "memory", "compliance", "config",
              "security", "ip", "tax", "data", "reports"]
NEVER = (".key", ".pem", "approval", "secret", ".env")
UPDATE_STAGES = ["TEST", "CANARY", "VALIDATE", "PROMOTE"]


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _files(root: Path, sub: list[str]) -> list[Path]:
    out = []
    for s in sub:
        d = root / s
        if d.exists():
            out += [p for p in sorted(d.rglob("*")) if p.is_file()
                    and not any(n in p.name for n in NEVER)]
    return out


def create(out_dir: Path, home: Path | None = None, code_root: Path | None = None
           ) -> dict[str, Any]:
    home = home or bau_home()
    code_root = code_root or Path(__file__).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    state = _files(home, STATE_DIRS)
    code = [p for p in sorted(code_root.rglob("*")) if p.is_file() and "__pycache__"
            not in p.parts]
    manifest = {
        "created_at": stamp, "bau_version": __version__,
        "code": {str(p.relative_to(code_root)): _hash(p) for p in code},
        "state": {str(p.relative_to(home)): _hash(p) for p in state},
    }
    man_path = out_dir / f"golden-{stamp}.json"
    man_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    bundle = out_dir / f"golden-{stamp}.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        for p in state:
            tar.add(p, arcname=str(p.relative_to(home)))
    manifest["bundle"] = str(bundle)
    manifest["bundle_sha256"] = _hash(bundle)
    man_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return {"manifest": str(man_path), "bundle": str(bundle),
            "files": len(manifest["code"]) + len(manifest["state"])}


def verify(manifest_path: Path, home: Path | None = None, code_root: Path | None = None
           ) -> dict[str, Any]:
    home = home or bau_home()
    code_root = code_root or Path(__file__).resolve().parent
    m = json.loads(manifest_path.read_text())
    drift: dict[str, list[str]] = {"changed": [], "missing": [], "added": []}
    for root, key, current in ((code_root, "code", [p for p in code_root.rglob("*")
                                                    if p.is_file() and "__pycache__"
                                                    not in p.parts]),
                               (home, "state", _files(home, STATE_DIRS))):
        cur = {str(p.relative_to(root)): _hash(p) for p in current}
        for path, h in m[key].items():
            if path not in cur:
                drift["missing"].append(f"{key}:{path}")
            elif cur[path] != h:
                drift["changed"].append(f"{key}:{path}")
        drift["added"] += [f"{key}:{p}" for p in cur if p not in m[key]]
    bundle_ok = Path(m["bundle"]).exists() and _hash(Path(m["bundle"])) == m.get(
        "bundle_sha256")
    return {"baseline": m["created_at"], "bundle_ok": bundle_ok,
            "clean": bundle_ok and not any(drift.values()), **drift}


class Updates:
    """TEST -> CANARY -> VALIDATE -> PROMOTE (or ROLLBACK at any point)."""

    def __init__(self, home: Path | None = None):
        self.log = JsonlStore((home or bau_home()) / "snapshots" / "updates.jsonl")

    def state(self, component: str) -> str | None:
        last = None
        for r in self.log:
            if r["component"] == component:
                last = r
        return last["stage"] if last else None

    def advance(self, component: str, version: str, stage: str, evidence: str,
                by: str) -> dict[str, Any]:
        cur = self.state(component)
        if stage == "ROLLBACK":
            pass
        elif stage not in UPDATE_STAGES:
            raise ValueError(f"stage must be one of {UPDATE_STAGES + ['ROLLBACK']}")
        else:
            expected = UPDATE_STAGES[0] if cur in (None, "PROMOTE", "ROLLBACK") else \
                UPDATE_STAGES[UPDATE_STAGES.index(cur) + 1]
            if stage != expected:
                raise ValueError(f"{component}: next stage must be {expected}, not {stage}")
            if stage == "PROMOTE" and not by.startswith("human:"):
                raise PermissionError("promotion to production is a human decision")
        return self.log.append({"component": component, "version": version, "stage": stage,
                                "evidence": evidence, "by": by,
                                "at": dt.datetime.now(dt.UTC).isoformat()})
