"""The open-source watch: Repo Scout running on its own, every week, across eight technology
categories the owner cares about. It keeps a history of each project (stars, last push)
so rising projects stand out, tells apart what BAU already runs, what is already
researched in the Toolbox and what is new, and ends in a short ranked list - test next,
watch, already have, ignore - with the reasons. It still never installs or runs anything,
never calls anything "adopt", and says cost is unknown until a benchmark has measured it.
Written before the code."""

import datetime as dt
import json
from pathlib import Path

import pytest
import yaml

from bau import scout as S
from bau.audit import AuditLog
from bau.scout import watch as W
from bau.scout.github import RateLimited, normalise

ROOT = Path(__file__).resolve().parents[1]
DAY1, DAY2 = dt.date(2026, 10, 1), dt.date(2026, 10, 15)


def repo(name, desc, stars=100, spdx="MIT", pushed="2026-09-20", topics=("agents",)):
    return {"full_name": name, "html_url": f"https://github.com/{name}", "description": desc,
            "topics": list(topics), "language": "Python", "fork": False, "archived": False,
            "pushed_at": pushed, "stargazers_count": stars, "size": 900,
            "license": {"spdx_id": spdx}}


class FakeGitHub:
    """search() answers by keyword; repo() answers the named seeds; counts every call."""
    name = "github"

    def __init__(self, by_word, repos, limit_after=None):
        self.by_word, self.repos, self.limit_after = by_word, repos, limit_after
        self.calls = []

    def _count(self, what):
        self.calls.append(what)
        if self.limit_after is not None and len(self.calls) > self.limit_after:
            raise RateLimited("GitHub asked to wait", until=4102444800.0)

    def search(self, q, per_page=10):
        self._count(("search", q))
        out = []
        for word, items in self.by_word.items():
            if word in q:
                out += [normalise(i) for i in items]
        return out

    def repo(self, name):
        self._count(("repo", name))
        return self.repos[name]

    def upstream(self, name):
        return None

    def readme(self, name):
        self._count(("readme", name))
        return "pip install it"


def catalog():
    return {"checked": "2026-10-13",
            "integrated": ["ggml-org/llama.cpp"],
            "categories": {
                "agents": {"title": "AI agents and orchestration", "why": "digital workforce",
                           "priority": 3, "queries": ["multi agent orchestration"],
                           "seeds": ["NousResearch/hermes-agent"]},
                "context": {"title": "Token and context reduction", "why": "lower costs",
                            "priority": 3, "queries": ["prompt compression"],
                            "seeds": ["ggml-org/llama.cpp"]}}}


def world(stars=100):
    agents = [repo("acme/swarm", "multi agent orchestration framework", stars),
              repo("bad/nc-agents", "multi agent orchestration", 5000, spdx="CC-BY-NC-4.0")]
    ctx = [repo("tiny/squeeze", "prompt compression to cut tokens", stars,
                topics=("prompt-compression",))]
    repos = {"NousResearch/hermes-agent": repo("NousResearch/hermes-agent",
                                               "persistent agent", 900),
             "ggml-org/llama.cpp": repo("ggml-org/llama.cpp", "LLM inference in C", 90000)}
    return {"multi": agents, "compression": ctx}, repos


def scout(tmp_path, src):
    return S.Scout(tmp_path, src, AuditLog(tmp_path / "audit.jsonl", key=b""))


def toolbox_repos():
    return {"NousResearch/hermes-agent": "Hermes Agent"}


# ------------------------------------------------------------------ the catalog

def test_the_shipped_catalog_tracks_the_owners_eight_categories():
    cat = W.load()
    assert set(cat["categories"]) == {"agents", "compression", "context", "inference",
                                      "memory", "computer_use", "self_improvement",
                                      "open_models"}
    for key, c in cat["categories"].items():
        assert c["title"] and c["why"] and c["queries"], key
        assert c["priority"] in (1, 2, 3), key
        for s in c.get("seeds", []):
            assert S.NAME.match(s), s
    assert "ggml-org/llama.cpp" in cat["integrated"]       # what BAU already runs
    assert cat["checked"]
    # The less-restricted models category is judged like any other: licence and limits.
    assert "licen" in cat["categories"]["open_models"]["why"].lower()


