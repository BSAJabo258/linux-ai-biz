"""Jobs, checkpoints and reboot recovery (spec §86-89).

Every write is atomic (write-temp, fsync, rename), so a power cut leaves the
previous checkpoint intact, never a torn one. On boot, ``recover()`` lists
every unfinished job and marks network-dependent ones WAITING_FOR_NETWORK
when offline, so nothing important silently disappears.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import socket
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .home import atomic_write_json, bau_home

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "ROLLED_BACK"}
STATES = {"PENDING", "RUNNING", "PAUSED", "WAITING_FOR_APPROVAL", "WAITING_FOR_NETWORK",
          "INTERRUPTED"} | TERMINAL


@dataclass
class Job:
    job_id: str
    mission_id: str
    objective: str
    agent: str
    model: str | None = None
    tools: list[str] = field(default_factory=list)
    status: str = "PENDING"
    needs_network: bool = False
    risk: str = "LOW"
    budget_usd: float = 0.0
    cost_usd: float = 0.0
    completed_steps: list[str] = field(default_factory=list)
    remaining_steps: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    approvals: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    retries: int = 0
    compliance_status: str = "UNKNOWN"
    rollback_state: str | None = None
    next_action: str | None = None
    updated_at: str = ""


class JobStore:
    def __init__(self, home: Path | None = None):
        self.dir = (home or bau_home()) / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, mission_id: str, objective: str, agent: str, steps: list[str],
               **kw: Any) -> Job:
        job = Job(job_id="job_" + secrets.token_hex(6), mission_id=mission_id,
                  objective=objective, agent=agent, remaining_steps=list(steps), **kw)
        self.checkpoint(job)
        return job

    def checkpoint(self, job: Job) -> None:
        if job.status not in STATES:
            raise ValueError(f"bad job status {job.status}")
        job.updated_at = dt.datetime.now(dt.UTC).isoformat()
        atomic_write_json(self.dir / f"{job.job_id}.json", asdict(job))

    def load(self, job_id: str) -> Job:
        return Job(**json.loads((self.dir / f"{job_id}.json").read_text()))

    def all(self) -> list[Job]:
        return [Job(**json.loads(p.read_text())) for p in sorted(self.dir.glob("job_*.json"))]

    def step_done(self, job: Job, step: str, cost_usd: float = 0.0) -> None:
        if step not in job.remaining_steps:
            raise ValueError(f"{step} is not a remaining step")
        job.remaining_steps.remove(step)
        job.completed_steps.append(step)
        job.cost_usd += cost_usd
        if job.budget_usd and job.cost_usd > job.budget_usd:
            job.status = "PAUSED"  # spec §102: over budget pauses, never continues
            job.next_action = "budget exceeded: optimize, change model, or request approval"
        elif not job.remaining_steps:
            job.status = "COMPLETED"
        self.checkpoint(job)


def network_up(host: str = "1.1.1.1", port: int = 53, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def recover(store: JobStore, online: bool | None = None) -> list[dict[str, Any]]:
    online = network_up() if online is None else online
    out = []
    for job in store.all():
        if job.status in TERMINAL:
            continue
        before = job.status
        if job.status == "RUNNING":
            job.status = "INTERRUPTED"
        if job.needs_network and not online:
            job.status = "WAITING_FOR_NETWORK"
        elif job.status == "WAITING_FOR_NETWORK" and online:
            job.status = "INTERRUPTED"
        if job.status != before:
            store.checkpoint(job)
        out.append({"job_id": job.job_id, "was": before, "now": job.status,
                    "next": job.remaining_steps[:1]})
    return out
