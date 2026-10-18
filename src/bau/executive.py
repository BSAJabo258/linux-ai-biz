"""Executive controller (prototype, docs/ARCHITECTURE_RFC.md).

One task, one adapter, one existing ``jobs.Job``. This is the small coordination
layer Jarvis can call between planning and execution; it is not a second Jarvis.
It reuses ``jobs.Job``/``jobs.JobStore`` and leaves the Gateway, Governor,
sandbox, policy engine, model registry and usage meter untouched.

What it does not do, deliberately:

* no permission, tool, budget or data-boundary enforcement - the Universal
  Gateway remains the only path from an agent to a capability;
* no approval: a HIGH/CRITICAL task waits for a caller-supplied approval
  reference that a human obtained elsewhere;
* no verification of an adapter's result, no retries, no background workers;
* no implicit persistence: the default store is in memory and writes nothing.
  Pass ``jobs.JobStore`` explicitly for durable checkpoints.
"""

from __future__ import annotations

import copy
import datetime as dt
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from . import blast, jobs
from .adapters import AdapterBase, AdapterRegistry, ExecutionContext, ExecutionResult
from .jobs import Job, JobStore

APPROVAL_RISKS = {"HIGH", "CRITICAL"}
DISPATCHABLE = {"PENDING", "INTERRUPTED"}


@dataclass
class TaskContract:
    """The caller's description of one task.

    Fields mirror the existing ``jobs.Job`` so the contract can be persisted
    without a second model. They are declarations, not authority: ``tools`` and
    ``budget_usd`` are recorded, not enforced here.
    """

    mission_id: str
    objective: str
    agent: str
    model: str | None = None
    tools: list[str] = field(default_factory=list)
    budget_usd: float = 0.0
    risk: str = "LOW"

    @property
    def needs_approval(self) -> bool:
        return self.risk in APPROVAL_RISKS

    @classmethod
    def from_job(cls, job: Job) -> TaskContract:
        """Rebuild the contract from the persisted job (the source of truth)."""
        return cls(mission_id=job.mission_id, objective=job.objective, agent=job.agent,
                   model=job.model, tools=list(job.tools), budget_usd=job.budget_usd,
                   risk=job.risk)


class JobBackend(Protocol):
    """The part of ``jobs.JobStore`` the controller relies on.

    ``JobStore`` satisfies it structurally; ``InMemoryJobStore`` implements the
    same methods without touching disk.
    """

    def create(self, mission_id: str, objective: str, agent: str, steps: list[str],
               **kw: Any) -> Job: ...

    def checkpoint(self, job: Job) -> None: ...

    def load(self, job_id: str) -> Job: ...


class InMemoryJobStore(JobStore):
    """``JobStore``'s interface with no filesystem side effects.

    Used when no store is injected. It keeps the same status validation and
    returns copies, so a caller cannot mutate stored state without a checkpoint.
    """

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}

    def checkpoint(self, job: Job) -> None:
        if job.status not in jobs.STATES:
            raise ValueError(f"bad job status {job.status}")
        job.updated_at = dt.datetime.now(dt.UTC).isoformat()
        self.jobs[job.job_id] = asdict(job)

    def load(self, job_id: str) -> Job:
        try:
            return Job(**copy.deepcopy(self.jobs[job_id]))
        except KeyError:
            raise KeyError(f"unknown task {job_id!r}") from None

    def all(self) -> list[Job]:
        return [Job(**copy.deepcopy(self.jobs[k])) for k in sorted(self.jobs)]


