"""IP ledger, monetization gate and royalty engine (spec §15, §64, §66-67, §81).

The system never claims "this AI-generated work is copyrighted". It records
human contribution and lets counsel decide. Unknown ownership blocks money.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from .. import jurisdiction
from ..decision import Decision
from ..policy import PolicyEngine

RIGHTS = ["music", "image", "video", "voice", "font", "stock", "model_license", "data_license",
          "character", "trademark", "likeness", "location", "archival"]


@dataclass
class IPAsset:
    ip_asset_id: str
    title: str
    owners: dict[str, Decimal]                       # party -> percent
    license: str | None
    commercial_rights: bool | None
    ai_contribution: str                             # none | assisted | generated
    human_contribution: list[str] = field(default_factory=list)
    model: str | None = None
    model_license_commercial: bool | None = None
    source_assets: list[str] = field(default_factory=list)
    rights: dict[str, str] = field(default_factory=dict)  # right -> cleared|not_used|unresolved
    royalty_splits: dict[str, Decimal] = field(default_factory=dict)  # payee -> percent
    copyright_claim_reviewed: bool = False  # counsel reviewed any claim over AI-generated parts

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["owners"] = {k: str(v) for k, v in self.owners.items()}
        d["royalty_splits"] = {k: str(v) for k, v in self.royalty_splits.items()}
        return d


def monetize_facts(a: IPAsset, market_country: str | None) -> dict[str, Any]:
    unresolved = [r for r in RIGHTS if a.rights.get(r, "unresolved") == "unresolved"]
    return {
        "jurisdictions": jurisdiction.resolve(market_country)[0],
        "ip": {
            "owner_known": bool(a.owners) and "UNKNOWN" not in a.owners,
            "ownership_sums_to_100": sum(a.owners.values(), Decimal(0)) == Decimal(100),
            "license_known": a.license is not None,
            "commercial_rights": a.commercial_rights,
            "model_license_commercial": a.model_license_commercial
            if a.ai_contribution != "none" else True,
            "unresolved_rights": unresolved,
            "unresolved_rights_count": len(unresolved),
            "human_contribution_recorded": bool(a.human_contribution)
            or a.ai_contribution == "none",
            "ai_contribution": a.ai_contribution,
            "copyright_claim_reviewed": a.copyright_claim_reviewed,
        },
    }


def check_monetization(a: IPAsset, engine: PolicyEngine, market_country: str | None = "US",
                       on: dt.date | None = None) -> Decision:
    return engine.evaluate("monetize", monetize_facts(a, market_country),
                           on=on or dt.date.today())


CENT = Decimal("0.01")


def royalty_statement(a: IPAsset, gross: Decimal, platform_fee: Decimal,
                      payment_fee: Decimal, withholding_pct: dict[str, Decimal] | None = None
                      ) -> dict[str, Any]:
    """Split net revenue. Refuses when ownership/splits are unresolved (spec §67)."""
    if not a.owners or "UNKNOWN" in a.owners:
        raise ValueError("ownership unresolved: no payment may be released")
    splits = a.royalty_splits or a.owners
    if sum(splits.values(), Decimal(0)) != Decimal(100):
        raise ValueError("royalty splits do not sum to 100%")
    net = gross - platform_fee - payment_fee
    if net < 0:
        raise ValueError("fees exceed gross revenue")
    withholding_pct = withholding_pct or {}
    lines, allocated = [], Decimal(0)
    payees = sorted(splits)
    for i, payee in enumerate(payees):
        share = (net * splits[payee] / 100).quantize(CENT, ROUND_HALF_EVEN)
        if i == len(payees) - 1:
            share = net - allocated  # rounding remainder goes to the last payee, never lost
        allocated += share
        wh = (share * withholding_pct.get(payee, Decimal(0)) / 100).quantize(CENT)
        lines.append({"payee": payee, "percent": str(splits[payee]), "gross_share": str(share),
                      "withholding": str(wh), "payable": str(share - wh)})
    return {"ip_asset_id": a.ip_asset_id, "gross": str(gross), "platform_fee": str(platform_fee),
            "payment_fee": str(payment_fee), "net": str(net), "lines": lines}
