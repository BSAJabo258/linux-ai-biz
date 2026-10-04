"""Compliance policy compiler (spec §74, §113, §117).

Regulation is data: policies are YAML records that reference regulation
IDs and express requirements over *facts*. Domain modules (email, SMS,
subscriptions, disclosure...) only extract facts; every decision comes
from here, so there is exactly one decision path to audit.

Expression grammar (three-valued: True / False / None = fact missing):
    {all: [expr, ...]}   {any: [expr, ...]}   {not: expr}
    {fact: "a.b.c", <op>: value}
ops: eq ne in not_in gt gte lt lte exists matches not_matches contains
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .decision import Decision, Finding, Status
from .home import data_dir
from .jurisdiction import EEA_EXTRA, EU_MEMBERS
from .regulations import Registry

Expr = Callable[[dict[str, Any]], bool | None]
_MISSING = object()
OPS = {"eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "exists", "matches",
       "not_matches", "contains"}
FAIL_STATES = {"BLOCKED", "PASS_WITH_REVIEW", "UNKNOWN", "CONFLICT", "INCOMPLETE_FACTS"}


class PolicyError(ValueError):
    pass


def get_fact(facts: dict[str, Any], path: str) -> Any:
    cur: Any = facts
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


def _leaf(node: dict[str, Any]) -> Expr:
    path = node["fact"]
    ops = [k for k in node if k != "fact"]
    if len(ops) != 1 or ops[0] not in OPS:
        raise PolicyError(f"leaf on {path!r} needs exactly one op from {sorted(OPS)}")
    op, want = ops[0], node[ops[0]]
    rx = re.compile(want, re.IGNORECASE) if op in ("matches", "not_matches") else None

    def ev(facts: dict[str, Any]) -> bool | None:
        v = get_fact(facts, path)
        if op == "exists":
            return (v is not _MISSING and v is not None) == bool(want)
        if v is _MISSING or v is None:
            return None
        try:
            if op == "eq":
                return bool(v == want)
            if op == "ne":
                return bool(v != want)
            if op == "in":
                return v in want
            if op == "not_in":
                return v not in want
            if op == "gt":
                return bool(v > want)
            if op == "gte":
                return bool(v >= want)
            if op == "lt":
                return bool(v < want)
            if op == "lte":
                return bool(v <= want)
            if op == "contains":
                return want in v
            assert rx is not None
            hit = rx.search(str(v)) is not None
            return hit if op == "matches" else not hit
        except TypeError:
            return None

    return ev


def compile_expr(node: Any) -> Expr:
    if not isinstance(node, dict):
        raise PolicyError(f"expression must be a mapping, got {node!r}")
    if "all" in node or "any" in node:
        key = "all" if "all" in node else "any"
        parts = [compile_expr(n) for n in node[key]]

        def ev(facts: dict[str, Any]) -> bool | None:
            vals = [p(facts) for p in parts]
            if key == "all":
                if any(v is False for v in vals):
                    return False
                return None if any(v is None for v in vals) else True
            if any(v is True for v in vals):
                return True
            return None if any(v is None for v in vals) else False

        return ev
    if "not" in node:
        inner = compile_expr(node["not"])

        def neg(facts: dict[str, Any]) -> bool | None:
            v = inner(facts)
            return None if v is None else not v

        return neg
    if "fact" in node:
        return _leaf(node)
    raise PolicyError(f"unrecognised expression {node!r}")


def _missing_facts(node: Any, facts: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        if "fact" in node and "exists" not in node:
            if get_fact(facts, node["fact"]) in (_MISSING, None):
                out.append(node["fact"])
        for v in node.values():
            if isinstance(v, (dict, list)):
                out.extend(_missing_facts(v, facts))
    elif isinstance(node, list):
        for n in node:
            out.extend(_missing_facts(n, facts))
    return out


def jurisdiction_matches(policy_j: list[str], fact_j: list[str]) -> bool:
    if "ANY" in policy_j:
        return True
    return any(f == p or f.startswith(p + "-") for p in policy_j for f in fact_j)


@dataclass
class Policy:
    id: str
    domain: str
    scope: str
    stage: int
    title: str
    regs: list[str]
    jurisdictions: list[str]
    require: list[Any]
    when: Any = None
    on_fail: str = "BLOCKED"
    remediation: str = ""
    sets: dict[str, Any] = field(default_factory=dict)
    _when: Expr | None = None
    _require: list[Expr] = field(default_factory=list)

    def compile(self) -> None:
        if self.on_fail not in FAIL_STATES:
            raise PolicyError(f"{self.id}: on_fail must be one of {sorted(FAIL_STATES)}")
        self._when = compile_expr(self.when) if self.when is not None else None
        self._require = [compile_expr(r) for r in self.require]


class PolicyEngine:
    def __init__(self, policies: list[Policy], orderings: dict[str, list[Any]],
                 registry: Registry, coverage: dict[str, list[str]] | None = None):
        self.policies = policies
        self.orderings = orderings
        self.registry = registry
        # Jurisdictions each domain has a rule set for. Anything else is UNKNOWN,
        # because "no rule matched" must never read as "nothing applies".
        self.coverage = coverage or {}

    @classmethod
    def load(cls, registry: Registry, directory: Path | None = None) -> PolicyEngine:
        directory = directory or data_dir("policies")
        policies: list[Policy] = []
        orderings: dict[str, list[Any]] = {}
        coverage: dict[str, list[str]] = {}
        seen: set[str] = set()
        for path in sorted(directory.glob("*.yaml")):
            doc = yaml.safe_load(path.read_text()) or {}
            orderings.update(doc.get("orderings", {}))
            coverage.update(doc.get("coverage", {}))
            for raw in doc.get("policies", []):
                try:
                    p = Policy(**raw)
                    p.compile()
                except (TypeError, PolicyError) as e:
                    raise PolicyError(f"{path.name}: {raw.get('id', '?')}: {e}") from e
                if p.id in seen:
                    raise PolicyError(f"duplicate policy id {p.id}")
                missing = [r for r in p.regs if registry.get(r) is None]
                if missing:
                    # A dangling reference is a loose end; refuse to load rather than
                    # silently evaluating a policy against nothing.
                    raise PolicyError(f"{p.id}: references unknown regulations {missing}")
                for k, v in p.sets.items():
                    if k in orderings and v not in orderings[k]:
                        raise PolicyError(f"{p.id}: {k}={v!r} not in ordering {orderings[k]}")
                seen.add(p.id)
                policies.append(p)
        return cls(policies, orderings, registry, coverage)

    def for_domain(self, domain: str, scope: str | None = None) -> list[Policy]:
        return sorted((p for p in self.policies if p.domain == domain
                       and (scope is None or p.scope == scope)), key=lambda p: p.stage)

    def _reg_state(self, p: Policy, on: dt.date) -> tuple[str, list[str], bool, bool]:
        """Return (applicability, notes, any_stale, all_active)."""
        states, notes, stale, active = [], [], False, True
        for rid in p.regs:
            reg = self.registry.get(rid)
            assert reg is not None
            a = reg.applicability(on)
            states.append(a)
            if a in ("in_force", "unknown_date"):
                stale |= reg.is_stale(on)
                active &= reg.active and a == "in_force"
                if a == "unknown_date":
                    notes.append(f"{rid}: enacted, operative date unknown - "
                                 "enforced as a precaution")
            else:
                notes.append(f"{rid}: {a}")
        if not p.regs:
            # Internal BAU policy: nothing external to verify, so a pass is a pass.
            return "in_force", notes, False, True
        if any(s in ("in_force", "unknown_date") for s in states):
            return "in_force", notes, stale, active
        return "not_applicable", notes, False, False

    def evaluate(self, domain: str, facts: dict[str, Any], scope: str | None = None,
                 on: dt.date | None = None) -> Decision:
        on = on or dt.date.today()
        findings: list[Finding] = []
        settings: dict[str, list[tuple[Any, str]]] = {}
        juris = facts.get("jurisdictions")
        cov = self.coverage.get(domain)
        if juris and cov is not None:
            # Member states are covered by the EU rule set (national variations are a
            # documented gap: see docs/SPEC_GAP_ANALYSIS.md).
            eu_cov = "EU" in juris and jurisdiction_matches(cov, ["EU"])
            uncovered = [j for j in juris if not jurisdiction_matches(cov, [j])
                         and not (eu_cov and j in EU_MEMBERS | EEA_EXTRA)
                         and not any(j.startswith(c + "-") or c.startswith(j + "-")
                                     for c in cov)]
            if uncovered:
                # Nothing covered -> UNKNOWN. Partly covered -> a human must look at the gap.
                none_covered = not jurisdiction_matches(cov, juris)
                findings.append(Finding(
                    rule_id=f"{domain}.coverage",
                    status=Status.UNKNOWN if none_covered else Status.PASS_WITH_REVIEW,
                    stage=0, message=f"no {domain} rule set for jurisdiction(s) {uncovered}",
                    remediation="add regulations/policies for this jurisdiction, exclude it, "
                                "or have counsel confirm no specific rule applies"))
        for p in self.for_domain(domain, scope):
            base = dict(rule_id=p.id, stage=p.stage, regs=p.regs, remediation=p.remediation)
            if not juris:
                findings.append(Finding(status=Status.UNKNOWN,
                                        message=f"{p.title}: jurisdiction undetermined", **base))
                continue
            if not jurisdiction_matches(p.jurisdictions, juris):
                continue
            applic, notes, stale, active = self._reg_state(p, on)
            if applic == "not_applicable":
                findings.append(Finding(status=Status.NOT_APPLICABLE, message=p.title,
                                        detail={"notes": notes}, **base))
                continue
            if p._when is not None:
                w = p._when(facts)
                if w is None:
                    findings.append(Finding(
                        status=Status.INCOMPLETE_FACTS,
                        message=f"{p.title}: cannot tell whether this applies",
                        detail={"missing": _missing_facts(p.when, facts)}, **base))
                    continue
                if not w:
                    continue
            results = [r(facts) for r in p._require]
            if any(r is False for r in results):
                failed = [p.require[i] for i, r in enumerate(results) if r is False]
                findings.append(Finding(status=Status(p.on_fail), message=p.title,
                                        detail={"failed": failed, "notes": notes}, **base))
                continue
            if any(r is None for r in results):
                findings.append(Finding(status=Status.INCOMPLETE_FACTS, message=p.title,
                                        detail={"missing": _missing_facts(p.require, facts),
                                                "notes": notes}, **base))
                continue
            for k, v in p.sets.items():
                settings.setdefault(k, []).append((v, p.id))
            if stale:
                status, msg = Status.EXPIRED, f"{p.title}: rule verification is past due"
            elif not active:
                status, msg = Status.PASS_WITH_REVIEW, f"{p.title} (rule not yet ACTIVE in BAU)"
            else:
                status, msg = Status.PASS, p.title
            findings.append(Finding(status=status, message=msg, detail={"notes": notes}, **base))
        resolved = self._resolve(settings, findings)
        return Decision(scope=f"{domain}:{scope or '*'}", findings=findings, resolved=resolved)

    def _resolve(self, settings: dict[str, list[tuple[Any, str]]],
                 findings: list[Finding]) -> dict[str, Any]:
        """Jurisdictions disagree -> strictest wins if ordered, else CONFLICT (spec §117)."""
        out: dict[str, Any] = {}
        for key, vals in settings.items():
            distinct = {v for v, _ in vals}
            if len(distinct) == 1:
                out[key] = vals[0][0]
            elif key in self.orderings:
                order = self.orderings[key]
                out[key] = max(distinct, key=order.index)
            else:
                findings.append(Finding(
                    rule_id=f"conflict.{key}", status=Status.CONFLICT, stage=999,
                    message=f"jurisdictions require different {key}: {sorted(map(str, distinct))}",
                    detail={"sources": [pid for _, pid in vals]}))
        return out
