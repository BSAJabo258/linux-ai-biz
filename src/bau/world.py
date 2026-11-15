"""The operations world (the owner's ask, 2026-11-15: an isometric floor of robot workers, from
his three reference pictures): every robot on the screen is one of the owner's agents, and the
room it stands in comes only from its latest real job in ``jobs/``. An agent with no job sits in
the lounge; nothing walks, types or glows unless a job says so.

Read-only: it reads the agent folders, the job store and HOLD, and changes nothing.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from .home import bau_home

# Rooms on the floor, in the order the screen lays them out. ``hq`` is Jarvis's core.
ROOMS = (("hq", "Jarvis core"), ("research", "Research lab"), ("studio", "Content studio"),
         ("workshop", "Workshop"), ("approvals", "Waiting for you"), ("delivery", "Delivered"),
         ("repair", "Stopped"), ("lounge", "Available"))
# Where an agent works while its job runs; any other agent works in the workshop.
DESK = {"researcher": "research", "producer": "studio"}
WORKING = {"PENDING", "RUNNING"}
STOPPED = {"PAUSED", "WAITING_FOR_NETWORK", "INTERRUPTED", "FAILED", "ROLLED_BACK"}
RECENT = dt.timedelta(hours=24)          # a finished job stays in its room this long
QUIET = dt.timedelta(minutes=30)         # a running job with no checkpoint this long is flagged


def _when(s: str) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def place(name: str, job: Any, now: dt.datetime) -> tuple[str, str]:
    """(room, state) for an agent from its latest job; ``job`` None means it has none."""
    if job is None:
        return "lounge", "idle"
    at = _when(job.updated_at)
    fresh = at is not None and now - at < RECENT
    if job.status in WORKING:
        return DESK.get(name, "workshop"), "working"
    if job.status == "WAITING_FOR_APPROVAL":
        return "approvals", "waiting for you"
    if job.status in STOPPED:
        return "repair", job.status.lower().replace("_", " ")
    if job.status == "COMPLETED" and fresh:
        return "delivery", "done"
    return "lounge", "idle"


def _agent_name(job_agent: str) -> str:
    return job_agent.removeprefix("folder:")


def world(home: Path | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    from . import agentfolders as AF
    from .governor import hold_reason
    from .jobs import JobStore
    home = home or bau_home()
    now = now or dt.datetime.now(dt.UTC)
    latest: dict[str, Any] = {}
    for job in JobStore(home).all():
        name = _agent_name(job.agent)
        old = latest.get(name)
        if old is None or (job.updated_at or "") >= (old.updated_at or ""):
            latest[name] = job
    agents = []
    names = AF.names(home)
    for name in names + sorted(set(latest) - set(names)):
        try:
            a = AF.load(name, home)
            info = {"description": a.description, "brain": a.brain, "tools": a.tools,
                    "mcp": a.mcp, "approval": AF.approval(a, home)}
        except (AF.AgentFolderError, FileNotFoundError, KeyError):
            info = {"description": "not an agent folder (a registry agent)", "brain": None,
                    "tools": [], "mcp": [], "approval": "unknown"}
        job = latest.get(name)
        room, state = place(name, job, now)
        rec: dict[str, Any] = {"name": name, **info, "room": room, "state": state,
                               "job": None}
        if job is not None:
            at = _when(job.updated_at)
            rec["job"] = {"job_id": job.job_id, "mission_id": job.mission_id,
                          "objective": job.objective[:300], "status": job.status,
                          "model": job.model, "updated_at": job.updated_at,
                          "steps_done": len(job.completed_steps),
                          "steps_left": len(job.remaining_steps),
                          "cost_usd": round(job.cost_usd, 4), "errors": job.errors[-3:],
                          "artifacts": job.artifacts[-5:], "next_action": job.next_action}
            if state == "working" and at is not None and now - at > QUIET:
                rec["quiet_minutes"] = int((now - at).total_seconds() // 60)
        agents.append(rec)
    held = hold_reason(home)
    counts = {r: sum(1 for a in agents if a["room"] == r) for r, _ in ROOMS if r != "hq"}
    return {"rooms": [{"id": r, "name": n} for r, n in ROOMS], "agents": agents,
            "hold": held, "counts": counts, "at": now.isoformat(timespec="seconds"),
            "how_to_read": "each robot is an agent; its room is its latest job's state"}
