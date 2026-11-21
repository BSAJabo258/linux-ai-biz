"""The AI workstation: agents as workers, with a Sims-like health and handoff loop.

The office is not a cartoon on top of nothing. Each worker is an approved agent folder,
its work comes from real ``JobStore`` records, and every delivery or failure in those logs
changes its health. A worker that reaches zero health retires; its successor is spawned
from the same role and inherits the open tasks and a short brief from the predecessor's
logs. The retired worker is kept in the graveyard: nothing is deleted.

The productivity manager is a policy gate, not a human approver. It may approve low-risk
internal work (research, drafts, reviews, retries) so the workstation can run on autopilot
without a confirm card. Anything that posts, spends, changes legal state, touches keys, or
deletes still stops at the owner's existing gateway approval, exactly as before. Agent
folders are still approved once by the owner; the manager cannot approve a folder.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .home import atomic_write_json, bau_home
from .jobs import JobStore
from .virtual_creator import MINOR_REFERENCE

VERSION = 1
MAX_EVENTS = 120
MAX_GRAVEYARD = 40
MAX_SEEN = 2000
START_HEALTH = 100
SUCCESSOR_HEALTH = 80
GOOD_HEALTH = 80
LOW_HEALTH = 25
IDLE_DECAY_PER_DAY = 4
LOW_RISK = {"research", "draft", "review", "retry", "continue", "organise", "organize",
            "fix", "test"}
EXTERNAL = re.compile(
    r"\b(post|publish|upload|send|email|sms|pay|spend|buy|purchase|trade|delete|remove|"
    r"deploy|install|sign|approve|money|transfer|password|api.?key)\b", re.I)
# "review": finished, but its result did not pass the check; it waits for the owner and is
# never run again by itself.
RETRY = "Retry after failure: "
OPEN = {"queued", "approved", "waiting_owner", "running", "review"}
NAMES = ("Nova", "Iris", "Juno", "Vera", "Sable", "Lark", "Rune", "Mica", "Echo",
         "Onyx", "Tess", "Wren", "Kite", "Marlow", "Indigo", "Remy")


def _now(now: dt.datetime | None = None) -> str:
    return (now or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds")


def _path(home: Path) -> Path:
    return home / "workstation" / "state.json"


def _default() -> dict[str, Any]:
    return {"version": VERSION, "seq": 0, "workers": [], "graveyard": [], "tasks": [],
            "events": [], "seen_jobs": [], "created": _now()}


def _load(home: Path) -> dict[str, Any]:
    try:
        st = json.loads(_path(home).read_text())
    except (OSError, ValueError):
        return _default()
    base = _default()
    base.update(st if isinstance(st, dict) else {})
    if base.get("version") != VERSION:
        base["version"] = VERSION
    return base


def _save(home: Path, st: dict[str, Any]) -> None:
    atomic_write_json(_path(home), st)


def _audit(home: Path, event: str, who: str, data: dict[str, Any]) -> None:
    from .audit import AuditLog
    AuditLog(home / "audit" / "chain.jsonl").append(f"workstation.{event}", who, data)


def _event(st: dict[str, Any], kind: str, worker: dict[str, Any] | None,
           text: str, **extra: Any) -> dict[str, Any]:
    st["seq"] = int(st.get("seq", 0)) + 1
    e = {"seq": st["seq"], "kind": kind, "at": _now(),
         "worker_id": worker.get("id") if worker else "",
         "worker": worker.get("name") if worker else "",
         "text": text[:300], **extra}
    st["events"].append(e)
    st["events"] = st["events"][-MAX_EVENTS:]
    return e


def _role(agent: str) -> str:
    return agent.split(":", 1)[1] if ":" in agent else agent


def _display_name(role: str, generation: int) -> str:
    base = sum(ord(c) for c in role)
    return NAMES[(base + generation - 1) % len(NAMES)]


def _mood(health: int) -> str:
    return ("thriving" if health >= GOOD_HEALTH else "steady" if health >= 50 else
            "strained" if health >= LOW_HEALTH else "critical")


def _living(st: dict[str, Any], role: str) -> dict[str, Any] | None:
    return next((w for w in st["workers"] if w["role"] == role), None)


def _new_worker(role: str, generation: int, now: str,
                inherited: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": f"{role}:{generation}", "name": _display_name(role, generation),
            "role": role, "generation": generation, "health": START_HEALTH,
            "status": "idle", "hired_at": now, "last_tick": now, "last_job": None,
            "stats": {"delivered": 0, "failed": 0, "streak": 0},
            "inherited": inherited or {}}


def _roles(home: Path) -> list[str]:
    from . import agentfolders as AF
    return AF.names(home)


def ensure_roster(st: dict[str, Any], home: Path, now: str) -> None:
    roles = _roles(home)
    for role in roles:
        if _living(st, role) is None:
            gens = [int(w["generation"]) for w in st["workers"] + st["graveyard"]
                    if w["role"] == role]
            if gens:
                continue                     # a death already spawned this role's successor
            st["workers"].append(_new_worker(role, 1, now))
            _event(st, "hired", _living(st, role), f"{role} clocked in")


def _approval(role: str, home: Path) -> tuple[str, str]:
    from . import agentfolders as AF
    try:
        a = AF.load(role, home)
    except AF.AgentFolderError as e:
        return "missing", str(e)
    problems = AF.problems(a)
    if problems:
        return "broken", "; ".join(problems)
    return AF.approval(a, home), ""


def manager_review(task: dict[str, Any], worker: dict[str, Any], home: Path) -> dict[str, Any]:
    """The productivity manager's decision. It can only say yes to low-risk internal work."""
    text = task.get("objective", "")
    if MINOR_REFERENCE.search(text):
        return {"approved": False, "reason": "refers to minors"}
    if EXTERNAL.search(text):
        return {"approved": False,
                "reason": "outside effect (posting, money, legal, keys or deletion) keeps "
                          "the owner's approval"}
    if task.get("kind") not in LOW_RISK:
        return {"approved": False, "reason": f"not a low-risk kind: {task.get('kind')}"}
    if worker.get("health", 0) < LOW_HEALTH:
        return {"approved": False, "reason": "health is below the work threshold; rest first"}
    state, why = _approval(worker["role"], home)
    if state != "approved":
        return {"approved": False,
                "reason": (f"agent folder {worker['role']} is {state}; the owner must run "
                           f"`bau agents approve {worker['role']}` once") +
                          (f" ({why})" if why else "")}
    return {"approved": True, "reason": "low-risk internal work; productivity manager approved"}


