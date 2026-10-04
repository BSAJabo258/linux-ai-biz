"""Backup gate (spec §4.1, §104-105).

A backup is not valid because it exists. ``verify`` reads every file back
from the backup medium and checks its hash: that read-back is the restore
test. Only a fully verified backup marks BAU-BACKUP-BASELINE as VERIFIED,
and the wipe gate refuses to proceed without it.

The manifest stores hashes and paths, never file contents, so it is safe
to keep with the documentation archive. Files that typically hold secrets
are flagged so the operator confirms the backup medium is encrypted.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

SKIP = {"__pycache__", "node_modules", ".cache", ".venv", "venv", ".Trash", "Cache",
        "CacheStorage", ".npm", ".cargo/registry"}
SENSITIVE = (".ssh", ".gnupg", ".env", ".netrc", ".aws", ".kube", "id_rsa", "id_ed25519",
             ".pem", ".key", "wallet", ".password-store", "keyring")


def _hash(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest(sources: list[Path], out: Path) -> dict[str, Any]:
    entries, sensitive, errors = [], [], []
    for src in sources:
        src = src.resolve()
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for f in files:
                p = Path(root) / f
                if p.is_symlink():
                    continue
                rel = str(Path(src.name) / p.relative_to(src))
                try:
                    entries.append({"path": rel, "size": p.stat().st_size, "sha256": _hash(p)})
                except OSError as e:
                    errors.append({"path": rel, "error": e.strerror})
                if any(s in rel for s in SENSITIVE):
                    sensitive.append(rel)
    doc = {"created_at": dt.datetime.now(dt.UTC).isoformat(),
           "sources": [str(s) for s in sources], "files": len(entries),
           "bytes": sum(e["size"] for e in entries), "entries": entries,
           "sensitive_paths": sensitive, "unreadable": errors}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    return doc


def verify(manifest_path: Path, backup_root: Path, baseline_out: Path,
           encrypted_confirmed: bool) -> dict[str, Any]:
    doc = json.loads(manifest_path.read_text())
    missing, mismatched, ok = [], [], 0
    for e in doc["entries"]:
        p = backup_root / e["path"]
        if not p.is_file():
            missing.append(e["path"])
        elif _hash(p) != e["sha256"]:
            mismatched.append(e["path"])
        else:
            ok += 1
    problems = []
    if missing:
        problems.append(f"{len(missing)} files missing from backup")
    if mismatched:
        problems.append(f"{len(mismatched)} files differ from source")
    if doc.get("unreadable"):
        problems.append(f"{len(doc['unreadable'])} source files could not be read")
    if doc["sensitive_paths"] and not encrypted_confirmed:
        problems.append("backup contains secret-bearing files but encryption not confirmed")
    status = "VERIFIED" if not problems else "FAILED"
    result = {"captured_at": dt.datetime.now(dt.UTC).isoformat(), "status": status,
              "manifest": str(manifest_path), "backup_root": str(backup_root),
              "files_verified": ok, "files_expected": doc["files"],
              "missing": missing[:100], "mismatched": mismatched[:100], "problems": problems,
              "encrypted_confirmed": encrypted_confirmed}
    baseline_out.parent.mkdir(parents=True, exist_ok=True)
    baseline_out.write_text(json.dumps(result, indent=2))
    return result
