"""The operations world (2026-11-15): every robot on the floor is an agent, and its room comes
only from its latest real job. No job: Available. Nothing is made up for the screen."""

import datetime as dt
import json
from pathlib import Path

from bau.jobs import JobStore
from bau.world import LIGHT, world

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
    assert "finance agent" in who["finance"] and "researcher" in who["research"]


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


def test_portraits_stop_at_once_when_the_picture_setup_is_not_running(tmp_path, monkeypatch,
                                                                      capsys):
    """On the owner's desktop `bau world portraits` printed nothing at all."""
    from bau import cli
    from bau import world as w
    drawn = []
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    monkeypatch.setattr(w, "pictures_running", lambda: False)
    monkeypatch.setattr("bau.media.comfy.draw", lambda *a, **k: drawn.append(a))
    assert cli.main(["world", "portraits"]) == 3
    err = capsys.readouterr().err
    assert "not running on this computer" in err and "bau-pictures.service" in err
    assert "Traceback" not in err and drawn == []
    assert not (tmp_path / "world" / "portraits").exists()


def test_each_portrait_is_said_as_it_goes_and_a_lost_connection_does_not_stop_the_rest(
        tmp_path):
    from bau.world import PORTRAIT_LOOKS, draw_portraits
    said = []

    def drawer(home, prompt, name, negative, **size):
        if name.endswith("producer"):
            raise ConnectionRefusedError(111, "Connection refused")    # ComfyUI went away
        media = home / "artifacts" / "media"
        media.mkdir(parents=True, exist_ok=True)
        (media / f"{name}.png").write_bytes(b"\x89PNG portrait")
    done = draw_portraits(tmp_path, drawer=drawer, ready=lambda: True, say=said.append)
    results = {d["look"]: d["result"] for d in done}
    assert results["producer"].startswith("not drawn: ") and "refused" in results["producer"]
    assert all(r == "drawn" for k, r in results.items() if k != "producer")
    n = len(PORTRAIT_LOOKS)
    assert said[0] == f"painting {PORTRAIT_LOOKS[0]} (1/{n})..."
    assert said[1] == f"  {PORTRAIT_LOOKS[0]}: drawn"
    assert len(said) == 2 * n and said[-2] == f"painting {PORTRAIT_LOOKS[-1]} ({n}/{n})..."
    assert f"  producer: {results['producer']}" in said


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


# The owner, 2026-11-18: "I don't think Jarvis has a menu to see what the virtual agents are
# doing". The world carries his picture's panels from records only: current tasks and status.
def test_the_world_says_what_each_agent_is_doing_and_the_system_status(tmp_path, monkeypatch):
    from bau import station
    monkeypatch.setattr(station, "MARK", tmp_path / "hq")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    job(tmp_path, "researcher", "RUNNING")
    job(tmp_path, "producer", "WAITING_FOR_APPROVAL")
    job(tmp_path, "scout", "FAILED")
    w = world(tmp_path, NOW)
    assert {(t["agent"], t["state"]) for t in w["tasks"]} == {
        ("researcher", "working"), ("producer", "waiting for you")}       # not the stopped one
    assert all(t["task"] == "find mug suppliers" for t in w["tasks"])
    money = w["system"].pop("money")
    assert w["system"].pop("problems") == [
        f"money machine: {money['ready']} of 9 links ready; next: creator profile (bau money)"]
    assert w["system"] == {"headquarters": False, "station": False, "stations_paired": 0,
                           "autopilot": {"paused": False, "running": 0, "queued": 0,
                                         "waiting_for_you": 0}}
    assert money["of"] == 9 and money["ready"] < 9 and money["next"] == "creator profile"
    (tmp_path / "hq").write_text("admin=owner\n")
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "authorized_keys").write_text(
        station.key_line("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIF5fqTjZQ8Kb2nqU7c9p0F5mD8qK0E3"
                         "x4J9w1nZp3m2t laptop") + "\n")
    s = world(tmp_path, NOW)["system"]
    assert s["headquarters"] is True and s["stations_paired"] == 1