def _new_task(st: dict[str, Any], role: str, objective: str, kind: str, source: str,
              source_job: str = "") -> dict[str, Any] | None:
    if any(t.get("source_job") == source_job and t["status"] in OPEN
           for t in st["tasks"] if source_job):
        return None
    t = {"id": "wt_" + secrets.token_hex(4), "role": role, "objective": objective[:1200],
         "kind": kind, "source": source, "source_job": source_job, "status": "queued",
         "created": _now(), "finished": "", "result": "", "manager": {}}
    st["tasks"].append(t)
    return t


def _outcome(job: Any) -> tuple[str, int, str] | None:
    if job.status == "COMPLETED":
        return "delivered", 8, "delivered work"
    if job.status in ("FAILED", "CANCELLED", "ROLLED_BACK"):
        return "failed", -25, "work failed"
    if job.status in ("PAUSED", "INTERRUPTED", "WAITING_FOR_APPROVAL", "WAITING_FOR_NETWORK"):
        return "stalled", -12, "work stalled"
    return None


def _job_task(st: dict[str, Any], job: Any, role: str, kind: str) -> None:
    objective = (job.objective or job.next_action or "continue the last task")[:1200]
    if objective.startswith(RETRY):
        return       # a retry failed too: it waits for the owner, not for a third try
    if kind == "retry":
        objective = RETRY + objective
    elif kind == "continue":
        objective = "Continue from the log: " + objective
        if job.remaining_steps:
            objective += " (steps: " + ", ".join(job.remaining_steps[:12]) + ")"
    _new_task(st, role, objective, kind, "job log", job.job_id)


