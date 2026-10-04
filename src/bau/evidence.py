"""Evidence packages (spec §96): one file per significant decision, linked from the audit chain."""

from __future__ import annotations

import datetime as dt
import json
import secrets
from pathlib import Path
from typing import Any

from .audit import AuditLog, canonical, sha256
from .home import atomic_write_json, bau_home


def write_package(kind: str, body: dict[str, Any], actor: str, audit: AuditLog | None = None,
                  home: Path | None = None, policy_version: str | None = None) -> Path:
    pkg_id = f"ev_{dt.date.today():%Y%m%d}_{secrets.token_hex(5)}"
    doc = {"evidence_id": pkg_id, "kind": kind,
           "created_at": dt.datetime.now(dt.UTC).isoformat(), "actor": actor,
           "policy_version": policy_version, "body": body}
    path = (home or bau_home()) / "evidence" / f"{pkg_id}.json"
    atomic_write_json(path, doc)
    digest = sha256(canonical(json.loads(path.read_text())))
    (audit or AuditLog()).append(f"evidence.{kind}", actor, {"evidence_id": pkg_id},
                                 policy_version=policy_version, artifact_hash=digest)
    return path
