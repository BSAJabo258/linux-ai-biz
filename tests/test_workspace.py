"""ICM workspaces: the creator-week pipeline one agent walks, the owner checks each stage."""

import json

import pytest

from bau import workspace as W
from bau.audit import AuditLog
from bau.models.providers import ScriptedProvider

MODEL = {"id": "test-model", "context": 32768}
PERSONA = """# Persona
- Name: Aria Vale
- Age (21 or older, fictional): 27
- Look (the same in every post): auburn bob, green eyes, freckles, silver hoop earrings
- Style: warm film-photo city fashion
- Niche: city fashion and coffee
- Never: real people's likeness
"""
VOICE = "# Voice\nWarm and playful. Every caption ends with #AI #virtualcreator.\n"


@pytest.fixture
def ws(tmp_path):
    w = W.create("creator-week", home=tmp_path)
    (w / "_shared" / "persona.md").write_text(PERSONA)
    (w / "_shared" / "voice.md").write_text(VOICE)
    return w


def walk_to(ws, ep, provider, upto, audit=None):
    for _ in range(upto):
        c, _ = W.draft(ws, ep, provider, MODEL, audit)
        W.check(ws, ep, c.stage[:2], "human:owner", audit)


def test_shipped_template_follows_the_icm_invariants():
    ws_src = W.shipped_data() / "workspaces" / "creator-week"
    entry = (ws_src / "CLAUDE.md").read_text().splitlines()
    assert len(entry) <= 60                                    # small routing entry file
    stages = sorted((ws_src / "_templates" / "episode" / "stages").iterdir())
    assert [s.name[:3] for s in stages] == ["01_", "02_", "03_", "04_"]
    for s in stages:
        c = W.parse_contract(s / "CONTEXT.md")              # every stage has a contract
        assert c.inputs and len(c.outputs) == 1 and c.human_check
        for _, rel in c.inputs:                              # inputs are exact, existing paths
            assert rel.startswith("../")
    assert not W.parse_contract(stages[-1] / "CONTEXT.md").agent   # 04: the owner's stage
    for s in stages[:-1]:                                    # every drafted stage: no minors
        assert W.parse_contract(s / "CONTEXT.md").checks == ["no_minors"]


