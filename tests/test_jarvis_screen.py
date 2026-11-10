"""The Jarvis screen: live nodes around the core, episode buttons, owner-only checks."""

import json
import threading
import urllib.error
import urllib.request

import pytest
from test_workspace import PERSONA, VOICE

from bau import workspace as W
from bau.assistant import Assistant, Voice
from bau.audit import AuditLog
from bau.models.providers import ScriptedProvider
from bau.overview import overview

MODEL = {"id": "test-model", "context": 32768}


def make(home, script=None):
    prov = ScriptedProvider(list(script)) if script is not None else None
    return Assistant(home, prov, MODEL if prov else {}, "human:owner",
                     AuditLog(home / "audit" / "chain.jsonl", key=b""))


def nodes(a):
    return {n["id"]: n for n in overview(a)["nodes"]}


def with_episode(home):
    ws = W.create("creator-week", home=home)
    (ws / "_shared" / "persona.md").write_text(PERSONA)
    (ws / "_shared" / "voice.md").write_text(VOICE)
    return ws, W.new_episode(ws, "Autumn city coffee week")


def test_fresh_system_shows_every_part_and_never_claims_unmeasured_green(tmp_path):
    n = nodes(make(tmp_path))
    for nid in ("chief", "producer", "publisher", "strategist", "researcher", "compliance",
                "finance", "watchdog", "models", "memory", "audit", "email", "tiktok"):
        assert nid in n
    assert n["models"]["state"] == "bad" and "plain mode" in n["models"]["summary"]
    assert n["producer"]["state"] == "idle" and n["finance"]["state"] == "idle"
    assert all(n[c]["state"] == "off" for c in ("email", "drive", "calendar", "crm",
                                                "tiktok"))
    assert n["audit"]["state"] == "ok"


def test_a_broken_source_shows_red_with_its_error(tmp_path):
    a = make(tmp_path)
    a.t_money = lambda: (_ for _ in ()).throw(OSError("ledger unreadable"))
    fin = nodes(a)["finance"]
    assert fin["state"] == "bad" and "ledger unreadable" in fin["summary"]


def test_episode_node_offers_draft_then_owner_check(tmp_path):
    a = make(tmp_path, ["Mon instagram sfw: latte by the window\n"])
    ws, ep = with_episode(tmp_path)
    prod = nodes(a)["producer"]
    assert prod["detail"]["episodes"][0]["next"] == {"action": "draft", "stage": "01"}
    out, err = a._run_tool("draft_stage", {"workspace": ws.name, "episode": ep.name})
    assert not err
    prod = nodes(a)["producer"]
    assert prod["state"] == "warn" and prod["detail"]["episodes"][0]["next"]["action"] == "check"
    card = a.stage_check(ws.name, ep.name, "01")
    assert "latte by the window" in card["summary"] and card["tool"] == "check_stage"
    assert not W.is_checked(W.contracts(ep)[0])                  # nothing until Confirm
    assert a.confirm(card["id"], True, "human:owner")["done"]
    assert W.is_checked(W.contracts(ep)[0])
    assert nodes(a)["producer"]["detail"]["episodes"][0]["next"]["stage"] == "02"


def test_the_model_can_never_check_a_stage(tmp_path):
    a = make(tmp_path, ["x"])
    ws, ep = with_episode(tmp_path)
    assert "check_stage" not in a.tools and "check_stage" not in [s.name for s in a.specs()]
    out, err = a._run_tool("check_stage", {"workspace": ws.name, "episode": ep.name,
                                           "stage": "01"})
    assert err and "unknown tool" in out["error"]
    with pytest.raises(W.WorkspaceError, match="not written yet"):
        a.stage_check(ws.name, ep.name, "01")
    a._run_tool("draft_stage", {"workspace": ws.name, "episode": ep.name})
    card = a.stage_check(ws.name, ep.name, "01")
    with pytest.raises(PermissionError):
        a.confirm(card["id"], True, "agent:jarvis")


