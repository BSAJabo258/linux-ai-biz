"""The kids series consistency engine: character and style sheets the owner fills in once,
then every clip prompt carries the same "lock" text so characters look the same in every
clip; story formats scaled to the episode length; drift and sameness checks. Written
before the code it tests."""

import json

import pytest
import yaml
from test_workspace import BIBLE

from bau import series as S
from bau import workspace as W

PIP = {"id": "pip", "name": "Pip", "kind": "a small round hedgehog",
       "look": ["soft round body, knee-high to a child", "warm brown spines and a cream face",
                "big dark eyes with a white sparkle"],
       "outfit": "a yellow knitted scarf", "colors": ["brown", "cream", "yellow"],
       "personality": "curious, a little shy, kind",
       "voice": {"tts": "kokoro", "voice": "af_bella", "pace": "slow"},
       "catchphrase": "Let's find out!", "never": ["angry", "sharp spines"]}
MO = {**PIP, "id": "mo", "name": "Mo", "kind": "a tall gentle moose",
      "look": ["long legs and a round nose", "soft grey-brown fur", "small velvet antlers"],
      "outfit": "a green backpack", "colors": ["grey", "brown", "green"],
      "catchphrase": "Together!"}
STYLE = {"art_style": "soft 3D clay animation, rounded shapes",
         "palette": "warm pastels: peach, mint and sky blue",
         "lighting": "soft, warm daylight", "camera": "slow, steady moves at a child's eye level",
         "aspect_ratio": "16:9", "avoid": ["scary faces", "fast flashing", "text on screen"]}


@pytest.fixture
def ws(tmp_path):
    w = W.create("kids-channel", home=tmp_path)
    (w / "_shared" / "series-bible.md").write_text(BIBLE)
    return w


def fill(ws, *chars, style=STYLE):
    d = ws / "_shared" / "characters"
    for f in d.glob("*.yaml"):
        f.unlink()
    for c in chars:
        (d / f"{c['id']}.yaml").write_text(yaml.safe_dump(c))
    (ws / "_shared" / "style.yaml").write_text(yaml.safe_dump(style))
    return S.Series(ws)


# ------------------------------------------------------------------ the owner's sheets

def test_new_workspace_has_sheets_to_fill_and_nothing_runs_until_filled(ws):
    assert (ws / "_shared" / "characters").is_dir() and (ws / "_shared" / "style.yaml").is_file()
    probs = S.Series(ws).problems()
    assert probs and any("{{" in p or "fill in" in p for p in probs)
    with pytest.raises(S.SeriesError):
        S.Series(ws).prompt("Pip finds a lost acorn", ["pip"])


def test_sheets_are_checked(ws):
    assert fill(ws, PIP, MO).problems() == []
    bad = [{**PIP, "look": ["round"]},                          # too little to lock a look
           {**PIP, "name": "Peppa Pig"},                        # someone else's character
           {k: v for k, v in PIP.items() if k != "outfit"}]
    for c in bad:
        assert fill(ws, c).problems(), c
    assert fill(ws, PIP, style={**STYLE, "aspect_ratio": "4:3"}).problems()


# ------------------------------------------------------------------ the lock

def test_every_prompt_carries_the_same_character_and_style_lock(ws):
    s = fill(ws, PIP, MO)
    a = s.prompt("Pip finds a lost acorn under a leaf", ["pip"])
    b = s.prompt("Pip and Mo carry the acorn home together", ["pip", "mo"])
    lock = s.lock("pip")
    assert lock in a and lock in b                                # word for word, every time
    assert "yellow knitted scarf" in lock and "hedgehog" in lock
    for part in (STYLE["art_style"], STYLE["palette"], STYLE["lighting"], STYLE["camera"]):
        assert part in a
    assert "Avoid: scary faces, fast flashing, text on screen" in a
    assert len(a) <= 2500


def test_prompts_refuse_unknown_characters_and_unsafe_scenes(ws):
    s = fill(ws, PIP)
    with pytest.raises(S.SeriesError, match="no character"):
        s.prompt("Zed waves", ["zed"])
    with pytest.raises(S.SeriesError, match="kids"):
        s.prompt("Pip finds a knife in a creepy cave", ["pip"])


# ------------------------------------------------------------------ drift

