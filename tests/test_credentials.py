"""One shared credential store (the owner, 2026-11-18: "the terminal connects, Jarvis doesn't
reuse it"). Found: the token was locked to the login that signed in, so the autopilot (the bau
account) could never read it; two processes could spend the one-use refresh token at once;
and an unreadable sign-in looked like no sign-in at all."""

import json
import threading
import time

from bau import credentials as C
from bau import fanvue as F
from bau import tiktok as T


class RotatingFanvue:
    """Fanvue's token endpoint: a refresh token works once, and the answer takes a moment."""

    def __init__(self):
        self.valid, self.calls, self.n = {"rt-0"}, 0, 0
        self.lock = threading.Lock()

    def request(self, method, url, headers, body):
        form = dict(p.split("=", 1) for p in body.decode().split("&"))
        with self.lock:
            self.calls += 1
            used = form["refresh_token"]
            if used not in self.valid:
                return 400, json.dumps({"error_description": "refresh token used"}).encode()
            self.valid.discard(used)
            self.n += 1
            new = f"rt-{self.n}"
            self.valid.add(new)
        time.sleep(0.3)                          # long enough for a second caller to arrive
        return 200, json.dumps({"access_token": f"at-{self.n}", "refresh_token": new,
                                "expires_in": 3600}).encode()


def expired(home):
    F.TokenStore(home).save({"access_token": "at-0", "refresh_token": "rt-0", "expires_in": 0})


