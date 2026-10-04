"""Incident management (spec §35): DETECT -> CONTAIN -> CLASSIFY -> PRESERVE EVIDENCE ->
NOTIFY -> REMEDIATE -> VERIFY -> DOCUMENT -> LEARN.

Stages cannot be skipped. Preserving evidence anchors the audit chain head so
later tampering is detectable; evidence is never deleted. Notification clocks
come from the regulation registry facts recorded on the incident (e.g. GDPR's
72 hours to the authority for a personal-data breach affecting the EU).
"""

from __future__ import annotations

import datetime as dt
import secrets
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .home import bau_home
from .store import YamlStore

CLASSES = {"SECURITY", "PRIVACY", "AI_SAFETY", "AI_MISUSE", "DATA_LOSS", "IP", "COPYRIGHT",
           "LICENSING", "CONSUMER", "FINANCIAL", "TAX", "REGULATORY", "ACCESSIBILITY",
           "MODEL_FAILURE", "CONTENT", "REPUTATIONAL"}
STAGES = ["DETECT", "CONTAIN", "CLASSIFY", "PRESERVE_EVIDENCE", "NOTIFY", "REMEDIATE",
          "VERIFY", "DOCUMENT", "LEARN"]
SEVERITIES = ["low", "medium", "high", "critical"]


def notification_clocks(personal_data: bool, jurisdictions: list[str],
                        detected: dt.datetime) -> list[dict[str, Any]]:
    clocks = []
    if personal_data and any(j == "EU" or j in ("GB",) for j in jurisdictions):
        clocks.append({"to": "supervisory authority (GDPR/UK GDPR Art. 33)",
                       "deadline": (detected + dt.timedelta(hours=72)).isoformat(),
                       "reg": "eu-gdpr"})
    if personal_data and any(j.startswith("US") for j in jurisdictions):
        clocks.append({"to": "affected US residents / state AGs",
                       "deadline": "without unreasonable delay - per-state statute; "
                                   "several states set 30-60 days",
                       "reg": "us-breach-notification"})
    return clocks


class Incidents:
    def __init__(self, home: Path | None = None, audit: AuditLog | None = None):
        self.home = home or bau_home()
        self.store = YamlStore(self.home / "security" / "incidents.yaml", [])
        self.audit = audit or AuditLog(self.home / "audit" / "chain.jsonl")

    def _all(self) -> list[dict[str, Any]]:
        return self.store.load() or []

    def open(self, title: str, cls: str, severity: str, personal_data: bool = False,
             jurisdictions: list[str] | None = None) -> dict[str, Any]:
        if cls not in CLASSES:
            raise ValueError(f"class must be one of {sorted(CLASSES)}")
        if severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}")
        now = dt.datetime.now(dt.UTC)
        inc = {"id": "inc_" + secrets.token_hex(4), "title": title, "class": cls,
               "severity": severity, "status": "open", "stage": "DETECT",
               "detected_at": now.isoformat(), "personal_data": personal_data,
               "jurisdictions": jurisdictions or [],
               "clocks": notification_clocks(personal_data, jurisdictions or [], now),
               "history": [{"stage": "DETECT", "at": now.isoformat(), "note": title}],
               "evidence_anchor": None}
        items = self._all()
        items.append(inc)
        self.store.save(items)
        self.audit.append("incident.opened", "system", {"id": inc["id"], "class": cls,
                                                        "severity": severity})
        return inc

    def advance(self, inc_id: str, note: str, by: str) -> dict[str, Any]:
        items = self._all()
        inc = next((i for i in items if i["id"] == inc_id), None)
        if inc is None:
            raise KeyError(inc_id)
        idx = STAGES.index(inc["stage"])
        if idx + 1 >= len(STAGES):
            raise ValueError("incident already at LEARN")
        nxt = STAGES[idx + 1]
        if nxt == "PRESERVE_EVIDENCE":
            inc["evidence_anchor"] = self.audit.anchor()
        if nxt == "LEARN":
            inc["status"] = "closed"
        inc["stage"] = nxt
        inc["history"].append({"stage": nxt, "at": dt.datetime.now(dt.UTC).isoformat(),
                               "note": note[:2000], "by": by})
        self.store.save(items)
        self.audit.append("incident.advanced", by, {"id": inc_id, "stage": nxt})
        return inc

    def open_items(self) -> list[dict[str, Any]]:
        return [i for i in self._all() if i["status"] != "closed"]
