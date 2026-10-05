from conftest import ON

from bau.brain import Brain, slug
from bau.jarvis import Jarvis


def test_sentence_from_the_whiteboard_becomes_a_workflow(tmp_path):
    b = Brain(tmp_path)
    edges = b.say("Product team runs Slack questions which consumes tickets and produces answers")
    assert edges == [("product-team", "runs", "slack-questions"),
                     ("slack-questions", "consumes", "tickets"),
                     ("slack-questions", "produces", "answers")]
    assert b.load("product-team").type == "team"
    assert b.load("slack-questions").type == "workflow"
    assert b.load("tickets").type == "artifact"
    assert b.workflows() == [{"workflow": "slack-questions", "title": "Slack questions",
                              "run_by": ["product-team"], "consumes": ["tickets"],
                              "produces": ["answers"], "uses": [], "governed_by": []}]
    assert not [i for i in b.lint() if i["issue"] == "workflow_incomplete"]


def test_object_lists_and_subject_carry_over(tmp_path):
    b = Brain(tmp_path)
    edges = b.say("Content team runs TikTok publishing which consumes scripts, music "
                  "and produces videos")
    assert ("tiktok-publishing", "consumes", "scripts") in edges
    assert ("tiktok-publishing", "consumes", "music") in edges
    assert ("tiktok-publishing", "produces", "videos") in edges
    edges = b.say("Marketing owns the brand and uses Claude, ffmpeg")
    assert edges == [("marketing", "owns", "brand"), ("marketing", "uses", "claude"),
                     ("marketing", "uses", "ffmpeg")]
    for bad in ["no verbs here", "runs everything"]:
        try:
            b.say(bad)
            raise AssertionError(bad)
        except ValueError:
            pass


def test_obsidian_files_keep_owner_text_and_links(tmp_path):
    b = Brain(tmp_path)
    b.say("Ops team runs refunds which consumes requests")
    p = b.path("refunds")
    text = p.read_text()
    assert text.startswith("---\nid: refunds\ntype: workflow")
    assert "- consumes [[requests]]" in text                   # Obsidian graph edge
    p.write_text(text.replace("# refunds", "# refunds\n\nWithin 14 days. See [[refund-policy]]."))
    b.say("Refunds produces confirmations")                   # regenerates relations only
    text = p.read_text()
    assert "Within 14 days" in text and "[[confirmations]]" in text
    g = b.graph()
    assert {"source": "refunds", "verb": "mentions", "target": "refund-policy"} in g["edges"]
    assert any(i["issue"] == "broken_link" and "refund-policy" in i["detail"]
               for i in b.lint())


def test_lint_finds_gaps_and_personal_data(tmp_path):
    b = Brain(tmp_path)
    b.upsert("Onboarding", "workflow")
    b.upsert("Vendor contact", "role", body="call 313-555-0100 or bob@example.com")
    issues = {(i["node"], i["issue"]) for i in b.lint()}
    assert ("onboarding", "workflow_incomplete") in issues
    assert ("vendor-contact", "personal_data") in issues
    b.upsert("Vendor contact", data_class="PERSONAL")
    assert ("vendor-contact", "personal_data") not in {(i["node"], i["issue"])
                                                       for i in b.lint()}


def test_context_is_model_agnostic_and_withholds_personal_notes(tmp_path):
    b = Brain(tmp_path)
    b.say("Support team runs Slack questions which consumes tickets and produces answers")
    b.upsert("Customer list", "artifact", data_class="PERSONAL", body="tickets from customers")
    b.say("Slack questions consumes customer list")
    ctx = b.context("how are slack tickets answered")
    assert ctx["nodes"][0] == "slack-questions"
    assert "Support team" in ctx["markdown"] and "answers" in ctx["markdown"]
    assert "customer-list" not in ctx["nodes"] and ctx["withheld_by_data_class"] == 1
    assert "customer-list" in b.context("tickets", allowed=("INTERNAL", "PERSONAL"))["nodes"]


def test_slugs_are_distinct_and_path_safe():
    assert slug("publish.video") != slug("publish_video")
    assert "/" not in slug("../../etc/passwd") and not slug(".hidden").startswith(".")
    assert slug("The Product Team") == "product-team"


def test_import_system_seeds_without_overwriting_owner_notes(tmp_path):
    b = Brain(tmp_path)
    b.upsert("faceless_media", "workflow", body="Owner's own description.")
    b.import_system()
    n = b.load("faceless_media")
    assert n.source == "owner" and n.type == "workflow" and "Owner's own" in n.body
    assert "publish-gate" in {e["source"] for e in b.graph()["edges"]
                              if e["target"] == "faceless_media" and e["verb"] == "governs"}
    assert b.load("publish_video").type == "mission_type"
    assert b.load("publish.video").type == "capability"


def test_agents_and_jarvis_use_the_brain(tmp_path, active_engine, monkeypatch):
    from bau import network
    from bau.gateway import CallRequest
    from bau.runtime import build_gateway
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    Brain(tmp_path).say("Content team runs TikTok publishing which produces videos")
    gw = build_gateway(tmp_path, trust=lambda: network.Trust.TRUSTED)
    out = gw.invoke(CallRequest("agent:x", "memory.brain", {"query": "tiktok videos"}))
    assert "tiktok-publishing" in out["nodes"] and "Content team" in out["context"]
    from test_commerce_disclosure import GOOD_OFFER

    from bau.commerce.subscriptions import offer_facts
    Brain(tmp_path).say("Growth team runs planner subscription which produces revenue")
    m = Jarvis(active_engine, home=tmp_path).plan(
        "Launch planner subscription", "launch_subscription",
        {"subscription": offer_facts(GOOD_OFFER, "US", "CA", ON)}, on=ON)
    assert "planner-subscription" in m.steps["brain"]


def test_mission_control_brain_view(tmp_path):
    from bau.ui.server import _api
    Brain(tmp_path).say("Product team runs Slack questions which consumes tickets")
    d = _api("/api/brain", tmp_path)
    assert len(d["nodes"]) == 3 and d["workflows"][0]["workflow"] == "slack-questions"
    assert any(i["issue"] == "workflow_incomplete" for i in d["lint"])     # no outputs yet


def test_dashboard_host_allow_list(monkeypatch):
    from bau.ui.server import allowed_hosts_from_env
    monkeypatch.delenv("BAU_UI_ALLOWED_HOSTS", raising=False)
    assert allowed_hosts_from_env() == {"127.0.0.1", "localhost"}
    monkeypatch.setenv("BAU_UI_ALLOWED_HOSTS",
                       "my-space-8765.app.github.dev, *.evil.example, a/b")
    hosts = allowed_hosts_from_env()
    assert "my-space-8765.app.github.dev" in hosts
    assert not any("*" in h or "/" in h for h in hosts)      # no wildcards, no junk
