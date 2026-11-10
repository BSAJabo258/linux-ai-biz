"""The rules for the owner's business (2026-11-01): one fictional adult virtual creator run
from Michigan, posting sfw to Instagram and TikTok and explicit content to Fanvue. Each record
comes from the official text, read on the date it carries; none says "compliant", all wait
for counsel. Records that cannot reach this business by their own text are gone.
Written before the records."""

import datetime as dt
from pathlib import Path

import yaml

from bau.home import shipped_data
from bau.platforms import FIELDS, PlatformRegistry
from bau.regulations import Registry

ROOT = Path(__file__).resolve().parents[1]
NEW = {
    "us-take-it-down-act": "https://www.congress.gov/",
    "us-mi-intimate-deepfakes": "https://www.legislature.mi.gov/",
    "us-2257-records": "https://www.govinfo.gov/",
    "industry-fanvue-ai-media": "https://help.fanvue.com/",
}


def test_the_creator_rules_come_from_official_pages_and_wait_for_counsel():
    reg = Registry.load()
    for rid, site in NEW.items():
        r = reg.get(rid)
        assert r is not None, rid
        assert str(r["source_url"]).startswith(site), rid
        assert str(r["last_verified"]) == "2026-11-01" and r["legal_review_required"] is True
        assert r["bau_status"] != "ACTIVE"                 # only counsel makes it ACTIVE


def test_rules_that_cannot_reach_this_business_are_gone():
    reg = Registry.load()
    for rid in ("industry-youtube-made-for-kids", "industry-youtube-inauthentic-content",
                "us-ca-ab1609-chatbot"):
        assert reg.get(rid) is None, rid


def test_the_real_likeness_rule_cites_the_deepfake_laws():
    pols = yaml.safe_load((shipped_data() / "policies" / "ai_disclosure.yaml").read_text())
    p = next(x for x in pols["policies"] if x["id"] == "pub.likeness_consent")
    assert {"us-take-it-down-act", "us-mi-intimate-deepfakes"} <= set(p["regs"])


def test_the_fanvue_policy_record_loads(tmp_path):
    rec = yaml.safe_load((ROOT / "examples" / "platform-fanvue.yaml").read_text())
    assert set(FIELDS) <= set(rec) and rec["requires_ai_label"] is True
    PlatformRegistry(tmp_path).upsert(rec)
    facts = PlatformRegistry(tmp_path).facts("fanvue", on=dt.date(2026, 11, 1))
    assert facts["platform_policy_current"]