# ------------------------------------------------------------------ one weekly run

def test_a_watch_run_searches_each_category_tags_and_snapshots_what_it_finds(tmp_path):
    words, repos = world()
    src = FakeGitHub(words, repos)
    sc = scout(tmp_path, src)
    run = W.watch(sc, catalog(), today=DAY1)
    store = sc.candidates()
    assert store["acme/swarm"]["categories"] == ["agents"]
    assert store["tiny/squeeze"]["categories"] == ["context"]
    assert store["nousresearch/hermes-agent"]["categories"] == ["agents"]   # seeds too
    assert store["acme/swarm"]["history"] == [{"on": "2026-10-01", "stars": 100,
                                               "pushed_at": "2026-09-20"}]
    assert run["categories"]["agents"]["searches"] == 1
    assert not any(c[0] not in ("search", "repo", "readme") for c in src.calls)  # read-only
    assert any(r["event"] == "scout.watch" for r in sc.audit.records())


def test_a_second_run_shows_what_is_rising(tmp_path):
    words, repos = world(stars=100)
    sc = scout(tmp_path, FakeGitHub(words, repos))
    W.watch(sc, catalog(), today=DAY1)
    words, repos = world(stars=400)                       # the same projects, two weeks on
    sc.source = FakeGitHub(words, repos)
    W.watch(sc, catalog(), today=DAY2)
    c = sc.candidates()["acme/swarm"]
    assert [h["stars"] for h in c["history"]] == [100, 400]
    assert W.trend(c, DAY2) == {"trend": "rising", "gained": 300, "days": 14}


def test_when_github_says_wait_the_run_stops_and_says_what_was_not_sent(tmp_path):
    words, repos = world()
    sc = scout(tmp_path, FakeGitHub(words, repos, limit_after=1))
    run = W.watch(sc, catalog(), today=DAY1)
    assert run["stopped"] and "wait" in run["stopped"]
    assert run["not_sent"]                                   # recorded, never "nothing found"


def test_a_run_where_github_refused_everything_says_so(tmp_path):
    class Refusing(FakeGitHub):
        def search(self, q, per_page=10):
            raise S.SourceError("GitHub HTTP 403: refused")

        def repo(self, name):
            raise S.SourceError("GitHub HTTP 403: refused")
    words, repos = world()
    run = W.watch(scout(tmp_path, Refusing(words, repos)), catalog(), today=DAY1)
    assert run["reached_github"] is False                  # never read as "nothing new"
    assert run["categories"]["agents"]["errors"]
    words, repos = world()
    ok = W.watch(scout(tmp_path / "ok", FakeGitHub(words, repos)), catalog(), today=DAY1)
    assert ok["reached_github"] is True


# ------------------------------------------------------------------ the shortlist

def test_the_shortlist_separates_new_researched_running_and_ignored(tmp_path):
    words, repos = world()
    sc = scout(tmp_path, FakeGitHub(words, repos))
    W.watch(sc, catalog(), today=DAY1)
    sl = W.shortlist(sc, catalog(), toolbox=toolbox_repos(), today=DAY1)
    by = {i["repo"]: i for group in sl.values() for i in group}
    assert by["ggml-org/llama.cpp"]["have"] == "running in BAU"
    assert by["NousResearch/hermes-agent"]["have"] == "researched in the Toolbox (Hermes Agent)"
    assert by["acme/swarm"]["have"] == "new"
    assert "bad/nc-agents" in [i["repo"] for i in sl["ignore"]]          # licence blocks it
    assert any("licence" in r for r in by["bad/nc-agents"]["why"])
    assert set(sl) == {"test_next", "watch", "already_have", "ignore"}
    for item in by.values():
        assert item["cost"] == "unknown until benchmarked"
        assert item["next"] != "adopt"                      # never decided by the machine