class ExecutiveController:
    """Create a task, dispatch it to one adapter, record the outcome.

    ``store`` and ``adapters`` are injected. With no store the controller uses
    ``InMemoryJobStore`` and creates no directories; with no adapters registered
    every dispatch raises ``KeyError``.
    """

    def __init__(self, store: JobBackend | None = None,
                 adapters: AdapterRegistry | None = None,
                 hold: Callable[[], str | None] | None = None):
        self.store: JobBackend = store if store is not None else InMemoryJobStore()
        self.adapters = adapters if adapters is not None else AdapterRegistry()
        # Inject governor.hold_reason (or an equivalent) to honour a HOLD. When
        # omitted the controller does not read BAU_HOME at all.
        self.hold = hold if hold is not None else (lambda: None)

    # ------------------------------------------------------------ tasks
    def validate_task(self, contract: TaskContract) -> list[str]:
        """Return the reasons a contract is invalid; an empty list means valid."""
        errors: list[str] = []
        for name in ("mission_id", "objective", "agent"):
            value = getattr(contract, name)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{name} must be a non-empty string")
        if contract.model is not None and (not isinstance(contract.model, str)
                                           or not contract.model.strip()):
            errors.append("model must be a non-empty string or None")
        if contract.risk not in blast.LEVELS:
            errors.append(f"risk must be one of {blast.LEVELS}")
        budget = contract.budget_usd
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) \
                or not math.isfinite(budget) or budget < 0:
            errors.append("budget_usd must be a finite number >= 0")
        if not isinstance(contract.tools, list) or any(
                not isinstance(t, str) or not t.strip() for t in contract.tools):
            errors.append("tools must be a list of non-empty strings")
        elif len(set(contract.tools)) != len(contract.tools):
            errors.append("tools must not repeat")
        return errors

    def create_task(self, contract: TaskContract) -> str:
        """Persist a PENDING job (or WAITING_FOR_APPROVAL for high risk)."""
        problems = self.validate_task(contract)
        if problems:
            raise ValueError("; ".join(problems))
        job = self.store.create(
            contract.mission_id, contract.objective, contract.agent, [],
            model=contract.model, tools=list(contract.tools),
            budget_usd=contract.budget_usd, risk=contract.risk)
        if contract.needs_approval:
            job.status = "WAITING_FOR_APPROVAL"
            job.next_action = "a human must approve this task before it can run"
            self.store.checkpoint(job)
        return job.job_id

    def get_status(self, task_id: str) -> Job:
        """The persisted job, which is the task's status record."""
        return self.store.load(task_id)

    def cancel(self, task_id: str) -> Job:
        """Request cancellation. A terminal task is left as it is.

        A running adapter is not interrupted; it sees ``should_cancel`` turn
        true through its ``ExecutionContext`` and is expected to stop.
        """
        job = self.store.load(task_id)
        if job.status in jobs.TERMINAL:
            return job
        job.status = "CANCELLED"
        job.next_action = "cancelled by the caller"
        self.store.checkpoint(job)
        return job

    # ------------------------------------------------------------ execution
    def dispatch(self, task_id: str, adapter_id: str,
                 approval_ref: str | None = None) -> ExecutionResult:
        """Run one adapter for a task and record the outcome on the job.

        A task needing approval refuses to run without ``approval_ref``. The
        controller records the reference; it cannot verify it, so the caller
        must supply one only after a human approved (for example after
        ``bau approve``). An unknown adapter leaves the task untouched.
        """
        job = self.store.load(task_id)
        if job.status in jobs.TERMINAL:
            raise ValueError(f"task {task_id} is {job.status}; it cannot run again")
        if job.status == "WAITING_FOR_APPROVAL":
            if not approval_ref:
                raise PermissionError(
                    f"task {task_id} waits for a human approval; pass the reference "
                    "only after a human approved it")
            job.approvals.append(approval_ref)
        elif job.status not in DISPATCHABLE:
            raise ValueError(f"task {task_id} is {job.status}; "
                             f"only {sorted(DISPATCHABLE)} can run")
        held = self.hold()
        if held:
            raise PermissionError(f"BAU is on HOLD ({held}); a human must release it")
        adapter = self.adapters.get(adapter_id)
        job.status = "RUNNING"
        self.store.checkpoint(job)

        context = ExecutionContext(
            task_id=job.job_id, mission_id=job.mission_id,
            should_cancel=lambda: self._status(job.job_id) == "CANCELLED")
        try:
            result = adapter.run(TaskContract.from_job(job), context)
            if not isinstance(result, ExecutionResult):
                raise TypeError(f"adapter {adapter_id!r} returned {type(result).__name__}, "
                                "not ExecutionResult")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            failed = self.store.load(task_id)
            failed.errors.append(error)
            failed.status = "FAILED"
            failed.next_action = "investigate the adapter failure before retrying"
            self.store.checkpoint(failed)
            return ExecutionResult(status="FAILED", errors=[error])

        done = self.store.load(task_id)
        done.artifacts.extend(result.artifacts)
        done.errors.extend(result.errors)
        if done.status == "CANCELLED":
            # A cancel recorded during the run wins over the adapter's own status.
            done.next_action = "cancelled cooperatively; the adapter stopped"
        else:
            done.status = result.status
            done.next_action = ("verify the result and record evidence"
                                if result.success else "adapter reported failure")
        self.store.checkpoint(done)
        return result

    def _status(self, task_id: str) -> str:
        try:
            return self.store.load(task_id).status
        except KeyError:
            return "MISSING"

    def register(self, adapter: AdapterBase) -> None:
        """Shortcut for ``controller.adapters.register(adapter)``."""
        self.adapters.register(adapter)
