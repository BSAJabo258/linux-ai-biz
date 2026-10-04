"""Business factory framework (spec §60-65).

A factory is an ordered list of stages. A run advances one stage at a time and
checkpoints after each, so a reboot or a failed stage resumes where it stopped
(spec §87-88). Gates and approvals are hard stops: a run parks in
``WAITING_GATE`` / ``WAITING_APPROVAL`` / ``WAITING_CHECKLIST`` until the facts,
the signature or the human confirmation exist.
"""

from __future__ import annotations

import datetime as dt
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .audit import AuditLog
from .decision import Status
from .home import atomic_write_json, bau_home, shipped_data
from .policy import PolicyEngine
from .store import YamlStore


def definitions(home: Path | None = None) -> dict[str, Any]:
    local = (home or bau_home()) / "config" / "factories.yaml"
    src = local if local.exists() else shipped_data() / "factories.yaml"
    return yaml.safe_load(src.read_text())


class Activation:
    def __init__(self, home: Path | None = None):
        self.store = YamlStore((home or bau_home()) / "config" / "factory_activation.yaml",
                               {"active": {}})

    def active(self) -> dict[str, Any]:
        return self.store.load()["active"]

    def activate(self, name: str, approver: str, approval_ref: str) -> None:
        if not approver.startswith("human:"):
            raise PermissionError("factories are activated by a human")
        data = self.store.load()
        data["active"][name] = {"by": approver, "approval": approval_ref,
                                "at": dt.datetime.now(dt.UTC).isoformat()}
        self.store.save(data)

    def deactivate(self, name: str) -> None:
        data = self.store.load()
        data["active"].pop(name, None)
        self.store.save(data)


@dataclass
class FactoryRun:
    run_id: str
    factory: str
    objective: str
    status: str = "RUNNING"          # RUNNING | WAITING_* | COMPLETED | FAILED
    stage_index: int = 0
    outputs: dict[str, Any] = field(default_factory=dict)
    checklist: dict[str, dict[str, Any]] = field(default_factory=dict)
    gate_facts: dict[str, Any] = field(default_factory=dict)
    approvals: dict[str, str] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    waiting_on: str = ""


Hooks = dict[str, Callable[..., Any]]


class FactoryRunner:
    """hooks: ``agent(agent_id, prompt, run) -> str``, ``tool(capability, run) -> Any``,
    ``approval_ok(capability, run, ref) -> bool``."""

    def __init__(self, engine: PolicyEngine, hooks: Hooks, home: Path | None = None,
                 audit: AuditLog | None = None):
        self.home = home or bau_home()
        self.engine = engine
        self.hooks = hooks
        self.defs = definitions(self.home)
        self.audit = audit or AuditLog(self.home / "audit" / "chain.jsonl")
        self.dir = self.home / "jobs" / "factory_runs"

    def _save(self, run: FactoryRun) -> None:
        atomic_write_json(self.dir / f"{run.run_id}.json", asdict(run))

    def load(self, run_id: str) -> FactoryRun:
        import json
        return FactoryRun(**json.loads((self.dir / f"{run_id}.json").read_text()))

    def start(self, factory: str, objective: str) -> FactoryRun:
        if factory not in self.defs:
            raise ValueError(f"unknown factory {factory}")
        if factory not in Activation(self.home).active():
            raise PermissionError(f"factory {factory} is not activated (spec §60)")
        run = FactoryRun(run_id="fr_" + secrets.token_hex(5), factory=factory,
                         objective=objective)
        self._save(run)
        self.audit.append("factory.started", "factory", {"run_id": run.run_id,
                                                         "factory": factory})
        return run

    def confirm(self, run: FactoryRun, item: str, by: str) -> None:
        if not by.startswith("human:"):
            raise PermissionError("checklist items are confirmed by a human")
        run.checklist[item] = {"by": by, "at": dt.datetime.now(dt.UTC).isoformat()}
        self._save(run)

    def advance(self, run: FactoryRun, max_stages: int = 100, on: dt.date | None = None
                ) -> FactoryRun:
        stages = self.defs[run.factory]["stages"]
        for _ in range(max_stages):
            if run.stage_index >= len(stages):
                run.status = "COMPLETED"
                run.waiting_on = ""
                break
            st = stages[run.stage_index]
            kind = st["type"]
            if kind == "agent":
                out = self.hooks["agent"](st["agent"], st["prompt"], run)
                run.outputs[st["id"]] = out
            elif kind == "tool":
                run.outputs[st["id"]] = self.hooks["tool"](st["capability"], run)
            elif kind == "checklist":
                missing = [i for i in st["items"] if i not in run.checklist]
                if missing:
                    run.status, run.waiting_on = "WAITING_CHECKLIST", f"{st['id']}: {missing}"
                    break
            elif kind == "gate":
                facts = run.gate_facts.get(st["domain"])
                if facts is None:
                    run.status = "WAITING_GATE"
                    run.waiting_on = f"{st['id']}: supply facts for gate {st['domain']}"
                    break
                d = self.engine.evaluate(st["domain"], facts, on=on)
                run.outputs[st["id"]] = d.to_dict()
                approved = st["domain"] in run.approvals
                if not d.may_proceed(approved=approved):
                    run.status = "WAITING_GATE"
                    run.waiting_on = (f"{st['id']}: {d.status} - "
                                      + "; ".join(f.message for f in d.blocking())[:300])
                    if d.status == Status.PASS_WITH_REVIEW:
                        run.waiting_on += " (needs signed approval)"
                    break
            elif kind == "approval":
                ref = run.approvals.get(st["capability"])
                if not ref or not self.hooks["approval_ok"](st["capability"], run, ref):
                    run.status = "WAITING_APPROVAL"
                    run.waiting_on = f"{st['id']}: signed approval for {st['capability']}"
                    break
            else:
                raise ValueError(f"unknown stage type {kind}")
            run.history.append({"stage": st["id"], "at": dt.datetime.now(dt.UTC).isoformat()})
            run.stage_index += 1
            run.status, run.waiting_on = "RUNNING", ""
            self._save(run)
        self._save(run)
        self.audit.append("factory.advanced", "factory", {
            "run_id": run.run_id, "status": run.status, "stage_index": run.stage_index})
        return run

