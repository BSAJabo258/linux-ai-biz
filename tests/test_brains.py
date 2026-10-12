"""Brains per stage: each workspace stage folder says which brain drafts it - `small` (the
free local model, for routine steps), `strong` (Claude or Jarvis's best model, for the
steps that need judgement) or `content` (a local uncensored model in the sealed content
lane: no tools, never a kids workspace, only the content jobs its record lists). The owner
picks once which model each brain means. Written before the code it tests."""

import json

import pytest

from bau import brains as B
from bau import workspace as W
from bau.audit import AuditLog
from bau.models.providers import ScriptedProvider
from bau.registry import CapabilityRegistry

BASE = {"name": "m", "version": "1", "source": "test", "license": "Apache-2.0",
        "commercial_use": True, "privacy": "local", "context": 8192, "input_types": ["text"],
        "quality": 0.5, "latency_ms": 100, "cost_in_per_mtok": 0, "cost_out_per_mtok": 0}
SMALL = {**BASE, "model_id": "tiny-local", "provider": "local", "deployment": "local",
         "trust_level": "QUANTIZED", "tools": True, "status": "APPROVED",
         "benchmark": {"reply_ok": True, "tool_calls": True}}
STRONG = {**BASE, "model_id": "claude-test", "provider": "anthropic", "deployment": "api",
          "trust_level": "OFFICIAL", "privacy": "vendor", "tools": True, "status": "APPROVED"}
CONTENT = {**BASE, "model_id": "tiny-uncensored", "provider": "local", "deployment": "local",
           "trust_level": "ABLITERATED", "tools": False, "status": "APPROVED",
           "lane": "content_only", "use_for": ["script", "lyrics"],
           "benchmark": {"reply_ok": True}}
STAGE = """# {n}_{name}: a test stage

One job: write {name}.md from the brief.

## Inputs
- Working (this run): ../../brief.md

## Process
1. Write it.

## Outputs
- {name}.md → output/

## Brain
{brain}

## Human check
Is it right?
"""


def registry(home, *recs):
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    for r in recs:
        reg.add("model", r)
    return reg


def workspace(home, stages, kids=False):
    ws = W.root(home) / "shop"
    t = ws / "_templates" / "episode"
    for n, (name, brain) in enumerate(stages, 1):
        d = t / "stages" / f"{n:02d}_{name}"
        d.mkdir(parents=True)
        (d / "CONTEXT.md").write_text(STAGE.format(n=f"{n:02d}", name=name, brain=brain))
    (t / "brief.md").write_text("# {{idea}}\n")
    (ws / "_shared").mkdir(parents=True)
    (ws / "CLAUDE.md").write_text("# A test workspace\n")
    if kids:
        (ws / "_shared" / "kids-rules.md").write_text("Kids rules.\n")
    (ws / "episodes").mkdir()
    return ws


class Factory:
    """Stands in for runtime.provider_for: a scripted model per registered id."""

    def __init__(self, home):
        self.home, self.made = home, []

    def __call__(self, mid, home=None):
        rec = CapabilityRegistry(self.home / "registry" / "capabilities.yaml").data["model"][mid]
        if rec["status"] not in ("APPROVED", "ACTIVE"):
            raise PermissionError(mid)
        self.made.append(mid)
        return ScriptedProvider([f"Draft by {mid}."] * 5), rec


JARVIS = (ScriptedProvider(["Draft by jarvis."] * 5), {"id": "jarvis-model"})


# ------------------------------------------------------------------ stage folders say which brain

def test_stage_folders_declare_their_brain(tmp_path):
    ws = workspace(tmp_path, [("pitch", "small"), ("script", "strong"),
                              ("lyrics", "content lyrics")])
    ep = W.new_episode(ws, "Summer sale")
    got = [(c.brain, c.content_kind) for c in W.contracts(ep)]
    assert got == [("small", ""), ("strong", ""), ("content", "lyrics")]
    bad = workspace(tmp_path / "b", [("x", "genius")])
    with pytest.raises(W.WorkspaceError, match="brain"):
        W.contracts(W.new_episode(bad, "idea"))


