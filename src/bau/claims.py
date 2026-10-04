"""Marketing-claim screening (spec §24-25) and fake-review blocking.

Screening is a tripwire, not a lawyer: a hit means a claim needs evidence
in the claims registry before it can ship. Absence of hits proves nothing.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Phrases from spec §24 plus common FTC enforcement triggers (AI-washing,
# earnings claims, deceptive subject lines).
RISKY = {
    "absolute_guarantee": r"\bguarantee[ds]?\b|\b100\s*%\s*(accurate|secure|guaranteed|safe)\b",
    "risk_free": r"\brisk[- ]free\b|\bno risk\b",
    "never_fails": r"\bnever fails?\b|\bcan'?t lose\b",
    "fully_autonomous": r"\bfully autonomous\b",
    "fully_compliant": r"\bfully compliant\b|\blegally protected\b|\blawsuit[- ]proof\b",
    "completely_secure": r"\bcompletely secure\b|\bunhackable\b|\bbank[- ]level security\b",
    "human_level": r"\bhuman[- ]level\b|\bsentient\b",
    "regulator_approval": r"\bFDA[- ]approved\b|\bgovernment[- ]approved\b|\bSEC[- ]approved\b",
    "copyright_guarantee": r"\bcopyright guaranteed\b",
    "tax_guarantee": r"\btax[- ](free|guaranteed)\b",
    "earnings": r"\bmake \$?\d[\d,]*(k)?\b.*\b(day|week|month)\b|\bpassive income\b|\bget rich\b",
    "ai_washing": r"\bpowered by (advanced )?AI\b|\bAI[- ]powered\b",
    "false_urgency": r"\b(only|last) \d+ (left|spots?)\b"
                     r"|\bexpires? (today|tonight|in \d+ (minutes|hours))\b",
}
SUBJECT_DECEPTION = {
    "fake_reply": r"^\s*(re|fw|fwd)\s*:",
    "account_alarm": r"\b(account|payment) (suspended|locked|on hold|failed)\b",
    "fake_win": r"\byou('ve| have)? won\b|\bwinner\b|\bclaim your (prize|reward)\b",
    "fake_personal": r"\b(as we discussed|per our (call|conversation))\b",
}


def scan(text: str, patterns: dict[str, str] | None = None) -> list[dict[str, str]]:
    hits = []
    for name, rx in (patterns or RISKY).items():
        m = re.search(rx, text or "", re.IGNORECASE)
        if m:
            hits.append({"claim_type": name, "match": m.group(0)})
    return hits


@dataclass
class ClaimRecord:
    claim: str
    claim_type: str
    evidence: str
    test: str
    date: str
    scope: str
    limitations: str
    reviewer: str
    expiration: str

    def status(self, on: dt.date) -> str:
        return "STALE" if dt.date.fromisoformat(self.expiration) < on else "SUBSTANTIATED"


class ClaimsRegistry:
    """AI_CAPABILITY_CLAIMS_REGISTRY (spec §25)."""

    def __init__(self, path: Path):
        self.path = path
        raw: list[dict[str, Any]] = []
        if path.exists():
            raw = yaml.safe_load(path.read_text()) or []
        self.records = [ClaimRecord(**r) for r in raw]

    def substantiated(self, claim_type: str, on: dt.date) -> bool:
        return any(r.claim_type == claim_type and r.status(on) == "SUBSTANTIATED"
                   for r in self.records)


def unsubstantiated(text: str, registry: ClaimsRegistry | None, on: dt.date) -> list[dict]:
    hits = scan(text)
    if registry is None:
        return hits
    return [h for h in hits if not registry.substantiated(h["claim_type"], on)]
