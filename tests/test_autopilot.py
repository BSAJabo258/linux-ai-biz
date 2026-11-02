"""Autopilot (the owner's ask, 2026-11-02): Jarvis works on his own, all the time, and grows.
Three lanes - GO (just does it, logged), VOTE (two of three voters: the rules, which can veto
alone; the evidence; the judge), ASK (one question card; the task waits, everything else
keeps going). A compass in the owner's words points every scan, vote and job at the
business. The owner talks to it any time: pause, resume, focus, skip, answer. Fakes only.
Written before the code."""

import json

import pytest

from bau import autopilot as A


def events(home):
    return [json.loads(x)["event"] for x in
            (home / "audit" / "chain.jsonl").read_text().splitlines()]


@pytest.fixture
def home(tmp_path):
    return tmp_path


def test_every_kind_has_a_lane_and_unknown_kinds_ask():
    assert A.lane("scan") == "GO" and A.lane("inspect") == "GO"
    assert A.lane("add_tool") == "VOTE"
    for k in ("post", "spend", "legal", "delete", "keys", "approve", "something_new"):
        assert A.lane(k) == "ASK"


def test_the_compass_points_at_the_business(home):
    c = A.compass(home)
    good = A.score("local video generation for an adult creator's posts", c)
    off = A.score("aimbot cheat for a video game", c)
    assert good > off and off <= 0


def test_go_tasks_run_by_themselves_and_their_follow_ups_continue(home):
    ran = []

    def scan(task):
        ran.append(task["title"])
        return {"ok": True, "evidence": "2 found",
                "follow_ups": [("inspect", "owner/fast-video", {"repo": "owner/fast-video"}),
                               ("inspect", "owner/aimbot", {"repo": "owner/aimbot"})]}

    def inspect(task):
        ran.append(task["title"])
        return {"ok": True, "evidence": "static scan clean"}

    A.add(home, "scan", "video tools")
    A.run(home, {"scan": scan, "inspect": inspect}, max_steps=10)
    assert ran[0] == "video tools" and "owner/fast-video" in ran
    st = A.status(home)
    assert st["done"] >= 2 and st["queued"] == 0
    assert "autopilot.done" in events(home)


def test_follow_ups_are_ordered_by_the_compass(home):
    A.add(home, "inspect", "aimbot cheat for a game")
    A.add(home, "inspect", "local video generation for posts")
    assert A.next_task(A._load(home))["title"] == "local video generation for posts"


def test_vote_two_of_three_and_the_rules_can_veto_alone(home):
    c = A.compass(home)
    good = {"kind": "add_tool", "title": "local video generation", "detail": {
        "tested": True, "security": "clean", "licence": "MIT"}}
    v = A.vote(good, c)
    assert v["passed"] and v["yes"] == 3
    unscanned = {**good, "detail": {**good["detail"], "security": "not scanned"}}
    v = A.vote(unscanned, c)
    assert v["passed"] and v["yes"] == 2                       # rules + judge outvote it
    off = {**unscanned, "title": "spreadsheet macro helper"}
    assert not A.vote(off, c)["passed"]                         # only the rules said yes
    for bad in ({**good, "detail": {**good["detail"], "licence": "non-commercial"}},
                {**good, "detail": {**good["detail"], "tested": False}},
                {**good, "title": "teen photo filter"},
                {**good, "title": "aimbot cheat for a game"}):
        v = A.vote(bad, c)
        assert v["veto"] and not v["passed"], bad


def test_a_vote_task_runs_only_if_the_vote_passes(home):
    did = []
    A.add(home, "add_tool", "local video generation",
          {"tested": True, "security": "clean", "licence": "Apache-2.0"})
    A.add(home, "add_tool", "spreadsheet macro helper", {"tested": True, "licence": "MIT"})
    A.run(home, {"add_tool": lambda t: did.append(t["title"]) or {"ok": True}}, max_steps=5)
    assert did == ["local video generation"]
    assert "autopilot.vetoed" in events(home) or "autopilot.voted_down" in events(home)