def test_a_stage_with_no_brain_line_uses_the_strong_brain(tmp_path):
    ws = W.create("kids-channel", home=tmp_path)
    W.contracts(W.new_episode(ws, "Pip finds an acorn"))         # parses
    ws2 = workspace(tmp_path / "o", [("x", "")])
    assert W.contracts(W.new_episode(ws2, "idea"))[0].brain == "strong"


def test_kids_template_uses_the_small_brain_for_routine_steps_and_never_content(tmp_path):
    ws = W.create("kids-channel", home=tmp_path)
    by = {c.stage: c.brain for c in W.contracts(W.new_episode(ws, "Pip counts"))
          if c.agent}
    assert by["01_pitch"] == "small" and by["05_metadata"] == "small"
    assert by["02_script"] == "strong" and by["04_video-prompts"] == "strong"
    assert "content" not in by.values()
    assert W.for_kids(ws)


# ------------------------------------------------------------------ the owner picks the models

def test_owner_chooses_which_model_each_brain_is(tmp_path):
    registry(tmp_path, SMALL, STRONG, CONTENT)
    audit = AuditLog(tmp_path / "audit" / "chain.jsonl", key=b"")
    assert B.config(tmp_path)["small"] == "tiny-local"            # first approved local
    assert B.config(tmp_path)["content"] is None                   # never chosen for you
    with pytest.raises(PermissionError):
        B.choose(tmp_path, "agent:jarvis", audit, content="tiny-uncensored")
    with pytest.raises(ValueError, match="content lane"):
        B.choose(tmp_path, "human:owner", audit, small="tiny-uncensored")   # the wall
    with pytest.raises(ValueError, match="content lane"):
        B.choose(tmp_path, "human:owner", audit, content="tiny-local")
    with pytest.raises(ValueError, match="not registered"):
        B.choose(tmp_path, "human:owner", audit, strong="nope")
    cfg = B.choose(tmp_path, "human:owner", audit, strong="claude-test",
                   content="tiny-uncensored")
    assert cfg == {"small": "tiny-local", "strong": "claude-test", "content": "tiny-uncensored"}
    assert any(r["event"] == "brains.chosen" for r in audit.records())


# ------------------------------------------------------------------ resolving a brain

def test_small_brain_runs_the_local_model_and_strong_is_jarvis(tmp_path):
    registry(tmp_path, SMALL, STRONG)
    ws = workspace(tmp_path, [("pitch", "small")])
    f = Factory(tmp_path)
    r = B.resolve("small", tmp_path, ws, JARVIS, factory=f)
    assert r["model"]["id"] == "tiny-local" and r["brain"] == "small" and not r["note"]
    r = B.resolve("strong", tmp_path, ws, JARVIS, factory=f)
    assert r["model"]["id"] == "jarvis-model"
    B.choose(tmp_path, "human:owner", None, strong="claude-test")
    assert B.resolve("strong", tmp_path, ws, JARVIS, factory=f)["model"]["id"] == "claude-test"


def test_no_small_model_falls_back_to_strong_and_says_so(tmp_path):
    registry(tmp_path, STRONG)
    ws = workspace(tmp_path, [("pitch", "small")])
    r = B.resolve("small", tmp_path, ws, JARVIS, factory=Factory(tmp_path))
    assert r["model"]["id"] == "jarvis-model" and "small" in r["note"]


def test_content_brain_is_walled_off(tmp_path):
    registry(tmp_path, SMALL, STRONG, CONTENT)
    f = Factory(tmp_path)
    shop = workspace(tmp_path, [("lyrics", "content lyrics")])
    with pytest.raises(ValueError, match="bau ws brains"):          # not chosen yet
        B.resolve("content", tmp_path, shop, JARVIS, factory=f, kind="lyrics")
    B.choose(tmp_path, "human:owner", None, content="tiny-uncensored")
    r = B.resolve("content", tmp_path, shop, JARVIS, factory=f, kind="lyrics")
    assert r["model"]["id"] == "tiny-uncensored"
    with pytest.raises(ValueError, match="use_for"):                  # not one of its jobs
        B.resolve("content", tmp_path, shop, JARVIS, factory=f, kind="ad_copy")
    with pytest.raises(ValueError, match="which content job"):
        B.resolve("content", tmp_path, shop, JARVIS, factory=f, kind="")
    kids = workspace(tmp_path / "k", [("lyrics", "content lyrics")], kids=True)
    with pytest.raises(ValueError, match="kids"):
        B.resolve("content", tmp_path, kids, JARVIS, factory=f, kind="lyrics")


