"""Accounting evidence, payees, 1099 tracking, payouts (spec §66-73).

Every business transaction keeps the evidence spec §72 lists. Payouts are
*prepared* here and *executed* only through the gateway's ``move.money``
capability (CRITICAL: signed human approval), after ownership, tax-form and
sanctions checks pass. This module never touches bank credentials.
"""

from __future__ import annotations

import datetime as dt
import secrets
from decimal import Decimal
from pathlib import Path
from typing import Any

from .home import bau_home
from .store import JsonlStore, YamlStore

TX_KINDS = {"invoice", "receipt", "order", "payment", "refund", "tax", "commission",
            "royalty", "expense"}
REQUIRED = ["kind", "amount", "currency", "date", "counterparty_ref", "description",
            "evidence_ref"]

# Information-return thresholds by calendar year of payment. Verify yearly with a CPA.
# 2026+: One Big Beautiful Bill Act raised the $600 NEC/MISC thresholds to $2,000
# (indexed after 2026). Royalties keep their separate $10 line on Form 1099-MISC.
THRESHOLDS = {
    2025: {"nonemployee_comp": Decimal(600), "rents": Decimal(600), "other": Decimal(600),
           "royalties": Decimal(10)},
    2026: {"nonemployee_comp": Decimal(2000), "rents": Decimal(2000),
           "other": Decimal(2000), "royalties": Decimal(10)},
}
BACKUP_WITHHOLDING_RATE = Decimal(24)
THRESHOLD_NOTE = ("2026 figures from OBBBA reporting (secondary sources); royalty $10 "
                  "line assumed unchanged - confirm with a CPA before filing")


class Books:
    def __init__(self, home: Path | None = None):
        base = (home or bau_home()) / "tax"
        self.tx = JsonlStore(base / "transactions.jsonl")
        self.payees = YamlStore(base / "payees.yaml", {"payees": {}})
        self.seq = YamlStore(base / "sequence.yaml", {"invoice": 0})

    def record(self, **rec: Any) -> dict[str, Any]:
        missing = [k for k in REQUIRED if not rec.get(k)]
        if missing:
            raise ValueError(f"business records need {missing} (spec §72)")
        if rec["kind"] not in TX_KINDS:
            raise ValueError(f"kind must be one of {sorted(TX_KINDS)}")
        rec["amount"] = str(Decimal(str(rec["amount"])))
        rec["id"] = "tx_" + secrets.token_hex(6)
        rec["recorded_at"] = dt.datetime.now(dt.UTC).isoformat()
        return self.tx.append(rec)

    def next_invoice_number(self, prefix: str = "BAU") -> str:
        data = self.seq.load()
        data["invoice"] = int(data.get("invoice", 0)) + 1
        self.seq.save(data)
        return f"{prefix}-{dt.date.today().year}-{data['invoice']:05d}"

    def add_payee(self, payee_id: str, name_ref: str, country: str, form: str | None,
                  tin_on_file: bool) -> dict[str, Any]:
        if form not in (None, "W-9", "W-8BEN", "W-8BEN-E"):
            raise ValueError("form must be W-9, W-8BEN, W-8BEN-E or None")
        data = self.payees.load()
        data["payees"][payee_id] = {"name_ref": name_ref, "country": country, "form": form,
                                    "tin_on_file": tin_on_file,
                                    "updated": dt.date.today().isoformat()}
        self.payees.save(data)
        return data["payees"][payee_id]

    def info_returns(self, year: int) -> list[dict[str, Any]]:
        """Which payees cross a 1099 threshold this year (US payees with W-9)."""
        th = THRESHOLDS.get(year) or THRESHOLDS[max(THRESHOLDS)]
        totals: dict[tuple[str, str], Decimal] = {}
        for t in self.tx:
            if t["kind"] not in ("payment", "royalty") or not t["date"].startswith(str(year)):
                continue
            cat = "royalties" if t["kind"] == "royalty" else t.get("category",
                                                                   "nonemployee_comp")
            key = (t["counterparty_ref"], cat)
            totals[key] = totals.get(key, Decimal(0)) + Decimal(t["amount"])
        payees = self.payees.load()["payees"]
        out = []
        for (payee, cat), amt in sorted(totals.items()):
            p = payees.get(payee, {})
            limit = th.get(cat, th["other"])
            if amt >= limit:
                form = "1099-MISC" if cat in ("royalties", "rents", "other") else "1099-NEC"
                if p.get("form", "").startswith("W-8"):
                    form = "1042-S (foreign payee - CPA review)"
                out.append({"payee": payee, "category": cat, "total": str(amt),
                            "threshold": str(limit), "form": form,
                            "missing_tax_form": not p.get("form"),
                            "note": THRESHOLD_NOTE})
        return out


def prepare_payout(books: Books, payee_id: str, amount: Decimal, ip_owner_resolved: bool,
                   sanctions_result: str) -> dict[str, Any]:
    """Returns a payout *request*. Blocks on unresolved ownership, sanctions hits or a
    missing tax form; applies backup withholding when no TIN is on file."""
    payee = books.payees.load()["payees"].get(payee_id)
    problems = []
    if not ip_owner_resolved:
        problems.append("ownership unresolved - no payment may be released (spec §67)")
    if sanctions_result != "CLEAR":
        problems.append(f"sanctions screening {sanctions_result}")
    if payee is None:
        problems.append("payee not registered")
    elif not payee.get("form"):
        problems.append("no W-9/W-8 on file")
    withholding = Decimal(0)
    if payee and payee.get("form") == "W-9" and not payee.get("tin_on_file"):
        withholding = (amount * BACKUP_WITHHOLDING_RATE / 100).quantize(Decimal("0.01"))
    return {"payee": payee_id, "gross": str(amount), "backup_withholding": str(withholding),
            "net": str(amount - withholding), "status": "BLOCKED" if problems else
            "READY_FOR_APPROVAL", "problems": problems,
            "next": "execute via gateway capability move.money with a signed approval"}
