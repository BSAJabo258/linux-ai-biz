"""Heretic / model transformation lab (spec §47).

A transformed model is a NEW registry entry with full lineage. The parent file
is never modified (its hash is re-checked), and the derived model starts
QUARANTINED at a lower trust level: changing behaviour never raises authority.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any

DERIVED_TRUST = {"quantize": "QUANTIZED", "merge": "MERGED", "finetune": "MODIFIED",
                 "abliterate": "ABLITERATED", "modify": "MODIFIED"}


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def derive(parent: dict[str, Any], parent_path: Path, derived_path: Path, operation: str,
           tool_version: str, configuration: dict[str, Any],
           benchmark: dict[str, Any] | None = None,
           behavior_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    if operation not in DERIVED_TRUST:
        raise ValueError(f"operation must be one of {sorted(DERIVED_TRUST)}")
    if parent_path.resolve() == derived_path.resolve():
        raise ValueError("never overwrite the original model")
    parent_hash = file_hash(parent_path)
    if parent.get("artifact_hash") and parent["artifact_hash"] != parent_hash:
        raise ValueError("parent model file changed since it was registered")
    derived_hash = file_hash(derived_path)
    return {
        "model_id": f"{parent['model_id']}+{operation}-{derived_hash[:8]}",
        "name": f"{parent['name']} ({operation})",
        "version": parent.get("version", "?"),
        "provider": parent.get("provider", "local"),
        "source": "heretic-lab",
        "license": parent["license"],            # licence obligations carry over
        "commercial_use": parent.get("commercial_use"),
        "deployment": "local",
        "trust_level": DERIVED_TRUST[operation],
        "privacy": "local",
        "status": "QUARANTINED",                 # never routable until reviewed
        "artifact_hash": derived_hash,
        "lineage": {
            "parent_model": parent["model_id"], "parent_hash": parent_hash,
            "tool_version": tool_version, "configuration": configuration,
            "timestamp": dt.datetime.now(dt.UTC).isoformat(), "derived_hash": derived_hash},
        "benchmark": benchmark,
        "behavior_profile": behavior_profile,
    }