# ------------------------------------------------------------------ Jarvis and the CLI

def test_jarvis_drafts_each_stage_with_its_brain(tmp_path):
    from bau.assistant import Assistant
    registry(tmp_path, SMALL, STRONG)
    ws = workspace(tmp_path, [("pitch", "small"), ("script", "strong")])
    ep = W.new_episode(ws, "Summer sale")
    f = Factory(tmp_path)
    a = Assistant(tmp_path, JARVIS[0], JARVIS[1], "human:owner",
                  AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""),
                  clients={"model_factory": f})
    out, err = a._run_tool("draft_stage", {"workspace": "shop", "episode": ep.name})
    assert not err and out["brain"] == "small" and out["model"] == "tiny-local"
    assert (ep / "stages" / "01_pitch" / "output" / "pitch.md").read_text().startswith(
        "Draft by tiny-local")
    W.check(ws, ep, "01", "human:owner", a.audit)
    out, err = a._run_tool("draft_stage", {"workspace": "shop", "episode": ep.name})
    assert not err and out["brain"] == "strong" and out["model"] == "jarvis-model"
    ev = [r for r in a.audit.records() if r["event"] == "workspace.drafted"]
    assert [e["data"]["brain"] for e in ev] == ["small", "strong"]
    calls = [json.loads(x) for x in (tmp_path / "usage" / "calls.jsonl").read_text().splitlines()]
    assert {c["model"] for c in calls} >= {"tiny-local", "jarvis-model"}   # both metered


def test_jarvis_can_redo_a_stage_with_the_strong_brain(tmp_path):
    from bau.assistant import Assistant
    registry(tmp_path, SMALL, STRONG)
    ws = workspace(tmp_path, [("pitch", "small")])
    ep = W.new_episode(ws, "Summer sale")
    a = Assistant(tmp_path, JARVIS[0], JARVIS[1], "human:owner",
                  AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""),
                  clients={"model_factory": Factory(tmp_path)})
    a._run_tool("draft_stage", {"workspace": "shop", "episode": ep.name})
    out, err = a._run_tool("draft_stage", {"workspace": "shop", "episode": ep.name,
                                           "brain": "strong"})
    assert not err and out["model"] == "jarvis-model"
    with pytest.raises(W.WorkspaceError, match="content brain"):
        a.tools["draft_stage"].fn(workspace="shop", episode=ep.name, brain="content")


def test_cli_shows_and_sets_brains(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    registry(tmp_path, SMALL, STRONG, CONTENT)
    assert main(["ws", "brains"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["brains"]["small"] == "tiny-local" and "content" in shown["what"]
    monkeypatch.setattr("bau.cli_ext._human", lambda: "human:owner")
    assert main(["ws", "brains", "--content", "tiny-uncensored"]) == 0
    assert json.loads(capsys.readouterr().out)["content"] == "tiny-uncensored"
    assert main(["ws", "brains", "--small", "tiny-uncensored"]) != 0


def test_shipped_small_and_uncensored_models_are_pinned_and_waiting_for_the_owner():
    import yaml

    from bau.home import shipped_data
    from bau.registry import validate
    models = yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text())["model"]
    for mid in ("qwen3.5-4b", "qwen3.5-0.8b", "qwen3-4b-heretic-content"):
        rec = models[mid]
        assert validate("model", rec) == []
        assert rec["status"] == "REGISTERED"                     # the owner benches, approves
        assert len(rec["download"]["sha256"]) == 64 and rec["download"]["size"] > 0
        assert rec["deployment"] == "local" and rec["commercial_use"] is True
    sealed = models["qwen3-4b-heretic-content"]
    assert sealed["lane"] == "content_only" and sealed["tools"] is False
    assert sealed["endpoint"] != models["qwen3.5-4b"]["endpoint"]  # never answers as Jarvis
