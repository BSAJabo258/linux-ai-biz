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
    # The portfolio (2026-11-11), set only by the owner (`bau mission set`): several missions
    # at once, each with its priority, its own budget (None: no cap of its own) and a measured
    # goal ({"metric": "profit_usd" | "revenue_usd", "at_least": USD, "by": date or None}).
    priority: int = 0
    budget_usd: float | None = None
    goal: dict[str, Any] = field(default_factory=dict)
    factory: str = ""


def _mission(row: dict[str, Any]) -> Mission:
    """A stored row as a Mission: older rows lack the newer fields (defaults), and a field a
    later version adds is skipped rather than breaking every read."""
    known = Mission.__dataclass_fields__
    return Mission(**{k: v for k, v in row.items() if k in known})


GOAL_METRICS = {"profit_usd", "revenue_usd"}
OVER = {"CANCELLED", "FAILED"}


def set_mission(j: Jarvis, mission_id: str, by: str, priority: int | None = None,
                budget_usd: float | None = None, goal: dict[str, Any] | None = None,
                factory: str | None = None) -> Mission:
    """The owner's choices for one mission (priority, budget, goal, factory): never a model's,
    never a default."""
    import math
    if not by.startswith("human:"):
        raise PermissionError("only the owner sets a mission's priority, budget and goal")
    m = j.get(mission_id)
    if m is None:
        raise KeyError(f"no mission {mission_id}")
    if budget_usd is not None:
        if not math.isfinite(budget_usd) or budget_usd < 0:
            raise ValueError("a budget is a number of dollars, 0 or more")
        m.budget_usd = round(float(budget_usd), 2)
    if goal is not None:
        at = goal.get("at_least")
        if goal.get("metric") not in GOAL_METRICS or not isinstance(at, (int, float)) \
                or isinstance(at, bool) or not math.isfinite(at) or at <= 0:
            raise ValueError(f"a goal is one of {sorted(GOAL_METRICS)} with at_least > 0")
        when = goal.get("by")
        if when is not None:
            dt.date.fromisoformat(str(when))
        m.goal = {"metric": goal["metric"], "at_least": float(at),
                  "by": str(when) if when else None}
    if priority is not None:
        m.priority = int(priority)
    if factory is not None:
        from .factories import definitions
        if factory and factory not in definitions(j.home):
            raise ValueError(f"unknown factory {factory}")
        m.factory = factory
    j.save(m)
    j.audit.append("mission.set", by, {"mission_id": mission_id, "priority": m.priority,
                                       "budget_usd": m.budget_usd, "goal": m.goal,
                                       "factory": m.factory})
    return m


