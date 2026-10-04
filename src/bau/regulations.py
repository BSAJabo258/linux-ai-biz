"""Regulation registry (spec §11, §92-93, §114-118).

Two lifecycles are kept apart because conflating them is how a vacated
rule ends up enforced as law (or a proposed one treated as final):

* ``legal_status``  - what the law itself is doing in the world.
* ``bau_status``    - how far BAU has verified and implemented it.

Asymmetry rule: an unverified rule can add restrictions but can never
grant permission. A policy that passes against a rule that is not ACTIVE
yields PASS_WITH_REVIEW, never a clean PASS.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .home import data_dir

LEGAL_STATUSES = {
    "proposed",            # bill, ANPRM, NPRM, draft - not law (spec §93)
    "enacted",             # signed/final but not yet operative
    "effective",
    "partially_effective",
    "enjoined",
    "vacated",
    "superseded",
    "repealed",
    "industry_requirement",  # mailbox-provider / platform / card-network rules
    "standard",              # NIST, WCAG, etc.
    "guidance",              # agency guidance: persuasive, not statute
}
IN_FORCE_STATUSES = {"effective", "partially_effective", "industry_requirement", "standard",
                     "guidance"}
DEAD_STATUSES = {"vacated", "repealed", "superseded", "enjoined"}

BAU_STATUSES = ["PROPOSED", "VERIFIED", "MAPPED", "IMPLEMENTED", "TESTED", "ACTIVE", "RETIRED"]

SOURCE_PRIORITY = [
    "statute", "final_regulation", "official_guidance", "official_interpretation",
    "court_decision", "standard", "industry_policy", "secondary_analysis", "news",
    "social_media",
]

REQUIRED = ["reg_id", "jurisdiction", "authority", "law", "legal_status", "bau_status",
            "obligations", "source_url", "source_type", "last_verified", "next_review",
            "legal_review_required"]


class RegistryError(ValueError):
    pass


def _date(v: Any) -> dt.date | None:
    if v in (None, "", "TBD"):
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v))


@dataclass
class Regulation:
    raw: dict[str, Any]
    reg_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.reg_id = self.raw["reg_id"]

    def __getitem__(self, k: str) -> Any:
        return self.raw.get(k)

    @property
    def effective_date(self) -> dt.date | None:
        return _date(self.raw.get("effective_date"))

    @property
    def next_review(self) -> dt.date | None:
        return _date(self.raw.get("next_review"))

    def applicability(self, on: dt.date) -> str:
        """Return in_force | future | unknown_date | not_law | dead (spec §115)."""
        ls = self.raw["legal_status"]
        if ls in DEAD_STATUSES:
            return "dead"
        if ls == "proposed":
            return "not_law"
        eff = self.effective_date
        if ls == "enacted":
            if eff is None:
                return "unknown_date"
            return "in_force" if eff <= on else "future"
        if eff is not None and eff > on:
            return "future"
        expires = _date(self.raw.get("expiration_date"))
        if expires is not None and expires < on:
            return "dead"
        return "in_force"

    def is_stale(self, on: dt.date) -> bool:
        nr = self.next_review
        return nr is None or nr < on

    @property
    def active(self) -> bool:
        return self.raw["bau_status"] == "ACTIVE"


def validate_record(rec: dict[str, Any]) -> list[str]:
    errs = [f"missing field: {k}" for k in REQUIRED if k not in rec]
    if errs:
        return errs
    if rec["legal_status"] not in LEGAL_STATUSES:
        errs.append(f"bad legal_status {rec['legal_status']!r}")
    if rec["bau_status"] not in BAU_STATUSES:
        errs.append(f"bad bau_status {rec['bau_status']!r}")
    if rec["source_type"] not in SOURCE_PRIORITY:
        errs.append(f"bad source_type {rec['source_type']!r}")
    if rec["source_type"] in ("news", "social_media") and rec["bau_status"] not in (
            "PROPOSED",):
        errs.append("news/social sources may discover a change but cannot establish it")
    if rec["bau_status"] == "ACTIVE" and rec["legal_status"] in ("proposed",):
        errs.append("a proposed rule cannot be ACTIVE (spec §93)")
    if rec["bau_status"] == "ACTIVE" and not rec.get("reviewed_by"):
        errs.append("ACTIVE requires reviewed_by (human sign-off)")
    if not isinstance(rec["obligations"], list) or not rec["obligations"]:
        errs.append("obligations must be a non-empty list")
    for k in ("effective_date", "last_verified", "next_review", "expiration_date"):
        try:
            _date(rec.get(k))
        except ValueError:
            errs.append(f"{k} is not an ISO date")
    if not str(rec["source_url"]).startswith("https://"):
        errs.append("source_url must be https")
    return errs


class Registry:
    def __init__(self, regs: dict[str, Regulation]):
        self.regs = regs

    @classmethod
    def load(cls, directory: Path | None = None) -> Registry:
        directory = directory or data_dir("regulations")
        regs: dict[str, Regulation] = {}
        problems: list[str] = []
        for path in sorted(directory.glob("*.yaml")):
            docs = yaml.safe_load(path.read_text()) or []
            for rec in docs:
                errs = validate_record(rec)
                if errs:
                    problems.append(f"{path.name}:{rec.get('reg_id', '?')}: {'; '.join(errs)}")
                    continue
                if rec["reg_id"] in regs:
                    problems.append(f"{path.name}: duplicate reg_id {rec['reg_id']}")
                    continue
                regs[rec["reg_id"]] = Regulation(rec)
        if problems:
            raise RegistryError("\n".join(problems))
        return cls(regs)

    def get(self, reg_id: str) -> Regulation | None:
        return self.regs.get(reg_id)

    def __iter__(self):
        return iter(self.regs.values())

    def due_for_review(self, on: dt.date, within_days: int = 0) -> list[Regulation]:
        horizon = on + dt.timedelta(days=within_days)
        return [r for r in self if r.next_review is None or r.next_review <= horizon]

    def upcoming(self, on: dt.date, within_days: int = 90) -> list[Regulation]:
        horizon = on + dt.timedelta(days=within_days)
        return [r for r in self if r.applicability(on) == "future"
                and r.effective_date is not None and r.effective_date <= horizon]


def _normalize(html: bytes) -> str:
    text = html.decode("utf-8", "replace")
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_url(url: str, timeout: int = 20, max_bytes: int = 5_000_000) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "BAU-regwatch/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https only)
            return resp.read(max_bytes)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def watch(registry: Registry, state_path: Path, on: dt.date,
          fetch: Callable[[str], bytes | None] = fetch_url) -> dict[str, Any]:
    """Discovery tripwire for official sources (spec §92).

    A changed page is DISCOVERED, not law: it is flagged for a human to verify
    and map (spec §93). Pages change for trivial reasons too; that is acceptable
    for a tripwire whose cost of a false alarm is one human look.
    """
    state: dict[str, Any] = json.loads(state_path.read_text()) if state_path.exists() else {}
    urls: dict[str, list[str]] = {}
    for r in registry:
        urls.setdefault(r["source_url"], []).append(r.reg_id)
    changed, unreachable = [], []
    for url, ids in sorted(urls.items()):
        body = fetch(url)
        entry = state.setdefault(url, {"reg_ids": ids})
        entry["reg_ids"] = ids
        entry["last_checked"] = on.isoformat()
        if body is None:
            unreachable.append(url)
            continue
        digest = hashlib.sha256(_normalize(body).encode()).hexdigest()
        if entry.get("hash") and entry["hash"] != digest:
            entry["changed_at"] = on.isoformat()
            changed.append({"url": url, "reg_ids": ids})
        entry["hash"] = digest
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True))
    return {"checked": len(urls), "changed": changed, "unreachable": unreachable}


def promote(path: Path, reg_id: str, to: str, reviewer: str, on: dt.date) -> dict[str, Any]:
    """Move a regulation one step along BAU's lifecycle. Skipping steps is refused."""
    if to not in BAU_STATUSES:
        raise RegistryError(f"unknown status {to}")
    docs = yaml.safe_load(path.read_text()) or []
    for rec in docs:
        if rec["reg_id"] != reg_id:
            continue
        cur = BAU_STATUSES.index(rec["bau_status"])
        nxt = BAU_STATUSES.index(to)
        if to != "RETIRED" and nxt != cur + 1:
            raise RegistryError(f"{reg_id}: {rec['bau_status']} -> {to} skips lifecycle steps")
        if to == "ACTIVE" and rec["legal_status"] == "proposed":
            raise RegistryError("proposed rules cannot become ACTIVE")
        rec["bau_status"] = to
        rec["reviewed_by"] = reviewer
        rec["last_verified"] = on.isoformat()
        errs = validate_record(rec)
        if errs:
            raise RegistryError("; ".join(errs))
        path.write_text(yaml.safe_dump(docs, sort_keys=False, allow_unicode=True))
        return rec
    raise RegistryError(f"{reg_id} not found in {path}")
