"""The operations world (2026-11-15): every robot on the floor is an agent, and its room comes
only from its latest real job. No job: Available. Nothing is made up for the screen."""

import datetime as dt
import json

from bau.jobs import JobStore
from bau.world import world

NOW = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.UTC)


def job(home, agent, status, minutes_ago=1, mission="m1", job_id=None):
    store = JobStore(home)
    j = store.create(mission, "find mug suppliers", agent, ["agent_loop"])
    (home / "jobs" / f"{j.job_id}.json").unlink()
    j.job_id = job_id or j.job_id
    j.status = status
    j.updated_at = (NOW - dt.timedelta(minutes=minutes_ago)).isoformat()
    (home / "jobs" / f"{j.job_id}.json").write_text(json.dumps(j.__dict__))
    return j


def rooms(home):
    return {a["name"]: (a["room"], a["state"]) for a in world(home, NOW)["agents"]}


def test_agents_with_no_job_wait_in_available(tmp_path):
    w = world(tmp_path, NOW)
    assert {a["name"] for a in w["agents"]} >= {"jarvis", "researcher", "producer"}
    assert all(a["room"] == "hq" and a["state"] == "idle" and a["job"] is None
               for a in w["agents"])
    assert {a["name"]: a["look"] for a in w["agents"]}["researcher"] == "researcher"
    assert [r["id"] for r in w["rooms"]][0] == "hq" and w["hold"] is None


def test_the_room_follows_the_latest_real_job(tmp_path):
    # The latest by time counts, whatever the file order: the older job sorts first, then last.
    job(tmp_path, "researcher", "COMPLETED", minutes_ago=90, job_id="job_000000000000")
    job(tmp_path, "researcher", "RUNNING", minutes_ago=2, job_id="job_555555555555")
    job(tmp_path, "researcher", "FAILED", minutes_ago=200, job_id="job_ffffffffffff")
    job(tmp_path, "folder:producer", "WAITING_FOR_APPROVAL")
    assert rooms(tmp_path)["researcher"] == ("research", "working")
    assert rooms(tmp_path)["producer"] == ("approvals", "waiting for you")
    r = next(a for a in world(tmp_path, NOW)["agents"] if a["name"] == "researcher")
    assert r["job"]["status"] == "RUNNING" and r["job"]["objective"] == "find mug suppliers"
    assert "quiet_minutes" not in r


def test_stopped_done_old_and_quiet_jobs(tmp_path):
    job(tmp_path, "researcher", "FAILED")
    job(tmp_path, "producer", "COMPLETED", minutes_ago=30)
    job(tmp_path, "helper", "COMPLETED", minutes_ago=60 * 30)        # a day and more ago
    job(tmp_path, "slowpoke", "RUNNING", minutes_ago=45)
    got = rooms(tmp_path)
    assert got["researcher"] == ("repair", "failed")
    assert got["producer"] == ("delivery", "done")
    assert got["helper"] == ("hq", "idle")
    assert got["slowpoke"] == ("forge", "working")                   # not an agent folder
    slow = next(a for a in world(tmp_path, NOW)["agents"] if a["name"] == "slowpoke")
    assert slow["quiet_minutes"] == 45 and slow["approval"] == "unknown"
    assert world(tmp_path, NOW)["counts"]["delivery"] == 1


def test_hold_shows_on_the_floor(tmp_path):
    (tmp_path / "governor").mkdir()
    (tmp_path / "governor" / "hold.json").write_text('{"reason": "test"}')
    assert world(tmp_path, NOW)["hold"]


def test_jarvis_goes_where_his_autopilot_works(tmp_path):
    from bau import autopilot
    t = autopilot.add(tmp_path, "sandbox_test", "try a tool in the sandbox")
    st = autopilot._load(tmp_path)
    st["tasks"][0].update(state="running", started=NOW.isoformat())
    autopilot._save(tmp_path, st)
    j = rooms(tmp_path)["jarvis"]
    assert j == ("testing", "working") and t is not None
    st["tasks"][0].update(state="done", finished=(NOW - dt.timedelta(hours=2)).isoformat())
    autopilot._save(tmp_path, st)
    assert rooms(tmp_path)["jarvis"] == ("delivery", "done")
    st["tasks"][0].update(finished=(NOW - dt.timedelta(days=2)).isoformat())
    autopilot._save(tmp_path, st)
    assert rooms(tmp_path)["jarvis"] == ("hq", "idle")


