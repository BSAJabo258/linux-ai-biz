import copy
import datetime as dt

import pytest
from conftest import WHEN

from bau.comms import sms
from bau.comms.consent import ConsentLedger, SuppressionList, UnsubscribeTokens
from bau.comms.dns_auth import check_domain
from bau.comms.email import WirelessDomains, preflight, unsubscribe_headers
from bau.decision import Status

UNSUB = "https://bau.example/u/abc"
ADDR = "BAU Media LLC, 100 Main St, Detroit, MI 48226"
GOOD_MSG = {
    "campaign_id": "c1", "category": "commercial", "purpose": "marketing",
    "list_source": "own_opt_in", "from_name": "BAU Media", "from_address": "news@bau.example",
    "reply_to": "support@bau.example", "subject": "October templates are here",
    "body_text": f"Advertisement. New planners.\n{ADDR}\nUnsubscribe: {UNSUB}",
    "ad_identified": True, "physical_address": ADDR, "unsubscribe_url": UNSUB,
    "sexually_explicit": False,
    "headers": unsubscribe_headers(UNSUB, "unsub@bau.example"),
}
GOOD_SENDER = {
    "owned_domains": ["bau.example"], "spf_present": True, "spf_single_record": True,
    "spf_not_permissive": True, "dkim_present": True, "dmarc_present": True,
    "dmarc_policy": "quarantine", "dmarc_rua": True, "dmarc_aligned": True, "tls": True,
    "complaint_rate": 0.0005, "unsubscribe_requires_login": False, "unsubscribe_fee": False,
    "unsubscribe_window_days": 60, "unsubscribe_processing_days": 0,
}


@pytest.fixture
def stores(tmp_path):
    ledger = ConsentLedger(tmp_path / "ledger.jsonl")
    supp = SuppressionList(tmp_path / "supp.jsonl")
    wl_path = tmp_path / "wl.txt"
    wl_path.write_text("# fetched_at: 2026-10-01\nvtext.com\n")
    return ledger, supp, WirelessDomains(wl_path)


def consent(ledger, addr, basis="double_opt_in", juris="US"):
    ledger.record(addr, "email", "marketing", basis, "https://bau.example/signup", "v3",
                  "sha256:form-snapshot", juris, captured_at=WHEN - dt.timedelta(days=30))


def run(engine, stores, msg=None, sender=None, rcpts=None):
    ledger, supp, wl = stores
    return preflight(msg or GOOD_MSG, rcpts or [{"address": "a@x.example", "country": "US"}],
                     sender or GOOD_SENDER, engine, ledger, supp, wl, when=WHEN)


def test_clean_campaign_passes_with_signed_off_rules(active_engine, stores):
    consent(stores[0], "a@x.example")
    rep = run(active_engine, stores)
    assert rep.message_decision.status == Status.PASS, rep.to_dict()
    assert len(rep.sendable) == 1


def test_clean_campaign_needs_review_until_counsel_signs_off(engine, stores):
    consent(stores[0], "a@x.example")
    rep = run(engine, stores)
    assert rep.message_decision.status == Status.PASS_WITH_REVIEW
    assert rep.sendable == []
    from bau.comms.email import preflight as pf
    approved = pf(GOOD_MSG, [{"address": "a@x.example", "country": "US"}], GOOD_SENDER, engine,
                  *stores, when=WHEN, approved=True)
    assert len(approved.sendable) == 1


@pytest.mark.parametrize("mutate,rule", [
    (lambda m: m.update(body_text="Advertisement.\nUnsubscribe: " + UNSUB), "email.postal_address"),
    (lambda m: m["headers"].pop("List-Unsubscribe-Post"), "email.unsubscribe.one_click"),
    (lambda m: m.update(list_source="purchased"), "email.list_source"),
    (lambda m: m.update(from_address="ceo@bigbank.example"), "email.identity"),
    (lambda m: m.update(subject="Guaranteed results, 100% risk-free"), "email.claims"),
    (lambda m: m.update(sexually_explicit=True), "email.no_explicit_content"),
])
def test_message_defects_block(active_engine, stores, mutate, rule):
    consent(stores[0], "a@x.example")
    msg = copy.deepcopy(GOOD_MSG)
    mutate(msg)
    rep = run(active_engine, stores, msg=msg)
    hit = [f for f in rep.message_decision.findings if f.rule_id == rule]
    assert hit and hit[0].status == Status.BLOCKED, rep.to_dict()
    assert rep.sendable == []


def test_deceptive_subject_needs_human(active_engine, stores):
    consent(stores[0], "a@x.example")
    rep = run(active_engine, stores, msg=dict(GOOD_MSG, subject="RE: your account suspended"))
    assert rep.message_decision.status == Status.PASS_WITH_REVIEW