def test_the_world_is_easy_to_find_and_shows_its_panels():
    page = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "jarvis.html").read_text()
    assert 'id="wake-world"' in page and "Open the operations world" in page   # on the wake screen
    assert ">OPERATIONS WORLD</button>" in page and 'class="chip world"' in page
    for panel in ('id="w-list"', 'id="w-tasks"', 'id="w-sys"'):
        assert panel in page
    assert "No agent is working right now" in page                     # never an empty floor alone


def test_the_photo_avatar_is_its_own_look_drawn_only_when_asked(tmp_path):
    from bau import world as Wd
    drawn = []

    def drawer(home, prompt, name, negative, width, height):
        drawn.append((prompt, negative))
        media = home / "artifacts" / "media"
        media.mkdir(parents=True, exist_ok=True)
        (media / f"{name}.png").write_bytes(b"png")

    Wd.draw_portraits(tmp_path, drawer=drawer, say=lambda line: None)
    assert Wd.AVATAR_PROMPT not in [d[0] for d in drawn] and len(drawn) == len(Wd.PORTRAIT_LOOKS)
    assert Wd.portrait_file(tmp_path, "avatar") is None
    out = Wd.draw_portraits(tmp_path, ["avatar"], drawer=drawer, say=lambda line: None)
    assert out == [{"look": "avatar", "result": "drawn"}]
    prompt, negative = drawn[-1]
    assert "photorealistic" in prompt and "original fictional adult" in prompt
    assert "celebrity" in negative and "minor" in negative
    assert Wd.portrait_file(tmp_path, "avatar").read_bytes() == b"png"


def test_the_page_shows_the_photo_face_where_the_orb_was():
    from importlib import resources
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert 'id="avphoto"' in page and '"/world/portrait/" + AV_PORTRAITS[0]' in page
    assert '"PHOTO"' in page and '"GLASS CORE"' in page


# The owner's neon headquarters picture, 2026-11-20: "the picture is the style, not the data".
# Its agents panel lists Architect, Developer, Coordinator... as Online; BAU shows only records.
def test_the_hq_agents_panel_shows_roles_bau_does_not_have_as_not_set_up(tmp_path):
    job(tmp_path, "researcher", "RUNNING")
    job(tmp_path, "scout", "FAILED")
    rows = {r["name"]: r for r in world(tmp_path, NOW)["roster"]}
    for role in ("architect", "developer", "tester", "coordinator"):
        assert rows[role] == {"name": role, "state": "not set up yet", "light": "off"}
    assert rows["researcher"]["state"] == "working" and rows["researcher"]["light"] == "working"
    assert rows["producer"]["state"] in ("free", "not approved")      # a real folder, no job
    assert rows["scout"] == {"name": "scout", "state": "failed", "light": "stopped"}
    assert rows["autopilot"] == {"name": "autopilot", "state": "nothing running, 0 queued",
                                 "light": "free"}
    assert rows["automaton"] == {"name": "automaton", "state": "not started", "light": "off"}
    assert "jarvis" not in rows
    assert not any("online" in r["state"].lower() for r in rows.values())


def test_the_hq_roster_shows_the_autopilot_and_automaton_as_their_records_say(tmp_path):
    from bau import automaton, autopilot
    autopilot.add(tmp_path, "research", "read about mugs")
    st = autopilot._load(tmp_path)
    st["paused"] = True
    autopilot._save(tmp_path, st)
    automaton._save(tmp_path, {"started_at": NOW.isoformat(), "on": False, "dead": "no income"})
    rows = {r["name"]: r for r in world(tmp_path, NOW)["roster"]}
    assert rows["autopilot"]["state"] == "paused by you"
    assert rows["automaton"] == {"name": "automaton", "state": "dead (only you can revive it)",
                                 "light": "stopped"}


def test_all_systems_healthy_only_when_nothing_is_wrong(tmp_path, monkeypatch):
    from bau import autopilot, money
    monkeypatch.setattr(money, "summary", lambda home: {"ready": 9, "of": 9, "next": None})
    assert world(tmp_path, NOW)["system"]["problems"] == []
    (tmp_path / "governor").mkdir()
    (tmp_path / "governor" / "hold.json").write_text('{"reason": "test"}')
    st = autopilot._load(tmp_path)
    st["paused"] = True
    autopilot._save(tmp_path, st)
    got = world(tmp_path, NOW)["system"]["problems"]
    assert got[0].startswith("HOLD") and "the autopilot is paused (bau autopilot resume)" in got
    monkeypatch.setattr(money, "summary", lambda home: 1 / 0)
    assert "the money machine could not be read (bau money)" in world(tmp_path, NOW)["system"][
        "problems"]


