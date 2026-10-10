"""Results tracker: what each posted video did (views, watch time, earnings) and whether it
made money once its clips are paid for. Read-only: it never posts, edits or deletes
anything on a platform. Written before the code it tests."""

import datetime as dt
import json
import threading
import urllib.parse
import urllib.request
from dataclasses import asdict

import pytest
import yaml

from bau import results as R
from bau import tiktok, youtube
from bau import workspace as W
from bau.audit import AuditLog
from bau.economics import Ledger
from bau.store import JsonlStore

TODAY = dt.date.today().isoformat()
POSTED = (dt.datetime.now(dt.UTC) - dt.timedelta(days=5)).isoformat()


class FakeYT(youtube.Http):
    """YouTube Analytics reports.query, enough to exercise the real client code."""

    def __init__(self, monetary=True):
        self.calls, self.monetary = [], monetary

    def request(self, method, url, headers, body=None, timeout=120):
        self.calls.append((method, url))
        if url.startswith(youtube.TOKEN_URL):
            return 200, {}, json.dumps({"access_token": "at2", "expires_in": 3599}).encode()
        assert method == "GET" and url.startswith(youtube.ANALYTICS)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        ids = q["filters"].removeprefix("video==").split(",")
        if q["metrics"] == "estimatedRevenue":
            if not self.monetary:
                return 403, {}, json.dumps({"error": {"message": "Forbidden"}}).encode()
            rows = [[v, {"yt1": 4.25, "yt2": 0.5}.get(v, 0.0)] for v in ids]
            return 200, {}, json.dumps({"columnHeaders": [{"name": "video"},
                                                          {"name": "estimatedRevenue"}],
                                        "rows": rows}).encode()
        names = q["metrics"].split(",")
        base = {"yt1": 1200, "yt2": 300}
        rows = [[v] + [base.get(v, 10) if n == "views" else 50 if n == "averageViewPercentage"
                       else 7 for n in names] for v in ids]
        return 200, {}, json.dumps({"columnHeaders": [{"name": "video"}] +
                                    [{"name": n} for n in names], "rows": rows}).encode()


class FakeTT(tiktok.Http):
    def __init__(self):
        self.calls = []

    def request(self, method, url, headers, body=None, timeout=120):
        self.calls.append((method, url, json.loads(body or b"{}")))
        assert method == "POST" and "/v2/video/query/" in url and "view_count" in url
        ids = json.loads(body)["filters"]["video_ids"]
        assert len(ids) <= 20
        return 200, json.dumps({"data": {"videos": [
            {"id": i, "title": "t", "view_count": 900, "like_count": 40, "comment_count": 3,
             "share_count": 2} for i in ids]}, "error": {"code": "ok"}}).encode()


def yt_client(home, scope=youtube.SCOPES, **kw):
    c = youtube.YouTubeClient(home, http=FakeYT(**kw), creds=("cid", "cs"))
    c.tokens.save({"access_token": "at", "refresh_token": "rt", "expires_in": 3600,
                   "scope": scope})
    return c


def tt_client(home, scope=tiktok.SCOPES):
    c = tiktok.TikTokClient(home, http=FakeTT(), creds=("ck", "cs"))
    c.tokens.save({"access_token": "at", "refresh_token": "rt", "expires_in": 86400,
                   "refresh_expires_in": 3e7, "open_id": "o1", "scope": scope})
    return c


def post_youtube(home, item_id, video_id, kids=True, status="POSTED"):
    JsonlStore(home / "publish" / "youtube" / "queue.jsonl").append(asdict(youtube.QueueItem(
        item_id=item_id, video=f"videos/{item_id}.mp4", title=f"Episode {item_id}", kids=kids,
        status=status, video_id=video_id if status == "POSTED" else "",
        result={"at": POSTED} if status == "POSTED" else {})))


