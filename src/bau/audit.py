"""Tamper-evident audit chain (spec §1.5, §97).

Each record carries the previous record's hash; editing or deleting any
record breaks every hash after it. With a key (``/etc/bau/audit.key``)
each record is also HMAC-signed, so the chain cannot be silently rebuilt
by anyone without the key. ``anchor`` exports the head hash so it can be
written somewhere the machine cannot rewrite (paper, offline USB).

Personal data never enters the chain (spec §20 vs §35 conflict): fields
that look like personal identifiers are refused. Log pseudonymous
references (``ref()``) instead, so a deletion request can be honoured
without breaking the evidence chain.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from .home import bau_home

GENESIS = "0" * 64
PII_KEYS = {"email", "phone", "name", "address", "ssn", "dob", "ip", "ip_address",
            "full_name", "first_name", "last_name", "card", "card_number", "password",
            "secret", "token", "api_key"}


class AuditError(RuntimeError):
    pass


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ref(value: str, salt: str = "bau") -> str:
    """Stable pseudonymous reference for a personal identifier."""
    return "ref:" + sha256(f"{salt}:{value.strip().lower()}".encode())[:32]


def _check_pii(obj: Any, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in PII_KEYS and not (isinstance(v, str) and v.startswith("ref:")):
                raise AuditError(f"refusing to write personal/secret field {path}{k!r} to the "
                                 "audit chain; log audit.ref(value) instead")
            _check_pii(v, f"{path}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _check_pii(v, f"{path}{i}.")


def _load_key() -> bytes | None:
    p = Path(os.environ.get("BAU_AUDIT_KEY", "/etc/bau/audit.key"))
    try:
        return p.read_bytes().strip() or None
    except OSError:
        return None


class AuditLog:
    def __init__(self, path: Path | None = None, key: bytes | None = None):
        self.path = path or (bau_home() / "audit" / "chain.jsonl")
        self.key = key if key is not None else _load_key()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _sig(self, digest: str) -> str | None:
        if not self.key:
            return None
        return hmac.new(self.key, digest.encode(), hashlib.sha256).hexdigest()

    def _last(self) -> tuple[int, str]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return -1, GENESIS
        with self.path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            pos = fh.tell() - 1
            while pos > 0:
                fh.seek(pos - 1)
                if fh.read(1) == b"\n":
                    break
                pos -= 1
            fh.seek(max(pos, 0))
            last = json.loads(fh.readline())
        return last["seq"], last["hash"]

    def append(self, event: str, actor: str, data: dict[str, Any] | None = None,
               policy_version: str | None = None, artifact_hash: str | None = None
               ) -> dict[str, Any]:
        data = data or {}
        _check_pii(data)
        with self.path.open("a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                seq, prev = self._last()
                body = {
                    "seq": seq + 1,
                    "ts": dt.datetime.now(dt.UTC).isoformat(),
                    "event": event,
                    "actor": actor,
                    "data": data,
                    "policy_version": policy_version,
                    "artifact_hash": artifact_hash,
                    "prev_hash": prev,
                }
                body["hash"] = sha256(canonical(body))
                body["sig"] = self._sig(body["hash"])
                fh.write(json.dumps(body, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
        return body

    def records(self):
        if not self.path.exists():
            return
        with self.path.open() as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)

    def verify(self) -> tuple[bool, str]:
        prev, expect_seq, n = GENESIS, 0, 0
        for rec in self.records():
            n += 1
            body = {k: v for k, v in rec.items() if k not in ("hash", "sig")}
            if rec["seq"] != expect_seq:
                return False, f"sequence gap at record {n}: expected {expect_seq}"
            if rec["prev_hash"] != prev:
                return False, f"chain broken at seq {rec['seq']}: prev_hash mismatch"
            if sha256(canonical(body)) != rec["hash"]:
                return False, f"record seq {rec['seq']} was modified"
            if self.key:
                if rec.get("sig") is None:
                    return False, f"seq {rec['seq']} is unsigned but a key is configured"
                if not hmac.compare_digest(rec["sig"], self._sig(rec["hash"]) or ""):
                    return False, f"seq {rec['seq']} signature invalid"
            prev, expect_seq = rec["hash"], expect_seq + 1
        return True, f"{n} records verified; head {prev}"

    def anchor(self) -> dict[str, Any]:
        seq, head = self._last()
        return {"seq": seq, "head": head,
                "at": dt.datetime.now(dt.UTC).isoformat(), "path": str(self.path)}