def test_what_we_doing_now_is_jarvis_real_task_or_nothing(tmp_path):
    from bau import autopilot
    assert world(tmp_path, NOW)["now"] is None
    autopilot.add(tmp_path, "research", "read about mug suppliers")
    st = autopilot._load(tmp_path)
    st["tasks"][0].update(state="running", started=NOW.isoformat())
    autopilot._save(tmp_path, st)
    assert world(tmp_path, NOW)["now"] == {"state": "working", "task": st["tasks"][0]["title"]}


def test_her_pose_changes_only_with_her_job_and_shows_only_a_drawn_picture(tmp_path):
    from bau.world import portrait_file
    w = {a["name"]: a for a in world(tmp_path, NOW)["agents"]}
    assert (w["researcher"]["pose"], w["researcher"]["neon"]) == ("idle", False)
    job(tmp_path, "researcher", "RUNNING")
    d = tmp_path / "world" / "portraits"
    d.mkdir(parents=True)
    (d / "neon-researcher-working.png").write_bytes(b"\x89PNG")
    w = {a["name"]: a for a in world(tmp_path, NOW)["agents"]}
    assert (w["researcher"]["pose"], w["researcher"]["neon"]) == ("working", True)
    job(tmp_path, "researcher", "WAITING_FOR_APPROVAL", minutes_ago=0)
    assert {a["name"]: a for a in world(tmp_path, NOW)["agents"]}["researcher"]["pose"] == "waiting"
    (d / "neon-researcher-dancing.png").write_bytes(b"\x89PNG")
    assert portrait_file(tmp_path, "neon-researcher-dancing") is None    # only the fixed poses


def test_neon_portraits_go_through_the_same_checks_and_never_stay_for_fanvue(tmp_path):
    from bau.world import NEON_POSES, PORTRAIT_NEGATIVE, draw_portraits
    asked = []

    def drawer(home, prompt, name, negative, **size):
        asked.append((name, prompt, negative))
        media = home / "artifacts" / "media"
        media.mkdir(parents=True, exist_ok=True)
        (media / f"{name}.png").write_bytes(b"\x89PNG neon")
    done = draw_portraits(tmp_path, ["producer"], drawer=drawer, style="neon")
    assert [d["look"] for d in done] == [f"neon-producer-{p}" for p in NEON_POSES]
    assert all(d["result"] == "drawn" for d in done)
    assert not list((tmp_path / "artifacts" / "media").glob("*.png"))       # none for Fanvue
    assert (tmp_path / "world" / "portraits" / "neon-producer-done.png").exists()
    for _, prompt, negative in asked:
        assert "adult woman" in prompt and "red hair" in prompt and negative == PORTRAIT_NEGATIVE
    one = draw_portraits(tmp_path, ["jarvis"], drawer=drawer, style="neon", poses=["waiting"])
    assert [d["look"] for d in one] == ["neon-jarvis-waiting"]


def test_the_page_lays_out_the_neon_headquarters_from_records():
    page = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "jarvis.html").read_text()
    for part in ('id="hq-agents"', 'id="hq-status"', 'id="hq-tasks"', 'id="hq-rooms"',
                 'id="hq-now"', 'id="hq-crew"', "BAUBSA JARVIS", "What We Doing Now?",
                 "Building the Ultimate<br>Virtual Operations World"):
        assert part in page
    assert "OPS.roster" in page and "S.problems" in page and "OPS.now" in page
    assert "All systems healthy" in page and "nothing right now" in page
    assert "Online" not in page.split('id="hqview"')[1].split("</div></div></div>")[0]
    assert "openRoom(" in page                               # a tile opens its room on the floor
    days = page.split("const HQ_DAYS = [")[1].split("];")[0]
    assert days.count('"') == 14 and "Tuesday" in days.split(",")[2]   # today's line, Sunday first
    assert "new Date().getDay()" in page