def test_rising_new_projects_rank_first_and_the_owners_priorities_count(tmp_path):
    words, repos = world(stars=100)
    sc = scout(tmp_path, FakeGitHub(words, repos))
    W.watch(sc, catalog(), today=DAY1)
    words, repos = world(stars=900)
    sc.source = FakeGitHub(words, repos)
    W.watch(sc, catalog(), today=DAY2)
    sl = W.shortlist(sc, catalog(), toolbox=toolbox_repos(), today=DAY2)
    ranked = [i for g in ("test_next", "watch") for i in sl[g]]
    assert ranked and ranked[0]["trend"] == "rising"
    assert all("opportunity" in i for i in ranked)
    low = {**catalog(), "categories": {**catalog()["categories"],
                                       "context": {**catalog()["categories"]["context"],
                                                   "priority": 1}}}
    a = {i["repo"]: i["opportunity"] for g in W.shortlist(sc, catalog(), {}, DAY2).values()
         for i in g}
    b = {i["repo"]: i["opportunity"] for g in W.shortlist(sc, low, {}, DAY2).values()
         for i in g}
    assert b["tiny/squeeze"] < a["tiny/squeeze"]


def test_the_report_is_plain_words(tmp_path):
    words, repos = world()
    sc = scout(tmp_path, FakeGitHub(words, repos))
    W.watch(sc, catalog(), today=DAY1)
    text = W.report(W.shortlist(sc, catalog(), toolbox_repos(), DAY1))
    for heading in ("Test next", "Watch", "Already have", "Ignored"):
        assert heading in text
    assert "nothing is installed" in text.lower()


# ------------------------------------------------------------------ Jarvis, the timer, the CLI

def test_jarvis_answers_whats_new_from_the_watch(tmp_path):
    from bau.assistant import TOOL_NODE, Assistant
    from bau.models.providers import ScriptedProvider
    words, repos = world()
    W.watch(scout(tmp_path, FakeGitHub(words, repos)), catalog(), today=DAY1)
    a = Assistant(tmp_path, ScriptedProvider(["ok"]), {"id": "jv", "model_id": "jv"},
                  "human:owner", AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""))
    t = a.tools["open_source_watch"]
    assert t.kind == "read" and TOOL_NODE["open_source_watch"] == "scout"


def test_it_runs_weekly_as_the_bau_account():
    sysd = ROOT / "installer" / "payload" / "systemd"
    timer = (sysd / "bau-scout-watch.timer").read_text()
    svc = (sysd / "bau-scout-watch.service").read_text()
    assert "OnCalendar=weekly" in timer or "Mon" in timer
    assert "User=bau" in svc and "bau scout watch" in svc
    assert "EnvironmentFile=-/etc/bau/models.env" in svc         # GITHUB_TOKEN if set
    assert "bau-scout-watch.timer" in (ROOT / "installer" / "payload" / "install.sh").read_text()


def test_cli_shortlist(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    words, repos = world()
    W.watch(scout(tmp_path, FakeGitHub(words, repos)), catalog(), today=DAY1)
    assert main(["scout", "shortlist", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"test_next", "watch", "already_have", "ignore"}


def test_docs_explain_it():
    doc = (ROOT / "docs" / "engineering" / "repo-intelligence.md").read_text()
    assert "bau scout watch" in doc and "bau scout shortlist" in doc
    cat = yaml.safe_load((ROOT / "src" / "bau" / "data" / "scout_watch.yaml").read_text())
    assert len(cat["categories"]) == 8


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("tests never use the network")
    monkeypatch.setattr("urllib.request.urlopen", refuse)