def process_jobs(st: dict[str, Any], home: Path, now: str) -> None:
    store = JobStore(home)
    seen = set(st.get("seen_jobs") or [])
    for job in sorted(store.all(), key=lambda j: j.updated_at or ""):
        role = _role(job.agent)
        if _living(st, role) is None:
            continue
        if job.status == "COMPLETED" and getattr(job, "verification", "") != "VERIFIED":
            # Finished, not checked or failed the check: never rewarded as delivered work.
            if job.job_id in seen:
                continue
            seen.add(job.job_id)
            if job.verification == "FAILED":
                worker = _living(st, role)
                worker["health"] = max(0, int(worker["health"]) - 12)
                worker["stats"]["streak"] = 0
                worker["last_job"] = job.job_id
                for t in st["tasks"]:
                    if t.get("source_job") == job.job_id and t["status"] in OPEN:
                        t.update(status="review", finished=now, result=job.next_action or "")
                _event(st, "stalled", worker, f"waits for your review: {job.objective[:120]}",
                       job=job.job_id)
            continue
        if job.status == "COMPLETED":
            if job.job_id in seen:
                continue
            seen.add(job.job_id)
            worker = _living(st, role)
            worker["health"] = min(100, int(worker["health"]) + 8)
            worker["stats"]["delivered"] += 1
            worker["stats"]["streak"] += 1
            worker["last_job"] = job.job_id
            worker["status"] = "delivering"
            for t in st["tasks"]:
                if t.get("source_job") == job.job_id and t["status"] in OPEN | {"approved"}:
                    t.update(status="done", finished=now, result="delivered")
            _event(st, "delivered", worker, f"dropped off: {job.objective[:120]}",
                   job=job.job_id)
            continue
        outcome = _outcome(job)
        if outcome is None or job.job_id in seen:
            continue
        seen.add(job.job_id)
        worker = _living(st, role)
        _kind, delta, text = outcome
        worker["health"] = max(0, int(worker["health"]) + delta)
        worker["stats"]["failed"] += 1
        worker["stats"]["streak"] = 0
        worker["last_job"] = job.job_id
        worker["status"] = "idle"
        # A failure is retried and an interrupted job continued, but a job the owner
        # cancelled, or one waiting for the owner's approval, is never picked up again here.
        if job.status in ("FAILED", "ROLLED_BACK"):
            _job_task(st, job, role, "retry")
        elif job.status in ("PAUSED", "INTERRUPTED", "WAITING_FOR_NETWORK"):
            _job_task(st, job, role, "continue")
        _event(st, "failed" if delta < -15 else "stalled", worker,
               f"{text}: {job.objective[:120]}", job=job.job_id)
    st["seen_jobs"] = list(seen)[-MAX_SEEN:]


def _inherit(st: dict[str, Any], dead: dict[str, Any], successor: dict[str, Any],
             now: str) -> list[dict[str, Any]]:
    moved = [t for t in st["tasks"] if t["role"] == dead["role"] and t["status"] in OPEN]
    for t in moved:
        t["role"] = successor["role"]
        if t["status"] in ("running", "waiting_owner"):
            t["status"] = "queued"           # the heir's manager looks at it afresh
        t["manager"] = {}
        t["inherited_from"] = dead["id"]
    logs = [e for e in st["events"] if e.get("worker_id") == dead["id"]][-6:]
    successor["inherited"] = {"from": dead["id"], "name": dead["name"],
                              "generation": dead["generation"], "at": now,
                              "logs": [e["text"] for e in logs], "tasks": len(moved)}
    return moved


def _retire(st: dict[str, Any], worker: dict[str, Any], home: Path, now: str,
            cause: str) -> None:
    worker["status"] = "dead"
    worker["died_at"] = now
    worker["cause"] = cause
    st["workers"] = [w for w in st["workers"] if w["id"] != worker["id"]]
    st["graveyard"].append(worker)
    st["graveyard"] = st["graveyard"][-MAX_GRAVEYARD:]
    _event(st, "died", worker, f"retired at 0 health: {cause}")
    if worker["role"] not in _roles(home):
        return
    successor = _new_worker(worker["role"], int(worker["generation"]) + 1, now)
    successor["health"] = SUCCESSOR_HEALTH
    moved = _inherit(st, worker, successor, now)
    st["workers"].append(successor)
    _event(st, "spawned", successor,
           f"{successor['name']} replaces {worker['name']} (gen {successor['generation']}) "
           f"and inherits {len(moved)} task(s) from the logs")
    _audit(home, "successor", "process:workstation",
           {"dead": worker["id"], "successor": successor["id"], "tasks": len(moved)})


