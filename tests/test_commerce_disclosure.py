import datetime as dt
from decimal import Decimal

import pytest
from conftest import ON

from bau.commerce import tax
from bau.commerce.ip import RIGHTS, IPAsset, check_monetization, royalty_statement
from bau.commerce.subscriptions import Cancellation, CancellationError, check_offer
from bau.decision import Status
from bau.disclosure import Provenance, check_publication

GOOD_OFFER = {
    "recurring": True, "price_disclosed": True, "billing_frequency_disclosed": True,
    "renewal_terms_disclosed": True, "total_commitment_disclosed": True,
    "cancellation_fees_disclosed": True, "material_limitations_disclosed": True,
    "cancellation_method_disclosed": True, "disclosed_before_billing_info": True,
    "trial": {"length_days": 7, "end_date_disclosed": True, "reminder_before_end": True},
    "consent": {"separate_affirmative_action": True, "prechecked": False,
                "evidence_retained": True},
    "acknowledgment_receipt": True, "signup_channels": ["online"],
    "cancellation_channels": ["online"], "signup_steps": 4, "cancellation_steps": 3,
    "cancellation_requires_survey": False, "save_offers_max": 1, "annual_reminder": True,
    "price_change_notice_days": 14, "refund_policy_visible": True, "contact_visible": True,
    "terms_accessible": True, "privacy_policy_accessible": True, "accessibility_tested": True,
    "cancellation_test_passed_at": "2026-10-01",
}


def test_good_offer_passes(active_engine):
    d = check_offer(GOOD_OFFER, active_engine, "US", "CA", on=ON)
    assert d.status == Status.PASS, d.to_dict()


@pytest.mark.parametrize("patch", [
    {"cancellation_channels": ["phone"]},                  # call-us-only
    {"cancellation_steps": 9},                             # harder than sign-up
    {"cancellation_requires_survey": True},
    {"consent": {"separate_affirmative_action": True, "prechecked": True,
                 "evidence_retained": True}},
    {"total_commitment_disclosed": False},                 # the Shutterstock pattern
    {"cancellation_test_passed_at": "2026-08-01"},         # stale regression test
    {"save_offers_max": 3},
])
def test_offer_defects_block(active_engine, patch):
    d = check_offer({**GOOD_OFFER, **patch}, active_engine, "US", "CA", on=ON)
    assert d.status == Status.BLOCKED, patch


def test_offer_outside_us_unknown(active_engine):
    assert check_offer(GOOD_OFFER, active_engine, "FR", on=ON).status != Status.PASS


def test_cancellation_state_machine():
    c = Cancellation("sub_1")
    c.offer_save()
    with pytest.raises(CancellationError):
        c.offer_save()
    with pytest.raises(CancellationError):
        c.obstacle("phone_only")
    with pytest.raises(CancellationError):
        c.cancel()  # cannot skip authentication
    c.authenticate("session")
    c.cancel()
    c.confirm("cx-1")
    with pytest.raises(CancellationError):
        c.stop_billing(verified_no_future_charges=False)
    c.stop_billing(verified_no_future_charges=True)
    c.send_receipt("rcpt-1")
    rec = c.record()
    assert [h["state"] for h in rec["history"]][-1] == "RECORDED"


def prov(**kw):
    base = dict(artifact_id="a1", media_type="video", ai_generated=True, ai_assisted=False,
                human_authored=False, human_modified=True, model_id="m1", provider="local",
                machine_readable_marking=True, visible_disclosure_text="AI-GENERATED VIDEO")
    base.update(kw)
    return Provenance(**base)


def test_disclosure_happy_path(active_engine):
    ctx = {"audience": [{"country": "US"}, {"country": "DE"}],
           "platform_requires_ai_label": True, "platform_label_set": True}
    d = check_publication(prov(), ctx, active_engine, on=ON)
    assert d.status == Status.PASS, d.to_dict()
    # The platform's labelling rule is a fact the caller must supply, not assume.
    d = check_publication(prov(), {"audience": [{"country": "US"}]}, active_engine, on=ON)
    assert d.status == Status.INCOMPLETE_FACTS


