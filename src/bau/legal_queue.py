"""Legal review queue (spec §120): questions only a qualified human may answer.

Items are opened automatically (new high-risk law, conflicts, digital replicas,
minors, health, finance, employment, tax ambiguity...) and closed only by a
human at a terminal. The machine never answers its own legal question.
"""

from __future__ import annotations

import datetime as dt
import secrets
import sys
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .home import bau_home
from .store import JsonlStore

TRIGGERS = {"new_high_risk_law", "unclear_applicability", "conflicting_jurisdictions",
            "high_financial_exposure", "high_privacy_exposure", "ip_dispute",
            "significant_contract", "regulated_industry", "high_impact_ai", "digital_replica",
            "children", "health", "finance", "employment", "government", "tax_ambiguity",
            "regulation_change", "other"}


class LegalQueue:
    def __init__(self, home: Path | None = None, audit: AuditLog | None = None):
        self.store = JsonlStore((home or bau_home()) / "compliance" / "legal_queue.jsonl")
        self.audit = audit or AuditLog()

    def open(self, trigger: str, subject: str, detail: str, refs: list[str] | None = None,
             blocking: bool = True) -> dict[str, Any]:
        if trigger not in TRIGGERS:
            raise ValueError(f"trigger must be one of {sorted(TRIGGERS)}")
        for item in self.items():                      # one open item per subject+trigger
            if item["status"] == "OPEN" and item["subject"] == subject \
                    and item["trigger"] == trigger:
                return item
        rec = {"id": "lq_" + secrets.token_hex(5), "trigger": trigger, "subject": subject,
               "detail": detail[:2000], "refs": refs or [], "blocking": blocking,
               "status": "OPEN", "opened_at": dt.datetime.now(dt.UTC).isoformat(),
               "resolution": None, "resolved_by": None}
        self.store.append(rec)
        self.audit.append("legal_queue.opened", "system", {"id": rec["id"], "trigger": trigger,
                                                           "subject": subject[:200]})
        return rec

    def items(self) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for r in self.store:
            latest[r["id"]] = r
        return list(latest.values())

    def open_items(self, subject: str | None = None) -> list[dict[str, Any]]:
        return [i for i in self.items() if i["status"] == "OPEN"
                and (subject is None or i["subject"] == subject)]

    def resolve(self, item_id: str, resolution: str, reviewer: str,
                require_tty: bool = True) -> dict[str, Any]:
        if require_tty and not sys.stdin.isatty():
            raise PermissionError("legal review items are resolved by a human at a terminal")
        if reviewer.startswith(("agent:", "model:")):
            raise PermissionError("an agent cannot resolve a legal question")
        item = next((i for i in self.items() if i["id"] == item_id), None)
        if item is None:
            raise KeyError(item_id)
        item = dict(item, status="RESOLVED", resolution=resolution[:4000],
                    resolved_by=reviewer, resolved_at=dt.datetime.now(dt.UTC).isoformat())
        self.store.append(item)
        self.audit.append("legal_queue.resolved", f"human:{reviewer}", {"id": item_id})
        return item