def decay(st: dict[str, Any], now: str) -> None:
    at = dt.datetime.fromisoformat(now)
    for w in st["workers"]:
        try:
            last = dt.datetime.fromisoformat(w.get("last_tick") or now)
        except ValueError:
            last = at
        days = max(0.0, (at - last).total_seconds() / 86400)
        if days >= 1:
            w["health"] = max(0, int(w["health"]) - int(days * IDLE_DECAY_PER_DAY))
            w["last_tick"] = now


def review(st: dict[str, Any], home: Path) -> None:
    for t in st["tasks"]:
        # A task parked only because its agent folder was not approved yet is looked at
        # again, so the owner's one `bau agents approve` lets the work go on by itself.
        parked = t["status"] == "waiting_owner" and \
            str((t.get("manager") or {}).get("reason", "")).startswith("agent folder ")
        if t["status"] != "queued" and not parked:
            continue
        worker = _living(st, t["role"])
        if worker is None:
            t["status"] = "blocked"
            t["manager"] = {"approved": False, "reason": "no living worker for this role"}
            continue
        decision = manager_review(t, worker, home)
        t["manager"] = decision
        t["status"] = "approved" if decision["approved"] else "waiting_owner"


def reap(st: dict[str, Any], home: Path, now: str) -> None:
    for w in list(st["workers"]):
        if int(w.get("health", 0)) <= 0:
            _retire(st, w, home, now, "health reached zero")