def test_dns_and_reputation_gates(active_engine, stores):
    consent(stores[0], "a@x.example")
    rep = run(active_engine, stores, sender=dict(GOOD_SENDER, dkim_present=False))
    assert rep.message_decision.status == Status.BLOCKED
    rep = run(active_engine, stores, sender=dict(GOOD_SENDER, complaint_rate=0.004))
    assert rep.message_decision.status == Status.BLOCKED
    rep = run(active_engine, stores, sender=dict(GOOD_SENDER, complaint_rate=0.002))
    assert rep.message_decision.status == Status.PASS_WITH_REVIEW
    missing = {k: v for k, v in GOOD_SENDER.items() if k != "dmarc_present"}
    rep = run(active_engine, stores, sender=missing)
    assert rep.message_decision.status == Status.INCOMPLETE_FACTS


def test_suppressed_recipient_blocked(active_engine, stores):
    consent(stores[0], "a@x.example")
    stores[1].add("A@X.example ", "complaint")  # normalisation: case and whitespace
    rep = run(active_engine, stores)
    assert rep.sendable == []
    assert rep.recipients[0]["status"] == "BLOCKED"


def test_eu_needs_opt_in_and_member_state_is_covered(active_engine, stores):
    consent(stores[0], "b@x.example", basis="existing_relationship", juris="DE")
    rep = run(active_engine, stores, rcpts=[{"address": "b@x.example", "country": "DE"}])
    assert rep.recipients[0]["status"] == "BLOCKED"
    consent(stores[0], "c@x.example", basis="double_opt_in", juris="DE")
    rep = run(active_engine, stores, rcpts=[{"address": "c@x.example", "country": "DE"}])
    assert rep.recipients[0]["may_proceed"], rep.recipients[0]


def test_unknown_location_gets_strictest_rules(active_engine, stores):
    consent(stores[0], "d@x.example", basis="existing_relationship")
    rep = run(active_engine, stores, rcpts=[{"address": "d@x.example"}])
    assert not rep.recipients[0]["may_proceed"]
    consent(stores[0], "e@x.example", basis="double_opt_in")
    rep = run(active_engine, stores, rcpts=[{"address": "e@x.example"}])
    assert rep.recipients[0]["may_proceed"], rep.recipients[0]
    assert rep.recipients[0]["resolved"]["consent_model"] == "opt_in_or_soft"


def test_casl_implied_consent_expires(active_engine, stores):
    ledger = stores[0]
    ledger.record("f@x.example", "email", "marketing", "implied_inquiry", "web", "v1", "sha",
                  "CA", captured_at=WHEN - dt.timedelta(days=200))
    rep = run(active_engine, stores, rcpts=[{"address": "f@x.example", "country": "CA"}])
    assert not rep.recipients[0]["may_proceed"]


def test_wireless_domain_rules(active_engine, stores, tmp_path):
    consent(stores[0], "5551234@vtext.com")
    rep = run(active_engine, stores, rcpts=[{"address": "5551234@vtext.com", "country": "US"}])
    assert not rep.recipients[0]["may_proceed"]
    ledger, supp, _ = stores
    stale = WirelessDomains(None)
    consent(ledger, "g@x.example")
    rep = preflight(GOOD_MSG, [{"address": "g@x.example", "country": "US"}], GOOD_SENDER,
                    active_engine, ledger, supp, stale, when=WHEN)
    assert rep.recipients[0]["status"] == "INCOMPLETE_FACTS"


def test_ad_label_not_needed_with_express_consent(active_engine, stores):
    consent(stores[0], "a@x.example")
    rep = run(active_engine, stores, msg=dict(GOOD_MSG, ad_identified=False))
    assert rep.recipients[0]["may_proceed"]
    consent(stores[0], "h@x.example", basis="existing_relationship")
    rep = run(active_engine, stores, msg=dict(GOOD_MSG, ad_identified=False),
              rcpts=[{"address": "h@x.example", "country": "US"}])
    assert not rep.recipients[0]["may_proceed"]


def test_synthetic_performer_disclosure_in_ny(active_engine, stores):
    consent(stores[0], "i@x.example", juris="US-NY")
    msg = dict(GOOD_MSG, synthetic_performer=True, synthetic_performer_disclosed=False)
    rep = run(active_engine, stores, msg=msg,
              rcpts=[{"address": "i@x.example", "country": "US", "region": "NY"}])
    assert rep.message_decision.status == Status.BLOCKED


def test_unsubscribe_token_roundtrip_and_forgery(tmp_path):
    supp = SuppressionList(tmp_path / "s.jsonl")
    ledger = ConsentLedger(tmp_path / "l.jsonl")
    consent(ledger, "j@x.example")
    t = UnsubscribeTokens(b"k" * 32)
    token = t.make(supp.key("j@x.example"), "weekly")
    assert "x.example" not in token and b"x.example".hex() not in token
    skey, lst = t.parse(token)
    supp.add_key(skey, "unsubscribe")
    assert ledger.withdraw_where(lambda c: supp.key(c) == skey) == 1
    assert supp.is_suppressed("j@x.example")
    with pytest.raises(ValueError):
        t.parse(token[:-1] + ("0" if token[-1] != "0" else "1"))
    with pytest.raises(ValueError):
        unsubscribe_headers("http://insecure.example/u")


