"""ICM workspaces: the kids-channel pipeline one agent walks, the owner checks each stage."""

import json

import pytest

from bau import workspace as W
from bau.audit import AuditLog
from bau.models.providers import ScriptedProvider

MODEL = {"id": "test-model", "context": 32768}
BIBLE = """# Series bible
- Channel name: Pip and Moss
- Age band: 4-6
- What children learn here: sharing and counting
## The world
A sunny meadow by a slow river.
## Characters
Pip: a small round yellow duckling with a blue scarf, curious and kind.
Moss: a green tortoise with a mossy shell, slow, wise and gentle.
## Episode shape
- Length: about 3 minutes
- Always: starts with a small problem, ends with a song
"""


@pytest.fixture
def ws(tmp_path):
    w = W.create("kids-channel", home=tmp_path)
    (w / "_shared" / "series-bible.md").write_text(BIBLE)
    return w


def walk_to(ws, ep, provider, upto, audit=None):
    for _ in range(upto):
        c, _ = W.draft(ws, ep, provider, MODEL, audit)
        W.check(ws, ep, c.stage[:2], "human:owner", audit)


def test_shipped_template_follows_the_icm_invariants():
    ws_src = W.shipped_data() / "workspaces" / "kids-channel"
    entry = (ws_src / "CLAUDE.md").read_text().splitlines()
    assert len(entry) <= 60                                    # small routing entry file
    stages = sorted((ws_src / "_templates" / "episode" / "stages").iterdir())
    assert [s.name[:3] for s in stages] == ["01_", "02_", "03_", "04_", "05_", "06_"]
    for s in stages:
        c = W.parse_contract(s / "CONTEXT.md")              # every stage has a contract
        assert c.inputs and len(c.outputs) == 1 and c.human_check
        for _, rel in c.inputs:                              # inputs are exact, existing paths
            assert rel.startswith("../")
    assert not W.parse_contract(stages[-1] / "CONTEXT.md").agent   # 06: the owner's stage


