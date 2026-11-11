"""The first real adapter (docs/JARVIS_IMPLEMENTATION_MAP.md, Phase 1): an approved agent folder
does the task. It adds no tool path: the agent's every tool still goes through the Universal
Gateway inside ``agents.run``. It continues the controller's own job, so a mission has one job.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import AdapterBase, ExecutionContext, ExecutionResult


class AgentFolderAdapter(AdapterBase):
    adapter_id = "agent_folder"
    capabilities = ("mission.research",)

    def __init__(self, store: Any, run_agent: Callable[..., Any]):
        """``run_agent(name, objective, mission_id, job) -> agents.RunResult``."""
        self.store = store
        self.run_agent = run_agent

    def run(self, contract: Any, context: ExecutionContext) -> ExecutionResult:
        job = self.store.load(context.task_id)
        res = self.run_agent(contract.agent, contract.objective, contract.mission_id, job)
        status = res.status if res.status in ("COMPLETED", "CANCELLED") else "FAILED"
        return ExecutionResult(status=status,
                               errors=[] if status != "FAILED" else
                               [f"the agent ended {res.status}"],
                               evidence={"run": res})
