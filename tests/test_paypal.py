"""PayPal (src/bau/paypal.py) against a fake PayPal that keeps its own state: tokens,
idempotency keys, invoice and order statuses, refunds, payouts and the transaction report."""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
import urllib.parse

import pytest

from bau import paypal as P
from bau.economics import Ledger, received_usd

NOW = dt.datetime(2026, 11, 24, 12, 0, tzinfo=dt.UTC)


class FakePayPal:
    def __init__(self, cid="cid", secret="sec"):
        self.good = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        self.calls: list[tuple[str, str, dict, dict]] = []
        self.invoices: dict[str, dict] = {}
        self.orders: dict[str, dict] = {}
        self.refunds: dict[str, dict] = {}   # PayPal-Request-Id -> refund
        self.payouts: dict[str, dict] = {}   # sender_batch_id -> batch
        self.tx: list[dict] = []
        self.seq = 0

    def _id(self, p):
        self.seq += 1
        return f"{p}{self.seq:04d}"

    def request(self, method, url, headers, body=None, timeout=0):
        u = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(u.query))
        data = json.loads(body) if body and u.path != "/v1/oauth2/token" else {}
        self.calls.append((method, u.path, dict(headers), data))
        if u.path == "/v1/oauth2/token":
            if headers.get("Authorization") != f"Basic {self.good}":
                return 401, {}, b'{"error":"invalid_client","error_description":"bad keys"}'
            return 200, {}, json.dumps({"access_token": "TOK", "expires_in": 32400}).encode()
        if headers.get("Authorization") != "Bearer TOK":
            return 401, {}, b'{"name":"AUTHENTICATION_FAILURE","debug_id":"d1"}'
        return self.route(method, u.path, q, data, headers)

    def ok(self, status, obj):
        return status, {}, json.dumps(obj).encode()

    def route(self, m, path, q, data, h):
        if path == "/v2/invoicing/generate-next-invoice-number":
            return self.ok(200, {"invoice_number": f"N{self.seq + 1}"})
        if path == "/v2/invoicing/invoices" and m == "POST":
            if not data["detail"].get("currency_code") or not data["items"]:
                return self.ok(400, {"name": "INVALID_REQUEST"})
            i = {"id": self._id("INV2-"), "status": "DRAFT", **data,
                 "amount": {"value": data["items"][0]["unit_amount"]["value"]}}
            self.invoices[i["id"]] = i
            return self.ok(201, i if h.get("Prefer") == "return=representation" else {})
        if path == "/v2/invoicing/invoices" and m == "GET":
            items = list(self.invoices.values())[: int(q["page_size"])]
            return self.ok(200, {"items": items, "total_items": len(self.invoices)})
        if path == "/v2/invoicing/search-invoices":
            items = [i for i in self.invoices.values() if i["status"] in data["status"]]
            return self.ok(200, {"items": items, "total_items": len(items)})
        mi = re.fullmatch(r"/v2/invoicing/invoices/([^/]+)(/\w+)?", path)
        if mi:
            inv = self.invoices.get(mi.group(1))
            if inv is None:
                return self.ok(404, {"name": "RESOURCE_NOT_FOUND"})
            act = mi.group(2)
            if act is None and m == "GET":
                return self.ok(200, inv)
            if act is None and m == "DELETE":
                if inv["status"] != "DRAFT":
                    return self.ok(422, {"name": "UNPROCESSABLE_ENTITY"})
                del self.invoices[inv["id"]]
                return 204, {}, b""
            if act == "/send":
                inv["status"] = "SENT"
                return self.ok(200, {"rel": "payer-view", "method": "GET",
                                     "href": f"https://www.sandbox.paypal.com/invoice/p/#{inv['id']}"})
            if act == "/payments":
                if inv["status"] != "SENT" or data["method"] not in P.PAY_METHODS:
                    return self.ok(422, {"name": "UNPROCESSABLE_ENTITY"})
                inv["status"] = "MARKED_AS_PAID"
                return self.ok(200, {"payment_id": "EXTR-1"})
            if act == "/cancel":
                inv["status"] = "CANCELLED"
                return 204, {}, b""
        if path == "/v2/checkout/orders" and m == "POST":
            o = {"id": self._id("ORD"), "status": "CREATED", **data, "links": [
                {"rel": "self", "href": "x"},
                {"rel": "approve", "href": f"https://www.sandbox.paypal.com/checkoutnow?token={self.seq}"}]}
            self.orders[o["id"]] = o
            return self.ok(201, o)
        mo = re.fullmatch(r"/v2/checkout/orders/([^/]+)(/capture)?", path)
        if mo:
            o = self.orders.get(mo.group(1))
            if o is None:
                return self.ok(404, {"name": "RESOURCE_NOT_FOUND"})
            if not mo.group(2):
                return self.ok(200, o)
            if o["status"] == "COMPLETED":             # PayPal-Request-Id replays the answer
                return self.ok(201, o)
            if o["status"] != "APPROVED":
                return self.ok(422, {"name": "UNPROCESSABLE_ENTITY",
                                     "details": [{"issue": "ORDER_NOT_APPROVED"}],
                                     "debug_id": "d2"})
            amt = o["purchase_units"][0]["amount"]
            o["status"] = "COMPLETED"
            o["purchase_units"][0]["payments"] = {"captures": [
                {"id": "CAP" + o["id"], "status": "COMPLETED", "amount": amt}]}
            return self.ok(201, o)
        mc = re.fullmatch(r"/v2/payments/captures/([^/]+)(/refund)?", path)
        if mc:
            if not mc.group(2):
                return self.ok(200, {"id": mc.group(1), "status": "COMPLETED"})
            key = h["PayPal-Request-Id"]
            if key not in self.refunds:
                self.refunds[key] = {"id": self._id("RF"), "status": "COMPLETED",
                                     "capture": mc.group(1), "body": data}
            return self.ok(201, self.refunds[key])
        if path == "/v1/payments/payouts" and m == "POST":
            bid = data["sender_batch_header"]["sender_batch_id"]
            if bid in self.payouts:
                return self.ok(400, {"name": "USER_BUSINESS_ERROR",
                                     "details": [{"issue": "DUPLICATE_REQUEST_ID"}]})
            self.payouts[bid] = {"batch_header": {"payout_batch_id": self._id("PB"),
                                                  "batch_status": "PENDING"}, "body": data}
            return self.ok(201, self.payouts[bid])
        if path.startswith("/v1/payments/payouts/"):
            return self.ok(200, {"batch_header": {"batch_status": "SUCCESS"}})
        if path == "/v1/reporting/transactions":
            lo = dt.datetime.fromisoformat(q["start_date"].replace("Z", "+00:00"))
            hi = dt.datetime.fromisoformat(q["end_date"].replace("Z", "+00:00"))
            assert hi - lo <= dt.timedelta(days=31)
            rows = [t for t in self.tx if lo <= dt.datetime.fromisoformat(
                t["transaction_initiation_date"].replace("+0000", "+00:00")) <= hi]
            size, page = int(q["page_size"]), int(q["page"])
            chunk = rows[(page - 1) * size: page * size]
            pages = max(1, -(-len(rows) // size))
            return self.ok(200, {"transaction_details": [{"transaction_info": t}
                                                         for t in chunk],
                                 "total_pages": pages})
        return self.ok(404, {"name": "NOT_FOUND"})


def client(tmp_path, fake=None, env="sandbox"):
    fake = fake or FakePayPal()
    return P.PayPalClient(tmp_path, http=fake, creds=("cid", "sec"), env=env), fake


def tx(tid, code, value, fee="0.00", status="S", when="2026-11-23T10:00:00+0000"):
    return {"transaction_id": tid, "transaction_event_code": code,
            "transaction_status": status, "transaction_initiation_date": when,
            "transaction_amount": {"currency_code": "USD", "value": value},
            "fee_amount": {"currency_code": "USD", "value": fee}}


# ------------------------------------------------------------------ the wire


def test_hosts_keys_and_mode(tmp_path, monkeypatch):
    assert P.mode(tmp_path) == "sandbox"
    assert P.PayPalClient(tmp_path, creds=("a", "b")).base == "https://api-m.sandbox.paypal.com"
    P.set_mode(tmp_path, "live")
    assert P.PayPalClient(tmp_path, creds=("a", "b")).base == "https://api-m.paypal.com"
    with pytest.raises(P.PayPalError):
        P.set_mode(tmp_path, "prod")
    for n in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_SANDBOX_CLIENT_ID",
              "PAYPAL_SANDBOX_CLIENT_SECRET"):
        monkeypatch.delenv(n, raising=False)
    env = tmp_path / "platforms.env"
    env.write_text("PAYPAL_SANDBOX_CLIENT_ID=s1\nPAYPAL_SANDBOX_CLIENT_SECRET=s2\n")
    assert P.app_credentials("sandbox", env) == ("s1", "s2")
    with pytest.raises(P.PayPalError, match="sudo bau keys set PAYPAL_CLIENT_ID"):
        P.app_credentials("live", env)


def test_paypal_keys_go_to_the_platforms_file():
    from bau.keys import route
    assert route({"PAYPAL_CLIENT_SECRET": "x"}) == {"platforms.env": {"PAYPAL_CLIENT_SECRET": "x"}}


def test_token_is_fetched_once_and_bad_keys_are_said(tmp_path):
    c, fake = client(tmp_path)
    c.invoices()
    c.invoices()
    assert [x[1] for x in fake.calls].count("/v1/oauth2/token") == 1
    assert fake.calls[0][3] == {}             # the form body is not JSON
    bad = P.PayPalClient(tmp_path, http=FakePayPal(secret="other"), creds=("cid", "sec"))
    with pytest.raises(P.PayPalError, match="refused the app keys .401.: bad keys"):
        bad.token()


def test_ids_cannot_change_the_path(tmp_path):
    c, _ = client(tmp_path)
    for bad in ("../v1/oauth2/token", "", "a/b", ".."):
        with pytest.raises(P.PayPalError, match="not a PayPal id"):
            c.invoice(bad)


def test_amounts_are_exact_and_positive():
    assert P.money("9.999") == "10.00"
    assert P.money(5) == "5.00"
    for bad in ("0", "-1", "0.001"):
        with pytest.raises(P.PayPalError):
            P.money(bad)


# ------------------------------------------------------------------ invoices


def test_invoice_lifecycle(tmp_path):
    c, fake = client(tmp_path)
    num = c.next_invoice_number()
    inv = c.create_invoice("buyer@example.com", [{"name": "Photo set", "price": "25"}],
                           number=num, note="thanks")
    create = next(x for x in fake.calls if x[1] == "/v2/invoicing/invoices")
    assert create[2]["Prefer"] == "return=representation"
    assert create[2]["PayPal-Request-Id"].startswith("inv-")
    assert create[3]["detail"] == {"currency_code": "USD", "invoice_number": num, "note": "thanks"}
    assert create[3]["items"][0]["unit_amount"] == {"currency_code": "USD", "value": "25.00"}
    assert create[3]["primary_recipients"][0]["billing_info"]["email_address"] == \
        "buyer@example.com"
    assert inv["status"] == "DRAFT"
    link = c.send_invoice(inv["id"])
    assert link.startswith("https://www.sandbox.paypal.com/invoice/p/")
    assert c.invoice(inv["id"])["status"] == "SENT"
    assert c.search_invoices(["SENT"])["total_items"] == 1
    with pytest.raises(P.PayPalError, match="method is one of"):
        c.record_invoice_payment(inv["id"], "25", method="BITCOIN")
    c.record_invoice_payment(inv["id"], "25", method="CHECK")
    assert c.invoice(inv["id"])["status"] == "MARKED_AS_PAID"
    other = c.create_invoice("b@example.com", [{"name": "x", "price": "1"}])
    c.send_invoice(other["id"])
    c.cancel_invoice(other["id"])
    assert c.invoice(other["id"])["status"] == "CANCELLED"
    draft = c.create_invoice("b@example.com", [{"name": "x", "price": "1"}])
    c.delete_invoice(draft["id"])
    with pytest.raises(P.PayPalError, match="404"):
        c.invoice(draft["id"])
    with pytest.raises(P.PayPalError, match="at least one item"):
        c.create_invoice("b@example.com", [])


# ------------------------------------------------------------------ checkout


def test_checkout_approve_and_capture(tmp_path):
    c, fake = client(tmp_path)
    o = c.create_order("12.5", description="Clip pack", return_url="https://e.com/ok")
    assert o["status"] == "CREATED" and "checkoutnow" in o["approve_url"]
    body = next(x[3] for x in fake.calls if x[1] == "/v2/checkout/orders")
    assert body["intent"] == "CAPTURE"
    assert body["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "12.50"}
    assert body["payment_source"]["paypal"]["experience_context"] == {
        "return_url": "https://e.com/ok"}
    with pytest.raises(P.PayPalError, match="ORDER_NOT_APPROVED debug_id d2"):
        c.capture(o["id"])                     # the buyer has not approved yet
    fake.orders[o["id"]]["status"] = "APPROVED"  # the buyer approves in the browser
    cap = c.capture(o["id"])
    assert cap["status"] == "COMPLETED" and cap["amount"] == "12.50"
    again = c.capture(o["id"])                 # a retry takes the money once
    assert again["id"] == cap["id"]
    keys = [x[2].get("PayPal-Request-Id") for x in fake.calls if x[1].endswith("/capture")]
    assert len(set(keys)) == 1
    assert c.captured(cap["id"])["status"] == "COMPLETED"


# ------------------------------------------------------------------ money out


def test_refund_and_payout_need_a_signed_approval_live(tmp_path):
    P.set_mode(tmp_path, "live")
    c, fake = client(tmp_path, env="live")
    path = P.prepare(tmp_path, "refund", capture_id="CAP1", amount="5")
    rec = json.loads(path.read_text())
    assert rec["mode"] == "live" and rec["amount"] == "5.00" and rec["id"].startswith("rf-")
    with pytest.raises(P.PayPalError, match="bau approve --capability move.money"):
        P.send(tmp_path, path, c, approved=False)
    assert fake.refunds == {}                  # nothing moved
    out = P.send(tmp_path, path, c, approved=True)
    assert out["status"] == "COMPLETED"
    refund_call = next(x for x in fake.calls if x[1].endswith("/refund"))
    assert refund_call[2]["PayPal-Request-Id"] == rec["id"]
    assert refund_call[3] == {"amount": {"currency_code": "USD", "value": "5.00"}}
    again = P.send(tmp_path, path, c, approved=True)
    assert "already sent" in again["note"] and len(fake.refunds) == 1

    po = P.prepare(tmp_path, "payout", items=[{"receiver": "v@example.com", "amount": "3"}])
    with pytest.raises(P.PayPalError, match="signed approval"):
        P.send(tmp_path, po, c, approved=False)
    res = P.send(tmp_path, po, c, approved=True)
    assert res["status"] == "PENDING"
    body = next(iter(fake.payouts.values()))["body"]
    assert body["sender_batch_header"]["sender_batch_id"] == json.loads(po.read_text())["id"]
    assert body["items"][0]["amount"] == {"value": "3.00", "currency": "USD"}


def test_a_request_is_sent_only_in_its_own_mode(tmp_path):
    path = P.prepare(tmp_path, "refund", capture_id="CAP1")        # made in the sandbox
    live, _ = client(tmp_path, env="live")
    with pytest.raises(P.PayPalError, match="made for sandbox"):
        P.send(tmp_path, path, live, approved=True)
    sandbox, fake = client(tmp_path)
    assert P.send(tmp_path, path, sandbox, approved=False)["status"] == "COMPLETED"
    assert next(iter(fake.refunds.values()))["body"] == {}         # a full refund


def test_bad_requests_are_refused_before_paypal(tmp_path):
    for kind, fields in (("refund", {}), ("payout", {}),
                         ("payout", {"items": [{"amount": "1"}]}), ("wire", {})):
        with pytest.raises(P.PayPalError):
            P.prepare(tmp_path, kind, **fields)


def test_the_cli_send_checks_the_signed_approval(tmp_path, monkeypatch):
    """`bau paypal send` in live mode moves nothing without a valid approval file."""
    from bau import cli_ext
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    P.set_mode(tmp_path, "live")
    path = P.prepare(tmp_path, "refund", capture_id="CAP1")
    fake = FakePayPal()
    real = P.PayPalClient
    monkeypatch.setattr(P, "PayPalClient",
                        lambda home: real(home, http=fake, creds=("cid", "sec"), env="live"))
    monkeypatch.setattr(cli_ext, "_human", lambda: "human:owner")
    ns = type("A", (), {"pp_cmd": "send", "file": str(path), "approval": None})()
    assert cli_ext.cmd_paypal(ns) == cli_ext.EXIT_BLOCKED
    assert fake.refunds == {}


# ------------------------------------------------------------------ connected, and the ledger


def test_check_says_connected_only_after_real_answers(tmp_path):
    c, _ = client(tmp_path)
    rec = P.check(tmp_path, c, now=NOW)
    assert rec["connected"] and [s["step"] for s in rec["steps"]] == [
        "token", "invoices", "transactions"]
    assert P.status(tmp_path)["connected"]
    bad = P.PayPalClient(tmp_path, http=FakePayPal(secret="x"), creds=("cid", "sec"))
    rec = P.check(tmp_path, bad, now=NOW)
    assert not rec["connected"] and rec["steps"][0]["ok"] is False and len(rec["steps"]) == 1
    assert not P.status(tmp_path)["connected"]
    assert P.status(tmp_path / "new") == {"mode": "sandbox", "connected": False,
                                          "checked_at": None}


def test_status_forgets_a_check_from_the_other_mode(tmp_path):
    c, _ = client(tmp_path)
    P.check(tmp_path, c, now=NOW)
    P.set_mode(tmp_path, "live")
    assert P.status(tmp_path)["connected"] is False


def test_sync_records_each_settled_payment_once(tmp_path):
    c, fake = client(tmp_path)
    fake.tx = [tx("A1", "T0006", "20.00", "-0.89"),           # checkout payment
               tx("A2", "T0007", "10.00", "-0.59", status="P"),  # pending: later
               tx("A3", "T1107", "-10.00", "0.00"),            # a refund given
               tx("A4", "T0400", "-50.00"),                    # money to the bank: not a sale
               tx("A5", "T0006", "-5.00"),                     # money BAU paid out
               tx("A6", "T1201", "-4.00")]                     # a chargeback
    r = P.sync_payments(tmp_path, c, now=NOW)
    assert r["new_rows"] == 3 and r["skipped"] == 3
    rows = list(Ledger(tmp_path).revenue)
    assert [(x["gross_usd"], x["refund"], x["factory"]) for x in rows] == [
        (20.0, False, "paypal"), (10.0, True, "paypal"), (4.0, True, "paypal")]
    assert rows[0]["payment_fee"] == pytest.approx(0.89)
    assert round(sum(received_usd(x) for x in rows), 2) == pytest.approx(5.11)
    assert r["net_usd"] == pytest.approx(5.11)
    again = P.sync_payments(tmp_path, c, now=NOW)
    assert again["new_rows"] == 0 and len(list(Ledger(tmp_path).revenue)) == 3
    fake.tx[1]["transaction_status"] = "S"                    # the pending one settles
    assert P.sync_payments(tmp_path, c, now=NOW)["new_rows"] == 1


def test_transactions_are_asked_31_days_and_every_page_at_a_time(tmp_path):
    c, fake = client(tmp_path)
    fake.tx = [tx(f"T{i}", "T0006", "1.00", when="2026-10-01T10:00:00+0000")
               for i in range(1201)]
    rows = c.transactions(NOW - dt.timedelta(days=90), NOW)
    assert len(rows) == 1201
    asks = [x for x in fake.calls if x[1] == "/v1/reporting/transactions"]
    assert len(asks) >= 3 + 2                                   # 3 windows, 3 pages in one


def test_sync_if_due_waits_for_a_check(tmp_path):
    c, fake = client(tmp_path)
    assert P.sync_if_due(tmp_path, c) is None
    P.check(tmp_path, c)
    assert P.sync_if_due(tmp_path, c)["new_rows"] == 0
    assert P.sync_if_due(tmp_path, c) is None                   # not again within the hour


# ------------------------------------------------------------------ the sandbox round trip


def test_sandbox_test_runs_every_method(tmp_path):
    c, fake = client(tmp_path)
    first = P.test(tmp_path, c, "buyer@example.com")
    assert all(s["ok"] is not False for s in first), first
    names = [s["step"] for s in first]
    for want in ("invoice A: delete the draft", "invoice B: record a cash payment",
                 "invoice C: cancel", "create checkout order", "approve as the sandbox buyer"):
        assert want in names
    shows = {s["step"]: s["result"] for s in first}
    assert shows["invoice B: show"] == "MARKED_AS_PAID"
    assert shows["invoice C: show"] == "CANCELLED"
    oid = next(iter(fake.orders))
    fake.orders[oid]["status"] = "APPROVED"
    second = P.test(tmp_path, c, "buyer@example.com", order_id=oid)
    assert all(s["ok"] for s in second), second
    assert [s["step"] for s in second] == ["capture", "show capture", "refund in full (sandbox)",
                                           "payout $1.00 to the sandbox buyer", "show payout",
                                           "transactions (last day)"]
    live, _ = client(tmp_path, env="live")
    with pytest.raises(P.PayPalError, match="only in the sandbox"):
        P.test(tmp_path, live, "buyer@example.com")


def test_sandbox_test_says_each_failure(tmp_path):
    c, fake = client(tmp_path)
    second = P.test(tmp_path, c, "buyer@example.com", order_id="ORD-NOPE")
    assert second[0] == {"step": "capture", "ok": False,
                         "error": "PayPal POST /v2/checkout/orders/ORD-NOPE/capture failed "
                                  "(404) RESOURCE_NOT_FOUND"}


def test_the_money_tool_reads_paypal_once_checked(tmp_path, monkeypatch):
    from bau.assistant import Assistant
    c, fake = client(tmp_path)
    fake.tx = [tx("Z1", "T0006", "30.00", "-1.20",
                  when=(dt.datetime.now(dt.UTC) - dt.timedelta(days=1)).strftime(
                      "%Y-%m-%dT%H:%M:%S+0000"))]
    monkeypatch.setattr(P, "PayPalClient", lambda home: c)
    assert "paypal" not in Assistant(tmp_path).t_money()       # never checked: not read
    P.check(tmp_path, c)
    out = Assistant(tmp_path).t_money()
    assert out["paypal"]["new_rows"] == 1 and round(out["revenue"], 2) == 30.0


def test_adult_content_is_never_sold_through_paypal(tmp_path):
    c, fake = client(tmp_path)
    for name in ("Nude set", "Level 3 unlock", "NSFW clip", "Fanvue bundle", "sexy pics"):
        with pytest.raises(P.PayPalError, match="Acceptable Use Policy"):
            c.create_invoice("b@example.com", [{"name": name, "price": "5"}])
    with pytest.raises(P.PayPalError, match="Acceptable Use Policy"):
        c.create_order("5", description="explicit video")
    assert not any(x[1] in ("/v2/invoicing/invoices", "/v2/checkout/orders")
                   for x in fake.calls)           # refused before PayPal is asked
    assert c.create_invoice("b@example.com", [{"name": "GTA 6 clip edit", "price": "5"}])