def test_drift_finds_a_character_described_differently(ws):
    s = fill(ws, PIP, MO)
    good = s.prompt("Pip waves hello", ["pip"])
    assert s.drift(good) == []
    text = "Scene 2: Pip, in a red scarf, runs to the pond."
    issues = s.drift(text)
    assert any(i["issue"] == "off_model" and "red" in i["detail"] for i in issues)
    assert any(i["issue"] == "no_lock" and "Pip" in i["detail"] for i in issues)


# ------------------------------------------------------------------ formats and plans

def test_formats_are_story_shapes_with_beats(ws):
    fmts = S.Series(ws).formats()
    assert {"problem-song-solution", "count-along", "question-reveal"} <= set(fmts)
    for f in fmts.values():
        assert f["beats"] and abs(sum(b["share"] for b in f["beats"]) - 1) < 1e-6


def test_plan_scales_a_format_to_the_episode_into_clip_sized_scenes(ws):
    s = fill(ws, PIP, MO)
    ep = W.new_episode(ws, "Pip learns to share berries")
    plan = s.plan(ep, "problem-song-solution", seconds=60, cast=["pip", "mo"])
    secs = [sc["seconds"] for sc in plan["scenes"]]
    assert all(3 <= x <= 15 for x in secs) and abs(sum(secs) - 60) <= 3
    assert all(s.lock("pip") in sc["prompt"] for sc in plan["scenes"])
    assert "share berries" in plan["scenes"][0]["scene"]
    saved = yaml.safe_load((ep / "series.yaml").read_text())
    assert saved["format"] == "problem-song-solution" and saved["cast"] == ["pip", "mo"]
    assert (ep / "series-plan.md").read_text().startswith("# Series plan")


def test_sameness_warns_before_the_channel_looks_mass_produced(ws):
    s = fill(ws, PIP)
    for idea in ("Pip counts apples", "Pip counts pears", "Pip counts plums"):
        s.plan(W.new_episode(ws, idea), "count-along", seconds=30, cast=["pip"])
    ep = W.new_episode(ws, "Pip counts cherries")
    plan = s.plan(ep, "count-along", seconds=30, cast=["pip"])
    assert any("same format" in w for w in plan["warnings"])
    assert any("almost the same" in w for w in plan["warnings"])


# ------------------------------------------------------------------ workspace, Jarvis, CLI

def test_video_prompt_stage_checks_the_lock(ws):
    s = fill(ws, PIP)
    ep = W.new_episode(ws, "Pip finds an acorn")
    c = next(c for c in W.contracts(ep) if c.stage.startswith("04"))
    assert "series_lock" in c.checks
    (c.out_dir / c.outputs[0]).write_text("1. Pip in a red scarf runs.\n")
    assert any(i["issue"] in ("off_model", "no_lock") for i in W.run_checks(ws, ep, c))
    (c.out_dir / c.outputs[0]).write_text("1. " + s.prompt("Pip runs", ["pip"]) + "\n")
    assert W.run_checks(ws, ep, c) == []


def test_jarvis_tools(ws, tmp_path):
    from bau.assistant import TOOL_NODE, Assistant
    from bau.audit import AuditLog
    fill(ws, PIP)
    W.new_episode(ws, "Pip finds an acorn")
    a = Assistant(tmp_path, None, {}, "human:owner", AuditLog(tmp_path / "a.jsonl", key=b""))
    assert a.tools["clip_prompt"].kind == "read" and TOOL_NODE["plan_episode"] == "producer"
    out, err = a._run_tool("clip_prompt", {"workspace": ws.name, "scene": "Pip waves",
                                           "cast": ["pip"]})
    assert not err and "hedgehog" in out["prompt"]
    out, err = a._run_tool("plan_episode", {"workspace": ws.name, "episode": "ep-001",
                                            "format": "count-along", "seconds": 30})
    assert not err and out["scenes"]


def test_cli(ws, tmp_path, monkeypatch, capsys):
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    fill(ws, PIP)
    assert main(["series", "check", ws.name]) == 0
    assert json.loads(capsys.readouterr().out)["problems"] == []
    assert main(["series", "prompt", ws.name, "Pip waves", "--cast", "pip"]) == 0
    assert "hedgehog" in capsys.readouterr().out
    W.new_episode(ws, "Pip finds an acorn")
    assert main(["series", "plan", ws.name, "ep-001", "--format", "question-reveal",
                 "--seconds", "45"]) == 0
    assert json.loads(capsys.readouterr().out)["scenes"]
    assert main(["series", "formats"]) == 0
