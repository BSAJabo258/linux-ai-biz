"""Opportunity Miner (spec §61): rank opportunities on evidence, not enthusiasm.

Each opportunity is scored on value, competition, capability fit, startup cost,
time to revenue, risk and automation potential. No evidence -> it cannot score
above PAUSE. Regulated areas route to the legal review queue before anything else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

REGULATED = re.compile(r"\b(health|medical|supplement|drug|pharma|loan|lending|credit|"
                       r"insurance|invest(ment|ing)?|crypto|securit(y|ies) trading|gambling|"
                       r"betting|cannabis|firearm|weapon|child(ren)?|kids|minor|employment|"
                       r"hiring|housing|tenant|legal advice|tax prep(aration)?|dating)\b",
                       re.IGNORECASE)


@dataclass
class Opportunity:
    name: str
    description: str
    evidence: list[str] = field(default_factory=list)   # URLs / data references
    value: int = 0               # 0-5 expected revenue potential
    competition: int = 3         # 0 none ... 5 saturated
    capability_fit: int = 0      # 0-5 how well existing factories/capabilities cover it
    startup_cost_usd: float = 0.0
    months_to_revenue: float = 6.0
    risk: int = 3                # 0-5 legal/reputational/operational
    automation_potential: int = 0  # 0-5
    current_status: str = "new"  # new | running
    actual_margin: float | None = None  # for running opportunities


def assess(o: Opportunity) -> dict[str, Any]:
    regulated = bool(REGULATED.search(f"{o.name} {o.description}"))
    cost_pen = 0 if o.startup_cost_usd <= 100 else 1 if o.startup_cost_usd <= 1000 else \
        2 if o.startup_cost_usd <= 5000 else 3
    time_pen = 0 if o.months_to_revenue <= 1 else 1 if o.months_to_revenue <= 3 else 2
    score = (2.0 * o.value + 1.5 * o.capability_fit + 1.0 * o.automation_potential
             - 1.0 * o.competition - 1.5 * o.risk - 1.0 * cost_pen - 1.0 * time_pen)
    evidence_ok = len(o.evidence) >= 2
    if o.current_status == "running" and o.actual_margin is not None and o.actual_margin < 0:
        action = "KILL" if score < 3 else "IMPROVE"
    elif not evidence_ok:
        action = "PAUSE"
    elif score >= 10 and o.automation_potential >= 4:
        action = "AUTOMATE"
    elif score >= 6:
        action = "CONTINUE"
    elif score >= 2:
        action = "IMPROVE"
    elif score >= -2:
        action = "PAUSE"
    else:
        action = "KILL"
    reasons = []
    if not evidence_ok:
        reasons.append("fewer than two pieces of evidence - cannot recommend investment")
    if regulated:
        reasons.append("regulated area: legal review required before any work (spec §120)")
    if o.risk >= 4:
        reasons.append("high risk")
    return {"name": o.name, "score": round(score, 2), "recommended_action": action,
            "regulated": regulated, "legal_review_required": regulated,
            "evidence_count": len(o.evidence), "reasons": reasons}


def rank(opps: list[Opportunity]) -> list[dict[str, Any]]:
    return sorted((assess(o) for o in opps), key=lambda r: r["score"], reverse=True)