def test_the_hq_roster_shows_a_recorded_job_not_yet_started_as_assigned(tmp_path):
    job(tmp_path, "researcher", "PENDING")      # main's #207: recorded, not started = assigned
    w = world(tmp_path, NOW)
    state = {a["name"]: a["state"] for a in w["agents"]}["researcher"]
    rows = {r["name"]: r for r in w["roster"]}
    assert rows["researcher"] == {"name": "researcher", "state": state, "light": LIGHT[state]}


def desk_task(home, role, status, objective="draft three captions", **extra):
    from bau import workstation as W
    st = W._load(home)
    st["tasks"].append({"id": f"wt_{role}_{status}", "role": role, "objective": objective,
                        "kind": "draft", "source": "test", "source_job": "", "status": status,
                        "created": NOW.isoformat(), "finished": "", "result": "",
                        "manager": {}, **extra})
    W._save(home, st)


def test_the_workstation_moves_her_when_her_job_log_says_nothing_stronger(tmp_path):
    """Found 2026-11-21: the workstation had her report waiting for the owner while the world
    showed her idle and counted nobody waiting."""
    from bau import workstation as W
    W.refresh(tmp_path)
    desk_task(tmp_path, "finance", "approved")
    desk_task(tmp_path, "researcher", "running")
    desk_task(tmp_path, "producer", "done", report="1. Golden hour on the balcony")
    desk_task(tmp_path, "marketer", "waiting_owner", manager={"reason": "outside effect"})
    before = (tmp_path / "workstation" / "state.json").read_bytes()
    w = world(tmp_path, NOW)
    got = {a["name"]: (a["room"], a["state"]) for a in w["agents"]}
    assert got["finance"] == ("hq", "assigned")
    assert got["researcher"] == ("research", "working")
    assert got["producer"] == ("approvals", "waiting for you")
    assert got["marketer"] == ("approvals", "waiting for you")
    a = {a["name"]: a for a in w["agents"]}
    assert a["producer"]["work"]["tasks"][0]["report"].startswith("1. Golden hour")
    assert a["marketer"]["work"]["tasks"][0]["reason"] == "outside effect"
    assert a["finance"]["work"]["worker"]["health"] == W.START_HEALTH
    assert {t["agent"] for t in w["tasks"]} >= {"finance", "researcher", "producer"}
    # reading the world never changes the workstation (no ageing, no retiring)
    assert (tmp_path / "workstation" / "state.json").read_bytes() == before


def test_a_running_job_outranks_her_workstation_and_filed_work_does_not_count(tmp_path):
    job(tmp_path, "researcher", "RUNNING")
    desk_task(tmp_path, "researcher", "approved")
    desk_task(tmp_path, "producer", "done", seen={"by": "human:owner", "kept": True})
    got = rooms(tmp_path)
    assert got["researcher"] == ("research", "working")
    assert got["producer"] == ("hq", "idle")


def test_a_waiting_card_says_which_agent_or_task_it_is_about():
    from bau.assistant import Pending
    p = Pending("ag_1", "agent_approve", {"agent": "finance"}, "New worker", "now")
    assert p.public()["about"] == {"agent": "finance"}
    assert Pending("su_1", "setup_step", {"step": "prices"}, "x", "now").public()["about"] == {}


def test_the_world_runs_the_business_full_screen_from_its_own_tabs():
    """The owner, 2026-11-21: full screen, the menu as tabs, and every agent's work run from
    her own panel: give work, run a shift, open what she needs from him, remove a held task."""
    page = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "jarvis.html").read_text()
    for tab in ("w-to-hq", "w-to-floor", "w-to-inbox", "w-to-desk", "w-to-mc", "world-close"):
        assert f'id="{tab}"' in page, tab
    assert "#worldbox.overlay{inset:0 0 84px 0" in page                 # all but the talk bar
    for call in ('"/api/workstation/assign"', '"/api/workstation/shift"',
                 '"/api/workstation/withdraw"', "focusCard(c.id)"):
        assert call in page, call
    assert "c.about.agent === a.name" in page                          # her own cards on her panel
