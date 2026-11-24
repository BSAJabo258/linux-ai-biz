"""PayPal: the business's payments (`bau paypal`, the owner's ask 2026-11-24: "the best payment
system ... test all methods, make sure everything is perfectly connectable and working").

The owner has a PayPal business account. BAU uses PayPal's REST API for everything a seller
does: invoices, checkout links, captures, refunds, payouts and the transaction report that
puts each settled payment into the ledger once.

Facts read on developer.paypal.com on 2026-11-24 (OpenAPI schemas under /api/<name>/schema.json,
/api/rest/, /api/rest/production, /reports/reference/t-codes):
- Hosts: sandbox https://api-m.sandbox.paypal.com, live https://api-m.paypal.com ("trade out
  the sandbox host ... for the live host"). Keys: Apps & Credentials; a developer account has
  two sandbox accounts by default (a personal buyer and a business seller).
- Token: POST /v1/oauth2/token, grant_type=client_credentials, Basic CLIENT_ID:CLIENT_SECRET,
  form encoded; the answer has access_token and expires_in.
- PayPal-Request-Id: "A unique ID identifying the request header for idempotency purposes"
  (orders, invoices, refunds); the payouts schema: "The server stores keys for 30 days."
- Invoicing v2: POST /v2/invoicing/generate-next-invoice-number; POST /v2/invoicing/invoices
  (draft; needs detail.currency_code, primary_recipients[].billing_info.email_address,
  items[] name, quantity, unit_amount; 201, the invoice back with Prefer: return=representation);
  POST .../{id}/send (send_to_recipient, send_to_invoicer; answers a payer-view link);
  GET .../{id}; GET /v2/invoicing/invoices (page 1..1000, page_size 1..100, total_required);
  POST /v2/invoicing/search-invoices (status: a list); POST .../{id}/payments (a payment made
  outside PayPal; method BANK_TRANSFER CASH CHECK CREDIT_CARD DEBIT_CARD PAYPAL WIRE_TRANSFER
  OTHER; answers payment_id); POST .../{id}/cancel (204); DELETE .../{id} (a draft or
  scheduled invoice). Statuses:
  DRAFT SENT SCHEDULED PAID MARKED_AS_PAID CANCELLED REFUNDED PARTIALLY_PAID PARTIALLY_REFUNDED
  MARKED_AS_REFUNDED UNPAID PAYMENT_PENDING AUTO_CANCELLED PAID_EXTERNAL REFUNDED_EXTERNAL SHARED.
- Orders v2: POST /v2/checkout/orders (intent, purchase_units[].amount currency_code + value;
  payment_source.paypal.experience_context return_url, cancel_url); the buyer approves on the
  "approve" link (or "payer-action"); GET /v2/checkout/orders/{id}; POST .../{id}/capture.
  Order statuses CREATED SAVED APPROVED VOIDED COMPLETED PAYER_ACTION_REQUIRED; "Check the
  payment status in purchase_units[].payments.captures[].status before fulfilling the order".
  Capture statuses COMPLETED DECLINED PARTIALLY_REFUNDED PENDING REFUNDED FAILED.
- Payments v2: GET /v2/payments/captures/{id}; POST .../{id}/refund ("For a full refund,
  include an empty payload"; amount, invoice_id, note_to_payer); refund statuses CANCELLED
  FAILED PENDING COMPLETED.
- Payouts v1: POST /v1/payments/payouts (sender_batch_header.sender_batch_id, email_subject;
  items[] recipient_type EMAIL|PHONE|PAYPAL_ID, amount value + currency, receiver, note,
  sender_item_id); "PayPal does not process duplicate payouts" for a sender_batch_id used in
  the last 30 days; GET /v1/payments/payouts/{id}; batch statuses DENIED PENDING PROCESSING
  SUCCESS CANCELED. Up to 15,000 payments per call.
- Transaction Search v1: GET /v1/reporting/transactions, start_date and end_date in RFC 3339
  with seconds, "The maximum supported range is 31 days", page_size up to 500, fields;
  transaction_status D (denied), P (pending), S (success), V (reversed); "It takes a maximum of
  three hours for executed transactions to appear". T-codes: T00xx payments received and sent,
  T1106 payment reversal, T1107 payment refund, T1201 chargeback. The pages do not say the
  sign of fee_amount; BAU counts its size.

PayPal's Acceptable Use Policy (paypal.com/us/legalhub/paypal/acceptableuse-full, last updated
November 4, 2026) bars "certain sexually oriented materials or services" and lists "Mature
Audience Content: Any adult content delivered digitally" among what needs PayPal's approval
first. So PayPal is for BAU's other work (clips, services, goods); the creator's content is
paid on Fanvue, never here, and an invoice or checkout that names adult content is refused.

BAU's rules on top: money leaving the business (a refund, a payout) is prepared as a request
file and sent only with the owner's SSH-signed approval of exactly that file (`bau approve
--capability move.money`), once (its request id is PayPal's idempotency key); the sandbox's
play money is the one exception, for `bau paypal test`. Nothing here is called "connected"
until a real request to PayPal succeeded (`check`). PayPal calls BAU never: no webhook, no open
port; BAU asks PayPal for the status instead.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import secrets
import time
import urllib.parse
from decimal import Decimal
from pathlib import Path
from typing import Any

from .home import atomic_write_json, bau_home
from .tiktok import _env_file
from .youtube import Http

HOSTS = {"sandbox": "https://api-m.sandbox.paypal.com", "live": "https://api-m.paypal.com"}
KEYS = {"sandbox": ("PAYPAL_SANDBOX_CLIENT_ID", "PAYPAL_SANDBOX_CLIENT_SECRET"),
        "live": ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET")}
MAX_RANGE_DAYS = 31
SETTLE_HOURS = 3
SALE_GROUP = "T00"
REFUND_CODES = {"T1106", "T1107", "T1201"}
PAY_METHODS = ("BANK_TRANSFER", "CASH", "CHECK", "CREDIT_CARD", "DEBIT_CARD", "PAYPAL",
               "WIRE_TRANSFER", "OTHER")
SYNC_EVERY_S = 3600


ADULT = re.compile(r"\b(nude|nudes|naked|nsfw|explicit|xxx|porn\w*|sex\w*|adult|erotic\w*|"
                   r"lewd|fetish\w*|onlyfans|fanvue|ppv|unlock\w*)\b", re.I)


class PayPalError(RuntimeError):
    pass


def _not_adult(*texts: str) -> None:
    for t in texts:
        if t and ADULT.search(t):
            raise PayPalError("PayPal's Acceptable Use Policy bars adult content: the "
                              "creator's content is paid on Fanvue, not PayPal "
                              f"({ADULT.search(t).group(0)!r} in {t[:60]!r})")


def _dir(home: Path) -> Path:
    return home / "paypal"


def mode(home: Path) -> str:
    """sandbox until the owner says live (`bau paypal mode live`)."""
    try:
        m = json.loads((_dir(home) / "mode.json").read_text()).get("mode")
    except (OSError, ValueError):
        return "sandbox"
    return m if m in HOSTS else "sandbox"


def set_mode(home: Path, m: str) -> None:
    if m not in HOSTS:
        raise PayPalError("mode is sandbox or live")
    _dir(home).mkdir(parents=True, exist_ok=True)
    atomic_write_json(_dir(home) / "mode.json", {"mode": m})


def app_credentials(m: str, env_file: Path = Path("/etc/bau/platforms.env")) -> tuple[str, str]:
    env = {**_env_file(env_file), **os.environ}
    cid_name, secret_name = KEYS[m]
    cid, secret = env.get(cid_name), env.get(secret_name)
    if not cid or not secret:
        raise PayPalError(f"PayPal's {m} app keys are not on this computer: copy them from "
                          "developer.paypal.com (Apps & Credentials, docs/PAYPAL.md), then "
                          f"sudo bau keys set {cid_name} {secret_name}")
    return cid, secret


def money(value: Any) -> str:
    """Two decimals, exact, positive."""
    d = Decimal(str(value)).quantize(Decimal("0.01"))
    if d <= 0:
        raise PayPalError("an amount must be more than 0")
    return str(d)


def request_id(prefix: str = "bau") -> str:
    return f"{prefix}-{secrets.token_hex(12)}"


class PayPalClient:
    def __init__(self, home: Path | None = None, http: Any = None,
                 creds: tuple[str, str] | None = None, env: str | None = None,
                 clock: Any = time.time):
        self.home = home or bau_home()
        self.env = env or mode(self.home)
        self.base = HOSTS[self.env]
        self.http = http or Http()
        self._creds = creds
        self.clock = clock
        self._token: tuple[str, float] | None = None

    @property
    def creds(self) -> tuple[str, str]:
        if self._creds is None:
            self._creds = app_credentials(self.env)
        return self._creds

    # -------------------------------------------------------- the wire

    def token(self) -> str:
        if self._token and self._token[1] > self.clock() + 60:
            return self._token[0]
        cid, secret = self.creds
        basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        status, _, body = self.http.request(
            "POST", self.base + "/v1/oauth2/token",
            {"Authorization": f"Basic {basic}", "Accept": "application/json",
             "Content-Type": "application/x-www-form-urlencoded"},
            b"grant_type=client_credentials", timeout=30)
        data = _json(body)
        if status != 200 or "access_token" not in data:
            raise PayPalError(f"PayPal refused the app keys ({status}): "
                              f"{data.get('error_description') or data.get('error') or ''}"
                              .rstrip(": "))
        self._token = (data["access_token"], self.clock() + int(data.get("expires_in", 0)))
        return self._token[0]

    def call(self, method: str, path: str, body: Any = None, *, query: dict | None = None,
             idem: str | None = None, prefer: bool = False) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token()}", "Accept": "application/json",
                   "Content-Type": "application/json"}
        if idem:
            headers["PayPal-Request-Id"] = idem
        if prefer:
            headers["Prefer"] = "return=representation"
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = None if body is None else json.dumps(body).encode()
        status, _, raw = self.http.request(method, url, headers, data, timeout=60)
        out = _json(raw)
        if status >= 400:
            detail = out.get("message") or out.get("name") or ""
            issues = [d.get("issue") for d in out.get("details") or [] if d.get("issue")]
            raise PayPalError(f"PayPal {method} {path} failed ({status}) {detail}"
                              f"{' ' + ', '.join(issues) if issues else ''}"
                              f"{' debug_id ' + out['debug_id'] if out.get('debug_id') else ''}"
                              .strip())
        return out

    # -------------------------------------------------------- invoices

    def next_invoice_number(self) -> str:
        return self.call("POST", "/v2/invoicing/generate-next-invoice-number")["invoice_number"]

    def create_invoice(self, email: str, items: list[dict[str, Any]], currency: str = "USD",
                       note: str = "", number: str | None = None,
                       idem: str | None = None) -> dict[str, Any]:
        if not items:
            raise PayPalError("an invoice needs at least one item")
        _not_adult(note, *(str(i.get("name", "")) for i in items))
        detail: dict[str, Any] = {"currency_code": currency}
        if number:
            detail["invoice_number"] = number
        if note:
            detail["note"] = note
        body = {"detail": detail,
                "primary_recipients": [{"billing_info": {"email_address": email}}],
                "items": [{"name": i["name"], "quantity": str(i.get("quantity", 1)),
                           "unit_amount": {"currency_code": currency,
                                           "value": money(i["price"])}} for i in items]}
        return self.call("POST", "/v2/invoicing/invoices", body, idem=idem or request_id("inv"),
                         prefer=True)

    def send_invoice(self, invoice_id: str, *, email_buyer: bool = True) -> str:
        """Sends it; answers the address where the buyer pays."""
        out = self.call("POST", f"/v2/invoicing/invoices/{_seg(invoice_id)}/send",
                        {"send_to_recipient": email_buyer, "send_to_invoicer": False})
        return _link(out, "payer-view")

    def invoice(self, invoice_id: str) -> dict[str, Any]:
        return self.call("GET", f"/v2/invoicing/invoices/{_seg(invoice_id)}")

    def invoices(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        return self.call("GET", "/v2/invoicing/invoices",
                         query={"page": page, "page_size": min(max(page_size, 1), 100),
                                "total_required": "true"})

    def search_invoices(self, status: list[str], page_size: int = 100) -> dict[str, Any]:
        return self.call("POST", "/v2/invoicing/search-invoices", {"status": status},
                         query={"page": 1, "page_size": min(max(page_size, 1), 100)})

    def record_invoice_payment(self, invoice_id: str, amount: Any, method: str = "CASH",
                               currency: str = "USD", when: dt.date | None = None,
                               note: str = "") -> dict[str, Any]:
        """A payment the buyer made outside PayPal (cash, a check, a bank transfer)."""
        if method not in PAY_METHODS:
            raise PayPalError(f"method is one of {', '.join(PAY_METHODS)}")
        body = {"method": method, "payment_date": (when or dt.date.today()).isoformat(),
                "amount": {"currency_code": currency, "value": money(amount)}}
        if note:
            body["note"] = note
        return self.call("POST", f"/v2/invoicing/invoices/{_seg(invoice_id)}/payments", body)

    def cancel_invoice(self, invoice_id: str, note: str = "") -> None:
        body: dict[str, Any] = {"send_to_recipient": True, "send_to_invoicer": False}
        if note:
            body["note"] = note
        self.call("POST", f"/v2/invoicing/invoices/{_seg(invoice_id)}/cancel", body)

    def delete_invoice(self, invoice_id: str) -> None:
        self.call("DELETE", f"/v2/invoicing/invoices/{_seg(invoice_id)}")

    # -------------------------------------------------------- checkout

    def create_order(self, amount: Any, currency: str = "USD", description: str = "",
                     return_url: str = "", cancel_url: str = "",
                     idem: str | None = None) -> dict[str, Any]:
        """A checkout: answers the order and the address where the buyer approves it."""
        _not_adult(description)
        unit: dict[str, Any] = {"amount": {"currency_code": currency, "value": money(amount)}}
        if description:
            unit["description"] = description[:127]
        body: dict[str, Any] = {"intent": "CAPTURE", "purchase_units": [unit]}
        if return_url or cancel_url:
            body["payment_source"] = {"paypal": {"experience_context": {
                k: v for k, v in (("return_url", return_url), ("cancel_url", cancel_url)) if v}}}
        out = self.call("POST", "/v2/checkout/orders", body, idem=idem or request_id("ord"))
        return {"id": out["id"], "status": out.get("status"),
                "approve_url": _link(out, "approve") or _link(out, "payer-action")}

    def order(self, order_id: str) -> dict[str, Any]:
        return self.call("GET", f"/v2/checkout/orders/{_seg(order_id)}")

    def capture(self, order_id: str, idem: str | None = None) -> dict[str, Any]:
        """Takes the buyer's approved payment; answers the capture (its id and status)."""
        out = self.call("POST", f"/v2/checkout/orders/{_seg(order_id)}/capture", {},
                        idem=idem or f"cap-{order_id}")
        caps = [c for u in out.get("purchase_units") or []
                for c in (u.get("payments") or {}).get("captures") or []]
        if not caps:
            raise PayPalError(f"PayPal answered the capture of {order_id} with no payment "
                              f"(order {out.get('status')})")
        c = caps[0]
        return {"order": out.get("id"), "order_status": out.get("status"), "id": c.get("id"),
                "status": c.get("status"), "amount": (c.get("amount") or {}).get("value"),
                "currency": (c.get("amount") or {}).get("currency_code")}

    def captured(self, capture_id: str) -> dict[str, Any]:
        return self.call("GET", f"/v2/payments/captures/{_seg(capture_id)}")

    # -------------------------------------------------------- money out (approval first)

    def refund(self, capture_id: str, amount: Any = None, currency: str = "USD",
               note: str = "", idem: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if amount is not None:
            body["amount"] = {"currency_code": currency, "value": money(amount)}
        if note:
            body["note_to_payer"] = note[:255]
        return self.call("POST", f"/v2/payments/captures/{_seg(capture_id)}/refund", body,
                         idem=idem or request_id("rf"))

    def payout(self, batch_id: str, items: list[dict[str, Any]], subject: str = "",
               currency: str = "USD") -> dict[str, Any]:
        if not items:
            raise PayPalError("a payout needs at least one person to pay")
        body = {"sender_batch_header": {"sender_batch_id": batch_id,
                                        **({"email_subject": subject[:255]} if subject else {})},
                "items": [{"recipient_type": i.get("type", "EMAIL"),
                           "amount": {"value": money(i["amount"]), "currency": currency},
                           "receiver": i["receiver"], "note": i.get("note", "")[:4000],
                           "sender_item_id": i.get("id") or f"{batch_id}-{n}"}
                          for n, i in enumerate(items, 1)]}
        out = self.call("POST", "/v1/payments/payouts", body, idem=batch_id)
        h = out.get("batch_header") or {}
        return {"id": h.get("payout_batch_id"), "status": h.get("batch_status")}

    def payout_batch(self, batch_id: str) -> dict[str, Any]:
        return self.call("GET", f"/v1/payments/payouts/{_seg(batch_id)}")

    # -------------------------------------------------------- reconciliation

    def transactions(self, start: dt.datetime, end: dt.datetime) -> list[dict[str, Any]]:
        """Every transaction in [start, end], 31 days per request, every page."""
        rows: list[dict[str, Any]] = []
        lo = start
        while lo < end:
            hi = min(end, lo + dt.timedelta(days=MAX_RANGE_DAYS))
            page, pages = 1, 1
            while page <= pages:
                out = self.call("GET", "/v1/reporting/transactions", query={
                    "start_date": _rfc(lo), "end_date": _rfc(hi), "fields": "transaction_info",
                    "page_size": 500, "page": page})
                rows += [t.get("transaction_info") or {}
                         for t in out.get("transaction_details") or []]
                pages = int(out.get("total_pages") or 1)
                page += 1
            lo = hi
        return rows


def _json(raw: bytes) -> dict[str, Any]:
    try:
        out = json.loads(raw or b"{}")
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


def _seg(s: str) -> str:
    """One path segment: an id from a person or a file never changes the path."""
    if not s or "/" in s or s in (".", ".."):
        raise PayPalError(f"not a PayPal id: {s!r}")
    return urllib.parse.quote(s, safe="-_")


def _link(out: dict[str, Any], rel: str) -> str:
    if out.get("rel") == rel:          # the send answer is one link
        return out.get("href", "")
    return next((x.get("href", "") for x in out.get("links") or [] if x.get("rel") == rel), "")


def _rfc(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ is it connected


def check(home: Path, client: PayPalClient | None = None,
          now: dt.datetime | None = None) -> dict[str, Any]:
    """Real requests only: the token, one invoice page, one day of transactions. Connected
    means all three answered; the answer is kept for `bau paypal status`."""
    client = client or PayPalClient(home)
    now = now or dt.datetime.now(dt.UTC)
    steps: list[dict[str, Any]] = []

    def step(name: str, fn: Any) -> bool:
        try:
            fn()
            steps.append({"step": name, "ok": True})
            return True
        except PayPalError as e:
            steps.append({"step": name, "ok": False, "error": str(e)})
            return False

    ok = step("token", client.token)
    ok = ok and step("invoices", lambda: client.invoices(page_size=1))
    ok = ok and step("transactions", lambda: client.transactions(now - dt.timedelta(days=1),
                                                                  now))
    rec = {"mode": client.env, "connected": bool(ok), "checked_at": now.isoformat(
        timespec="seconds"), "steps": steps}
    _dir(home).mkdir(parents=True, exist_ok=True)
    atomic_write_json(_dir(home) / "check.json", rec)
    return rec


def status(home: Path) -> dict[str, Any]:
    try:
        rec = json.loads((_dir(home) / "check.json").read_text())
    except (OSError, ValueError):
        rec = {"connected": False, "checked_at": None}
    if rec.get("mode") not in (None, mode(home)):
        rec = {"connected": False, "checked_at": None, "note": "mode changed since the check"}
    return {"mode": mode(home), **rec}


# ------------------------------------------------------------------ payments into the ledger


def sync_payments(home: Path, client: PayPalClient, now: dt.datetime | None = None,
                  days: int = 30) -> dict[str, Any]:
    """Every settled PayPal payment once into economics/revenue.jsonl: money received (T00xx,
    a positive amount) as a sale with PayPal's fee, refunds, reversals and chargebacks as
    refunds. Pending, denied, withdrawals, holds and money BAU sent are left out."""
    from .economics import Ledger
    now = now or dt.datetime.now(dt.UTC)
    seen_path = _dir(home) / "seen.json"
    try:
        known = set(json.loads(seen_path.read_text())["ids"])
    except (OSError, ValueError, KeyError):
        known = set()
    rows = client.transactions(now - dt.timedelta(days=days), now)
    ledger, added, net, skipped = Ledger(home), 0, Decimal(0), 0
    for t in rows:
        tid, code = t.get("transaction_id"), str(t.get("transaction_event_code") or "")
        if not tid or tid in known:
            continue
        if t.get("transaction_status") != "S":
            skipped += 1                  # pending ones come back settled next time
            continue
        value = Decimal(str((t.get("transaction_amount") or {}).get("value") or 0))
        fee = abs(Decimal(str((t.get("fee_amount") or {}).get("value") or 0)))
        sale = code.startswith(SALE_GROUP) and value > 0
        refund = code in REFUND_CODES and value < 0
        if not (sale or refund):
            known.add(tid)
            skipped += 1
            continue
        when = _when(t.get("transaction_initiation_date")) or now
        ledger.sale(float(abs(value)), factory="paypal", customer_ref=tid,
                    payment_fee=float(fee if sale else -fee), refund=refund, when=when)
        known.add(tid)
        added += 1
        net += (value - fee) if sale else (value + fee)
    rec = {"ids": sorted(known), "synced_at": now.isoformat(timespec="seconds")}
    _dir(home).mkdir(parents=True, exist_ok=True)
    atomic_write_json(seen_path, rec)
    return {"new_rows": added, "net_usd": float(net), "skipped": skipped,
            "synced_at": rec["synced_at"],
            "note": f"PayPal lists a payment up to {SETTLE_HOURS} hours after it happens"}


def sync_if_due(home: Path, client: PayPalClient | None = None) -> dict[str, Any] | None:
    """At most once an hour, and only after a check found PayPal connected."""
    if not status(home).get("connected"):
        return None
    try:
        last = dt.datetime.fromisoformat(
            json.loads((_dir(home) / "seen.json").read_text())["synced_at"])
        if (dt.datetime.now(dt.UTC) - last).total_seconds() < SYNC_EVERY_S:
            return None
    except (OSError, ValueError, KeyError):
        pass
    return sync_payments(home, client or PayPalClient(home))


def _when(s: Any) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00").replace("+0000",
                                                                                "+00:00"))
    except ValueError:
        return None


