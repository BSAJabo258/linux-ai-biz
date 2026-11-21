"""The workstation floor (the owner, 2026-11-21: "all sections and AI models have motion when
delivering or walking to different stations"), and what kept its workers from working: a
strong-brain agent had no model, failed retries were retried again, and an agent's history
outgrew the local model's window until the server stopped answering."""

from pathlib import Path

from bau import agentfolders as AF
from bau import agents
from bau import workstation as W
from bau.jobs import JobStore
from bau.models.providers import ToolSpec
from bau.world import ROOMS

PAGE = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "workstation.html"
        ).read_text(encoding="utf-8")


def job(home, role, status, objective="draft a caption"):
    store = JobStore(home)
    j = store.create("m1", objective, f"folder:{role}", ["s1"])
    j.status = status
    j.verification = "VERIFIED" if status == "COMPLETED" else "UNCHECKED"
    store.checkpoint(j)
    return j


def test_every_department_is_a_station_and_each_ai_stands_where_its_job_is(tmp_path):
    for r in ("producer", "researcher", "finance"):
        AF.approve(r, "human:owner", tmp_path)
    job(tmp_path, "researcher", "RUNNING", "find a new way to earn")
    job(tmp_path, "producer", "WAITING_FOR_APPROVAL")
    job(tmp_path, "finance", "COMPLETED", "the earnings report")
    f = W.view(tmp_path)["floor"]
    assert [r["id"] for r in f["rooms"]] == [r for r, _, _ in ROOMS]
    at = {a["role"]: (a["room"], a["state"]) for a in f["agents"]}
    assert at["jarvis"] == ("hq", "idle")
    looks = {a["role"]: a["look"] for a in f["agents"]}
    assert looks["jarvis"] == "jarvis" and looks["researcher"] == "researcher"
    import json
    sheet = json.loads((Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "world" /
                        "characters.json").read_text())
    assert set(looks.values()) <= set(sheet["characters"])     # every look is on the sheet
    assert at["researcher"] == ("research", "working")
    assert at["producer"] == ("approvals", "waiting for you")
    assert at["finance"] == ("delivery", "done")
    assert at["marketer"] == ("hq", "idle")                  # no job yet: the lounge


def test_a_worker_walks_only_when_its_real_job_changes(tmp_path):
    AF.approve("marketer", "human:owner", tmp_path)
    j = job(tmp_path, "marketer", "RUNNING", "plan the week")
    room = lambda: next(a["room"] for a in W.view(tmp_path)["floor"]["agents"]  # noqa: E731
                        if a["role"] == "marketer")
    assert room() == "market" and room() == "market"          # nothing invented between
    j.status = "COMPLETED"
    j.verification = "VERIFIED"
    JobStore(tmp_path).checkpoint(j)
    assert room() == "delivery"


def test_the_page_walks_between_stations_and_respects_reduced_motion():
    assert "function renderFloor(f, delivered)" in PAGE
    assert 'w.classList.add("walking")' in PAGE and ".walker.placed{transition:left" in PAGE
    # the owner, 2026-11-21: "the motion should be the virtual ai models": her own character
    # from the world's sprite sheet, her walk while she walks, her state's animation after
    assert 'url("/world/characters.png")' in PAGE and 'apiJson("/world/characters.json")' in PAGE
    assert '"walk_back" : "walk_front"' in PAGE
    for anim in ("work", "wait", "done", "idle", "blocked"):
        assert f'["{anim}", ' in PAGE
    assert "@media(prefers-reduced-motion:reduce)" in PAGE
    assert "Math.random" not in PAGE                          # motion only from real state
    assert 'id="drop"' not in PAGE                           # Delivered is a station now


def test_a_failed_retry_is_not_retried_again(tmp_path):
    AF.approve("marketer", "human:owner", tmp_path)
    job(tmp_path, "marketer", "FAILED", "plan the week")
    st = W.refresh(tmp_path)
    assert [t["objective"] for t in st["tasks"]] == ["Retry after failure: plan the week"]
    job(tmp_path, "marketer", "FAILED", "Retry after failure: plan the week")
    st = W.refresh(tmp_path)
    assert not any(t["objective"].startswith("Retry after failure: Retry")
                   for t in st["tasks"])


def test_a_shift_gives_the_agent_the_team_boss_as_jarvis(tmp_path, monkeypatch):
    # The researcher's brain is "strong": with no strong model chosen it uses Jarvis's own,
    # and a shift passed none, so it failed every time ("no approved model to draft with").
    AF.approve("researcher", "human:owner", tmp_path)
    W.assign(tmp_path, "researcher", "research open source video tools", "human:owner",
             kind="research")
    boss = (object(), {"id": "qwen3.5-9b"})
    monkeypatch.setattr(W, "_boss", lambda home: boss)
    seen = {}

    def fake_run(name, objective, home, audit=None, **kw):
        seen.update(kw)
        return agents.RunResult("COMPLETED", "done", 1, [], 0.0, 0)
    monkeypatch.setattr(AF, "run", fake_run)
    W.run_shift(tmp_path, by="human:owner")
    assert seen.get("jarvis") is boss


def spec(deployment):
    return agents.AgentSpec("a", "p", [], {"deployment": deployment, "context": 16384})


