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
        self.found = {}

    def inspect(self, repo):
        self.inspected.append(repo)
        ok = repo == "good/video"
        rec = {"full_name": repo, "license": {"declared": "MIT" if ok else "GPL-3.0"},
               "security": {"status": "COMMERCIAL_OK" if ok else "COPYLEFT_REVIEW"},
               "inspected": {"commit": "a" * 40, "install_hooks": [], "secrets": 0}}
        self.found[repo.lower()] = rec
        return rec

    def candidates(self):
        return self.found


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
    assert tests[0]["state"] == "failed"           # it ran; the fake left no quarantine copy
    assert "quarantine" in tests[0]["note"]


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


# ------------------------------------------------------------------ learning and safe adoption
def test_sandbox_test_writes_a_plan_and_never_runs_the_repository(home):
    from bau import autopilot_jobs as J
    q = home / "scout" / "quarantine" / "good__video"
    q.mkdir(parents=True)
    (q / "pyproject.toml").write_text("[project]\nname = 'good-video'\n")

    class PlanScout(FakeScout):
        def candidates(self):
            return {"good/video": {
                "full_name": "good/video", "security": {"status": "COMMERCIAL_OK"},
                "inspected": {"commit": "a" * 40}}}

    A.add(home, "sandbox_test", "good/video", {"repo": "good/video"})
    A.run(home, J.handlers(home, PlanScout()), max_steps=1)
    plan = home / "scout" / "test_plans" / "good__video.json"
    import json
    saved = json.loads(plan.read_text())
    assert saved["approved"] is False and saved["test_command"] == [
        "python3", "-m", "pytest", "-q"]
    assert "--approved --execute" in saved["run_after_signed_approval"]
    assert A._load(home)["tasks"][0]["state"] == "done"


def test_add_tool_only_writes_a_proposal(home):
    from bau import autopilot_jobs as J
    A.add(home, "add_tool", "local video generation",
          {"repo": "good/video", "tested": True, "security": "clean",
           "licence": "MIT", "commit": "a" * 40})
    A.run(home, J.handlers(home), max_steps=1)
    proposal = home / "autopilot" / "proposals" / f"{A._load(home)['tasks'][0]['id']}.json"
    assert proposal.is_file()
    assert "nothing is installed" in proposal.read_text()
    assert A._load(home)["tasks"][0]["state"] == "done"


def test_learn_writes_a_lesson_from_recent_work(home):
    from bau import autopilot_jobs as J
    from bau.assistant import Assistant
    from bau.memory import MemoryLane
    A.add(home, "scan", "video tools")
    A.run(home, {"scan": lambda t: {"ok": True, "evidence": "3 found"}})
    A.add(home, "learn", "review what the autopilot did", {"since_days": 7})
    A.run(home, J.handlers(home), max_steps=1)
    hits = MemoryLane(home).search("autopilot video tools", kinds=["lesson"])
    assert hits and "video tools" in hits[0][1].body
    lessons = Assistant(home).tools["lessons"].fn()
    assert lessons and "video tools" in lessons[0]["lesson"]


def test_seed_queues_a_lesson_after_work(home):
    from bau import autopilot_jobs as J
    A.add(home, "scan", "video tools")
    A.run(home, {"scan": lambda t: {"ok": True}})
    J.seed(home)
    assert any(t["kind"] == "learn" for t in A._load(home)["tasks"])


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


def test_a_task_left_running_by_a_dead_run_is_freed(tmp_path):
    # 2026-11-20 on the desktop: three draft tasks stayed "running" after a reboot (one for 40
    # hours) and the feed, counting them as pictures on the way, made none.
    import datetime as dt
    t1 = A.add(tmp_path, "draft", "old, from before runs were recorded")
    t2 = A.add(tmp_path, "draft", "a run on a previous boot")
    t3 = A.add(tmp_path, "draft", "a run still alive")
    t4 = A.add(tmp_path, "draft", "recent, from before runs were recorded")
    st = A._load(tmp_path)
    now = dt.datetime(2026, 11, 20, 20, 0, tzinfo=dt.UTC)
    for t in st["tasks"]:
        t["state"] = "running"
    by = {t["id"]: t for t in st["tasks"]}
    by[t1["id"]]["started"] = "2026-11-19T02:39:37+00:00"
    by[t2["id"]].update(started="2026-11-20T19:00:00+00:00", run={"pid": 11, "boot": "old"})
    by[t3["id"]].update(started="2026-11-20T19:00:00+00:00", run={"pid": 12, "boot": "b"})
    by[t4["id"]]["started"] = "2026-11-20T19:00:00+00:00"
    A._save(tmp_path, st)
    freed = A.recover(tmp_path, now=now, boot="b", alive=lambda pid: pid == 12)
    assert sorted(freed) == sorted([t1["id"], t2["id"]])
    states = {t["id"]: t["state"] for t in A._load(tmp_path)["tasks"]}
    assert states[t3["id"]] == states[t4["id"]] == "running"
    assert "interrupted" in next(t for t in A._load(tmp_path)["tasks"]
                                 if t["id"] == t1["id"])["note"]
    assert A.recover(tmp_path, now=now, boot="b", alive=lambda pid: pid == 12) == []  # once


def test_a_started_task_records_its_run(tmp_path):
    import os
    A.add(tmp_path, "scan", "x")
    seen = {}

    def handler(t):
        seen.update(A._load(tmp_path)["tasks"][0])
        return {"ok": True}
    A.run(tmp_path, {"scan": handler}, max_steps=1)
    assert seen["run"]["pid"] == os.getpid() and "boot" in seen["run"]
