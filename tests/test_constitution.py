"""The owner's operating constitution: loaded into every Jarvis conversation, editable,
never above the safety rules."""

import json

from bau.assistant import CONSTITUTION_MAX, PERSONA, Assistant, load_constitution
from bau.audit import AuditLog
from bau.home import init_home
from bau.models.providers import ScriptedProvider


def make(home, script=()):
    return Assistant(home, ScriptedProvider(script=list(script)), {}, "human:owner",
                     AuditLog(home / "audit" / "chain.jsonl", key=b""))


def test_shipped_constitution_has_six_layers_in_order(tmp_path):
    text = load_constitution(tmp_path)              # nothing copied yet: the shipped one
    heads = [line for line in text.splitlines() if line.startswith("# ")]
    assert heads == ["# Core identity", "# Learning principles", "# Engineering rules",
                     "# Security rules", "# Self-improvement", "# BAUBSA mode"]
    assert "think correctly, move correctly, build correctly" in text
    assert "Seek root causes instead of symptoms." in text


def test_jarvis_gets_it_on_every_turn_after_the_safety_rules(tmp_path):
    a = make(tmp_path, ["Hello."])
    a.ask("Hi")
    sent = a.provider.calls[0]["system"]
    safety = PERSONA.splitlines()[0]
    assert sent.index(safety) < sent.index("never overrides the rules above") \
        < sent.index("# Core identity")
    assert "approvals stay the owner's" in sent


def test_owner_edits_survive_init_and_reach_jarvis(tmp_path):
    init_home(tmp_path)
    mine = tmp_path / "constitution" / "2-learning-rules.md"
    assert mine.exists()
    mine.write_text("# Learning principles\n\n1. Teach with songs.\n")
    init_home(tmp_path)                             # a later `bau init` keeps the edit
    assert mine.read_text().endswith("Teach with songs.\n")
    (tmp_path / "constitution" / "7-kids.md").write_text("# Kids\n\nOne idea per episode.")
    a = make(tmp_path, ["Ok."])
    a.ask("Hi")
    sent = a.provider.calls[0]["system"]
    assert "Teach with songs." in sent and "One idea per episode." in sent
    assert sent.index("Teach with songs.") < sent.index("One idea per episode.")


def test_constitution_is_bounded(tmp_path):
    init_home(tmp_path)
    (tmp_path / "constitution" / "9-huge.md").write_text("x" * (CONSTITUTION_MAX * 2))
    assert len(load_constitution(tmp_path)) == CONSTITUTION_MAX


def test_lessons_saved_with_remember_come_back_with_recall(tmp_path):
    a = make(tmp_path)
    a._run_tool("remember", {"title": "Lesson: Z.ai busy", "note": "The free model is "
                             "sometimes overloaded; wait a minute and ask again."})
    out, err = a._run_tool("recall", {"query": "overloaded model"})
    assert not err and out[0]["title"] == "Lesson: Z.ai busy"
    assert a.tools["recall"].kind == "read"


def test_cli_shows_where_the_constitution_lives(tmp_path, monkeypatch, capsys):
    from bau import cli_ext
    monkeypatch.setenv("BAU_HOME", str(tmp_path))

    class A:
        jv_cmd = "constitution"
    assert cli_ext.cmd_jarvis(A()) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["yours"] is False and "bau init" in out["edit"]
    init_home(tmp_path)
    cli_ext.cmd_jarvis(A())
    out = json.loads(capsys.readouterr().out)
    assert out["yours"] is True and out["files"][0] == "1-identity.md"