def test_a_local_request_is_cut_to_fit_the_servers_window():
    from bau.assistant import CHARS_PER_TOKEN, LOCAL_SERVER_CTX
    big = '<untrusted_data source="search.web">' + "x" * 60000 + "</untrusted_data>"
    msgs = [{"role": "user", "content": "plan the week"},
            {"role": "tool", "tool_call_id": "1", "content": big}]
    tools = [ToolSpec("search__web", "search", {"type": "object"})]
    answer = agents.fit_local(spec("local"), "system", msgs, tools)
    assert answer == agents.LOCAL_ANSWER
    import json
    size = len("system") + len(json.dumps([t.__dict__ for t in tools])) + len(json.dumps(msgs))
    assert size <= (LOCAL_SERVER_CTX - answer - 256) * CHARS_PER_TOKEN
    assert msgs[1]["content"].endswith("</untrusted_data>")   # the block stays closed
    assert agents.CUT in msgs[1]["content"] and msgs[0]["content"] == "plan the week"


def test_a_hosted_model_keeps_its_own_answer_length_and_history():
    msgs = [{"role": "user", "content": "x" * 90000}]
    assert agents.fit_local(spec("cloud"), "s", msgs, []) == 16000
    assert len(msgs[0]["content"]) == 90000


def test_held_work_stops_at_a_card_and_goes_on_at_the_owners_yes(tmp_path, monkeypatch):
    # The owner, 2026-11-21: "other people's AI virtual offices can run most tasks, stopping
    # at confirming". Held work used to sit as waiting_owner with no way to say yes.
    from test_assistant import make
    j = make(tmp_path)
    t = W.assign(tmp_path, "marketer", "post the week's plan on Fanvue", "human:owner")
    assert t["status"] == "waiting_owner"                     # the manager held it
    W.assign(tmp_path, "marketer", "email the plan to a fan", "human:owner")
    W.assign(tmp_path, "marketer", "post pictures of a teen", "human:owner")
    cards = [p for p in j.setup_waiting() if p["tool"] == "work_hold"]
    assert len(cards) == 2                                    # minors: never a card
    assert "post the week's plan" in cards[0]["summary"] and "asks you again" in cards[0]["summary"]
    assert len([p for p in j.setup_waiting() if p["tool"] == "work_hold"]) == 2   # once each
    assert "work_hold" not in {s.name for s in j.specs()}     # never offered to a model
    assert j.confirm(cards[0]["id"], True, "human:owner")["done"]
    j.confirm(cards[1]["id"], False, "human:owner")
    st = {x["objective"]: x["status"] for x in W._load(tmp_path)["tasks"]}
    assert st["post the week's plan on Fanvue"] == "approved"
    assert st["email the plan to a fan"] == "declined"
    ran = []
    monkeypatch.setattr(AF, "run", lambda name, objective, home, audit=None, **kw: ran.append(
        objective) or agents.RunResult("COMPLETED", "done", 1, [], 0.0, 0))
    W.run_shift(tmp_path, by="process:autopilot")
    assert ran == ["post the week's plan on Fanvue"]


def test_only_the_owner_answers_held_work(tmp_path):
    import pytest
    AF.approve("marketer", "human:owner", tmp_path)
    t = W.assign(tmp_path, "marketer", "post the plan", "human:owner")
    with pytest.raises(PermissionError):
        W.owner_decide(tmp_path, t["id"], "process:autopilot", True)
    with pytest.raises(PermissionError):
        W.owner_decide(tmp_path, t["id"], "agent:jarvis", True)


def test_a_held_card_for_work_already_answered_never_errors(tmp_path):
    # The owner's screen, 2026-11-21: "That didn't go through: KeyError: 'no held work
    # wt_c0eba147'". Jarvis's page and the workstation asked for cards at the same moment and
    # each made one for the same task; he approved one, and the other then failed.
    import threading
    from test_assistant import make
    import time
    j = make(tmp_path)
    W.assign(tmp_path, "marketer", "post the week's plan on Fanvue", "human:owner")

    class Slow(dict):                     # a card takes a moment to save: the asks overlap
        def __setitem__(self, k, v):
            time.sleep(0.05)
            super().__setitem__(k, v)
    j.pending = Slow(j.pending)
    out = []
    ts = [threading.Thread(target=lambda: out.append(j.setup_waiting())) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    cards = [p for p in j.pending.values() if p.tool == "work_hold"]
    assert len(cards) == 1                                   # one card, however many ask
    task = cards[0].args["task"]
    W.owner_decide(tmp_path, task, "human:owner", True)      # answered elsewhere meanwhile
    out = j.confirm(cards[0].id, True, "human:owner")
    assert out["done"] and out["result"]["said"].startswith("Already taken care of")
    assert not [p for p in j.setup_waiting() if p["tool"] == "work_hold"]   # taken down


def test_a_stale_held_card_is_taken_down(tmp_path):
    from test_assistant import make
    j = make(tmp_path)
    t = W.assign(tmp_path, "marketer", "post the week's plan on Fanvue", "human:owner")
    assert [p for p in j.setup_waiting() if p["tool"] == "work_hold"]
    W.owner_decide(tmp_path, t["id"], "human:owner", False)  # dropped on the other page
    assert not [p for p in j.setup_waiting() if p["tool"] == "work_hold"]
