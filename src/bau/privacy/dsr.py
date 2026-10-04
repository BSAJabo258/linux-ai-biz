"""Data-subject rights requests with real deletion propagation (spec §19-20).

Deadlines are the *outer* statutory limits. BAU's target is faster.
Every registered data store must report an outcome for a deletion: done,
retained-with-legal-basis, or not-applicable. A request cannot be closed
while any store is silent - that is how "deleted from the UI only" happens.
"""

from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..audit import AuditLog, ref
from ..home import atomic_write_json, bau_home

# (initial_days, extension_days, reg_id). Most-specific jurisdiction wins.
DEADLINES: dict[str, tuple[int, int, str]] = {
    "US-CA": (45, 45, "us-ca-ccpa-cpra"),
    "US": (45, 45, "us-state-privacy-generic"),   # most comprehensive state laws: 45 + 45
    "EU": (30, 60, "eu-gdpr"),                    # "one month", extendable by two
    "GB": (30, 60, "uk-gdpr-dpa"),
    "CA": (30, 30, "ca-pipeda"),
}

# Every place personal data can live (spec §20). Each needs an outcome.
DEFAULT_STORES = ["primary_database", "backups", "search_index", "vector_database",
                  "agent_memory", "cache", "logs", "analytics", "exports", "object_storage",
                  "model_context", "customer_workspaces", "third_party_processors",
                  "consent_ledger", "suppression_list"]

OUTCOMES = {"deleted", "retained_legal_basis", "not_present", "suppression_hash_kept",
            "expires_by_retention"}


def deadline_for(jurisdictions: list[str]) -> tuple[int, int, str]:
    best = None
    for j in jurisdictions:
        for key in (j, j.split("-")[0]):
            if key in DEADLINES:
                cand = DEADLINES[key]
                if best is None or cand[0] < best[0]:
                    best = cand
    return best or (30, 0, "bau-default-strict")


@dataclass
class DSRequest:
    request_id: str
    subject_ref: str
    jurisdictions: list[str]
    rights_invoked: list[str]
    received_at: str
    deadline: str
    identity_verified: bool = False
    stores: dict[str, dict[str, str]] = field(default_factory=dict)
    exceptions: list[str] = field(default_factory=list)
    completed_at: str | None = None

    def open_stores(self) -> list[str]:
        return [s for s in DEFAULT_STORES if s not in self.stores]


class DSRManager:
    def __init__(self, home: Path | None = None, audit: AuditLog | None = None):
        self.dir = (home or bau_home()) / "dsr"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.audit = audit or AuditLog()

    def _path(self, rid: str) -> Path:
        return self.dir / f"{rid}.json"

    def open(self, subject: str, jurisdictions: list[str], rights: list[str],
             received: dt.datetime | None = None) -> DSRequest:
        received = received or dt.datetime.now(dt.UTC)
        days, _, reg = deadline_for(jurisdictions)
        req = DSRequest(request_id="dsr_" + secrets.token_hex(6), subject_ref=ref(subject),
                        jurisdictions=jurisdictions, rights_invoked=rights,
                        received_at=received.isoformat(),
                        deadline=(received + dt.timedelta(days=days)).date().isoformat())
        self.save(req)
        self.audit.append("dsr.opened", "dsr", {"request_id": req.request_id,
                                                "subject": req.subject_ref, "rights": rights,
                                                "deadline": req.deadline, "reg": reg})
        return req

    def save(self, req: DSRequest) -> None:
        atomic_write_json(self._path(req.request_id), asdict(req))

    def load(self, rid: str) -> DSRequest:
        import json
        return DSRequest(**json.loads(self._path(rid).read_text()))

    def record_store(self, req: DSRequest, store: str, outcome: str, note: str = "") -> None:
        if outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {sorted(OUTCOMES)}")
        if outcome == "retained_legal_basis" and not note:
            raise ValueError("retention requires the documented legal basis (spec §20)")
        req.stores[store] = {"outcome": outcome, "note": note,
                             "at": dt.datetime.now(dt.UTC).isoformat()}
        self.save(req)

    def complete(self, req: DSRequest) -> DSRequest:
        if not req.identity_verified:
            raise ValueError("identity not verified")
        missing = req.open_stores()
        if missing:
            raise ValueError(f"stores without an outcome: {missing}")
        req.completed_at = dt.datetime.now(dt.UTC).isoformat()
        self.save(req)
        self.audit.append("dsr.completed", "dsr", {"request_id": req.request_id,
                                                   "stores": {k: v["outcome"] for k, v in
                                                              req.stores.items()}})
        return req

    def overdue(self, on: dt.date | None = None) -> list[DSRequest]:
        on = on or dt.date.today()
        out = []
        for p in self.dir.glob("dsr_*.json"):
            r = self.load(p.stem)
            if not r.completed_at and dt.date.fromisoformat(r.deadline) < on:
                out.append(r)
        return out


def as_dict(req: DSRequest) -> dict[str, Any]:
    return asdict(req)