def test_ask_tasks_wait_for_the_owner_and_the_rest_keeps_going(home):
    did = []
    A.add(home, "post", "Post Monday's teaser", {"question": "Post Monday's teaser now?"})
    A.add(home, "scan", "voice tools")
    A.run(home, {"scan": lambda t: did.append("scan") or {"ok": True},
                 "post": lambda t: did.append("post") or {"ok": True}}, max_steps=5)
    assert did == ["scan"]
    qs = A.questions(home)
    assert len(qs) == 1 and qs[0]["question"] == "Post Monday's teaser now?"
    A.answer(home, qs[0]["id"], "yes", by="human:owner")
    A.run(home, {"post": lambda t: did.append("post") or {"ok": True}}, max_steps=5)
    assert did == ["scan", "post"] and A.questions(home) == []


def test_a_no_answer_closes_the_task_and_only_a_human_answers(home):
    A.add(home, "spend", "Buy more GPU time", {"question": "Spend $20?"})
    A.run(home, {}, max_steps=3)
    q = A.questions(home)[0]
    with pytest.raises(PermissionError):
        A.answer(home, q["id"], "yes", by="jarvis")
    A.answer(home, q["id"], "no", by="human:owner")
    assert A.status(home)["declined"] == 1


def test_owner_talks_back_pause_focus_skip(home):
    ran = []
    A.add(home, "scan", "voice tools")
    A.add(home, "scan", "video tools")
    A.pause(home, by="human:owner")
    assert A.run(home, {"scan": lambda t: ran.append(t["title"]) or {"ok": True}})["paused"]
    A.resume(home, by="human:owner")
    A.focus(home, "video", by="human:owner")
    A.run(home, {"scan": lambda t: ran.append(t["title"]) or {"ok": True}}, max_steps=1)
    assert ran == ["video tools"]
    t = next(x for x in A._load(home)["tasks"] if x["title"] == "voice tools")
    A.skip(home, t["id"], by="human:owner")
    assert A.status(home)["queued"] == 0


def test_a_failure_is_recorded_and_the_run_continues(home):
    A.add(home, "scan", "broken")
    A.add(home, "scan", "fine")

    def scan(t):
        if t["title"] == "broken":
            raise RuntimeError("GitHub said 500")
        return {"ok": True}
    A.run(home, {"scan": scan}, max_steps=5)
    st = A.status(home)
    assert st["failed"] == 1 and st["done"] == 1


def test_no_handler_is_said_plainly_never_faked(home):
    A.add(home, "inspect", "owner/repo")
    A.run(home, {}, max_steps=2)
    t = A._load(home)["tasks"][0]
    assert t["state"] == "blocked" and "no handler" in t["note"]


def test_the_same_task_is_not_queued_twice_and_runs_are_capped(home):
    A.add(home, "scan", "video tools")
    A.add(home, "scan", "video tools")
    assert A.status(home)["queued"] == 1

    def forever(t):
        return {"ok": True, "follow_ups": [("scan", f"more {t['id']}", {})]}
    A.run(home, {"scan": forever}, max_steps=4)
    assert A.status(home)["done"] == 4                         # stops at the cap


def test_the_digest_says_what_happened(home):
    A.add(home, "scan", "video tools")
    A.add(home, "post", "Post it", {"question": "Post it?"})
    A.run(home, {"scan": lambda t: {"ok": True, "evidence": "3 found"}}, max_steps=5)
    d = A.digest(home)
    assert "video tools" in d and "1 question" in d


# ------------------------------------------------------------------ the real jobs, faked
class FakeScout:
    stopped = None

    def __init__(self):
        self.inspected = []

    def inspect(self, repo):
        self.inspected.append(repo)
        ok = repo == "good/video"
        return {"full_name": repo, "license": {"declared": "MIT" if ok else "GPL-3.0"},
                "security": {"status": "COMMERCIAL_OK" if ok else "COPYLEFT_REVIEW"},
                "inspected": {"commit": "a" * 40, "install_hooks": [], "secrets": 0}}