def refresh(home: Path | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    home = home or bau_home()
    stamp = _now(now)
    st = _load(home)
    ensure_roster(st, home, stamp)
    decay(st, stamp)
    process_jobs(st, home, stamp)
    reap(st, home, stamp)
    review(st, home)
    _save(home, st)
    return st


def assign(home: Path, role: str, objective: str, by: str, kind: str = "review",
           source_note: str = "") -> dict[str, Any]:
    """Put one piece of work in a role's inbox. The manager reviews it at once."""
    if not by.startswith(("human:", "process:autopilot")):
        raise PermissionError("only the owner or the autopilot assigns work")
    objective = " ".join((objective or "").split())[:1200]
    if len(objective) < 3:
        raise ValueError("say what the work is")
    if role not in _roles(home):
        raise KeyError(f"no agent folder {role!r}; have {', '.join(_roles(home)) or 'none'}")
    st = refresh(home)
    if _living(st, role) is None:
        raise ValueError(f"no living worker for {role}")
    _new_task(st, role, objective, kind, f"assigned by {by}" + (f" {source_note}"
                                                                 if source_note else ""))
    review(st, home)
    _save(home, st)
    t = st["tasks"][-1]
    _audit(home, "assigned", by, {"task": t["id"], "role": role,
                                   "manager": t.get("manager", {})})
    return t


def queued(home: Path | None = None) -> int:
    st = refresh(home)
    return sum(t["status"] in ("approved", "queued") for t in st["tasks"])


def _boss(home: Path) -> tuple[Any, dict[str, Any]] | None:
    """The team's boss model as Jarvis's own: an agent on the strong brain uses it when no
    strong model is chosen (2026-11-21: without it the researcher failed every shift with
    "no approved model to draft with")."""
    from . import team
    from .runtime import provider_for
    boss = team.show(home).get("boss")
    if not boss:
        return None
    try:
        p, rec = provider_for(boss, home)
    except (KeyError, PermissionError, ImportError, ValueError):
        return None
    return p, {**rec, "id": boss}


def run_shift(home: Path | None = None, audit: Any = None, runner: Callable[..., Any] | None = None,
              max_tasks: int = 1, by: str = "process:autopilot") -> dict[str, Any]:
    """Run manager-approved work. The runner defaults to an approved agent folder; a test
    can pass its own. No confirm card is created for manager-approved internal work."""
    home = home or bau_home()
    if not by.startswith(("human:", "process:autopilot")):
        raise PermissionError("only the owner or the autopilot can run a shift")
    st = refresh(home)
    done: list[dict[str, Any]] = []
    for _ in range(max(0, int(max_tasks))):
        task = next((t for t in st["tasks"] if t["status"] == "approved"), None)
        if task is None:
            break
        worker = _living(st, task["role"])
        if worker is None:
            task["status"], task["manager"] = "blocked", {
                "approved": False, "reason": "worker retired before the shift"}
            break
        task["status"] = "running"
        worker["status"] = "working"
        _save(home, st)
        try:
            # The same path as a mission: one job through the executive controller, every
            # tool through the gateway, then the same check (jarvis.run_checked). A result
            # that does not pass waits for the owner's review; only a checked one is done.
            from .jarvis import run_checked
            if runner is None:
                from . import agentfolders as AF

                def runner(name: str, objective: str, mission_id: str, job: Any) -> Any:
                    return AF.run(name, objective, home, audit, mission_id=mission_id, job=job,
                                  jarvis=_boss(home))
            checked = run_checked(home, task["role"], task["objective"],
                                  f"workstation:{task['id']}", runner)
            status, text = checked["status"], checked["report"] or ""
            ok = checked["verified"]
            task.update(status="done" if ok else
                        "review" if status == "COMPLETED" else "failed",
                        finished=_now(), source_job=checked["job_id"],
                        result=(text if ok else checked["why_not_verified"] or text)[:600],
                        report=text[:4000])   # what the owner reads on the delivered card
            linked = next((j for j in JobStore(home).all()
                           if j.job_id == checked["job_id"]), None)
            if linked is not None:
                # The real agent made a job: its log drives health and the drop-off walk.
                process_jobs(st, home, _now())
            elif ok:
                worker["stats"]["delivered"] += 1
                worker["stats"]["streak"] += 1
                worker["health"] = min(100, int(worker["health"]) + 8)
                _event(st, "delivered", worker, f"dropped off: {task['objective'][:120]}",
                       task=task["id"])
            else:
                worker["stats"]["failed"] += 1
                worker["stats"]["streak"] = 0
                worker["health"] = max(0, int(worker["health"]) - 20)
                _event(st, "failed", worker, f"{status}: {text[:120]}", task=task["id"])
        except Exception as e:  # noqa: BLE001 - a failed shift is evidence, not a crash
            task.update(status="failed", finished=_now(),
                        result=f"{type(e).__name__}: {e}"[:600])
            worker["stats"]["failed"] += 1
            worker["health"] = max(0, int(worker["health"]) - 20)
            _event(st, "failed", worker, f"shift failed: {e}"[:180], task=task["id"])
        worker["status"] = "idle"
        worker["last_tick"] = _now()
        _audit(home, "shift", by, {"task": task["id"], "role": task["role"],
                                    "result": task["status"]})
        _save(home, st)
        done.append({k: task.get(k) for k in ("id", "role", "objective", "status", "result")})
    reap(st, home, _now())
    review(st, home)
    _save(home, st)
    return {**view_from(st, home), "ran": done}


def view_from(st: dict[str, Any], home: Path) -> dict[str, Any]:
    tasks = [t for t in st["tasks"] if t["status"] in OPEN]
    for t in tasks:
        t["manager"] = t.get("manager") or {}
    graveyard = [{"id": w["id"], "name": w["name"], "role": w["role"],
                  "generation": w["generation"], "died_at": w.get("died_at"),
                  "cause": w.get("cause"), "stats": w.get("stats")}
                 for w in st["graveyard"][-10:]]
    return {"auto": True, "manager": {
                "name": "Productivity manager", "mode": "autopilot",
                "note": "approves low-risk internal work; posting, money, legal, keys and "
                        "deletion keep the owner's approval"},
            "workers": [{"id": w["id"], "name": w["name"], "role": w["role"],
                         "generation": w["generation"], "health": w["health"],
                         "mood": _mood(w["health"]), "status": w["status"],
                         "stats": w["stats"], "last_job": w["last_job"],
                         "inherited": w.get("inherited") or {},
                         "tasks": [t["id"] for t in tasks if t["role"] == w["role"]]}
                        for w in st["workers"]],
            "tasks": [{"id": t["id"], "role": t["role"], "objective": t["objective"],
                       "kind": t["kind"], "source": t["source"], "state": t["status"],
                       "manager": t.get("manager", {}), "created": t["created"],
                       "inherited_from": t.get("inherited_from", "")} for t in tasks],
            "graveyard": graveyard,
            "floor": floor(home, st["workers"]),
            "events": st["events"][-20:],
            "outbox": sum(e["kind"] == "delivered" for e in st["events"]),
            "seq": st["seq"]}


def floor(home: Path, workers: list[dict[str, Any]],
          now: dt.datetime | None = None) -> dict[str, Any]:
    """Every department of the operations world as a station, and who stands at which: the
    room is the one the world gives for that AI's latest real job (world.place, world.jarvis),
    so a worker walks only when its job really changes (the owner, 2026-11-21: "all sections
    and AI models have motion when delivering or walking to different stations")."""
    from . import team
    from . import world as WD
    now = now or dt.datetime.now(dt.UTC)
    latest: dict[str, Any] = {}
    for job in JobStore(home).all():
        name = _role(job.agent)
        if name not in latest or (job.updated_at or "") >= (latest[name].updated_at or ""):
            latest[name] = job
    me = WD.jarvis(home, now)
    people = [{"id": "jarvis", "name": "Jarvis", "role": "jarvis", "room": me["room"],
               "state": me["state"], "task": ((me["job"] or {}).get("objective") or "")[:160],
               "model": team.show(home).get("boss"), "mood": "steady", "look": "jarvis"}]
    for w in workers:
        job = latest.get(w["role"])
        room, state = WD.place(w["role"], job, now)
        people.append({"id": w["id"], "name": w["name"], "role": w["role"], "room": room,
                       "state": state, "task": job.objective[:160] if job else "",
                       "model": job.model if job else None, "mood": _mood(w["health"]),
                       "look": WD.look(w["role"])})
    return {"rooms": [{"id": r, "name": n, "who": who} for r, n, who in WD.ROOMS],
            "agents": people}


def view(home: Path | None = None) -> dict[str, Any]:
    home = home or bau_home()
    return view_from(refresh(home), home)


def delivered_unseen(home: Path | None = None) -> list[dict[str, Any]]:
    """Finished work the owner has not looked at yet: done (checked) or waiting for review."""
    st = _load(home or bau_home())
    return [t for t in st["tasks"] if t["status"] in ("done", "review") and not t.get("seen")]


def mark_seen(home: Path, task_id: str, by: str, kept: bool) -> dict[str, Any]:
    """The owner read a delivered piece of work (kept: Accept, else Not now)."""
    if not by.startswith("human:"):
        raise PermissionError("only the owner files delivered work")
    st = _load(home)
    t = next((t for t in st["tasks"] if t["id"] == task_id), None)
    if t is None:
        raise KeyError(task_id)
    t["seen"] = {"by": by, "at": _now(), "kept": bool(kept)}
    _save(home, st)
    _audit(home, "seen", by, {"task": task_id, "kept": bool(kept)})
    return t


def held(home: Path | None = None) -> list[dict[str, Any]]:
    """Work the productivity manager held for the owner. Each becomes a card, so the office
    runs on by itself and stops only at his yes (the owner, 2026-11-21: "other people's AI
    virtual offices can run most tasks, stopping at confirming"). Not: work held only
    because its folder is unapproved (that has its own card), or work about minors."""
    st = _load(home or bau_home())
    out = []
    for t in st["tasks"]:
        why = str((t.get("manager") or {}).get("reason", ""))
        if t["status"] == "waiting_owner" and not why.startswith("agent folder ") \
                and why != "refers to minors" and not MINOR_REFERENCE.search(t["objective"]):
            out.append(t)
    return out


def owner_decide(home: Path, task_id: str, by: str, yes: bool) -> dict[str, Any]:
    """The owner's answer to held work: yes, it runs on the next shift (the agent's own
    gateway still stops at every post, payment or send); no, it is dropped."""
    if not by.startswith("human:"):
        raise PermissionError("only the owner answers held work")
    st = _load(home)
    t = next((t for t in st["tasks"] if t["id"] == task_id), None)
    if t is None or t["status"] != "waiting_owner":
        raise KeyError(f"no held work {task_id}")
    if MINOR_REFERENCE.search(t["objective"]):
        raise PermissionError("refers to minors")
    if yes:
        t.update(status="approved", manager={"approved": True, "reason": f"approved by {by}"})
    else:
        t.update(status="declined", finished=_now(), result=f"dropped by {by}")
    _event(st, "approved" if yes else "declined", _living(st, t["role"]),
           f"{'you approved' if yes else 'you dropped'}: {t['objective'][:120]}", task=task_id)
    _save(home, st)
    _audit(home, "owner_decided", by, {"task": task_id, "yes": bool(yes)})
    return t