def test_full_episode_walk_with_owner_checks(ws, tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    ep = W.new_episode(ws, "Pip learns to share berries")
    assert ep.name == "ep-001-pip-learns-to-share-berries"
    p = ScriptedProvider([
        "# Pip shares the berries\nLearning goal: sharing.\nPip finds berries ...",
        "SCENE: the meadow\nNarrator: Pip finds five red berries.\n",
        "1. Meadow, Pip and Moss, 20 s\n",
        "1. A small round yellow duckling with a blue scarf in a sunny meadow\n",
        "Title: Pip shares the berries\nDescription: Pip and Moss learn to share.\n"
        "Tags: sharing, counting, preschool\n"])
    walk_to(ws, ep, p, 5, audit)
    rows = W.status(ws, ep)
    assert [r["state"] for r in rows] == ["checked"] * 5 + ["yours to do"]
    assert W.next_stage(ep).stage == "06_review"
    with pytest.raises(W.WorkspaceError, match="owner's stage"):
        W.draft(ws, ep, p, MODEL)
    # Each stage loaded only what its contract lists: the script stage saw the pitch,
    # not the brief; the storyboard stage saw the script, not the bible's voice file.
    script_call, board_call = p.calls[1], p.calls[2]
    msg = script_call["messages"][0]["content"]
    assert "pitch.md" in msg and "brief.md" not in msg and "voice.md" in msg
    assert "voice.md" not in board_call["messages"][0]["content"]
    assert "Pip shares the berries" in (ws / "_index" / "episodes.md").read_text()
    events = [r["event"] for r in audit.records()]
    assert events.count("workspace.drafted") == 5 and events.count("workspace.checked") == 5


def test_nothing_runs_until_the_owner_checked_the_last_output(ws):
    ep = W.new_episode(ws, "Counting clouds")
    p = ScriptedProvider(["# Counting clouds\nLearning goal: counting to five."])
    W.draft(ws, ep, p, MODEL)
    with pytest.raises(W.WorkspaceError, match="needs your check"):
        W.draft(ws, ep, p, MODEL)
    assert W.status(ws, ep)[0]["state"] == "drafted: owner check needed"


def test_editing_after_the_check_voids_it(ws):
    ep = W.new_episode(ws, "Moss is slow")
    W.draft(ws, ep, ScriptedProvider(["# Moss is slow\nGoal: patience."]), MODEL)
    c = W.check(ws, ep, "01", "human:owner")
    assert W.is_checked(c)
    (c.out_dir / "pitch.md").write_text("# Moss is slow\nGoal: patience. Edited.\n")
    assert not W.is_checked(c) and W.status(ws, ep)[0]["state"].startswith("drafted")


def test_kids_checks_block_the_owner_check_until_fixed(ws):
    ep = W.new_episode(ws, "Pip goes exploring")
    p = ScriptedProvider(["# Pip goes exploring\nGoal: curiosity.",
                          "SCENE: woods\nNarrator: Pip meets Peppa Pig. Comment below your "
                          "name and age!\n"])
    walk_to(ws, ep, p, 1)
    c, out = W.draft(ws, ep, p, MODEL)
    issues = " ".join(W.status(ws, ep)[1]["issues"])
    assert "someone else owns" in issues and "personal information" in issues
    with pytest.raises(W.WorkspaceError, match="fix these first"):
        W.check(ws, ep, "02", "human:owner")
    out.write_text("SCENE: woods\nNarrator: Pip meets a friendly frog.\n")   # owner fixes
    assert W.check(ws, ep, "02", "human:owner").stage == "02_script"


def test_metadata_checks_titles_and_near_duplicates(ws):
    first = W.new_episode(ws, "Berries")
    meta = "Title: Pip shares the berries\nDescription: Sharing.\nTags: sharing\n"
    p = ScriptedProvider(["# Berries", "SCENE: a\nHi.", "1. a", "1. a", meta])
    walk_to(ws, first, p, 5)
    second = W.new_episode(ws, "Berries again")
    p2 = ScriptedProvider(["# Berries again", "SCENE: a\nHi.", "1. a", "1. a",
                           "Title: PIP SHARES THE BERRIES!!!\nDescription: Watch "
                           "www.example.com\nTags: sharing\n"])
    walk_to(ws, second, p2, 4)
    W.draft(ws, second, p2, MODEL)
    issues = " ".join(W.status(ws, second)[4]["issues"])
    assert "sensational title" in issues and "off YouTube" in issues
    assert "almost the same as ep-001" in issues


def test_setup_placeholders_and_the_model_budget_stop_a_stage(tmp_path):
    ws = W.create("kids-channel", home=tmp_path)            # bible still has {{...}}
    ep = W.new_episode(ws, "Idea")
    with pytest.raises(W.WorkspaceError, match="set up series-bible.md first"):
        W.draft(ws, ep, ScriptedProvider(["x"]), MODEL)
    (ws / "_shared" / "series-bible.md").write_text(BIBLE + "x" * 40000)
    with pytest.raises(W.WorkspaceError, match="over this model's budget"):
        W.draft(ws, ep, ScriptedProvider(["x"]), {"id": "small", "context": 8192})


def test_only_a_human_checks_and_outputs_stay_inside_the_stage(ws):
    ep = W.new_episode(ws, "Idea")
    c, out = W.draft(ws, ep, ScriptedProvider(["```markdown\n# Idea\nGoal: x\n```"]), MODEL)
    assert out.parent == c.out_dir and out.read_text() == "# Idea\nGoal: x\n"   # fences off
    with pytest.raises(PermissionError):
        W.check(ws, ep, "01", "agent:jarvis")
    rec = json.loads((W.check(ws, ep, "01", "human:owner").out_dir / ".checked").read_text())
    assert rec["by"] == "human:owner" and len(rec["sha256"]["pitch.md"]) == 64


def test_create_refuses_to_overwrite_and_unknown_templates(tmp_path):
    W.create("kids-channel", home=tmp_path)
    with pytest.raises(W.WorkspaceError, match="already exists"):
        W.create("kids-channel", home=tmp_path)
    with pytest.raises(W.WorkspaceError, match="no workspace template"):
        W.create("nope", home=tmp_path)


def test_asking_jarvis_to_draft_puts_the_owners_check_on_screen(ws, tmp_path):
    # The owner kept getting stuck: Jarvis drafted, then waited on a typed command.
    from bau.assistant import Assistant
    W.new_episode(ws, "Pip and the rainbow")
    jv = Assistant(tmp_path, ScriptedProvider([
        {"tool": "draft_stage", "input": {"workspace": "kids-channel", "episode": "ep-001"}},
        "# Pip and the rainbow\nGoal: colours.",
        "Drafted. Your check is on screen."]), MODEL, "human:owner")
    r = jv.ask("draft the next step of episode 1")
    assert r.text == "Drafted. Your check is on screen."
    assert [p["tool"] for p in r.pending] == ["check_stage"]
    out = jv.confirm(r.pending[0]["id"], True, "human:owner")
    assert out["done"] and out["result"]["checked"] == "01_pitch"


def test_jarvis_drafts_stages_but_has_no_way_to_check_them(ws, tmp_path):
    from bau.assistant import Assistant
    ep = W.new_episode(ws, "Pip and the rainbow")
    jv = Assistant(tmp_path, ScriptedProvider(["# Pip and the rainbow\nGoal: colours."]),
                   MODEL, "human:owner")
    assert not any("check" in name for name in jv.tools)       # checking is owner-only
    assert jv.tools["draft_stage"].kind == "act"
    out, err = jv._run_tool("draft_stage", {"workspace": "kids-channel",
                                            "episode": "ep-001"})
    assert not err and out["stage"] == "01_pitch"
    # The owner's check pops up on their screen; it is never a tool the model can call.
    from bau.assistant import CONFIRMATION_NOTE
    assert out["status"] == CONFIRMATION_NOTE
    card = jv.pending[out["pending_id"]]
    assert card.tool == "check_stage" and "Pip and the rainbow" in card.summary
    with pytest.raises(PermissionError):
        jv.confirm(card.id, True, "agent:jarvis")                # still the owner's click
    seen, err = jv._run_tool("workspaces", {})
    assert seen["kids-channel"][ep.name][0] == "01_pitch: drafted: owner check needed"
    again, err = jv._run_tool("draft_stage", {"workspace": "kids-channel",
                                              "episode": "ep-001"})
    assert err and "needs your check" in again["error"]
