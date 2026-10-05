"""BAU Executive / Jarvis (spec §7, §8, §113, §122, §125).

Jarvis turns an objective into a mission and walks the 22 steps of spec §7.
It coordinates; it does not hold authority. Every external effect goes through
the Universal Gateway, every gate through the policy engine, and every decision
a human must make lands in the approval list or the legal review queue.

Mission lifecycle: PLANNED -> (BLOCKED | NEEDS_REVIEW | READY) -> RUNNING ->
(COMPLETED | PAUSED | FAILED). Nothing runs from BLOCKED or NEEDS_REVIEW.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import blast
from .audit import AuditLog
from .decision import Status
from .evidence import write_package
from .home import bau_home, shipped_data
from .legal_queue import LegalQueue
from .memory import MemoryLane
from .policy import PolicyEngine
from .store import JsonlStore

STEPS = ["understand", "context", "jurisdiction", "laws", "risk", "data", "ip", "blast_radius",
         "plan", "agents", "models", "tools", "permissions", "approvals", "execute", "verify",
         "evidence", "economics", "memory", "checkpoint", "recover", "next_action"]


def mission_types(home: Path | None = None) -> dict[str, Any]:
    local = (home or bau_home()) / "config" / "missions.yaml"
    src = local if local.exists() else shipped_data() / "missions.yaml"
    return yaml.safe_load(src.read_text())


@dataclass
class Mission:
    mission_id: str
    objective: str
    mission_type: str
    status: str = "PLANNED"
    created_at: str = ""
    jurisdictions: list[str] = field(default_factory=list)
    steps: dict[str, Any] = field(default_factory=dict)
    gates: dict[str, Any] = field(default_factory=dict)
    approvals_needed: list[str] = field(default_factory=list)
    legal_items: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    next_action: str = ""


class Jarvis:
    def __init__(self, engine: PolicyEngine, home: Path | None = None,
                 memory: MemoryLane | None = None, legal: LegalQueue | None = None,
                 audit: AuditLog | None = None):
        self.home = home or bau_home()
        self.engine = engine
        self.memory = memory or MemoryLane(self.home)
        self.audit = audit or AuditLog(self.home / "audit" / "chain.jsonl")
        self.legal = legal or LegalQueue(self.home, self.audit)
        self.types = mission_types(self.home)
        self.store = JsonlStore(self.home / "jobs" / "missions.jsonl")

    # ------------------------------------------------------------ persistence
    def save(self, m: Mission) -> None:
        self.store.append(asdict(m))

    def get(self, mission_id: str) -> Mission | None:
        found = None
        for r in self.store:
            if r["mission_id"] == mission_id:
                found = r
        return Mission(**found) if found else None

    def list(self) -> list[Mission]:
        latest: dict[str, dict[str, Any]] = {}
        for r in self.store:
            latest[r["mission_id"]] = r
        return [Mission(**r) for r in latest.values()]

    # ------------------------------------------------------------ planning (steps 1-14)
    def plan(self, objective: str, mission_type: str, facts: dict[str, dict[str, Any]],
             blast_factors: blast.Factors | None = None, on: dt.date | None = None
             ) -> Mission:
        """``facts`` maps gate domain -> facts dict (the same facts the domain gates use)."""
        if mission_type not in self.types:
            raise ValueError(f"unknown mission type {mission_type}; "
                             f"known: {sorted(self.types)}")
        mt = self.types[mission_type]
        m = Mission(mission_id="msn_" + secrets.token_hex(5), objective=objective,
                    mission_type=mission_type,
                    created_at=dt.datetime.now(dt.UTC).isoformat())
        m.steps["understand"] = {"type": mission_type, "description": mt["description"]}
        hits = self.memory.search(objective, k=5, include_status={"CURRENT", "PLANNED"})
        m.steps["context"] = [{"id": r.id, "title": r.title, "status": r.status}
                              for _, r in hits]
        from .brain import Brain
        m.steps["brain"] = Brain(self.home).context(objective, hops=1, max_nodes=12)["nodes"]
        juris: list[str] = []
        for f in facts.values():
            for j in f.get("jurisdictions") or []:
                if j not in juris:
                    juris.append(j)
        m.jurisdictions = juris
        m.steps["jurisdiction"] = juris or "UNDETERMINED"
        m.steps["data"] = mt.get("data_classes", [])
        # Steps 4 + 7 + compliance dependencies (spec §113)
        statuses = []
        for domain in mt.get("requires", []):
            if domain not in facts:
                m.gates[domain] = {"status": Status.INCOMPLETE_FACTS.value,
                                   "action": f"supply facts for the {domain} gate"}
                statuses.append(Status.INCOMPLETE_FACTS)
                continue
            d = self.engine.evaluate(domain, facts[domain], on=on)
            m.gates[domain] = d.to_dict()
            statuses.append(d.status)
        m.steps["laws"] = {d: g["status"] for d, g in m.gates.items()}
        b = blast.score(blast_factors or blast.Factors())
        m.steps["blast_radius"] = b["level"]
        risk = "HIGH" if mt.get("high_impact") or b["level"] in ("HIGH", "CRITICAL") else (
            "MEDIUM" if b["level"] == "MEDIUM" else "LOW")
        m.steps["risk"] = risk
        if mt.get("legal_review"):
            item = self.legal.open(mt["legal_review"], f"mission:{mission_type}", objective)
            m.legal_items.append(item["id"])
        m.steps["plan"] = [f"capability {c}" for c in mt.get("capabilities", [])]
        m.steps["tools"] = mt.get("capabilities", [])
        if mt.get("high_impact"):
            m.approvals_needed.append("high-impact action: human review required (spec §33)")
        if b["requires_approval"]:
            m.approvals_needed.append(f"blast radius {b['level']}: human approval required")
        for domain, g in m.gates.items():
            if g["status"] == Status.PASS_WITH_REVIEW.value:
                m.approvals_needed.append(f"{domain} gate passed with review")
        worst = max((s for s in statuses), default=Status.PASS,
                    key=lambda s: ["NOT_APPLICABLE", "PASS", "PASS_WITH_REVIEW",
                                   "INCOMPLETE_FACTS", "UNKNOWN", "EXPIRED", "CONFLICT",
                                   "BLOCKED"].index(str(s)))
        if worst not in (Status.PASS, Status.PASS_WITH_REVIEW, Status.NOT_APPLICABLE):
            m.status = "BLOCKED"
            m.next_action = f"resolve {worst} gate findings before anything runs"
        elif m.legal_items or m.approvals_needed:
            m.status = "NEEDS_REVIEW"
            m.next_action = "obtain the listed approvals / legal review, then run"
        else:
            m.status = "READY"
            m.next_action = "run"
        m.steps["approvals"] = m.approvals_needed
        self.save(m)
        self.audit.append("mission.planned", "jarvis", {
            "mission_id": m.mission_id, "type": mission_type, "status": m.status,
            "gates": m.steps["laws"], "blast": b["level"]})
        return m

    # ------------------------------------------------------------ execution (steps 15-22)
    def mark_approved(self, m: Mission, approval_ref: str) -> Mission:
        """Called after a human-signed approval was verified for this mission."""
        open_legal = [i for i in m.legal_items
                      if any(x["id"] == i for x in self.legal.open_items())]
        if open_legal:
            raise PermissionError(f"legal review still open: {open_legal}")
        if m.status != "NEEDS_REVIEW":
            raise ValueError(f"mission is {m.status}, not NEEDS_REVIEW")
        m.status = "READY"
        m.steps["approvals"] = {"needed": m.approvals_needed, "approval_ref": approval_ref}
        self.save(m)
        self.audit.append("mission.approved", "jarvis", {"mission_id": m.mission_id,
                                                         "approval_ref": approval_ref})
        return m

    def run(self, m: Mission, executor: Any) -> Mission:
        """``executor(mission) -> dict`` does the work (an agent run, a factory run, ...)."""
        if m.status != "READY":
            raise PermissionError(f"mission {m.mission_id} is {m.status}; only READY runs")
        from .governor import hold_reason
        held = hold_reason(self.home)
        if held:
            raise PermissionError(f"BAU is on HOLD ({held}); a human must release it")
        m.status = "RUNNING"
        self.save(m)
        try:
            result = executor(m) or {}
        except Exception as e:
            m.status = "FAILED"
            m.next_action = f"investigate failure: {type(e).__name__}"
            self.save(m)
            self.audit.append("mission.failed", "jarvis", {"mission_id": m.mission_id,
                                                           "error": type(e).__name__})
            raise
        m.steps["execute"] = {k: v for k, v in result.items() if k != "artifacts"}
        verified = bool(result.get("verified", result.get("status") == "COMPLETED"))
        m.steps["verify"] = verified
        m.cost_usd = float(result.get("cost_usd", 0.0))
        m.steps["economics"] = {"cost_usd": m.cost_usd}
        ev = write_package("mission", {"mission": asdict(m), "result": result}, "jarvis",
                           self.audit, self.home)
        m.evidence.append(str(ev))
        m.status = "COMPLETED" if verified else "PAUSED"
        m.next_action = "learning loop (spec §110)" if verified else \
            "verification failed - human review"
        self.memory.add("mission", f"mission {m.mission_type}: {m.objective[:80]}",
                        json.dumps({"status": m.status, "gates": m.steps.get("laws"),
                                    "cost_usd": m.cost_usd})[:4000], tags=[m.mission_type],
                        source=m.mission_id)
        m.steps["memory"] = "recorded"
        m.steps["checkpoint"] = "saved"
        self.save(m)
        return m

    def retrospective(self, m: Mission, answers: dict[str, str]) -> dict[str, Any]:
        """Learning loop (spec §110). Only human-verified lessons are stored as CURRENT."""
        questions = ["worked", "failed", "cost_too_much", "automate", "remove",
                     "regulation_applied", "missed", "security_event", "customer_feedback",
                     "profit"]
        rec = {q: answers.get(q, "") for q in questions}
        verified = answers.get("verified_by_human") == "yes"
        self.memory.add("lesson", f"retrospective {m.mission_id}", json.dumps(rec),
                        tags=[m.mission_type, "retrospective"],
                        status="CURRENT" if verified else "UNKNOWN", source=m.mission_id)
        return rec
