import datetime as dt

import pytest
import yaml
from conftest import ON

from bau.decision import Decision, Finding, Status
from bau.home import shipped_data
from bau.policy import PolicyEngine, PolicyError, compile_expr
from bau.regulations import Registry, RegistryError, promote, validate_record


def test_shipped_registry_and_policies_load(engine):
    assert len(engine.registry.regs) >= 40
    assert len(engine.policies) >= 50


def test_three_valued_logic():
    e = compile_expr({"all": [{"fact": "a", "eq": 1}, {"fact": "b", "eq": 2}]})
    assert e({"a": 1, "b": 2}) is True
    assert e({"a": 1}) is None
    assert e({"a": 0}) is False  # a definite False beats a missing fact
    anyx = compile_expr({"any": [{"fact": "a", "eq": 1}, {"fact": "b", "eq": 2}]})
    assert anyx({"a": 1}) is True
    assert anyx({"a": 0}) is None
    assert compile_expr({"not": {"fact": "a", "eq": 1}})({}) is None


def test_bad_operator_rejected():
    with pytest.raises(PolicyError):
        compile_expr({"fact": "a", "equals": 1})


def test_empty_decision_is_unknown_not_pass():
    assert Decision("x", []).status == Status.UNKNOWN
    assert not Decision("x", []).may_proceed()


def test_review_needs_approval():
    d = Decision("x", [Finding("r", Status.PASS_WITH_REVIEW, "m")])
    assert not d.may_proceed()
    assert d.may_proceed(approved=True)
    blocked = Decision("x", [Finding("r", Status.BLOCKED, "m")])
    assert not blocked.may_proceed(approved=True)


def test_vacated_rule_is_not_enforced_and_proposed_is_not_law(engine):
    reg = engine.registry
    assert reg.get("us-ftc-click-to-cancel-2024").applicability(ON) == "dead"
    assert reg.get("us-ftc-negative-option-anprm-2026").applicability(ON) == "not_law"


def test_date_awareness(engine):
    art50 = engine.registry.get("eu-ai-act-art50")
    assert art50.applicability(dt.date(2026, 8, 1)) == "future"
    assert art50.applicability(dt.date(2026, 8, 2)) == "in_force"
    hr = engine.registry.get("eu-ai-act-high-risk")
    assert hr.applicability(ON) == "future"
    sb1050 = engine.registry.get("us-ca-sb1050-synthetic-performer")
    assert sb1050.applicability(ON) == "unknown_date"


def test_stale_rule_expires_pass(engine):
    facts = {"jurisdictions": ["US"], "offer": {"recurring": True}}
    later = dt.date(2027, 6, 1)  # past every shipped next_review
    d = engine.evaluate("subscription", {**facts, "offer": {
        "recurring": True, "has_trial": False, "online_cancel_if_online_signup": True,
        "cancel_not_harder": True, "cancellation_requires_survey": False,
        "save_offers_max": 1}}, on=later)
    statuses = {f.rule_id: f.status for f in d.findings}
    assert statuses["sub.cancel.simple"] == Status.EXPIRED


def test_unverified_rule_never_grants_clean_pass(engine, active_engine):
    facts = {"jurisdictions": ["US"], "ip": {}}
    good = {"owner_known": True, "ownership_sums_to_100": True, "license_known": True,
            "commercial_rights": True, "model_license_commercial": True,
            "unresolved_rights_count": 0, "human_contribution_recorded": True,
            "ai_contribution": "assisted", "copyright_claim_reviewed": False}
    facts["ip"] = good
    assert engine.evaluate("monetize", facts, on=ON).status == Status.PASS_WITH_REVIEW
    assert active_engine.evaluate("monetize", facts, on=ON).status == Status.PASS


def test_missing_jurisdiction_is_unknown(engine):
    d = engine.evaluate("monetize", {"ip": {}}, on=ON)
    assert d.status == Status.UNKNOWN


def test_uncovered_jurisdiction(engine):
    d = engine.evaluate("sms", {"jurisdictions": ["BR"], "message": {"category": "marketing"},
                                "recipient": {"suppressed": False}}, on=ON)
    assert any(f.rule_id == "sms.coverage" and f.status == Status.UNKNOWN for f in d.findings)


def test_dangling_regulation_reference_refuses_to_load(tmp_path):
    (tmp_path / "p.yaml").write_text(yaml.safe_dump({"policies": [{
        "id": "x", "domain": "d", "scope": "s", "stage": 1, "title": "t",
        "regs": ["does-not-exist"], "jurisdictions": ["ANY"], "require": []}]}))
    with pytest.raises(PolicyError):
        PolicyEngine.load(Registry.load(shipped_data() / "regulations"), tmp_path)


def test_conflict_without_ordering(tmp_path):
    reg = Registry.load(shipped_data() / "regulations")
    (tmp_path / "p.yaml").write_text(yaml.safe_dump({"policies": [
        {"id": "a", "domain": "d", "scope": "s", "stage": 1, "title": "a", "regs": [],
         "jurisdictions": ["US"], "require": [], "sets": {"age_gate": 13}},
        {"id": "b", "domain": "d", "scope": "s", "stage": 2, "title": "b", "regs": [],
         "jurisdictions": ["EU"], "require": [], "sets": {"age_gate": 16}}]}))
    eng = PolicyEngine.load(reg, tmp_path)
    d = eng.evaluate("d", {"jurisdictions": ["US", "EU"]}, on=ON)
    assert d.status == Status.CONFLICT


def test_registry_validation_rules():
    base = yaml.safe_load((shipped_data() / "regulations" / "ai.yaml").read_text())[0]
    bad = dict(base, bau_status="ACTIVE")
    assert any("reviewed_by" in e for e in validate_record(bad))
    news = dict(base, source_type="news", bau_status="MAPPED")
    assert validate_record(news)
    assert validate_record(dict(base, source_url="http://x"))


def test_promote_refuses_skipping(tmp_path):
    f = tmp_path / "r.yaml"
    f.write_text((shipped_data() / "regulations" / "ai.yaml").read_text())
    with pytest.raises(RegistryError):
        promote(f, "eu-ai-act-art50", "ACTIVE", "counsel", ON)
    rec = promote(f, "eu-ai-act-art50", "TESTED", "counsel", ON)
    assert rec["bau_status"] == "TESTED"
    rec = promote(f, "eu-ai-act-art50", "ACTIVE", "counsel", ON)
    assert rec["reviewed_by"] == "counsel"
    with pytest.raises(RegistryError):
        promote(f, "us-ca-ab1609-chatbot", "ACTIVE", "counsel", ON)


def test_regulation_watch_flags_changed_sources(tmp_path, engine):
    from bau.regulations import watch
    pages = {}

    def fetch(url):
        return pages.get(url, b"<html><body>stable text</body></html>")

    state = tmp_path / "watch.json"
    first = watch(engine.registry, state, ON, fetch)
    assert first["checked"] > 10 and first["changed"] == []
    url = engine.registry.get("us-canspam")["source_url"]
    pages[url] = b"<html><script>x()</script><body>stable   text</body></html>"
    assert watch(engine.registry, state, ON, fetch)["changed"] == []  # cosmetic only
    pages[url] = b"<html><body>penalty now $60,000</body></html>"
    res = watch(engine.registry, state, ON, fetch)
    assert [c["url"] for c in res["changed"]] == [url]
    off = watch(engine.registry, state, ON, lambda u: None)
    assert len(off["unreachable"]) == first["checked"]