def test_dns_checker_parsing():
    zone = {
        "bau.example": ["v=spf1 include:_spf.esp.example -all"],
        "_dmarc.bau.example": ["v=DMARC1; p=quarantine; rua=mailto:d@bau.example"],
        "s1._domainkey.bau.example": ["v=DKIM1; k=rsa; p=MIIBIjAN"],
    }
    f = check_domain("bau.example", ["s1"], resolver=lambda n: zone.get(n, []))
    assert f == {"spf_present": True, "spf_single_record": True, "spf_not_permissive": True,
                 "dmarc_present": True, "dmarc_policy": "quarantine", "dmarc_rua": True,
                 "dkim_present": True}
    zone["bau.example"].append("v=spf1 +all")
    f = check_domain("bau.example", [], resolver=lambda n: zone.get(n, []))
    assert f["spf_single_record"] is False
    assert check_domain("x.example", ["s"], resolver=lambda n: None) == {}


# ------------------------------------------------------------------ SMS
def sms_ok(ledger, number="+13135550100"):
    ledger.record(number, "sms", "marketing", "prior_express_written", "web", "v1", "sha",
                  "US-MI", captured_at=WHEN - dt.timedelta(days=5))


SMS_MSG = {"category": "marketing", "brand": "BAU", "body": "BAU: new kits. Reply STOP to opt out"}


def test_sms_happy_path_and_quiet_hours(active_engine, tmp_path):
    ledger, supp = ConsentLedger(tmp_path / "l"), SuppressionList(tmp_path / "s")
    sms_ok(ledger)
    rcpt = {"number": "+13135550100", "country": "US", "region": "MI",
            "timezone": "America/Detroit", "dnc_checked": True, "on_dnc": False,
            "messages_last_24h": 0}
    _, d = sms.preflight(SMS_MSG, rcpt, active_engine, ledger, supp, when=WHEN)
    assert d.status == Status.PASS, d.to_dict()
    late = dt.datetime(2026, 10, 5, 2, 0, tzinfo=dt.UTC)  # 22:00 in Detroit
    _, d = sms.preflight(SMS_MSG, rcpt, active_engine, ledger, supp, when=late)
    assert d.status == Status.BLOCKED
    _, d = sms.preflight(SMS_MSG, dict(rcpt, timezone=None), active_engine, ledger, supp,
                         when=WHEN)
    assert d.status == Status.INCOMPLETE_FACTS


def test_sms_florida_is_stricter(active_engine, tmp_path):
    ledger, supp = ConsentLedger(tmp_path / "l"), SuppressionList(tmp_path / "s")
    sms_ok(ledger, "+13055550100")
    rcpt = {"number": "+13055550100", "country": "US", "region": "FL",
            "timezone": "America/New_York", "dnc_checked": True, "on_dnc": False,
            "messages_last_24h": 0}
    at_830pm = dt.datetime(2026, 10, 5, 0, 30, tzinfo=dt.UTC)
    _, d = sms.preflight(SMS_MSG, rcpt, active_engine, ledger, supp, when=at_830pm)
    assert d.status == Status.BLOCKED
    _, d = sms.preflight(SMS_MSG, dict(rcpt, messages_last_24h=3), active_engine, ledger, supp,
                         when=WHEN)
    assert d.status == Status.BLOCKED


def test_sms_revocation_is_global(active_engine, tmp_path):
    ledger, supp = ConsentLedger(tmp_path / "l"), SuppressionList(tmp_path / "s")
    sms_ok(ledger)
    assert sms.is_revocation("Stop")
    assert sms.is_revocation("please don't text me anymore")
    assert not sms.is_revocation("what time do you close?")
    assert sms.handle_inbound("STOP", "+13135550100", ledger, supp)
    assert supp.is_suppressed("+13135550100", "email")  # revocation covers every channel
    after = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=1)  # opt-out uses the real clock
    assert ledger.current("+13135550100", "sms", "marketing", after) is None


def test_sms_outside_us_is_unknown(active_engine, tmp_path):
    ledger, supp = ConsentLedger(tmp_path / "l"), SuppressionList(tmp_path / "s")
    _, d = sms.preflight(SMS_MSG, {"number": "+5511999999999", "country": "BR"},
                         active_engine, ledger, supp, when=WHEN)
    assert d.status in (Status.UNKNOWN, Status.BLOCKED)
    assert not d.may_proceed(approved=True)