def _latest(home: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for r in JsonlStore(home / "jobs" / "missions.jsonl"):
        latest[r["mission_id"]] = r
    return latest


def mission_budget(home: Path, mission_id: str) -> float | None:
    """The owner's budget for a mission, None when it has none (the gateway's mission cap)."""
    r = _latest(home).get(mission_id)
    return None if r is None else r.get("budget_usd")


def portfolio(home: Path, now: dt.datetime | None = None) -> dict[str, Any]:
    """Every mission at once, read from the one mission store, its jobs and the ledger: status,
    the owner's priority, budget left, its money (economics.pnl) and whether its goal is met.
    Work finished is not a goal met: only the ledger meets a goal. Active missions first, by
    priority. Nothing here moves money or changes a limit."""
    from .economics import Ledger, pnl
    from .jobs import JobStore
    now = now or dt.datetime.now(dt.UTC)
    led = Ledger(home)
    jobs: dict[str, list[dict[str, Any]]] = {}
    for jb in JobStore(home).all():
        jobs.setdefault(jb.mission_id, []).append(
            {"job_id": jb.job_id, "agent": jb.agent, "status": jb.status})
    rows, keys = [], ("kept_usd", "cost_usd", "profit_usd", "refunds_usd", "fees_usd")
    totals = dict.fromkeys(keys, 0.0)
    for r in _latest(home).values():
        m = _mission(r)
        money = pnl(led, m.mission_id)
        goal = None
        if m.goal:
            got = money["profit_usd" if m.goal["metric"] == "profit_usd" else "kept_usd"]
            goal = {**m.goal, "measured": got, "met": got >= m.goal["at_least"]}
            if not goal["met"] and m.goal.get("by") and \
                    now.date() > dt.date.fromisoformat(m.goal["by"]):
                goal["note"] = f"past its date ({m.goal['by']}) and not met"
        active = m.status not in OVER and (not goal["met"] if goal else
                                           m.status != "COMPLETED")
        rows.append({"mission_id": m.mission_id, "objective": m.objective[:160],
                     "type": m.mission_type, "factory": m.factory or None,
                     "status": m.status, "active": active, "priority": m.priority,
                     "budget_usd": m.budget_usd,
                     "budget_left_usd": None if m.budget_usd is None
                     else round(m.budget_usd - money["cost_usd"], 4),
                     "goal": goal, "money": money, "jobs": jobs.get(m.mission_id, []),
                     "next_action": m.next_action, "evidence": m.evidence[-1:]})
        for k in keys:
            totals[k] += money[k]
    rows.sort(key=lambda x: (not x["active"], -x["priority"], x["mission_id"]))
    # Everything else in the ledger: rows with no mission (Fanvue's sync today) and rows under
    # an id that is not a mission (a factory run's id). The totals are the whole ledger.
    mine = {x["mission_id"] for x in rows}
    other = {r.get("mission_id", "") for r in [*led.revenue, *led.costs]} - mine
    loose = dict.fromkeys(keys, 0.0)
    for oid in other:
        p = pnl(led, oid)
        for k in keys:
            loose[k] += p[k]
    loose = {k: round(v, 2) for k, v in loose.items()}
    loose["ids"] = sorted(other)
    for k in keys:
        totals[k] = round(totals[k] + loose[k], 2)
    return {"missions": rows, "active": sum(1 for x in rows if x["active"]),
            "unattributed": loose, "totals": totals,
            "one_store": str(home / "jobs" / "missions.jsonl")}


# Mission types an approved agent folder can carry out (the audit, 2026-11-10: missions were
# planned and never ran; `bau mission` had no run and nothing executed a plan).
AGENT_FOR = {"research": "researcher"}


def agent_executor(home: Path, audit: Any, jarvis: Any = None, factory: Any = None,
                   run_agent: Any = None) -> Any:
    """The executor for a mission an agent can do: the agent folder works the objective (every
    tool through the gateway). Verified only when it completed with an answer and every fact in
    that answer (links, quotes, amounts, numbers) appears in what its tools returned; anything
    else ends PAUSED for the owner's review, never COMPLETED on the agent's word."""
    from .supervisor import facts, unchecked

    def run_one(name: str, objective: str, mission_id: str, job: Any) -> Any:
        if run_agent is not None:
            return run_agent(name, objective, mission_id, job=job)
        from . import agentfolders as AF
        return AF.run(name, objective, home, audit, jarvis=jarvis, factory=factory,
                      mission_id=mission_id, job=job)

    def execute(m: Mission) -> dict[str, Any]:
        name = AGENT_FOR.get(m.mission_type)
        if name is None:
            raise PermissionError(f"no agent carries out {m.mission_type} missions yet")
        # Through the executive controller (Phase 1, docs/JARVIS_IMPLEMENTATION_MAP.md): one
        # job per mission run, kept in the jobs folder, honouring HOLD and the owner's cancel.
        from .adapters.agent_folder import AgentFolderAdapter
        from .executive import ExecutiveController, TaskContract
        from .governor import hold_reason
        from .jobs import JobStore
        store = JobStore(home)
        ctl = ExecutiveController(store, hold=lambda: hold_reason(home))
        ctl.register(AgentFolderAdapter(store, run_one))
        job_id = ctl.create_task(TaskContract(m.mission_id, m.objective, agent=name))
        out = ctl.dispatch(job_id, "agent_folder")
        res = out.evidence.get("run")
        if res is None:                 # the agent itself crashed: the job says why
            raise RuntimeError("; ".join(out.errors) or "the agent did not run")
        loose = unchecked(res.final_text, [m.objective, *res.evidence])
        # At least one fact the tools backed: on the real model (2026-11-10) an answer of only
        # questions back to the owner had nothing false in it, and counted as done.
        # Backed by what the TOOLS returned: on the real model a quoted mission title counted
        # as found, because the task's own words were in the pool (2026-11-10).
        def norm(t: str) -> str:
            return "".join(t.split()).rstrip(".,;:").lower()
        found, asked = norm(" ".join(res.evidence)), norm(m.objective)
        backed = [f for f in facts(res.final_text)
                  if norm(f) in found and norm(f) not in asked]
        answered = bool((res.final_text or "").strip())
        verified = res.status == "COMPLETED" and answered and bool(backed) and not loose
        return {"agent": name, "job_id": job_id, "status": res.status,
                "report": (res.final_text or "")[:4000],
                "unbacked_facts": loose[:10], "verified": verified,
                "cost_usd": res.cost_usd,
                "tools_used": [c.get("capability") for c in res.tool_calls if c.get("ok")],
                "why_not_verified": None if verified else (
                    f"the agent ended {res.status}" if res.status != "COMPLETED" else
                    "no answer" if not answered else
                    f"{len(loose)} fact(s) no tool result backs: {', '.join(loose[:5])}"
                    if loose else "no fact in the answer is backed by what the tools found "
                    "(it may be asking you questions: answer them, or plan the mission again "
                    "more precisely)")}
    return execute


def cancel_mission(j: Jarvis, mission_id: str, by: str) -> dict[str, Any]:
    """The owner's cancel (`bau mission cancel`): every unfinished job of the mission is marked
    CANCELLED through the executive controller; a running agent stops at its next step."""
    if not by.startswith("human:"):
        raise PermissionError("only the owner cancels a mission")
    from .executive import ExecutiveController
    from .jobs import TERMINAL, JobStore
    m = j.get(mission_id)
    if m is None:
        raise KeyError(f"no mission {mission_id}")
    store = JobStore(j.home)
    ctl = ExecutiveController(store)
    done = [ctl.cancel(job.job_id).job_id for job in store.all()
            if job.mission_id == mission_id and job.status not in TERMINAL]
    if m.status in ("READY", "RUNNING", "PAUSED"):
        m.status, m.next_action = "CANCELLED", "cancelled by the owner"
        j.save(m)
    j.audit.append("mission.cancelled", by, {"mission_id": mission_id, "jobs": done})
    return {"mission_id": mission_id, "status": m.status, "cancelled_jobs": done}


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
        return _mission(found) if found else None

    def list(self) -> list[Mission]:
        latest: dict[str, dict[str, Any]] = {}
        for r in self.store:
            latest[r["mission_id"]] = r
        return [_mission(r) for r in latest.values()]

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
        if m.budget_usd is not None:
            from .economics import Ledger
            spent = Ledger(self.home).spent(mission_id=m.mission_id)
            if spent > m.budget_usd:
                raise PermissionError(f"mission {m.mission_id} is over its budget "
                                      f"(${spent:.2f} of ${m.budget_usd:.2f}): the owner "
                                      "raises it with `bau mission set` or stops it")
        m.status = "RUNNING"
        m.steps["run_started"] = dt.datetime.now(dt.UTC).isoformat()
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
        if result.get("status") == "CANCELLED":
            m.status, m.next_action = "CANCELLED", "cancelled by the owner"
        else:
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
