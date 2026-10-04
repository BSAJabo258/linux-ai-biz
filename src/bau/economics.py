"""Cost, revenue, budgets and the usage dashboard (spec §84-85, §102).

Every model call, API call and tool run records a cost line; every sale records
a revenue line. Budgets are enforced *before* work runs (spec §102: exceeded ->
PAUSE). Secret values never appear here - key health tracks names and dates only.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .home import bau_home
from .store import JsonlStore, YamlStore

COST_KINDS = {"model", "api", "gpu", "cpu", "storage", "network", "tool", "human_time",
              "distribution", "payment_fee", "royalty", "tax", "failure", "marketing"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _ts(rec: dict[str, Any]) -> dt.datetime:
    return dt.datetime.fromisoformat(rec["ts"])


class Ledger:
    def __init__(self, home: Path | None = None):
        base = (home or bau_home()) / "economics"
        self.costs = JsonlStore(base / "costs.jsonl")
        self.revenue = JsonlStore(base / "revenue.jsonl")
        self.hours = JsonlStore(base / "human_hours.jsonl")

    def cost(self, kind: str, usd: float, *, agent: str = "", job_id: str = "",
             mission_id: str = "", provider: str = "", model: str = "",
             tokens_in: int = 0, tokens_out: int = 0, note: str = "",
             when: dt.datetime | None = None) -> dict[str, Any]:
        if kind not in COST_KINDS:
            raise ValueError(f"unknown cost kind {kind}")
        if usd < 0:
            raise ValueError("cost cannot be negative")
        return self.costs.append({
            "ts": (when or _now()).isoformat(), "kind": kind, "usd": round(usd, 6),
            "agent": agent, "job_id": job_id, "mission_id": mission_id,
            "provider": provider, "model": model, "tokens_in": tokens_in,
            "tokens_out": tokens_out, "note": note})

    def sale(self, gross_usd: float, *, mission_id: str = "", factory: str = "",
             customer_ref: str = "", new_customer: bool = False, platform_fee: float = 0.0,
             payment_fee: float = 0.0, refund: bool = False,
             when: dt.datetime | None = None) -> dict[str, Any]:
        return self.revenue.append({
            "ts": (when or _now()).isoformat(), "gross_usd": round(gross_usd, 2),
            "platform_fee": platform_fee, "payment_fee": payment_fee,
            "mission_id": mission_id, "factory": factory, "customer_ref": customer_ref,
            "new_customer": new_customer, "refund": refund})

    def human_time(self, hours: float, *, mission_id: str = "", note: str = "",
                   when: dt.datetime | None = None) -> dict[str, Any]:
        return self.hours.append({"ts": (when or _now()).isoformat(), "hours": hours,
                                  "mission_id": mission_id, "note": note})

    def spent(self, *, agent: str | None = None, job_id: str | None = None,
              mission_id: str | None = None, since: dt.datetime | None = None) -> float:
        total = 0.0
        for r in self.costs:
            if agent is not None and r["agent"] != agent:
                continue
            if job_id is not None and r["job_id"] != job_id:
                continue
            if mission_id is not None and r["mission_id"] != mission_id:
                continue
            if since is not None and _ts(r) < since:
                continue
            total += r["usd"]
        return total


@dataclass
class Budget:
    per_job: float | None = None
    per_hour: float | None = None
    per_day: float | None = None
    per_mission: float | None = None


@dataclass
class Budgets:
    """Per-agent budgets (spec §102). Unknown agents get the default budget."""
    by_agent: dict[str, Budget] = field(default_factory=dict)
    default: Budget = field(default_factory=lambda: Budget(per_job=1.0, per_hour=2.0,
                                                           per_day=10.0, per_mission=5.0))

    @classmethod
    def load(cls, path: Path | None = None) -> Budgets:
        raw = YamlStore(path or (bau_home() / "config" / "budgets.yaml")).load()
        b = cls()
        if "default" in raw:
            b.default = Budget(**raw["default"])
        for agent, lim in (raw.get("agents") or {}).items():
            b.by_agent[agent] = Budget(**lim)
        return b

    def check(self, ledger: Ledger, agent: str, add_usd: float, job_id: str = "",
              mission_id: str = "", now: dt.datetime | None = None) -> tuple[bool, str]:
        now = now or _now()
        b = self.by_agent.get(agent, self.default)
        checks = [
            ("per_job", b.per_job, lambda: ledger.spent(agent=agent, job_id=job_id)
             if job_id else 0.0),
            ("per_mission", b.per_mission, lambda: ledger.spent(agent=agent,
                                                                mission_id=mission_id)
             if mission_id else 0.0),
            ("per_hour", b.per_hour, lambda: ledger.spent(
                agent=agent, since=now - dt.timedelta(hours=1))),
            ("per_day", b.per_day, lambda: ledger.spent(
                agent=agent, since=now - dt.timedelta(days=1))),
        ]
        for name, limit, spent in checks:
            if limit is not None and spent() + add_usd > limit:
                return False, f"{agent} would exceed {name} budget ${limit:.2f}"
        return True, ""


def metrics(ledger: Ledger, since: dt.datetime | None = None,
            jobs: list[Any] | None = None) -> dict[str, Any]:
    """Business metrics (spec §84). Every figure is computed from the ledgers."""
    def inside(r: dict[str, Any]) -> bool:
        return since is None or _ts(r) >= since

    sales = [r for r in ledger.revenue if inside(r)]
    costs = [r for r in ledger.costs if inside(r)]
    hours = sum(r["hours"] for r in ledger.hours if inside(r))
    revenue = sum(-r["gross_usd"] if r["refund"] else r["gross_usd"] for r in sales)
    fees = sum(r["platform_fee"] + r["payment_fee"] for r in sales)
    by_kind: dict[str, float] = {}
    for c in costs:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0.0) + c["usd"]
    direct = sum(v for k, v in by_kind.items()
                 if k in ("model", "api", "gpu", "cpu", "tool", "distribution", "royalty"))
    total_cost = sum(by_kind.values()) + fees
    ai_cost = by_kind.get("model", 0.0) + by_kind.get("api", 0.0) + by_kind.get("gpu", 0.0)
    customers = {r["customer_ref"] for r in sales if r["customer_ref"]}
    new_customers = sum(1 for r in sales if r["new_customer"])
    out: dict[str, Any] = {
        "revenue": round(revenue, 2),
        "costs_by_kind": {k: round(v, 4) for k, v in sorted(by_kind.items())},
        "fees": round(fees, 2),
        "gross_margin": round((revenue - fees - direct) / revenue, 4) if revenue else None,
        "net_margin": round((revenue - total_cost) / revenue, 4) if revenue else None,
        "profit": round(revenue - total_cost, 2),
        "profit_per_hour": round((revenue - total_cost) / hours, 2) if hours else None,
        "ai_cost_to_revenue": round(ai_cost / revenue, 4) if revenue else None,
        "customer_acquisition_cost": round(by_kind.get("marketing", 0.0) / new_customers, 2)
        if new_customers else None,
        "lifetime_value": round(revenue / len(customers), 2) if customers else None,
    }
    if jobs is not None:
        done = [j for j in jobs if j.status in ("COMPLETED", "FAILED")]
        out["failure_rate"] = (round(sum(1 for j in done if j.status == "FAILED") / len(done), 4)
                               if done else None)
        out["automation_pct"] = (round(sum(1 for j in done if not j.approvals) / len(done), 4)
                                 if done else None)
    return out


def usage_dashboard(ledger: Ledger, home: Path | None = None,
                    now: dt.datetime | None = None) -> dict[str, Any]:
    """MAYA usage dashboard (spec §85): spend, burn, runway, key health. No secret values."""
    now = now or _now()
    cfg = YamlStore((home or bau_home()) / "config" / "providers.yaml").load()
    out = {}
    week = now - dt.timedelta(days=7)
    for name, p in (cfg.get("providers") or {}).items():
        spend_7d = sum(r["usd"] for r in ledger.costs
                       if r["provider"] == name and _ts(r) >= week)
        burn = spend_7d / 7
        bal = p.get("balance_usd")
        rotated = p.get("key_rotated_at")
        age = (now.date() - dt.date.fromisoformat(str(rotated))).days if rotated else None
        out[name] = {
            "spend_total": round(sum(r["usd"] for r in ledger.costs
                                     if r["provider"] == name), 4),
            "burn_per_day": round(burn, 4),
            "balance_usd": bal,
            "runway_days": round(bal / burn, 1) if bal is not None and burn > 0 else None,
            "key_env_var": p.get("key_env_var"),       # the NAME only, never the value
            "key_age_days": age,
            "rotation_due": age is not None and age > int(p.get("rotate_every_days", 90)),
            "last_auth_failure": p.get("last_auth_failure"),
        }
    return out
