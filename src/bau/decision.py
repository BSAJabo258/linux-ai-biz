"""Gate states and how findings combine into one decision.

Spec §12 and §75 are unified here into a single state set. The rule that
matters most: UNKNOWN is never COMPLIANT. Only PASS proceeds on its own;
PASS_WITH_REVIEW proceeds only with a verified human approval.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    PASS = "PASS"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PASS_WITH_REVIEW = "PASS_WITH_REVIEW"
    INCOMPLETE_FACTS = "INCOMPLETE_FACTS"
    UNKNOWN = "UNKNOWN"
    EXPIRED = "EXPIRED"
    CONFLICT = "CONFLICT"
    BLOCKED = "BLOCKED"


# Higher number wins when combining findings.
SEVERITY: dict[Status, int] = {
    Status.NOT_APPLICABLE: 0,
    Status.PASS: 1,
    Status.PASS_WITH_REVIEW: 2,
    Status.INCOMPLETE_FACTS: 3,
    Status.UNKNOWN: 4,
    Status.EXPIRED: 5,
    Status.CONFLICT: 6,
    Status.BLOCKED: 7,
}

# What the operator is told to do for each non-passing state (spec §12).
ACTION: dict[Status, str] = {
    Status.PASS: "proceed",
    Status.NOT_APPLICABLE: "proceed",
    Status.PASS_WITH_REVIEW: "obtain human approval",
    Status.INCOMPLETE_FACTS: "request missing information",
    Status.UNKNOWN: "escalate",
    Status.EXPIRED: "re-verify the rule or evidence",
    Status.CONFLICT: "human legal review",
    Status.BLOCKED: "do not proceed",
}


def worst(statuses: list[Status]) -> Status:
    if not statuses:
        # Nothing evaluated is not evidence of compliance.
        return Status.UNKNOWN
    return max(statuses, key=lambda s: SEVERITY[s])


@dataclass
class Finding:
    rule_id: str
    status: Status
    message: str
    stage: int = 0
    regs: list[str] = field(default_factory=list)
    remediation: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class Decision:
    scope: str
    findings: list[Finding]
    # Settings resolved across jurisdictions (strictest wins), e.g. consent_model.
    resolved: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> Status:
        relevant = [f.status for f in self.findings if f.status != Status.NOT_APPLICABLE]
        if not relevant and self.findings:
            return Status.PASS
        return worst(relevant)

    def may_proceed(self, approved: bool = False) -> bool:
        s = self.status
        return s == Status.PASS or (s == Status.PASS_WITH_REVIEW and approved)

    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if SEVERITY[f.status] >= SEVERITY[Status.INCOMPLETE_FACTS]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "status": self.status.value,
            "action": ACTION[self.status],
            "resolved": self.resolved,
            "findings": [f.to_dict() for f in sorted(self.findings, key=lambda f: f.stage)],
        }