def call(url, path, body=None, key="k123"):
    h = {"X-Jarvis-Key": key}
    data = None
    if body is not None:
        data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url + path, data=data,
                                                           headers=h)) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def test_screen_endpoints_draft_and_stage_checks_behind_the_key(tmp_path):
    from bau.ui.jarvis_server import serve
    a = make(tmp_path, ["Mon instagram sfw: latte by the window\n"])
    ws, ep = with_episode(tmp_path)
    srv, _ = serve(a, Voice(tmp_path), 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert call(url, "/api/overview", key="nope")[0] == 403
        code, o = call(url, "/api/overview")
        assert code == 200 and {n["id"] for n in o["nodes"]} >= {"producer", "models"}
        code, r = call(url, "/api/check", {"workspace": ws.name, "episode": ep.name,
                                          "stage": "01"})
        assert "not written yet" in r["error"]
        code, r = call(url, "/api/draft", {"workspace": ws.name, "episode": ep.name})
        assert code == 200 and not r["error"] and r["result"]["stage"] == "01_plan"
        # The owner's check comes back with the draft: the page pops it up at once.
        assert r["pending"][0]["tool"] == "check_stage"
        assert r["pending"][0]["id"] == r["result"]["pending_id"]
        code, r = call(url, "/api/check", {"workspace": ws.name, "episode": ep.name,
                                          "stage": "01"})
        pid = r["pending"][0]["id"]
        code, r = call(url, "/api/confirm", {"id": pid, "approve": True})
        assert r["done"] and r["result"]["checked"] == "01_plan"
    finally:
        srv.shutdown()


def test_owner_choices_are_big_buttons_with_nothing_preselected():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "jarvis.html"
            ).read_text(encoding="utf-8")
    assert "<select" not in page and 'el("select")' not in page        # no fiddly drop-downs
    assert 'el("button", "opt", label)' in page and "picked = {}" in page
    assert "To confirm, first choose: " in page                      # says what's missing
    assert "queueConfirms(r.pending)" in page                        # drafts pop the check


def test_confirm_is_never_focused_and_ignores_the_first_moment():
    # Seen 2026-10-10 in a live run: a check was confirmed seconds after it appeared, with
    # no click. The box focused Confirm, so any stray Enter/Space/"y" approved it unread.
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "jarvis.html"
            ).read_text(encoding="utf-8")
    assert '$("yes")).focus()' not in page and '$("yes").focus()' not in page
    assert 'querySelector(".box")).focus()' in page and 'class="box" tabindex="-1"' in page
    assert "const CONFIRM_SETTLE_MS = 900;" in page
    assert "if (approve && performance.now() - shownAt < CONFIRM_SETTLE_MS) return;" in page


def test_a_waiting_card_never_covers_the_controls():
    # The owner, 2026-11-09: setup steps, autopilot questions and Fanvue pictures popped a
    # full-screen box that blocked the header buttons, the chat box and the mic. The card
    # is docked in a corner; only the card itself takes clicks, and keys reach the chat
    # unless the owner is inside the card.
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "jarvis.html"
            ).read_text(encoding="utf-8")
    rule = page.split("#confirm{", 1)[1].split("}", 1)[0]
    assert "inset:0" not in rule and "background" not in rule
    assert "pointer-events:none" in rule
    assert "#confirm .box{pointer-events:auto" in page
    assert 'aria-modal="false"' in page
    assert page.count('$("confirm").classList.contains("show") && '
                      '$("confirm").contains(document.activeElement)') == 2