def test_scan_queues_inspections_and_a_clean_one_goes_on_to_a_sandbox_test(home, monkeypatch):
    from bau import autopilot_jobs as J
    from bau.scout import watch as W
    monkeypatch.setattr(W, "watch", lambda sc, only=None: {
        "categories": {only: {"searches": 2}}, "stopped": None})
    monkeypatch.setattr(W, "shortlist", lambda sc: {"test_next": [
        {"repo": "good/video", "claims": "local video generation", "categories": ["media"]},
        {"repo": "gpl/thing", "claims": "local image tool", "categories": ["media"]}]})
    sc = FakeScout()
    A.add(home, "scan", "scan media tools", {"category": "media"})
    A.run(home, J.handlers(home, sc), max_steps=10)
    assert sorted(sc.inspected) == ["good/video", "gpl/thing"]
    tasks = A._load(home)["tasks"]
    tests = [t for t in tasks if t["kind"] == "sandbox_test"]
    assert [t["detail"]["repo"] for t in tests] == ["good/video"]
    assert tests[0]["state"] == "blocked"          # its job comes next; nothing was faked


def test_seed_keeps_it_growing_once_a_week_per_category(home):
    from bau import autopilot_jobs as J
    n = J.seed(home)
    assert n >= 5 and J.seed(home) == 0           # not twice while queued


# ------------------------------------------------------------------ in Jarvis
def test_jarvis_shows_questions_as_cards_accept_is_yes_not_now_is_no(home):
    from bau.assistant import Assistant
    A.add(home, "post", "Post the teaser", {"question": "Post the teaser now?"})
    A.add(home, "spend", "Buy GPU time", {"question": "Spend $20?"})
    A.run(home, {}, max_steps=5)
    j = Assistant(home)
    cards = [p for p in j.setup_waiting() if p["tool"] == "autopilot_answer"]
    assert len(cards) == 2 and "Post the teaser now?" in cards[0]["summary"]
    assert len([p for p in j.setup_waiting() if p["tool"] == "autopilot_answer"]) == 2
    j.confirm(cards[0]["id"], True, "human:owner")
    j.confirm(cards[1]["id"], False, "human:owner")
    st = A.status(home)
    assert st["queued"] == 1 and st["declined"] == 1
    assert "autopilot_answer" not in j.tools               # never offered to a model


@pytest.mark.parametrize("said,check", [
    ("pause", lambda s: s["paused"]),
    ("Jarvis, focus on video tools", lambda s: s["focus"] == "video tools"),
])
def test_talking_to_jarvis_steers_the_autopilot(home, said, check):
    from bau.assistant import Assistant
    j = Assistant(home)
    r = j.ask(said)
    assert check(A.status(home)) and r.text
    j.ask("resume")
    assert not A.status(home)["paused"]


def test_what_are_you_working_on_reads_the_digest(home):
    from bau.assistant import Assistant
    A.add(home, "scan", "video tools")
    A.run(home, {"scan": lambda t: {"ok": True, "evidence": "3 found"}})
    assert "video tools" in Assistant(home).ask("what are you working on?").text


def test_the_briefing_says_what_the_autopilot_did(home):
    from bau.assistant import Assistant
    A.add(home, "scan", "video tools")
    A.run(home, {"scan": lambda t: {"ok": True}})
    j = Assistant(home)
    assert "Autopilot" in j.plain_briefing(j.facts())


# ------------------------------------------------------------------ the screen
def test_the_screen_view_has_status_jobs_votes_and_the_compass(home):
    A.add(home, "add_tool", "local video generation",
          {"tested": True, "security": "clean", "licence": "MIT"})
    A.run(home, {"add_tool": lambda t: {"ok": True}})
    A.focus(home, "video", by="human:owner")
    v = A.view(home)
    assert v["tasks"][0]["vote"]["passed"] and v["tasks"][0]["lane"] == "VOTE"
    assert any(g["focus"] for g in v["goals"]) and v["focus"] == "video"
    assert v["status"]["done"] == 1


def test_jarvis_page_has_the_mind_and_the_autopilot_panel():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "src/bau/ui"
    page = (root / "jarvis.html").read_text()
    assert "function drawMind" in page and 'id="mindhud"' in page and "/api/autopilot" in page
    assert '"/api/autopilot"' in (root / "jarvis_server.py").read_text()
