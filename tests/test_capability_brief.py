"""One task, one answer: what BAU already has, the gap, the researched tools and this
week's newest open-source candidates. Read-only, offline, and never a decision."""

import json
from pathlib import Path

from bau.assistant import TOOL_NODE, Assistant
from bau.audit import AuditLog
from bau.cli import main
from bau.toolbox import Toolbox, brief

ROOT = Path(__file__).resolve().parents[1]


def assistant(home):
    return Assistant(home, None, {}, "human:owner", AuditLog(home / "a.jsonl", key=b""))


def latest(repo, claims, categories=("computer_use",), **kw):
    item = {"repo": repo, "url": f"https://github.com/{repo}", "categories": list(categories),
            "claims": claims, "have": "new", "trend": "steady", "new": True,
            "created": "2026-10-01", "opportunity": 52.0,
            "next": "bau scout inspect it, then a sandbox test; you decide"}
    item.update(kw)
    return item


def test_a_task_gets_the_layer_what_bau_has_and_researched_tools(isolated_home):
    b = brief("browse websites and fill in forms")

    assert b["layer"]["id"] == "web" and b["layer"]["status"] == "gap"
    assert b["layer"]["build"] == 1
    assert any(x["path"] == "src/bau/gateway.py" for x in b["already_have"])
    assert b["researched"]
    assert "browser lane" in b["next"].lower()
    assert "find_tools" in b["search"]
    assert "watch has not run" in b["latest_note"]
    assert not (isolated_home / "scout").exists()          # read-only, nothing created


def test_a_capability_bau_has_says_so_instead_of_adding_another_tool():
    b = brief("long term memory for the business")

    assert b["layer"]["id"] == "memory" and b["layer"]["status"] == "have"
    assert {x["path"] for x in b["already_have"]} >= {"src/bau/memory.py", "src/bau/brain.py"}
    assert "already has this" in b["next"]
    assert all(e.get("map_plan") in (None, "skip", "later") for e in b["researched"])


def test_connectors_match_plain_words():
    b = brief("connect to Gmail")

    assert b["layer"]["id"] == "connect"
    assert b["layer"]["status"] == "partial"
    assert "MCP Registry" in b["next"]


def test_an_unknown_task_is_honest_about_it():
    b = brief("telepathy for cats")

    assert b["layer"] is None and b["already_have"] == [] and b["researched"] == []
    assert b["latest"] == []
    assert "No capability layer" in b["next"]


def test_latest_candidates_are_relevant_and_say_what_is_new():
    watch = {"test_next": [
        latest("acme/browser", "browser automation for agents"),
        latest("acme/radio", "music generation", categories=("media",)),
    ], "watch": [latest("acme/scrape", "headless browser scraping", new=False,
                        created="2025-01-01")]}

    b = brief("browser automation", watch=watch)

    assert [i["repo"] for i in b["latest"]] == ["acme/browser", "acme/scrape"]
    assert "90 days" in b["latest_note"]
    assert b["latest"][0]["new"] is True and b["latest"][0]["created"] == "2026-10-01"
    assert b["latest"][1]["new"] is False


def test_latest_falls_back_to_the_watch_when_nothing_matches():
    watch = {"test_next": [latest("acme/radio", "music generation", categories=("media",))]}

    assert [i["repo"] for i in brief("quantum accounting", watch=watch)["latest"]] == [
        "acme/radio"]


def test_jarvis_gets_one_tool_for_the_question(isolated_home):
    a = assistant(isolated_home)

    assert a.tools["capability_brief"].kind == "read"
    assert TOOL_NODE["capability_brief"] == "scout"
    assert "capability_brief" in a.system_prompt()
    out, err = a._run_tool("capability_brief", {"task": "long term memory"})
    assert not err and out["layer"]["id"] == "memory"


def test_the_cli_shows_the_same_answer(isolated_home, monkeypatch, capsys):
    monkeypatch.setenv("BAU_HOME", str(isolated_home))

    assert main(["toolbox", "brief", "browse websites and fill in forms"]) == 0

    out = json.loads(capsys.readouterr().out)
    assert out["layer"]["id"] == "web" and out["next"]


def test_the_owner_docs_explain_the_brief():
    toolbox_doc = (ROOT / "docs" / "TOOLBOX.md").read_text()
    map_doc = (ROOT / "docs" / "CAPABILITY-MAP.md").read_text()
    assert "bau toolbox brief" in toolbox_doc
    assert "bau toolbox brief" in map_doc


def test_the_brief_does_not_change_the_catalogue():
    before = Toolbox().problems()
    brief("browse websites")
    assert Toolbox().problems() == before == []
