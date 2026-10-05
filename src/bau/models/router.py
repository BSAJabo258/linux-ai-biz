"""Model router (spec §45, §83).

Hard filters first (never traded off against quality):
  routable status, commercial licence, data may go to that provider, context
  fits, tools / modality supported, offline -> local only, health.
Then score what is left on quality, cost, latency and privacy.
Deterministic work gets no model at all (spec §45).

Content lane: a model approved with ``lane: content_only`` (e.g. an abliterated
local model) is considered ONLY for the job kinds its record lists in ``use_for``,
only when the task needs no tools and carries no data beyond PUBLIC/INTERNAL.
For those jobs it is preferred (the owner listed it because it does them best);
for every other job it does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..datagov import provider_allows
from ..registry import CONTENT_LANE

LANE_DATA = {"PUBLIC", "INTERNAL"}

DETERMINISTIC = {"arithmetic", "format", "validate", "hash", "lookup", "schedule", "sort",
                 "regex", "template"}


@dataclass
class TaskSpec:
    kind: str                                   # reasoning, coding, writing, research, ...
    data_classes: list[str] = field(default_factory=lambda: ["INTERNAL"])
    min_quality: float = 0.0
    context_tokens: int = 0
    needs_tools: bool = False
    input_types: list[str] = field(default_factory=lambda: ["text"])
    offline: bool = False
    max_cost_per_mtok_out: float | None = None
    max_latency_ms: int | None = None
    prefer: str = "balanced"                    # quality | cost | balanced | private


@dataclass
class Route:
    model: dict[str, Any] | None
    reason: str
    candidates: list[dict[str, Any]]
    rejected: dict[str, str]


def route(task: TaskSpec, models: list[dict[str, Any]], providers: dict[str, dict[str, Any]],
          health: dict[str, bool] | None = None) -> Route:
    if task.kind in DETERMINISTIC:
        return Route(None, "deterministic task: use a tool, not a model", [], {})
    health = health or {}
    rejected: dict[str, str] = {}
    ok: list[dict[str, Any]] = []
    for m in models:
        mid = m["model_id"]
        if m.get("status") not in ("APPROVED", "ACTIVE"):
            rejected[mid] = f"status {m.get('status')}"
            continue
        if m.get("commercial_use") is not True:
            rejected[mid] = "licence does not allow commercial use"
            continue
        if m.get("lane") == CONTENT_LANE:
            if task.kind not in (m.get("use_for") or []):
                rejected[mid] = f"content lane: not designated for {task.kind}"
                continue
            if task.needs_tools:
                rejected[mid] = "content lane: no tools"
                continue
            if not set(task.data_classes) <= LANE_DATA:
                rejected[mid] = "content lane: public/internal data only"
                continue
        local = m.get("deployment") == "local"
        if task.offline and not local:
            rejected[mid] = "offline: local models only"
            continue
        if not local:
            allowed, why = provider_allows(providers.get(m["provider"]), task.data_classes)
            if not allowed:
                rejected[mid] = f"data boundary: {why}"
                continue
        if task.context_tokens and int(m.get("context", 0)) < task.context_tokens:
            rejected[mid] = "context too small"
            continue
        if task.needs_tools and not m.get("tools", False):
            rejected[mid] = "no tool support"
            continue
        if not set(task.input_types) <= set(m.get("input_types", ["text"])):
            rejected[mid] = "input type unsupported"
            continue
        if health.get(mid) is False:
            rejected[mid] = "unhealthy"
            continue
        if float(m.get("quality", 0)) < task.min_quality:
            rejected[mid] = "below quality floor"
            continue
        cost = float(m.get("cost_out_per_mtok", 0))
        if task.max_cost_per_mtok_out is not None and cost > task.max_cost_per_mtok_out:
            rejected[mid] = "over cost ceiling"
            continue
        lat = int(m.get("latency_ms", 0))
        if task.max_latency_ms is not None and lat > task.max_latency_ms:
            rejected[mid] = "too slow"
            continue
        ok.append(m)
    if not ok:
        return Route(None, "no model satisfies the hard constraints", [], rejected)
    weights = {"quality": (0.7, 0.15, 0.15, 0.0), "cost": (0.3, 0.55, 0.15, 0.0),
               "balanced": (0.5, 0.3, 0.2, 0.0), "private": (0.4, 0.2, 0.1, 0.3)}[task.prefer]
    max_cost = max(float(m.get("cost_out_per_mtok", 0)) for m in ok) or 1.0
    max_lat = max(int(m.get("latency_ms", 0)) for m in ok) or 1

    def score(m: dict[str, Any]) -> float:
        q = float(m.get("quality", 0))
        c = 1 - float(m.get("cost_out_per_mtok", 0)) / max_cost
        lat = 1 - int(m.get("latency_ms", 0)) / max_lat
        p = 1.0 if m.get("deployment") == "local" else 0.0
        return weights[0] * q + weights[1] * c + weights[2] * lat + weights[3] * p

    ranked = sorted(ok, key=lambda m: (m.get("lane") == CONTENT_LANE, score(m)),
                    reverse=True)
    best = ranked[0]
    if best.get("lane") == CONTENT_LANE:
        return Route(best, f"content lane: owner-designated for {task.kind}", ranked,
                     rejected)
    return Route(best, f"best {task.prefer} score among {len(ranked)} eligible", ranked,
                 rejected)


def estimate_usd(model: dict[str, Any], tokens_in: int, tokens_out: int) -> float:
    return (tokens_in * float(model.get("cost_in_per_mtok", 0))
            + tokens_out * float(model.get("cost_out_per_mtok", 0))) / 1_000_000