def test_full_week_walk_with_owner_checks(ws, tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    ep = W.new_episode(ws, "Autumn city coffee week")
    assert ep.name == "ep-001-autumn-city-coffee-week"
    p = ScriptedProvider([
        "Mon instagram sfw: latte by the window\nFri fanvue explicit: after-hours studio\n",
        "Mon instagram: First latte of autumn. #AI #virtualcreator\n",
        "1. Auburn bob, green eyes, freckles, silver hoops; cafe window, film light\n"])
    walk_to(ws, ep, p, 3, audit)
    rows = W.status(ws, ep)
    assert [r["state"] for r in rows] == ["checked"] * 3 + ["yours to do"]
    assert W.next_stage(ep).stage == "04_review"
    with pytest.raises(W.WorkspaceError, match="owner's stage"):
        W.draft(ws, ep, p, MODEL)
    # Each stage loaded only what its contract lists: captions saw the plan, not the brief;
    # the prompts stage saw the persona, not the voice file.
    captions_call, prompts_call = p.calls[1], p.calls[2]
    msg = captions_call["messages"][0]["content"]
    assert "plan.md" in msg and "brief.md" not in msg and "voice.md" in msg
    assert "voice.md" not in prompts_call["messages"][0]["content"]
    assert "Autumn city coffee week" in (ws / "_index" / "episodes.md").read_text()
    events = [r["event"] for r in audit.records()]
    assert events.count("workspace.drafted") == 3 and events.count("workspace.checked") == 3


def test_nothing_runs_until_the_owner_checked_the_last_output(ws):
    ep = W.new_episode(ws, "Rainy day")
    p = ScriptedProvider(["Mon instagram sfw: umbrella walk\n"])
    W.draft(ws, ep, p, MODEL)
    with pytest.raises(W.WorkspaceError, match="needs your check"):
        W.draft(ws, ep, p, MODEL)
    assert W.status(ws, ep)[0]["state"] == "drafted: owner check needed"


def test_editing_after_the_check_voids_it(ws):
    ep = W.new_episode(ws, "Gallery day")
    W.draft(ws, ep, ScriptedProvider(["Mon instagram sfw: gallery\n"]), MODEL)
    c = W.check(ws, ep, "01", "human:owner")
    assert W.is_checked(c)
    (c.out_dir / "plan.md").write_text("Mon instagram sfw: gallery. Edited.\n")
    assert not W.is_checked(c) and W.status(ws, ep)[0]["state"].startswith("drafted")


def test_the_no_minors_check_blocks_the_owner_check_until_fixed(ws):
    # The creator is a fictional adult: a stage that refers to minors cannot be checked.
    ep = W.new_episode(ws, "Back to school week")
    c, out = W.draft(ws, ep, ScriptedProvider(["Mon instagram sfw: schoolgirl outfit\n"]),
                     MODEL)
    issues = " ".join(W.status(ws, ep)[0]["issues"])
    assert "refers to minors" in issues and "schoolgirl" in issues
    with pytest.raises(W.WorkspaceError, match="fix these first"):
        W.check(ws, ep, "01", "human:owner")
    out.write_text("Mon instagram sfw: tailored autumn blazer\n")      # owner fixes
    assert W.check(ws, ep, "01", "human:owner").stage == "01_plan"


def test_setup_placeholders_and_the_model_budget_stop_a_stage(tmp_path):
    ws = W.create("creator-week", home=tmp_path)            # persona still has {{...}}
    ep = W.new_episode(ws, "Idea")
    with pytest.raises(W.WorkspaceError, match="set up persona.md first"):
        W.draft(ws, ep, ScriptedProvider(["x"]), MODEL)
    (ws / "_shared" / "persona.md").write_text(PERSONA + "x" * 40000)
    with pytest.raises(W.WorkspaceError, match="over this model's budget"):
        W.draft(ws, ep, ScriptedProvider(["x"]), {"id": "small", "context": 8192})


def test_only_a_human_checks_and_outputs_stay_inside_the_stage(ws):
    ep = W.new_episode(ws, "Idea")
    c, out = W.draft(ws, ep, ScriptedProvider(["```markdown\nMon instagram sfw: x\n```"]),
                     MODEL)
    assert out.parent == c.out_dir and out.read_text() == "Mon instagram sfw: x\n"  # no fences
    with pytest.raises(PermissionError):
        W.check(ws, ep, "01", "agent:jarvis")
    rec = json.loads((W.check(ws, ep, "01", "human:owner").out_dir / ".checked").read_text())
    assert rec["by"] == "human:owner" and len(rec["sha256"]["plan.md"]) == 64


def test_create_refuses_to_overwrite_and_unknown_templates(tmp_path):
    W.create("creator-week", home=tmp_path)
    with pytest.raises(W.WorkspaceError, match="already exists"):
        W.create("creator-week", home=tmp_path)
    with pytest.raises(W.WorkspaceError, match="no workspace template"):
        W.create("nope", home=tmp_path)


def test_asking_jarvis_to_draft_puts_the_owners_check_on_screen(ws, tmp_path):
    # The owner kept getting stuck: Jarvis drafted, then waited on a typed command.
    from bau.assistant import Assistant
    W.new_episode(ws, "Rooftop sunset week")
    jv = Assistant(tmp_path, ScriptedProvider([
        {"tool": "draft_stage", "input": {"workspace": "creator-week", "episode": "ep-001"}},
        "Mon instagram sfw: rooftop sunset\n",
        "Drafted. Your check is on screen."]), MODEL, "human:owner")
    r = jv.ask("draft the next step of week 1")
    assert r.text == "Drafted. Your check is on screen."
    assert [p["tool"] for p in r.pending] == ["check_stage"]
    out = jv.confirm(r.pending[0]["id"], True, "human:owner")
    assert out["done"] and out["result"]["checked"] == "01_plan"


def test_jarvis_drafts_stages_but_has_no_way_to_check_them(ws, tmp_path):
    from bau.assistant import Assistant
    ep = W.new_episode(ws, "Rooftop sunset week")
    jv = Assistant(tmp_path, ScriptedProvider(["Mon instagram sfw: rooftop sunset\n"]),
                   MODEL, "human:owner")
    assert not any("check" in name for name in jv.tools)       # checking is owner-only
    assert jv.tools["draft_stage"].kind == "act"
    out, err = jv._run_tool("draft_stage", {"workspace": "creator-week",
                                            "episode": "ep-001"})
    assert not err and out["stage"] == "01_plan"
    # The owner's check pops up on their screen; it is never a tool the model can call.
    from bau.assistant import CONFIRMATION_NOTE
    assert out["status"] == CONFIRMATION_NOTE
    card = jv.pending[out["pending_id"]]
    assert card.tool == "check_stage" and "rooftop sunset" in card.summary
    with pytest.raises(PermissionError):
        jv.confirm(card.id, True, "agent:jarvis")                # still the owner's click
    seen, err = jv._run_tool("workspaces", {})
    assert seen["creator-week"][ep.name][0] == "01_plan: drafted: owner check needed"
    again, err = jv._run_tool("draft_stage", {"workspace": "creator-week",
                                              "episode": "ep-001"})
    assert err and "needs your check" in again["error"]