def test_disclosure_failures(active_engine):
    eu = {"audience": [{"country": "FR"}]}
    assert check_publication(prov(machine_readable_marking=False), eu, active_engine,
                             on=ON).status == Status.BLOCKED
    stripped = prov(machine_readable_marking=False, input_had_provenance_marking=True)
    assert check_publication(stripped, {"audience": [{"country": "US"}]}, active_engine,
                             on=ON).status == Status.BLOCKED
    face = prov(likeness_used=True, consent_status="ambiguous")
    assert check_publication(face, {"audience": [{"country": "US"}]}, active_engine,
                             on=ON).status == Status.BLOCKED
    ad = {"audience": [{"country": "US", "region": "NY"}], "is_advertisement": True,
          "synthetic_performer": True}
    assert check_publication(prov(visible_disclosure_text=None), ad, active_engine,
                             on=ON).status == Status.BLOCKED
    review = {"audience": [{"country": "US"}], "is_review_or_testimonial": True}
    assert check_publication(prov(media_type="text"), review, active_engine,
                             on=ON).status == Status.BLOCKED


def test_disclosure_before_art50_applies(active_engine):
    d = check_publication(prov(machine_readable_marking=False, visible_disclosure_text="x"),
                          {"audience": [{"country": "FR"}]}, active_engine,
                          on=dt.date(2026, 7, 1))
    marking = [f for f in d.findings if f.rule_id == "pub.eu.machine_marking"]
    assert marking[0].status == Status.NOT_APPLICABLE


def asset(**kw):
    base = dict(ip_asset_id="ip1", title="Planner pack", owners={"BAU LLC": Decimal(100)},
                license="BAU-commercial", commercial_rights=True, ai_contribution="assisted",
                human_contribution=["layout", "selection"], model="m1",
                model_license_commercial=True, rights={r: "not_used" for r in RIGHTS})
    base.update(kw)
    return IPAsset(**base)


def test_monetization_gate(active_engine):
    assert check_monetization(asset(), active_engine, on=ON).status == Status.PASS
    assert check_monetization(asset(owners={"UNKNOWN": Decimal(100)}), active_engine,
                              on=ON).status == Status.BLOCKED
    r = {k: "not_used" for k in RIGHTS} | {"music": "unresolved"}
    assert check_monetization(asset(rights=r), active_engine, on=ON).status == Status.BLOCKED
    gen = asset(ai_contribution="generated")
    assert check_monetization(gen, active_engine, on=ON).status == Status.PASS_WITH_REVIEW


def test_royalties_exact_and_refuse_unresolved():
    a = asset(owners={"A": Decimal(50), "B": Decimal(50)},
              royalty_splits={"A": Decimal("33.33"), "B": Decimal("33.33"),
                              "C": Decimal("33.34")})
    st = royalty_statement(a, Decimal("100.00"), Decimal("10.00"), Decimal("3.20"),
                           {"C": Decimal(24)})
    total = sum(Decimal(line["gross_share"]) for line in st["lines"])
    assert total == Decimal("86.80")
    assert st["lines"][2]["withholding"] == "6.95"  # 24% of 28.94, half-even
    with pytest.raises(ValueError):
        royalty_statement(asset(owners={"UNKNOWN": Decimal(100)}), Decimal(1), Decimal(0),
                          Decimal(0))


def test_tax_nexus(tmp_path):
    (tmp_path / "nexus_rules.yaml").write_text("""
- jurisdiction: US-ZZ
  sales_threshold: 100000
  transactions_threshold: 200
  combinator: or
  measurement: previous_or_current_calendar_year
  effective_date: 2019-01-01
  source_url: https://tax.example.gov/nexus
  last_verified: 2026-09-01
  next_review: 2027-03-01
- jurisdiction: US-YY
  sales_threshold: 100000
  combinator: or
  measurement: previous_calendar_year
  effective_date: 2019-01-01
  source_url: https://tax.example.gov/yy
  last_verified: null
  next_review: null
""")
    rules = tax.load_rules(tmp_path)
    hit = tax.assess("US-ZZ", Decimal(5000), 250, rules, False, ON)
    assert hit["status"] == tax.POTENTIAL
    assert tax.assess("US-ZZ", Decimal(5000), 10, rules, False, ON)["status"] == tax.NONE
    assert tax.assess("US-ZZ", Decimal(5000), 10, rules, None, ON)["status"] == tax.UNKNOWN
    assert tax.assess("US-YY", Decimal(1), 1, rules, False, ON)["status"] == tax.UNKNOWN
    assert tax.assess("US-QQ", Decimal(1), 1, rules, False, ON)["status"] == tax.UNKNOWN