def post_tiktok(home, item_id, post_id):
    JsonlStore(home / "publish" / "tiktok" / "queue.jsonl").append(asdict(tiktok.QueueItem(
        item_id=item_id, video=f"videos/{item_id}.mp4", caption=f"Clip {item_id}",
        status="POSTED", publish_id="p_" + item_id,
        result={"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [post_id]})))


def clip(home, cid, usd):
    JsonlStore(home / "studio" / "jobs.jsonl").append({"id": cid, "status": "completed",
                                                       "usd": usd, "prompt": "p"})
    Ledger(home).cost("api", usd, agent="studio", job_id=cid, provider="higgsfield")


@pytest.fixture
def home(tmp_path):
    return tmp_path


def tracker(home, yt=None, tt=None):
    clients = {k: v for k, v in (("youtube", yt), ("tiktok", tt)) if v is not None}
    return R.Results(home, AuditLog(home / "audit" / "chain.jsonl", key=b""), clients)


# ------------------------------------------------------------------ what was posted

def test_finds_every_posted_video_and_nothing_else(home):
    post_youtube(home, "yt_a", "yt1")
    post_youtube(home, "yt_q", "", status="QUEUED")
    post_tiktok(home, "tt_a", 7001)
    vids = tracker(home).videos()
    assert {(v["platform"], v["video_id"]) for v in vids} == {("youtube", "yt1"),
                                                              ("tiktok", "7001")}
    yt = next(v for v in vids if v["platform"] == "youtube")
    assert yt["made_for_kids"] is True and yt["title"] == "Episode yt_a"


def test_logins_now_ask_to_read_the_numbers():
    assert "yt-analytics.readonly" in youtube.SCOPES
    assert "yt-analytics-monetary.readonly" in youtube.SCOPES
    assert "video.list" in tiktok.SCOPES


# ------------------------------------------------------------------ YouTube

def test_youtube_views_watch_time_and_earnings_per_video(home):
    post_youtube(home, "yt_a", "yt1")
    post_youtube(home, "yt_b", "yt2")
    yt = yt_client(home)
    out = tracker(home, yt=yt).refresh()
    assert out["refreshed"]["youtube"] == 2 and not out["errors"]
    gets = [u for m, u in yt.http.calls if u.startswith(youtube.ANALYTICS)]
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(gets[0]).query))
    assert q["ids"] == "channel==MINE" and q["dimensions"] == "video"
    assert set(q["filters"].removeprefix("video==").split(",")) == {"yt1", "yt2"}
    assert int(q["maxResults"]) <= 200 and q["sort"] and q["endDate"] == TODAY
    assert all(m == "GET" for m, u in yt.http.calls if "googleapis" in u)   # read only
    rep = tracker(home).report()
    v = next(x for x in rep["videos"] if x["video_id"] == "yt1")
    assert v["views"] == 1200 and v["avg_view_pct"] == 50 and v["revenue_usd"] == 4.25
    assert rep["totals"]["views"] == 1500 and rep["totals"]["revenue_usd"] == 4.75
    assert any("estimate" in n for n in rep["notes"])


def test_earnings_not_shared_is_said_plainly_and_views_still_come(home):
    post_youtube(home, "yt_a", "yt1")
    tracker(home, yt=yt_client(home, monetary=False)).refresh()
    v = tracker(home).report()["videos"][0]
    assert v["views"] == 1200 and v["revenue_usd"] is None
    assert any("Partner Program" in n for n in v["notes"])


def test_an_old_login_is_asked_to_log_in_again(home):
    post_youtube(home, "yt_a", "yt1")
    old = "https://www.googleapis.com/auth/youtube.upload"
    out = tracker(home, yt=yt_client(home, scope=old)).refresh()
    assert "bau youtube login" in out["errors"]["youtube"]


def test_refresh_is_polite_and_recorded(home):
    post_youtube(home, "yt_a", "yt1")
    yt = yt_client(home)
    t = tracker(home, yt=yt)
    t.refresh()
    n = len(yt.http.calls)
    out = t.refresh()                                      # within the hour: nothing sent
    assert len(yt.http.calls) == n and out["skipped"]["youtube"]
    t.refresh(force=True)
    assert len(yt.http.calls) > n
    ev = [r for r in t.audit.records() if r["event"] == "results.refreshed"]
    assert ev and ev[-1]["data"]["youtube"] == 1


# ------------------------------------------------------------------ TikTok

def test_tiktok_counts_in_batches_of_twenty(home):
    for i in range(21):
        post_tiktok(home, f"tt_{i}", 7000 + i)
    tt = tt_client(home)
    out = tracker(home, tt=tt).refresh()
    assert out["refreshed"]["tiktok"] == 21 and len(tt.http.calls) == 2
    v = tracker(home).report()["videos"][0]
    assert v["views"] == 900 and v["likes"] == 40 and v["revenue_usd"] is None
    assert any("TikTok" in n and "earnings" in n for n in v["notes"])


def test_tiktok_old_login_is_asked_to_log_in_again(home):
    post_tiktok(home, "tt_a", 7001)
    out = tracker(home, tt=tt_client(home, scope="video.publish")).refresh()
    assert "bau tiktok login" in out["errors"]["tiktok"]


def test_a_platform_not_connected_does_not_stop_the_other(home):
    post_youtube(home, "yt_a", "yt1")
    post_tiktok(home, "tt_a", 7001)
    out = tracker(home, yt=yt_client(home)).refresh()      # TikTok never logged in
    assert out["refreshed"]["youtube"] == 1 and "tiktok" in out["errors"]


# ------------------------------------------------------------------ money per video

def test_profit_per_video_from_the_clips_it_used(home):
    post_youtube(home, "yt_a", "yt1")
    post_youtube(home, "yt_b", "yt2")
    clip(home, "clip_a", 1.5)
    clip(home, "clip_b", 2.0)
    clip(home, "clip_spare", 9.0)
    t = tracker(home, yt=yt_client(home))
    t.link("youtube", "yt_a", "human:owner", clips=["clip_a", "clip_b"])
    t.refresh()
    rep = t.report()
    a = next(v for v in rep["videos"] if v["item_id"] == "yt_a")
    b = next(v for v in rep["videos"] if v["item_id"] == "yt_b")
    assert a["cost_usd"] == 3.5 and a["profit_usd"] == 0.75
    assert b["cost_usd"] is None and b["profit_usd"] is None
    assert any("bau results link" in n for n in b["notes"])
    assert rep["totals"]["unlinked_clip_spend_usd"] == 9.0
    with pytest.raises(ValueError):
        t.link("youtube", "yt_a", "human:owner", clips=["clip_nope"])
    with pytest.raises(ValueError):
        t.link("youtube", "nope", "human:owner", clips=["clip_a"])
    with pytest.raises(ValueError, match="workspace/episode"):
        t.link("youtube", "yt_a", "human:owner", episode="kids-channel/ep-404")


def test_what_works_compares_story_formats(home):
    ws = W.create("kids-channel", home=home)
    for n, (fmt, vid) in enumerate((("count-along", "yt1"), ("question-reveal", "yt2")), 1):
        ep = W.new_episode(ws, f"Idea {n}")
        (ep / "series.yaml").write_text(yaml.safe_dump({"format": fmt}))
        post_youtube(home, f"yt_{n}", vid)
    t = tracker(home, yt=yt_client(home))
    t.link("youtube", "yt_1", "human:owner", episode=f"{ws.name}/ep-001")
    t.link("youtube", "yt_2", "human:owner", episode=f"{ws.name}/ep-002")
    t.refresh()
    rep = t.report()
    fmts = rep["by_format"]
    assert [f["format"] for f in fmts] == ["count-along", "question-reveal"]   # most watched
    assert fmts[0]["avg_views"] == 1200 and fmts[0]["videos"] == 1
    assert rep["best"][0]["video_id"] == "yt1"
    assert any("count-along" in w for w in rep["what_works"])


def test_report_before_anything_was_posted_says_what_to_do(home):
    rep = tracker(home).report()
    assert rep["videos"] == [] and rep["totals"]["views"] == 0
    assert any("post" in n.lower() for n in rep["notes"])


# ------------------------------------------------------------------ Jarvis, screen, CLI

def test_jarvis_tool_node_endpoints_and_page(home, tmp_path):
    from importlib import resources

    from bau.assistant import TOOL_NODE, Assistant, Voice
    from bau.overview import overview
    from bau.ui.jarvis_server import serve
    post_youtube(home, "yt_a", "yt1")
    a = Assistant(home, None, {}, "human:owner", AuditLog(home / "audit" / "chain.jsonl",
                                                          key=b""),
                  clients={"youtube": yt_client(home)})
    assert a.tools["results"].kind == "read" and TOOL_NODE["results"] == "results"
    out, err = a._run_tool("results", {"refresh": True})
    assert not err and out["totals"]["views"] == 1200
    assert "results" in {n["id"] for n in overview(a)["nodes"]}
    srv, _ = serve(a, Voice(tmp_path), 0, key="k1")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def call(path, body=None):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode()
                                         if body is not None else None, headers={
                                             "X-Jarvis-Key": "k1",
                                             "Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        assert call("/api/results")["totals"]["views"] == 1200
        r = call("/api/results/refresh", {"force": True})
        for _ in range(60):
            if "job" not in r:
                break
            import time
            time.sleep(.05)
            r = call(f"/api/job/{r['job']}")
        assert r["totals"]["views"] == 1200
    finally:
        srv.shutdown()
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert 'n.id === "results"' in page and "function renderResults" in page
    assert 'c.tool === "results"' in page and "/api/results/refresh" in page


def test_cli(home, monkeypatch, capsys):
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(home))
    post_youtube(home, "yt_a", "yt1")
    clip(home, "clip_a", 1.0)
    assert main(["results"]) == 0
    assert json.loads(capsys.readouterr().out)["videos"][0]["video_id"] == "yt1"
    assert main(["results", "link", "youtube", "yt_a", "--clips", "clip_a"]) == 0
    capsys.readouterr()
    assert main(["results"]) == 0
    assert json.loads(capsys.readouterr().out)["videos"][0]["cost_usd"] == 1.0
    assert main(["results", "link", "youtube", "yt_a", "--clips", "clip_zz"]) != 0
