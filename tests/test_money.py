"""`bau money` (the owner, 2026-11-18: "test all values to make sure this is money making
ready"): every link from the creator to Fanvue earnings, read live from its real record, with
the exact fix; only looks, never changes anything."""

import json

import yaml

from bau import money

ALL_UP = {"pictures_running": True, "pictures_installed": True, "autopilot_timer": True,
          "fanvue_keys": True, "face_ready": True}


def probe(**over):
    facts = dict(ALL_UP, **over)
    return lambda what: facts[what]


def ready_home(home):
    (home / "creators").mkdir(parents=True)
    (home / "creators" / "aria.yaml").write_text(yaml.safe_dump(
        {"id": "aria", "name": "Aria",
         "prices": {"subscription": 9.99, "nude": 10.99, "xxx": 14.99}}))
    faces = home / "creators" / "faces" / "candidates"
    faces.mkdir(parents=True)
    (faces / "aria-1.png").write_bytes(b"face")
    from bau import face
    face.pick(home, {"id": "aria"}, 1, "human:owner")
    (home / "config").mkdir()
    (home / "config" / "brains.yaml").write_text(yaml.safe_dump({"small": "qwen-local"}))
    (home / "registry").mkdir()
    (home / "registry" / "capabilities.yaml").write_text(yaml.safe_dump(
        {"model": {"qwen-local": {"status": "APPROVED", "deployment": "local"}}}))
    (home / "fanvue").mkdir()
    (home / "fanvue" / "token.json").write_text(json.dumps({"access_token": "x"}))
    (home / "fanvue" / "autopost.json").write_text(json.dumps(
        {"on": True, "per_day": 1, "audience": "subscribers"}))
    return home


def test_a_ready_machine_says_so(tmp_path, monkeypatch):
    from bau import fanvue
    home = ready_home(tmp_path)
    fanvue.TokenStore(home).save({"access_token": "x", "expires_in": 3600})   # the real store
    ls = money.links(home, probe())
    assert [link["ok"] for link in ls] == [True] * len(ls), ls
    s = money.summary(home, probe())
    assert s == {"ready": len(ls), "of": len(ls), "next": None, "next_fix": None}
    assert "Everything is ready" in money.report(home, probe())


def test_each_broken_link_is_named_with_its_fix(tmp_path, monkeypatch):
    home = tmp_path
    ls = {link["link"]: link for link in money.links(home, probe(
        pictures_running=False, pictures_installed=True, autopilot_timer=False,
        fanvue_keys=False))}
    assert ls["creator profile"]["fix"].startswith("bau creator init")
    assert "bau team set --boss" in ls["boss model (writes captions, runs the agents)"]["fix"]
    pic = ls["pictures (ComfyUI on this computer)"]
    assert pic["found"] == "installed, not running"
    assert pic["fix"] == "sudo systemctl start bau-pictures.service"
    assert ls["Fanvue connected"]["fix"].startswith("bau fanvue status")
    assert "autopost on" in ls["autopost (Fanvue posts by themselves)"]["fix"]
    assert ls["no HOLD"]["ok"] is True
    s = money.summary(home, probe(fanvue_keys=False))
    assert s["next"] == "creator profile" and s["ready"] < s["of"]   # first missing, in order


def test_a_paused_autopilot_and_a_hold_are_not_ready(tmp_path, monkeypatch):
    from bau import autopilot, fanvue
    from bau.governor import Governor
    home = ready_home(tmp_path)
    fanvue.TokenStore(home).save({"access_token": "x", "expires_in": 3600})   # the real store
    monkeypatch.setattr(autopilot, "status", lambda h: {"paused": True})
    ap = next(link for link in money.links(home, probe()) if link["link"].startswith("autopilot"))
    assert not ap["ok"] and ap["found"] == "paused by you" and ap["fix"] == "bau autopilot resume"
    Governor(home).hold("test", by="human:owner")
    held = next(link for link in money.links(home, probe()) if link["link"] == "no HOLD")
    assert not held["ok"] and held["fix"].startswith("bau governor release")


def test_what_happened_counts_the_real_queue_and_money(tmp_path):
    q = tmp_path / "fanvue" / "queue"
    q.mkdir(parents=True)
    for i, st in enumerate(("REVIEW", "QUEUED", "POSTED", "POSTED")):
        (q / f"fv_{i}.json").write_text(json.dumps(
            {"item_id": f"fv_{i}", "status": st, "queued_at": f"2026-11-1{i}"}))
    eco = tmp_path / "economics"
    eco.mkdir()
    (eco / "revenue.jsonl").write_text(json.dumps(
        {"ts": "2026-11-17T00:00:00+00:00", "gross_usd": 10.0, "platform_fee": 2.0}) + "\n")
    a = money.activity(tmp_path)
    assert a == {"waiting_for_you": 1, "queued": 1, "posted": 2, "money_received_usd": 8.0}


def test_the_command_only_looks_and_exits_blocked_until_ready(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    monkeypatch.setattr(money, "_probe", probe(pictures_running=False,
                                               pictures_installed=False))
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert main(["money"]) == 3
    out = capsys.readouterr().out
    assert "✗ creator profile" in out and "Start here: bau creator init" in out
    created = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert all(str(p).startswith(("audit", "governor")) for p in set(created) - set(before))


def test_the_world_shows_the_money_score(tmp_path):
    from bau.world import world
    w = world(tmp_path)
    m = w["system"]["money"]
    assert m["of"] == 9 and m["ready"] < 9 and m["next"]


def test_on_the_laptop_station_it_points_at_the_desktop(tmp_path, monkeypatch, capsys):
    from bau import station
    from bau.cli import main
    mark = tmp_path / "station"
    mark.write_text("on=x\n")
    monkeypatch.setattr(station, "STATION_MARK", mark)
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    monkeypatch.setattr(money, "links", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("read the laptop's own empty state")))
    assert money.report(tmp_path) == money.STATION_TEXT
    assert "runs on the desktop" in money.STATION_TEXT
    assert money.summary(tmp_path)["station"] is True
    assert main(["money"]) == 0
    assert capsys.readouterr().out.strip() == money.STATION_TEXT
    from bau.world import world
    s = world(tmp_path)["system"]
    assert s["station"] is True and s["money"]["station"] is True
