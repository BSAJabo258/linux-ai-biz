"""The toolbox: researched open-source tools Jarvis looks up before guessing, each with its
sources and check date; Scout turns a claim into an inspected fact. Written before the
code it tests."""

import json

import pytest
import yaml
from test_scout import item

from bau.assistant import Assistant
from bau.audit import AuditLog
from bau.models.providers import ScriptedProvider
from bau.toolbox import CATEGORIES, Toolbox

ENTRY = {"name": "Instructor", "repo": "567-labs/instructor",
         "url": "https://github.com/567-labs/instructor", "category": "structured-output",
         "problem": "Model answers come back as loose text instead of checked data.",
         "how_used": "Wrap the model call so the reply is validated against a schema.",
         "licence": "MIT", "stars": "~12k (2026-10-10)", "last_activity": "2026-10",
         "sources": ["https://github.com/567-labs/instructor"], "caveats": ""}
MEMORY = {**ENTRY, "name": "mem0", "repo": "mem0ai/mem0", "url": "https://github.com/mem0ai/mem0",
          "category": "memory", "problem": "Assistants forget what users told them before.",
          "how_used": "Store and recall long-term facts across conversations.",
          "licence": "Apache-2.0", "sources": ["https://github.com/mem0ai/mem0"]}
GROUND = {**ENTRY, "name": "Ragas", "repo": "explodinggradients/ragas",
          "url": "https://github.com/explodinggradients/ragas", "category": "evals",
          "problem": "Nobody measures whether answers are grounded or hallucinated.",
          "how_used": "Score answers for faithfulness against the retrieved sources.",
          "licence": "Apache-2.0", "sources": ["https://github.com/explodinggradients/ragas"]}


def box(tmp_path, entries=(ENTRY, MEMORY, GROUND)):
    p = tmp_path / "toolbox.yaml"
    p.write_text(yaml.safe_dump({"checked": "2026-10-10", "entries": list(entries)}))
    return Toolbox(tmp_path, data=p)


# ------------------------------------------------------------------ the shipped catalogue

def test_shipped_catalogue_is_complete_sourced_and_dated():
    tb = Toolbox()
    assert tb.problems() == []
    assert tb.checked == "2026-10-10" and len(tb.entries) >= 40
    cats = {e["category"] for e in tb.entries}
    for need in ("connect", "grounding", "evals", "agents", "memory", "local-models",
                 "speech-to-text", "text-to-speech", "video-editing"):
        assert need in cats, need
    assert any(e["name"].lower().startswith("hermes") for e in tb.entries)
    assert len({e["repo"].lower() for e in tb.entries}) == len(tb.entries)   # no repeats


def test_bad_entries_are_refused(tmp_path):
    bad = [{**ENTRY, "sources": []}, {**ENTRY, "repo": "not a repo"},
           {**ENTRY, "category": "magic"}, {**ENTRY, "problem": "Guaranteed compliant."},
           {k: v for k, v in ENTRY.items() if k != "licence"},
           {**ENTRY, "sources": ["http://insecure.example"]}]
    bad = [{**b, "repo": f"owner/tool{i}"} if b.get("repo") == ENTRY["repo"] else b
           for i, b in enumerate(bad)]                    # one fault per entry
    probs = box(tmp_path, bad).problems()
    assert len(probs) == len(bad), probs
    assert set(CATEGORIES) >= {"grounding", "memory", "connect"}


# ------------------------------------------------------------------ asking the right question

def test_plain_questions_find_the_right_tools(tmp_path):
    tb = box(tmp_path)
    assert tb.ask("how do I stop the model making things up?")[0]["name"] == "Ragas"
    assert tb.ask("Jarvis keeps forgetting what I told him")[0]["name"] == "mem0"
    assert tb.ask("get clean structured data back from the model")[0]["name"] == "Instructor"
    assert tb.ask("xyzzy plugh") == []
    assert [e["name"] for e in tb.ask("", category="memory")] == ["mem0"]


