"""Tax nexus engine (spec §68-71).

Thresholds are data with effective dates and a verification stamp; nothing
is hard-coded. A rule nobody has verified yields UNKNOWN, never "no nexus".
The output is a flag for a CPA, not tax advice.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from ..home import bau_home

POTENTIAL, CONFIRMED, NONE, UNKNOWN = ("POTENTIAL_NEXUS", "CONFIRMED_NEXUS", "NO_CURRENT_NEXUS",
                                       "UNKNOWN")


@dataclass
class NexusRule:
    jurisdiction: str
    sales_threshold: Decimal | None
    transactions_threshold: int | None
    combinator: str                 # "or" | "and"
    measurement: str                # e.g. previous_or_current_calendar_year
    effective_date: dt.date
    expiration_date: dt.date | None
    source_url: str
    last_verified: dt.date | None
    next_review: dt.date | None

    def usable(self, on: dt.date) -> tuple[bool, str]:
        if self.last_verified is None:
            return False, "rule never verified against the official source"
        if self.next_review is None or self.next_review < on:
            return False, "rule verification is past due"
        if self.effective_date > on or (self.expiration_date and self.expiration_date < on):
            return False, "rule not in effect on this date"
        return True, ""


def load_rules(path: Path | None = None) -> dict[str, NexusRule]:
    path = path or (bau_home() / "tax")
    f = path / "nexus_rules.yaml" if path.is_dir() else path
    rules: dict[str, NexusRule] = {}
    if not f.exists():
        return rules
    for r in yaml.safe_load(f.read_text()) or []:
        def d(k: str, r: dict[str, Any] = r) -> dt.date | None:
            v = r.get(k)
            return dt.date.fromisoformat(str(v)) if v else None
        rules[r["jurisdiction"]] = NexusRule(
            jurisdiction=r["jurisdiction"],
            sales_threshold=Decimal(str(r["sales_threshold"])) if r.get("sales_threshold")
            is not None else None,
            transactions_threshold=r.get("transactions_threshold"),
            combinator=r.get("combinator", "or"), measurement=r["measurement"],
            effective_date=d("effective_date") or dt.date.min,
            expiration_date=d("expiration_date"), source_url=r["source_url"],
            last_verified=d("last_verified"), next_review=d("next_review"))
    return rules


def assess(jurisdiction: str, sales: Decimal, transactions: int, rules: dict[str, NexusRule],
           physical_presence: bool | None, on: dt.date,
           marketplace_only: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"jurisdiction": jurisdiction, "sales": str(sales),
                           "transactions": transactions, "on": on.isoformat()}
    if physical_presence:
        return dict(out, status=CONFIRMED, reason="physical presence (verify with CPA)")
    rule = rules.get(jurisdiction)
    if rule is None:
        return dict(out, status=UNKNOWN, reason="no nexus rule on file - escalate")
    ok, why = rule.usable(on)
    if not ok:
        return dict(out, status=UNKNOWN, reason=why, source=rule.source_url)
    hits = []
    if rule.sales_threshold is not None:
        hits.append(sales >= rule.sales_threshold)
    if rule.transactions_threshold is not None:
        hits.append(transactions >= rule.transactions_threshold)
    crossed = any(hits) if rule.combinator == "or" else all(hits) if hits else False
    if crossed:
        reason = "economic threshold crossed"
        if marketplace_only:
            reason += "; marketplace facilitator may collect - confirm registration duty"
        return dict(out, status=POTENTIAL, reason=reason, source=rule.source_url,
                    measurement=rule.measurement)
    if physical_presence is None:
        return dict(out, status=UNKNOWN, reason="physical-presence facts missing")
    return dict(out, status=NONE, reason="below thresholds on verified rule",
                source=rule.source_url, measurement=rule.measurement)