def test_rooms_say_who_works_there(tmp_path):
    w = world(tmp_path, NOW)
    who = {r["id"]: r["who"] for r in w["rooms"]}
    assert who["finance"] == "no agent works here yet" and "researcher" in who["research"]


# The owner's picture, 2026-11-17: his AI assistants are seven different women. An agent with
# no look of its own gets one of the other four, and always the same one.
def test_every_other_agent_gets_one_of_the_other_looks_and_keeps_it(tmp_path):
    from bau.world import OTHER_LOOKS
    job(tmp_path, "scout", "RUNNING")
    job(tmp_path, "tester", "RUNNING")
    looks = [{a["name"]: a["look"] for a in world(tmp_path, NOW)["agents"]} for _ in range(2)]
    assert looks[0] == looks[1]
    assert looks[0]["scout"] in OTHER_LOOKS and looks[0]["tester"] in OTHER_LOOKS
    assert looks[0]["jarvis"] == "jarvis"


def test_portraits_are_drawn_safely_and_never_left_for_fanvue(tmp_path):
    from bau.media.comfy import NEGATIVE, ComfyError
    from bau.world import PORTRAIT_LOOKS, PORTRAIT_NEGATIVE, draw_portraits
    asked = []

    def drawer(home, prompt, name, negative, **size):
        asked.append((name, prompt, negative, size))
        if name.endswith("analyst"):
            raise ComfyError("the picture could pass for under 20 (0.30)")
        media = home / "artifacts" / "media"
        media.mkdir(parents=True, exist_ok=True)
        (media / f"{name}.png").write_bytes(b"\x89PNG portrait")
        (media / f"{name}.png.provenance.json").write_text("{}")
    done = {d["look"]: d["result"] for d in draw_portraits(tmp_path, drawer=drawer)}
    assert set(done) == set(PORTRAIT_LOOKS) and done["jarvis"] == "drawn"
    assert done["analyst"].startswith("not drawn: the picture could pass")   # the rest go on
    assert not list((tmp_path / "artifacts" / "media").glob("*.png"))       # none for Fanvue
    assert (tmp_path / "world" / "portraits" / "jarvis.png").read_bytes() == b"\x89PNG portrait"
    for _, prompt, negative, _size in asked:
        assert "adult woman" in prompt and negative == PORTRAIT_NEGATIVE
        assert "nudity" in negative and "child" in negative
    assert "child" in NEGATIVE                                  # the sfw lane's own words too
    assert {a["name"]: a["portrait"] for a in world(tmp_path, NOW)["agents"]}["jarvis"] is True
    asked.clear()
    again = {d["look"]: d["result"] for d in draw_portraits(tmp_path, drawer=drawer)}
    assert again["jarvis"] == "already drawn" and [a[0] for a in asked] == [
        "world-portrait-analyst"]
    assert draw_portraits(tmp_path, ["../etc"], drawer=drawer)[0]["result"] == "unknown look"
    rows = (tmp_path / "audit" / "chain.jsonl").read_text()
    assert rows.count('"world.portrait"') == len(PORTRAIT_LOOKS) - 1


def test_the_page_gets_only_the_fixed_portraits(tmp_path):
    import http.client
    import threading

    from test_assistant import make

    from bau.assistant import Voice
    from bau.ui.jarvis_server import serve
    (tmp_path / "world" / "portraits").mkdir(parents=True)
    (tmp_path / "world" / "portraits" / "jarvis.png").write_bytes(b"\x89PNG jarvis")
    (tmp_path / "secret.png").write_bytes(b"\x89PNG secret")
    srv, key = serve(make(tmp_path), Voice(tmp_path), 0, key="k" * 24)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        port = srv.server_address[1]

        def get(path):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
            r = c.getresponse()
            return r.status, r.read()
        assert get("/world/portrait/jarvis.png") == (200, b"\x89PNG jarvis")
        assert get("/world/portrait/producer.png")[0] == 404          # not drawn yet
        assert get("/world/portrait/../../secret.png")[0] == 404
        assert get("/world/portrait/%2e%2e%2fsecret.png")[0] == 404
    finally:
        srv.shutdown()
