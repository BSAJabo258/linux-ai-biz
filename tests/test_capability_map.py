"""The capability map: every layer Jarvis needs (thinking, seeing, browsing, computer use,
connectors, coding, memory, planning, teams of agents, workflows, checking, media,
business), what BAU already has for it, which researched tools could fill each gap and
how (use directly, behind an adapter, or skip because BAU already does it), and the order
to build in. Written before the code it tests."""

import json
from pathlib import Path

import pytest
import yaml

from bau.toolbox import PLANS, STATUSES, CapabilityMap, Toolbox

ROOT = Path(__file__).resolve().parents[1]
LAYER = {"id": "web", "name": "Web interaction", "what": "Use websites and fill forms.",
         "status": "gap", "in_bau": [{"path": "src/bau/scout/", "does": "reads GitHub"}],
         "tools": [{"name": "Browser Use", "plan": "adapter", "why": "best fit"}],
         "risk": "high", "rules": ["submitting is the owner's click"],
         "next": "build the browser lane", "build": 1}


def shipped():
    return CapabilityMap()


def mapped(tmp_path, layers):
    p = tmp_path / "capability_map.yaml"
    p.write_text(yaml.safe_dump({"checked": "2026-10-12", "layers": layers}))
    return CapabilityMap(data=p, toolbox=Toolbox())


# ------------------------------------------------------------------ the shipped map

def test_shipped_map_is_complete_and_valid():
    m = shipped()
    assert m.problems() == []
    ids = [layer["id"] for layer in m.layers]
    for need in ("intelligence", "perception", "computer-use", "web", "connect", "coding",
                 "memory", "planning", "agents", "workflows", "verification", "media",
                 "business"):
        assert need in ids, need
    builds = [layer["build"] for layer in m.layers if layer.get("build")]
    assert len(builds) == len(set(builds)) and min(builds) == 1     # one clear order
    assert all(layer.get("next") for layer in m.layers if layer["status"] != "have")


def test_what_bau_already_has_really_exists():
    for layer in shipped().layers:
        for have in layer["in_bau"]:
            assert (ROOT / have["path"]).exists(), (layer["id"], have["path"])


def test_every_tool_named_is_researched_in_the_toolbox():
    tb = Toolbox()
    for layer in shipped().layers:
        for t in layer["tools"]:
            assert tb.find(t["name"]) is not None, (layer["id"], t["name"])
            assert t["plan"] in PLANS and t["why"]


def test_the_browser_lane_keeps_submit_for_the_owner():
    web = shipped().layer("web")
    assert web["status"] != "have" and web["build"] == 1
    assert web["permissions"] == ["read", "fill", "draft", "submit"]
    assert web["owner_confirms"] == ["submit"]
    assert any("untrusted" in r for r in web["rules"])
    names = {t["name"] for t in web["tools"]}
    assert {"Browserable", "Pie", "BrowserSkill"} <= names           # the owner's leads
    logged_in = next(t for t in web["tools"] if t["name"] == "BrowserSkill")
    assert logged_in["plan"] == "later"                              # riskiest goes last


def test_duplicates_say_what_bau_already_does():
    skips = [t for layer in shipped().layers for t in layer["tools"] if t["plan"] == "skip"]
    assert skips and all("BAU" in t["why"] or "bau" in t["why"] for t in skips)


# ------------------------------------------------------------------ bad maps are refused

def test_bad_maps_are_refused(tmp_path):
    bad = [{**LAYER, "status": "magic"},
           {**LAYER, "tools": [{"name": "Not A Real Tool", "plan": "adapter", "why": "x"}]},
           {**LAYER, "tools": [{"name": "Browser Use", "plan": "yolo", "why": "x"}]},
           {**LAYER, "next": "", "status": "gap"},
           {**LAYER, "what": "Makes BAU fully compliant."},
           {k: v for k, v in LAYER.items() if k != "risk"}]
    for i, b in enumerate(bad):
        assert mapped(tmp_path, [{**b, "id": f"l{i}", "build": i + 1}]).problems(), b
    assert mapped(tmp_path, [LAYER, {**LAYER, "build": 2}]).problems()      # id twice
    assert mapped(tmp_path, [LAYER]).problems() == []
    assert set(STATUSES) == {"have", "partial", "gap"}


# ------------------------------------------------------------------ reading it

def test_summary_and_one_layer_with_evidence():
    m = shipped()
    s = m.summary()
    assert [x["build"] for x in s["build_order"]] == sorted(x["build"] for x in s["build_order"])
    assert s["build_order"][0]["id"] == "web"
    assert s["counts"]["have"] >= 3 and s["counts"]["gap"] >= 1
    web = m.show("web")
    tool = next(t for t in web["tools"] if t["name"] == "Browser Use")
    assert tool["evidence"].startswith("claimed") and tool["next"].startswith("bau toolbox")
    with pytest.raises(KeyError):
        m.show("telepathy")


def test_new_toolbox_entries_carry_their_own_check_date():
    tb = Toolbox()
    e = tb.find("Browserable")
    assert e["checked"] == "2026-10-12"
    hit = next(h for h in tb.ask("fill forms on websites", k=20) if h["name"] == "Browserable")
    assert "2026-10-12" in hit["evidence"]
    assert tb.problems() == []


def test_jarvis_and_cli(tmp_path, monkeypatch, capsys):
    from bau.assistant import TOOL_NODE, Assistant
    from bau.audit import AuditLog
    from bau.cli import main
    a = Assistant(tmp_path, None, {}, "human:owner", AuditLog(tmp_path / "a.jsonl", key=b""))
    assert a.tools["capability_map"].kind == "read" and TOOL_NODE["capability_map"] == "scout"
    out, err = a._run_tool("capability_map", {})
    assert not err and out["build_order"][0]["id"] == "web"
    out, err = a._run_tool("capability_map", {"layer": "web"})
    assert not err and out["owner_confirms"] == ["submit"]
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    assert main(["toolbox", "map"]) == 0
    assert json.loads(capsys.readouterr().out)["build_order"]
    assert main(["toolbox", "map", "--layer", "memory"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "have"


def test_owner_guide_covers_every_layer():
    doc = (ROOT / "docs" / "CAPABILITY-MAP.md").read_text()
    for layer in shipped().layers:
        assert layer["name"] in doc, layer["name"]
    assert "bau toolbox map" in doc
