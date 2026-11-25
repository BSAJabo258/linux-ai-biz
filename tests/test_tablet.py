"""The tablet's task board (docs/TABLET.md): every real job in its column with its steps, read
only, behind Jarvis's key. The Android app's tunnel is tested in android/tunnel (Gradle)."""

import datetime as dt
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from test_world import job

from bau.assistant import Assistant, Voice
from bau.audit import AuditLog
from bau.world import BOARD, board

PAGE = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "watch.html").read_text()


def verified(home, j, ver):
    p = home / "jobs" / f"{j.job_id}.json"
    d = json.loads(p.read_text())
    d["verification"] = ver
    p.write_text(json.dumps(d))


def test_each_job_lands_in_its_column(tmp_path):
    job(tmp_path, "researcher", "PENDING", minutes_ago=5, job_id="job_a")
    job(tmp_path, "producer", "RUNNING", minutes_ago=4, job_id="job_b")
    verified(tmp_path, job(tmp_path, "finance", "COMPLETED", minutes_ago=3, job_id="job_c"),
             "VERIFIED")
    verified(tmp_path, job(tmp_path, "marketer", "COMPLETED", minutes_ago=2, job_id="job_d"),
             "FAILED")
    job(tmp_path, "researcher", "FAILED", minutes_ago=1, job_id="job_e")
    b = board(tmp_path)
    cols = {c["job_id"]: c["column"] for c in b["cards"]}
    assert cols == {"job_a": "waiting", "job_b": "working", "job_c": "done",
                    "job_d": "your review", "job_e": "stopped"}
    assert b["columns"] == list(BOARD) and b["counts"] == {c: 1 for c in BOARD}
    assert [c["job_id"] for c in b["cards"]] == ["job_e", "job_d", "job_c", "job_b", "job_a"]
    done = next(c for c in b["cards"] if c["job_id"] == "job_c")
    assert [s["step"] for s in done["steps"]][-1] == "Delivered"
    assert done["steps"][-1]["state"] == "done" and done["agent"] == "finance"


def test_an_empty_store_is_an_empty_board(tmp_path):
    b = board(tmp_path)
    assert b["cards"] == [] and set(b["counts"].values()) == {0}


def test_the_board_is_served_behind_the_key(tmp_path):
    from bau.ui.jarvis_server import serve
    job(tmp_path, "producer", "RUNNING", job_id="job_b")
    a = Assistant(tmp_path, None, {}, "human:owner",
                  AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""))
    srv, _ = serve(a, Voice(tmp_path), 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"

    def get(path, key=None):
        h = {"X-Jarvis-Key": key} if key else {}
        try:
            with urllib.request.urlopen(urllib.request.Request(url + path, headers=h)) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""
    try:
        assert get("/watch?k=nope")[0] == 403
        code, page = get("/watch?k=k123")
        assert code == 200 and b"task board" in page
        assert get("/api/board", "nope")[0] == 403
        code, body = get("/api/board", "k123")
        assert code == 200 and json.loads(body)["cards"][0]["column"] == "working"
    finally:
        srv.shutdown()


def test_the_page_only_reads():
    assert 'fetch("/api/board"' in PAGE and "X-Jarvis-Key" in PAGE
    assert "method" not in PAGE and "/api/confirm" not in PAGE and "POST" not in PAGE
    assert "innerHTML" not in PAGE                  # text only: an objective is never markup
    assert "<select" not in PAGE


def test_the_newest_come_first_and_the_list_is_capped(tmp_path):
    for i in range(5):
        job(tmp_path, "producer", "COMPLETED", minutes_ago=10 - i, job_id=f"job_{i}")
    b = board(tmp_path, limit=3)
    assert [c["job_id"] for c in b["cards"]] == ["job_4", "job_3", "job_2"]
    assert dt.datetime.fromisoformat(b["at"])