# ------------------------------------------------------------------ money out: request, sign, send


def _requests(home: Path) -> Path:
    return _dir(home) / "requests"


def prepare(home: Path, kind: str, **fields: Any) -> Path:
    """A refund or payout request file for the owner to read and sign. Its id is PayPal's
    idempotency key, so sending it twice moves the money once."""
    if kind == "refund":
        if not fields.get("capture_id"):
            raise PayPalError("a refund needs the capture id")
        if fields.get("amount") is not None:
            fields["amount"] = money(fields["amount"])
    elif kind == "payout":
        items = fields.get("items") or []
        if not items:
            raise PayPalError("a payout needs at least one person to pay")
        for i in items:
            i["amount"] = money(i["amount"])
            if not i.get("receiver"):
                raise PayPalError("every payout needs a receiver")
    else:
        raise PayPalError("kind is refund or payout")
    rid = request_id("rf" if kind == "refund" else "po")
    rec = {"id": rid, "kind": kind, "mode": mode(home), "currency": fields.pop("currency", "USD"),
           **fields, "prepared_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    _requests(home).mkdir(parents=True, exist_ok=True)
    path = _requests(home) / f"{rid}.json"
    atomic_write_json(path, rec)
    return path


def send(home: Path, path: Path, client: PayPalClient, approved: bool) -> dict[str, Any]:
    """Sends a prepared request once. Live money needs `approved` (the owner's signed approval
    of exactly this file, checked by the caller); the sandbox's play money does not."""
    rec = json.loads(path.read_text())
    done = path.with_suffix(".sent.json")
    if done.exists():
        return {**json.loads(done.read_text()), "note": "already sent; nothing sent again"}
    if rec.get("mode") != client.env:
        raise PayPalError(f"this request was made for {rec.get('mode')}, BAU is on {client.env}")
    if client.env == "live" and not approved:
        raise PayPalError("money leaving the business needs your signed approval of this file: "
                          f"bau approve --capability move.money --request-id {rec['id']} "
                          f"--requester bau --bind {path} --out {path.with_suffix('.sig.json')}")
    if rec["kind"] == "refund":
        out = client.refund(rec["capture_id"], rec.get("amount"), rec["currency"],
                            rec.get("note", ""), idem=rec["id"])
        result = {"id": out.get("id"), "status": out.get("status")}
    else:
        result = client.payout(rec["id"], rec["items"], rec.get("subject", ""), rec["currency"])
    result = {**result, "request": rec["id"], "kind": rec["kind"], "mode": client.env,
              "sent_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    atomic_write_json(done, result)
    return result


# ------------------------------------------------------------------ the sandbox round trip


def test(home: Path, client: PayPalClient, buyer_email: str,
         order_id: str | None = None) -> list[dict[str, Any]]:
    """Every method against the sandbox, each step said plainly. Without an order: token,
    invoice number, draft invoice, read it, list, search, delete it; a checkout order and
    its approve link (the buyer approves in a browser with the sandbox personal account).
    With the approved order: capture, read the capture, refund it in full, transactions."""
    if client.env != "sandbox":
        raise PayPalError("the test runs only in the sandbox (bau paypal mode sandbox)")
    out: list[dict[str, Any]] = []

    def step(name: str, fn: Any) -> Any:
        try:
            v = fn()
            out.append({"step": name, "ok": True, "result": v})
            return v
        except (PayPalError, KeyError) as e:
            out.append({"step": name, "ok": False, "error": str(e)})
            return None

    def draft(label: str) -> str | None:
        num = step(f"{label}: invoice number", client.next_invoice_number)
        inv = step(f"{label}: create draft invoice", lambda: client.create_invoice(
            buyer_email, [{"name": "BAU sandbox test", "price": "1.00"}],
            number=num, note="BAU sandbox test, not a real bill"))
        return (inv or {}).get("id")

    if order_id is None:
        step("token", lambda: "ok" if client.token() else "")
        a = draft("invoice A")
        if a:
            step("invoice A: show", lambda: client.invoice(a).get("status"))
            step("list invoices", lambda: client.invoices(page_size=5).get("total_items"))
            step("search invoices", lambda: client.search_invoices(["DRAFT"]).get("total_items"))
            step("invoice A: delete the draft", lambda: client.delete_invoice(a) or "deleted")
        b = draft("invoice B")
        if b:
            step("invoice B: send", lambda: client.send_invoice(b, email_buyer=False))
            step("invoice B: record a cash payment", lambda: client.record_invoice_payment(
                b, "1.00", note="BAU sandbox test").get("payment_id", "recorded"))
            step("invoice B: show", lambda: client.invoice(b).get("status"))
        c = draft("invoice C")
        if c:
            step("invoice C: send", lambda: client.send_invoice(c, email_buyer=False))
            step("invoice C: cancel", lambda: client.cancel_invoice(c) or "cancelled")
            step("invoice C: show", lambda: client.invoice(c).get("status"))
        order = step("create checkout order", lambda: client.create_order(
            "1.00", description="BAU sandbox test"))
        if order:
            step("show order", lambda: client.order(order["id"]).get("status"))
            out.append({"step": "approve as the sandbox buyer", "ok": None,
                        "result": f"open {order['approve_url']} , sign in with the sandbox "
                                  f"personal account, approve, then: bau paypal test "
                                  f"--order {order['id']}"})
        return out
    cap = step("capture", lambda: client.capture(order_id))
    if cap and cap.get("id"):
        step("show capture", lambda: client.captured(cap["id"]).get("status"))
        step("refund in full (sandbox)", lambda: client.refund(
            cap["id"], idem=f"test-rf-{cap['id']}").get("status"))
    batch = step("payout $1.00 to the sandbox buyer", lambda: client.payout(
        f"test-po-{order_id}", [{"receiver": buyer_email, "amount": "1.00",
                                 "note": "BAU sandbox test"}]))
    if batch and batch.get("id"):
        step("show payout", lambda: (client.payout_batch(batch["id"]).get("batch_header")
                                     or {}).get("batch_status"))
    now = dt.datetime.now(dt.UTC)
    step("transactions (last day)", lambda: len(client.transactions(
        now - dt.timedelta(days=1), now)))
    return out