def test_two_processes_refreshing_at_once_spend_the_refresh_token_once(tmp_path):
    expired(tmp_path)
    http = RotatingFanvue()
    got, errors = [], []

    def use():                                   # Jarvis's sync and the autopilot's post
        try:
            got.append(F.FanvueClient(tmp_path, http=http, creds=("c", "s")).access_token())
        except F.FanvueError as e:
            errors.append(str(e))
    threads = [threading.Thread(target=use) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [] and got == ["at-1", "at-1"] and http.calls == 1


def test_the_store_is_shared_with_the_bau_group_and_nobody_else(tmp_path):
    expired(tmp_path)
    assert (tmp_path / "secrets").stat().st_mode & 0o7777 == C.DIR_MODE
    assert (tmp_path / "secrets" / "fanvue.json").stat().st_mode & 0o777 == C.FILE_MODE
    T.TokenStore(tmp_path).save({"access_token": "a", "refresh_token": "r"})
    assert (tmp_path / "secrets" / "tiktok.json").stat().st_mode & 0o777 == 0o660


def test_an_older_owner_only_sign_in_is_opened_to_the_group_by_its_owner(tmp_path):
    d = tmp_path / "secrets"
    d.mkdir(mode=0o700)
    (d / "fanvue.json").write_text(json.dumps({"access_token": "a", "refresh_token": "r",
                                               "access_expires_at": time.time() + 600}))
    (d / "fanvue.json").chmod(0o600)              # how it was saved before 2026-11-18
    assert F.TokenStore(tmp_path).load()["access_token"] == "a"
    assert d.stat().st_mode & 0o7777 == 0o2770
    assert (d / "fanvue.json").stat().st_mode & 0o777 == 0o660


def test_an_unreadable_sign_in_is_said_with_its_fix_never_as_not_connected(tmp_path,
                                                                            monkeypatch):
    expired(tmp_path)

    def denied(self, *a, **k):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(type(tmp_path), "read_text", denied)
    st = F.status(tmp_path)
    assert st["sign_in"] == "unreadable" and st["connected"] is False
    assert st["fix"].startswith("sudo chgrp -R bau") and "chmod 2770" in st["fix"]
    try:
        F.FanvueClient(tmp_path, http=RotatingFanvue(), creds=("c", "s")).access_token()
        raise AssertionError("an unreadable sign-in must not pass")
    except F.FanvueError as e:
        assert "cannot read it" in str(e) and "sudo chgrp" in str(e)


def test_status_is_the_same_answer_everywhere_and_shows_no_secret(tmp_path, monkeypatch,
                                                                  capsys):
    from bau import money
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    monkeypatch.setenv("FANVUE_CLIENT_ID", "cid")
    monkeypatch.setenv("FANVUE_CLIENT_SECRET", "csecret")
    assert main(["fanvue", "status"]) == 3                       # not signed in yet
    out = json.loads(capsys.readouterr().out)
    assert out["sign_in"] == "missing" and out["fix"] == "bau fanvue login"
    F.TokenStore(tmp_path).save({"access_token": "SECRET-AT", "refresh_token": "SECRET-RT",
                                 "expires_in": 3600})
    assert main(["fanvue", "status"]) == 0
    text = capsys.readouterr().out
    assert "SECRET" not in text and json.loads(text)["access"].startswith("valid for")
    link = next(x for x in money.links(tmp_path, lambda w: True)
                if x["link"] == "Fanvue connected")
    assert link["ok"] and link["found"] == "connected"


def test_the_jarvis_card_runs_the_terminals_own_sign_in_and_hands_back_its_link(tmp_path):
    from bau import setup_steps as S
    from bau.audit import AuditLog
    done = threading.Event()

    def login(open_browser):                      # stands in for fanvue.login: same contract
        open_browser("https://auth.fanvue.com/oauth2/auth?client_id=cid&state=s")
        F.TokenStore(tmp_path).save({"access_token": "a", "refresh_token": "r",
                                     "expires_in": 3600})
        done.set()
    out = S.connect_in_jarvis("fanvue", tmp_path, "human:owner", login=login)
    assert out["started"] and out["open"].startswith("https://auth.fanvue.com/")
    assert "own browser" in out["said"] and "bau fanvue status" in out["said"]
    assert done.wait(5)
    time.sleep(0.2)
    events = [r["event"] for r in AuditLog(tmp_path / "audit" / "chain.jsonl").records()]
    assert "fanvue.connected" in events
    assert F.status(tmp_path)["sign_in"] == "present"      # the one store the terminal uses


def test_a_busy_callback_port_is_said_on_the_card(tmp_path):
    from bau import setup_steps as S

    def login(open_browser):
        raise OSError(98, "Address already in use")
    out = S.connect_in_jarvis("fanvue", tmp_path, "human:owner", login=login)
    assert "Address already in use" in out["error"]


def test_accepting_connect_fanvue_no_longer_needs_a_terminal(tmp_path, monkeypatch):
    from bau import setup_steps as S
    seen = []
    monkeypatch.setattr(S, "connect_in_jarvis",
                        lambda p, home, owner: seen.append(p) or {"started": True})
    out = S.run("fanvue", tmp_path, owner="human:owner",
                terminal=lambda t, c: (_ for _ in ()).throw(AssertionError("no terminal")))
    assert out == {"started": True} and seen == ["fanvue"]


def test_the_page_opens_the_sign_in_link_and_shows_what_the_card_said():
    from pathlib import Path
    html = (Path(__file__).parent.parent / "src/bau/ui/jarvis.html").read_text()
    assert "r.result.say || r.result.said" in html
    assert 'window.open(r.result.open, "_blank", "noopener")' in html


def test_signed_in_through_jarvis_the_terminal_uses_it_without_a_second_sign_in(tmp_path):
    """The real fanvue.login and callback server, run from the Jarvis card; only Fanvue's
    token answer and the browser are stand-ins."""
    import socket
    import urllib.parse
    import urllib.request

    from bau import setup_steps as S

    class Token:
        def request(self, method, url, headers, body):
            form = dict(urllib.parse.parse_qsl(body.decode()))
            assert form["grant_type"] == "authorization_code" and form["code"] == "the-code"
            return 200, json.dumps({"access_token": "AT", "refresh_token": "RT",
                                    "expires_in": 3600}).encode()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    jarvis = F.FanvueClient(tmp_path, http=Token(), creds=("cid", "csecret"))
    out = S.connect_in_jarvis("fanvue", tmp_path, "human:owner",
                              login=lambda ob: F.login(jarvis, port=port, open_browser=ob))
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(out["open"]).query))
    assert q["redirect_uri"] == f"http://127.0.0.1:{port}/callback"
    back = f"{q['redirect_uri']}?code=the-code&state={q['state']}"     # Fanvue sends him back
    with urllib.request.urlopen(back, timeout=5) as r:
        assert b"connected" in r.read()
    terminal = F.FanvueClient(tmp_path, http=Token(), creds=("cid", "csecret"))
    assert terminal.access_token() == "AT"                         # no second authorization
    assert F.status(tmp_path)["connected"] is True
