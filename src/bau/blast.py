"""Blast radius (spec §54): how bad is it if this action goes wrong?

Each factor scores 0-3; the worst single factor sets a floor, so one
irreversible, external, money-moving action can never average out to LOW.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass
class Factors:
    data_affected: int = 0        # 0 none, 1 internal, 2 personal, 3 sensitive/bulk personal
    systems_affected: int = 0     # 0 one sandbox, 1 one system, 2 several, 3 core/all
    financial_usd: float = 0.0
    external_visibility: int = 0  # 0 private, 1 one customer, 2 public post, 3 mass send
    irreversible: bool = False
    credentials: bool = False
    customers_affected: int = 0
    legal_exposure: int = 0       # 0 none ... 3 regulated / high penalty


def _money(usd: float) -> int:
    return 0 if usd <= 0 else 1 if usd < 100 else 2 if usd < 2000 else 3


def _people(n: int) -> int:
    return 0 if n == 0 else 1 if n < 10 else 2 if n < 1000 else 3


def score(f: Factors) -> dict[str, object]:
    parts = {
        "data": f.data_affected,
        "systems": f.systems_affected,
        "financial": _money(f.financial_usd),
        "visibility": f.external_visibility,
        "irreversible": 3 if f.irreversible else 0,
        "credentials": 3 if f.credentials else 0,
        "customers": _people(f.customers_affected),
        "legal": f.legal_exposure,
    }
    worst = max(parts.values())
    total = sum(parts.values())
    idx = max(worst - (0 if worst == 3 else 1), 0)
    if total >= 10:
        idx = max(idx, 3)
    elif total >= 6:
        idx = max(idx, 2)
    elif total >= 3:
        idx = max(idx, 1)
    if f.irreversible and (f.financial_usd > 0 or f.external_visibility >= 2):
        idx = 3
    return {"level": LEVELS[idx], "parts": parts, "factors": asdict(f),
            "requires_approval": idx >= 2}
