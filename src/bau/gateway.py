"""Universal Gateway (spec §50): the only path from an agent to a capability.

Every call runs the same checks in the same order, and every outcome -
allowed or denied - is written to the audit chain:

  1. capability registered and handler bound      (no hidden execution paths)
  2. agent may use this tool                       (agent's own tool list)
  3. not revoked; permission level; human approval (spec §49, §55)
  4. network trust allows this level              (spec §52)
  5. data may leave to this provider               (spec §83, §101)
  6. blast radius; HIGH/CRITICAL need approval     (spec §54)
  7. budget has room                               (spec §102)
  8. execute, record cost, record evidence
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import blast, network
from .audit import AuditLog
from .datagov import provider_allows
from .economics import Budgets, Ledger
from .security.permissions import Approval, CapabilityTable, PermissionDenied

VERBS = {"discover", "search", "inspect", "status", "run", "build", "test", "browser", "files",
         "project", "workflow", "artifact", "checkpoint", "resume", "verify", "revoke",
         "model", "media", "spatial", "publish", "email", "sms", "payment", "move", "memory",
         "github", "delete", "change", "regulation", "system", "data", "genesis", "factory"}


class GatewayDenied(PermissionError):
    def __init__(self, step: str, reason: str):
        super().__init__(f"{step}: {reason}")
        self.step = step
        self.reason = reason


class WaitingForNetwork(GatewayDenied):
    pass


@dataclass
class Handler:
    fn: Callable[..., Any]
    level: str
    needs_network: bool = False
    provider: str | None = None          # external provider id, if data leaves the machine
    estimate_usd: Callable[[dict[str, Any]], float] = field(default=lambda args: 0.0)
    description: str = ""


@dataclass
class CallRequest:
    agent: str
    capability: str
    args: dict[str, Any] = field(default_factory=dict)
    data_classes: list[str] = field(default_factory=list)
    blast: blast.Factors | None = None
    approval: Approval | None = None
    job_id: str = ""
    mission_id: str = ""


class Gateway:
    def __init__(self, table: CapabilityTable | None = None, audit: AuditLog | None = None,
                 ledger: Ledger | None = None, budgets: Budgets | None = None,
                 providers: dict[str, dict[str, Any]] | None = None,
                 authority: Any = None, trust: Callable[[], network.Trust] | None = None,
                 agent_tools: dict[str, list[str]] | None = None):
        self.table = table or CapabilityTable()
        self.audit = audit or AuditLog()
        self.ledger = ledger or Ledger()
        self.budgets = budgets or Budgets()
        self.providers = providers or {}
        self.authority = authority
        self.trust = trust or (lambda: network.TrustPolicy().classify(network.detect()))
        self.agent_tools = agent_tools or {}
        self.handlers: dict[str, Handler] = {}

    def register(self, capability: str, handler: Handler) -> None:
        verb = capability.split(".", 1)[0]
        if verb not in VERBS:
            raise ValueError(f"unknown gateway verb {verb!r}")
        self.table.levels.setdefault(capability, handler.level)
        self.handlers[capability] = handler

    def _deny(self, req: CallRequest, step: str, reason: str,
              exc: type[GatewayDenied] = GatewayDenied) -> GatewayDenied:
        self.audit.append("gateway.denied", req.agent, {
            "capability": req.capability, "step": step, "reason": reason[:300],
            "job_id": req.job_id, "mission_id": req.mission_id})
        return exc(step, reason)

    def check(self, req: CallRequest) -> dict[str, Any]:
        """Run steps 1-7 without executing. Used for dry runs and plan validation."""
        h = self.handlers.get(req.capability)
        if h is None:
            raise self._deny(req, "registered", "no handler bound to this capability")
        allowed = self.agent_tools.get(req.agent)
        if allowed is not None and req.capability not in allowed:
            raise self._deny(req, "agent_tools", f"{req.agent} is not granted {req.capability}")
        b = blast.score(req.blast) if req.blast else {"level": "LOW",
                                                       "requires_approval": False}
        try:
            level = self.table.authorize(
                req.agent, req.capability, req.approval, self.authority,
                min_level="APPROVAL_REQUIRED" if b["requires_approval"] else None)
        except PermissionDenied as e:
            raise self._deny(req, "permission", str(e)) from e
        trust = self.trust()
        if h.needs_network and trust == network.Trust.OFFLINE:
            raise self._deny(req, "network", "offline - job must WAIT_FOR_NETWORK",
                             WaitingForNetwork)
        if not network.allows(trust, level):
            raise self._deny(req, "network", f"{trust} network cannot run {level} actions")
        if h.provider is not None:
            ok, why = provider_allows(self.providers.get(h.provider), req.data_classes)
            if not ok:
                raise self._deny(req, "data_boundary", why)
        est = float(h.estimate_usd(req.args))
        ok, why = self.budgets.check(self.ledger, req.agent, est, req.job_id, req.mission_id)
        if not ok:
            raise self._deny(req, "budget", why)
        return {"level": level, "blast": b["level"], "trust": str(trust), "estimate_usd": est}

    def invoke(self, req: CallRequest) -> Any:
        info = self.check(req)
        h = self.handlers[req.capability]
        started = time.monotonic()
        try:
            result = h.fn(**req.args)
        except Exception as e:
            self.audit.append("gateway.failed", req.agent, {
                "capability": req.capability, "error": type(e).__name__,
                "job_id": req.job_id, "mission_id": req.mission_id})
            raise
        cost = result.get("cost_usd", info["estimate_usd"]) if isinstance(result, dict) \
            else info["estimate_usd"]
        if cost:
            self.ledger.cost("tool" if h.provider is None else "api", float(cost),
                             agent=req.agent, job_id=req.job_id, mission_id=req.mission_id,
                             provider=h.provider or "", note=req.capability)
        self.audit.append("gateway.invoked", req.agent, {
            "capability": req.capability, "level": info["level"], "blast": info["blast"],
            "trust": info["trust"], "cost_usd": cost, "job_id": req.job_id,
            "mission_id": req.mission_id,
            "ms": int((time.monotonic() - started) * 1000),
            "at": dt.datetime.now(dt.UTC).isoformat()})
        return result

    def catalog(self) -> list[dict[str, Any]]:
        return [{"capability": c, "level": self.table.levels.get(c, h.level),
                 "revoked": c in self.table.revoked, "needs_network": h.needs_network,
                 "provider": h.provider, "description": h.description}
                for c, h in sorted(self.handlers.items())]