def test_answers_say_what_is_claimed_and_what_scout_checked(tmp_path):
    tb = box(tmp_path)
    hit = tb.ask("remember things")[0]
    assert hit["evidence"] == "claimed: research checked 2026-10-10, not inspected yet"
    assert hit["next"] == "bau toolbox check mem0"
    (tmp_path / "scout").mkdir()
    (tmp_path / "scout" / "candidates.json").write_text(json.dumps({"mem0ai/mem0": {
        "full_name": "mem0ai/mem0", "decision": "eligible",
        "inspected": {"verdict": "ELIGIBLE_FOR_SANDBOX", "at": "2026-10-11T09:00:00+00:00"}}}))
    hit = tb.ask("remember things")[0]
    assert hit["evidence"].startswith("inspected 2026-10-11: ELIGIBLE_FOR_SANDBOX")
    assert hit["scout_decision"] == "eligible"


# ------------------------------------------------------------------ going to get it

class RepoGitHub:
    name = "github"

    def __init__(self):
        self.asked = []

    def repo(self, name):
        self.asked.append(name)
        it = item(name, desc="long-term memory for AI agents", spdx="Apache-2.0")
        return {"full_name": it["full_name"], "html_url": it["url"],
                "description": it["description"], "topics": ["memory"],
                "language": "Python", "fork": False, "archived": False,
                "pushed_at": "2026-10-01", "stargazers_count": 40000, "size": 900,
                "homepage": None, "license": {"spdx_id": "Apache-2.0"}}


def test_check_fetches_and_inspects_one_known_tool_safely(tmp_path):
    def cloner(url, dest):
        dest.mkdir(parents=True)
        (dest / "LICENSE").write_text("Apache License\nVersion 2.0, January 2004")
        return "abc123"
    tb = box(tmp_path)
    gh = RepoGitHub()
    audit = AuditLog(tmp_path / "audit" / "chain.jsonl", key=b"")
    c = tb.check("mem0", source=gh, cloner=cloner, audit=audit, actor="human:owner")
    assert gh.asked == ["mem0ai/mem0"]
    assert c["inspected"]["commit"] == "abc123" and c["origin"] == "toolbox"
    assert tb.ask("remember things")[0]["evidence"].startswith("inspected")
    events = [r["event"] for r in audit.records()]
    assert "scout.added" in events and "scout.inspected" in events
    with pytest.raises(KeyError):
        tb.check("no-such-tool", source=gh, cloner=cloner, audit=audit)


# ------------------------------------------------------------------ Jarvis, terminal, screen

def test_jarvis_looks_in_the_toolbox_before_guessing(tmp_path, monkeypatch):
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    a = Assistant(tmp_path, ScriptedProvider(["ok"]), {"id": "m"}, "human:owner",
                  AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""))
    assert a.tools["toolbox"].kind == "read"
    assert "toolbox" in a.system_prompt()
    out = a._run_tool("toolbox", {"question": "stop hallucinations"})[0]
    assert out["answers"] and all("evidence" in h and "next" in h for h in out["answers"])
    assert "find_tools" in out["if_nothing_fits"]


def test_cli_and_screen(tmp_path, monkeypatch, capsys):
    import threading
    import urllib.request

    from bau.assistant import Voice
    from bau.cli import main
    from bau.ui.jarvis_server import serve
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    assert main(["toolbox", "ask", "long-term memory for my assistant"]) == 0
    hits = json.loads(capsys.readouterr().out)
    assert hits and all(h["sources"] for h in hits)
    assert main(["toolbox", "list", "--category", "memory"]) == 0
    assert all(h["category"] == "memory" for h in json.loads(capsys.readouterr().out))
    a = Assistant(tmp_path, None, {}, "human:owner",
                  AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""))
    srv, _ = serve(a, Voice(tmp_path), 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/toolbox?q=memory"
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-Jarvis-Key": "k123"})) as r:
            assert json.loads(r.read())["answers"]
    finally:
        srv.shutdown()
    from importlib import resources
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert "/api/toolbox" in page