def test_the_screen_keeps_answering_while_jarvis_thinks(tmp_path):
    # /api/overview used to wait for the whole model turn; the page polls it, the waiting
    # requests used up the browser's connections and the live feed stalled.
    import time

    from bau.ui.jarvis_server import serve
    gate = threading.Event()

    class Slow(ScriptedProvider):
        def complete(self, *a, **k):
            gate.wait(10)
            return super().complete(*a, **k)

    a = Assistant(tmp_path, Slow(["done"]), MODEL, "human:owner",
                  AuditLog(tmp_path / "audit" / "chain.jsonl", key=b""))
    srv, _ = serve(a, Voice(tmp_path), 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert call(url, "/api/overview")[0] == 200
        threading.Thread(target=call, args=(url, "/api/ask", {"text": "think hard"}),
                         daemon=True).start()
        time.sleep(0.5)
        t0 = time.monotonic()
        code, o = call(url, "/api/overview")
        assert code == 200 and o["nodes"] and time.monotonic() - t0 < 2
    finally:
        gate.set()
        srv.shutdown()


# ---------------------------------------------------------------- the screen audit (2026-11-08)
def test_every_part_says_what_it_is_for_and_quiet_ones_say_the_next_step(tmp_path):
    from bau.assistant import Assistant
    from bau.overview import overview
    nodes = {n["id"]: n for n in overview(Assistant(tmp_path))["nodes"]}
    team = ["chief", "producer", "publisher", "strategist", "researcher", "compliance",
            "finance", "studio", "watchdog"]
    assert all(nodes[i]["about"] for i in team + ["fanvue", "tiktok", "memory", "scout"])
    for i in ("publisher", "strategist", "finance", "memory", "scout", "fanvue"):
        assert nodes[i]["next"], i                       # an empty home: each says what next


def test_fanvue_is_on_the_screen_with_autopost_queue_and_earnings(tmp_path):
    import hashlib
    import json

    from bau import fanvue as F
    from bau.assistant import Assistant
    from bau.overview import overview
    node = {n["id"]: n for n in overview(Assistant(tmp_path))["nodes"]}["fanvue"]
    assert node["state"] == "off" and "Connect Fanvue" in node["next"]
    F.TokenStore(tmp_path).save({"access_token": "a", "refresh_token": "r", "expires_in": 60})
    media = tmp_path / "artifacts" / "media"
    media.mkdir(parents=True)
    (media / "a.png").write_bytes(b"x")
    (media / "a.png.provenance.json").write_text(json.dumps({
        "ai_generated": True, "file_sha256": hashlib.sha256(b"x").hexdigest(),
        "age_check": {"passed": True}}))
    F.Queue(tmp_path).add("a.png", "Evening in", 1, "human:owner")
    F.set_autopost(tmp_path, True, "human:owner", "subscribers", 3)
    node = {n["id"]: n for n in overview(Assistant(tmp_path))["nodes"]}["fanvue"]
    assert node["state"] == "ok" and node["detail"]["queued"] == 1
    assert "up to 3 a day to subscribers" in node["detail"]["autopost"]


def test_the_panel_shows_about_and_next():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src/bau/ui/jarvis.html").read_text()
    assert 'el("div", "about", n.about)' in page and '"Next: " + n.next' in page


def test_the_sound_layer_follows_the_voice_and_the_work():
    # the owner's ask (2026-11-08): the best visualizations possible
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src/bau/ui/jarvis.html").read_text()
    assert "an.getByteFrequencyData(fbuf)" in page  # the real voice
    assert "drawSpectrum(X, Y, R, now);" in page and "drawShocks(dt);" in page
    assert 'if (e.kind === "start") burst(CORE[0], CORE[1], nd.x, nd.y' in page   # work → sparks
    assert "REDUCED ? 4 : 18" in page and "if (!REDUCED) shock(" in page        # calm when asked
    assert "#caption:not(:empty){" in page                          # the caption always reads


def test_nothing_invisible_covers_the_buttons():
    # the owner, 2026-11-09: overlapping parts stopped the mouse from reaching buttons
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src/bau/ui/jarvis.html").read_text()
    # the side panels are only as tall as what they show, not a see-through strip to the bottom
    assert "aside{position:fixed;top:56px;max-height:calc(100vh - 166px);" in page
    assert "#timeline{position:fixed;top:56px;max-height:calc(100vh - 166px);" in page
    # a card answered before waking also takes the wake screen away
    assert '$("confirm").addEventListener("click", () => { if (!woke) wake(); }' in page


def test_the_tapestry_is_sacred_geometry_that_never_takes_a_click():
    # The owner, 2026-11-09: the screen as a psychedelic, esoteric tapestry (sacred geometry,
    # sound and frequency, magnetic fields), alive with Jarvis, with an off switch.
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "jarvis.html"
            ).read_text(encoding="utf-8")
    assert '<canvas id="sacred" aria-hidden="true"></canvas>' in page
    assert "canvas#sacred{position:fixed;inset:0;width:100%;height:100%;display:block;pointer-events:none}" in page
    assert page.index('id="sacred"') < page.index('<canvas id="core"')        # under the core
    for part in ("buildFlower(", "buildMetatron(", "buildChladni(", "PHI_ANGLE", "SOLFEGGIO", "L * Math.sin(th) ** 2"):
        assert part in page
    assert 'id="c-geo"' in page and 'localStorage.setItem("jarvis-tapestry"' in page
    assert "REDUCED ? 100 : 33" in page                                        # ~30 fps, calmer if asked


def test_a_toolbox_card_with_missing_fields_does_not_break():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "src" / "bau" / "ui" / "jarvis.html"
            ).read_text(encoding="utf-8")
    assert 'h = Object.assign({ name: "", repo: "", sources: [], evidence: ""' in page
