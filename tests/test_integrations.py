"""Integration doctor (docs/INTEGRATIONS.md): pre-flight, flight recorder, states, report.
Fanvue's and TikTok's answers are stand-ins; the callback server and sign-in code are real."""

import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

from bau import fanvue as F
from bau import integrations as ig
from bau import tiktok as T

CREDS = ("cid-public", "csecret-SHOULD-NEVER-SHOW")
OK_LOC = "https://www.fanvue.com/oauth/login?login_challenge=abc"
BAD_REDIRECT = ("https://www.fanvue.com/oauth/error?error=invalid_request&error_description="
                "The+%27redirect_uri%27+parameter+does+not+match+any+of+the+OAuth+2.0+Client")
BAD_CLIENT = ("https://www.fanvue.com/oauth/error?error=invalid_client&error_description="
              "Client+authentication+failed")


@pytest.fixture(autouse=True)
def _no_platform_keys(monkeypatch):
    for k in ("FANVUE_CLIENT_ID", "FANVUE_CLIENT_SECRET", "TIKTOK_CLIENT_KEY",
              "TIKTOK_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(F, "app_credentials", lambda *a: CREDS)
    monkeypatch.setattr(T, "app_credentials", lambda *a: CREDS)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def checks(pre):
    return {c["check"]: c for c in pre["checks"]}


class Token:
    """Fanvue's token endpoint: answers a code exchange, or refuses it."""

    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body or {"access_token": "AT-SECRET", "refresh_token": "RT-SECRET",
                             "expires_in": 3600, "scope": F.SCOPES}

    def request(self, method, url, headers, body=None, timeout=120):
        if "/v1/users/me" in url:
            return self.status_me, json.dumps(self.me).encode()
        return self.status, json.dumps(self.body).encode()

    status_me = 200
    me = {"handle": "aria", "uuid": "u1"}


def sign_in(tmp_path, http, back=lambda q: f"code=the-code&state={q['state']}", port=None):
    """Run the real fanvue.login; the 'browser' follows the link and Fanvue sends it back."""
    port = port or free_port()
    client = F.FanvueClient(tmp_path, http=http, creds=CREDS)
    rec = ig.Recorder("fanvue", tmp_path)
    got = {}

    def browser(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))

        def go():
            time.sleep(0.05)
            try:
                urllib.request.urlopen(f"{q['redirect_uri']}?{back(q)}", timeout=5).read()
            except urllib.error.HTTPError:
                pass
        threading.Thread(target=go, daemon=True).start()
    try:
        got["tok"] = F.login(client, port=port, open_browser=browser, timeout=5, rec=rec)
    except F.FanvueError as e:
        got["error"] = str(e)
    return client, rec, got


# ---------------------------------------------------------------- 1-4: before the browser

def test_1_a_missing_callback_handler_is_found_before_login(tmp_path, monkeypatch):
    monkeypatch.delattr(F, "login")
    pre = ig.preflight("fanvue", tmp_path, port=free_port(), probe=False)
    assert pre["ready"] is False and checks(pre)["callback_handler"]["ok"] is False


def test_2_a_busy_port_is_found_before_login(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        pre = ig.preflight("fanvue", tmp_path, port=s.getsockname()[1], probe=False)
    assert pre["ready"] is False and "already in use" in checks(pre)["port"]["detail"]


def test_3_a_port_that_differs_from_the_last_working_one_is_found(tmp_path):
    ig.save_known_good("fanvue", tmp_path, "http://127.0.0.1:3456/callback", 3456, F.SCOPES,
                       "aria", "terminal")
    pre = ig.preflight("fanvue", tmp_path, port=free_port(), probe=False)
    c = checks(pre)["redirect_vs_last_working"]
    assert c["ok"] is False and "3456" in c["detail"] and "--port 3456" in c["fix"]


def test_4_an_unregistered_redirect_is_found_before_the_browser_opens(tmp_path):
    seen = []

    def get(url):
        seen.append(url)
        return 302, BAD_REDIRECT
    pre = ig.preflight("fanvue", tmp_path, port=free_port(), get=get)
    c = checks(pre)["platform_accepts_redirect"]
    assert pre["ready"] is False and c["ok"] is False
    assert c["detail"].startswith("redirect_not_registered")
    assert pre["redirect"] in pre["next"] and "Authentication tab" in pre["next"]
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(seen[0]).query))
    assert q["client_id"] == CREDS[0] and q["redirect_uri"] == pre["redirect"]
    assert CREDS[1] not in seen[0]                       # the secret never leaves


def test_the_probe_tells_a_good_address_and_an_unknown_app_apart(tmp_path):
    ok = ig.preflight("fanvue", tmp_path, port=free_port(), get=lambda u: (302, OK_LOC))
    assert ok["ready"] is True and ok["next"] == "bau fanvue login"
    bad = ig.preflight("fanvue", tmp_path, port=free_port(), get=lambda u: (302, BAD_CLIENT))
    assert checks(bad)["platform_accepts_redirect"]["detail"].startswith("unknown_client")


def test_no_internet_during_the_probe_does_not_block_the_sign_in(tmp_path):
    def get(url):
        raise OSError("Network is unreachable")
    pre = ig.preflight("fanvue", tmp_path, port=free_port(), get=get)
    assert pre["ready"] is True and checks(pre)["platform_accepts_redirect"]["ok"] is None


def test_tiktok_is_not_probed_but_its_exact_address_is_said(tmp_path):
    pre = ig.preflight("tiktok", tmp_path, port=free_port(),
                       get=lambda u: pytest.fail("TikTok's probe answer is unverified"))
    assert pre["redirect"].endswith("/callback/")
    assert checks(pre)["platform_accepts_redirect"]["ok"] is None


# ---------------------------------------------------------------- 5-8: the attempt itself

def test_5_a_wrong_state_is_rejected_and_recorded(tmp_path):
    _, rec, got = sign_in(tmp_path, Token(), back=lambda q: "code=x&state=forged")
    assert "state mismatch" in got["error"]
    cb = [r for r in ig.last_attempt("fanvue", tmp_path) if r["stage"] == "callback"][0]
    assert cb["ok"] is False and cb["state_valid"] is False


def test_6_a_pkce_mismatch_is_a_token_exchange_failure_not_a_callback_one(tmp_path):
    http = Token(400, {"error": "invalid_grant",
                       "error_description": "PKCE verifier does not match"})
    _, _, got = sign_in(tmp_path, http)
    assert "PKCE" in got["error"]
    st = {r["stage"]: r for r in ig.last_attempt("fanvue", tmp_path)}
    assert st["callback"]["ok"] is True                 # 8: callback fine ...
    assert st["token_exchange"]["ok"] is False          # ... the exchange failed
    assert "invalid_grant" in st["token_exchange"]["next"]


def test_7_missing_scopes_are_reported(tmp_path):
    http = Token(body={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600,
                       "scope": "openid offline_access read:self"})
    sign_in(tmp_path, http)
    st = ig.state("fanvue", tmp_path)
    assert st["state"] == "PERMISSION_DENIED"
    assert "write:post" in st["missing_scopes"] and "read:self" not in st["missing_scopes"]


def test_a_refusal_on_the_consent_page_is_recorded_with_fanvues_words(tmp_path):
    _, _, got = sign_in(tmp_path, Token(),
                        back=lambda q: f"error=access_denied&state={q['state']}")
    assert "access_denied" in got["error"]
    assert ig.state("fanvue", tmp_path)["state"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------- 9-11: after

def test_9_an_expired_token_is_refreshed_and_10_a_revoked_one_is_detected(tmp_path):
    client, rec, _ = sign_in(tmp_path, Token())
    tok = client.tokens.load()
    tok["access_expires_at"] = 0
    client.tokens.store.save(tok)
    assert ig.state("fanvue", tmp_path)["state"] == "REFRESH_REQUIRED"
    assert client.access_token() == "AT-SECRET"           # refreshed with the rotated token
    ig.record_api_check("fanvue", tmp_path, False, error="Fanvue GET /v1/users/me: HTTP 401",
                        http_status=401)
    st = ig.state("fanvue", tmp_path)
    assert st["state"] == "REVOKED" and "login" in st["next"]


def test_11_consent_alone_is_authenticated_never_api_verified(tmp_path):
    sign_in(tmp_path, Token())
    assert ig.state("fanvue", tmp_path)["state"] == "AUTHENTICATED"
    ig.record_api_check("fanvue", tmp_path, True, account="aria")
    assert ig.state("fanvue", tmp_path)["state"] == "API_VERIFIED"


def test_a_newer_sign_in_is_not_verified_by_an_older_api_check(tmp_path):
    sign_in(tmp_path, Token())
    ig.record_api_check("fanvue", tmp_path, True)
    sign_in(tmp_path, Token())
    assert ig.state("fanvue", tmp_path)["state"] == "AUTHENTICATED"


def test_states_before_any_sign_in(tmp_path, monkeypatch):
    assert ig.state("fanvue", tmp_path)["state"] == "READY_TO_AUTHORIZE"

    def none(*a):
        raise F.FanvueError("set FANVUE_CLIENT_ID")
    monkeypatch.setattr(F, "app_credentials", none)
    assert ig.state("fanvue", tmp_path)["state"] == "NOT_CONFIGURED"
    assert set(ig.STATES) >= {ig.state(p, tmp_path)["state"] for p in ig.REGISTRY}


# ---------------------------------------------------------------- 12, 14, 15

def test_12_no_secret_reaches_the_record_or_the_report(tmp_path):
    sign_in(tmp_path, Token())
    ig.Recorder("fanvue", tmp_path).stage(
        "test", False, error="Authorization: Bearer eyJhbGciOi.secret.part and "
        "https://x/cb?code=AUTHCODE123&state=s refresh_token=RT-SECRET",
        client_secret=CREDS[1], cookie="sid=abc", wallet_secret="w")
    raw = (tmp_path / "integrations" / "attempts.jsonl").read_text()
    text = ig.report("fanvue", tmp_path)
    for secret in ("AT-SECRET", "RT-SECRET", "the-code", "AUTHCODE123", CREDS[1],
                   "eyJhbGciOi", "sid=abc"):
        assert secret not in raw and secret not in text
    assert "[redacted]" in raw


def test_14_a_failed_connection_gives_a_copyable_report(tmp_path):
    def get(url):
        return 302, BAD_REDIRECT
    pre = ig.preflight("fanvue", tmp_path, port=free_port(), get=get)
    ig.Recorder("fanvue", tmp_path).stage("preflight", False, checks=pre["checks"],
                                          next=pre["next"])
    text = ig.report("fanvue", tmp_path, pre=pre)
    assert "[FAIL] platform_accepts_redirect" in text and "fix: register exactly" in text
    assert "https://auth.fanvue.com/oauth2/auth" in text
    assert "implementation-guide" in text


def test_15_a_verified_connection_is_saved_and_reused(tmp_path):
    client, rec, got = sign_in(tmp_path, Token())
    ig.record_api_check("fanvue", tmp_path, True, account="aria", rec=rec)
    ig.save_known_good("fanvue", tmp_path, "http://127.0.0.1:3456/callback", 3456,
                       got["tok"]["scope"], "aria", "terminal")
    good = ig.known_good("fanvue", tmp_path)
    assert good["account"] == "aria" and any("Authentication tab" in s for s in good["steps"])
    assert "last verified" in ig.report("fanvue", tmp_path)


def test_a_timeout_says_the_address_and_the_laptop_case(tmp_path):
    port = free_port()
    client = F.FanvueClient(tmp_path, http=Token(), creds=CREDS)
    with pytest.raises(F.FanvueError):
        F.login(client, port=port, open_browser=lambda u: None, timeout=0.3,
                rec=ig.Recorder("fanvue", tmp_path))
    last = ig.last_attempt("fanvue", tmp_path)[-1]
    assert last["stage"] == "callback" and not last["ok"]
    assert f"127.0.0.1:{port}/callback" in last["next"] and "this computer" in last["next"]


def test_tiktok_sign_in_is_recorded_stage_by_stage(tmp_path):
    class TT:
        def request(self, method, url, headers, body=None, timeout=120):
            return 200, json.dumps({"access_token": "AT", "refresh_token": "RT",
                                    "expires_in": 7200, "refresh_expires_in": 15552000,
                                    "scope": T.SCOPES}).encode()
    port = free_port()
    client = T.TikTokClient(tmp_path, http=TT(), creds=CREDS)

    def browser(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        threading.Thread(target=lambda: (time.sleep(0.05), urllib.request.urlopen(
            f"{q['redirect_uri']}?code=c&state={q['state']}", timeout=5).read()),
            daemon=True).start()
    T.login(client, port=port, open_browser=browser, timeout=5)
    stages = [r["stage"] for r in ig.last_attempt("tiktok", tmp_path)]
    assert stages == ["authorize_url", "callback", "token_exchange", "stored"]
    assert ig.state("tiktok", tmp_path)["state"] == "AUTHENTICATED"


# ---------------------------------------------------------------- 13, 16, Jarvis, CLI

def test_13_the_jarvis_card_stops_before_the_browser_when_the_address_is_unregistered(
        tmp_path, monkeypatch):
    from bau import setup_steps as S
    monkeypatch.setattr(ig, "_get_no_follow", lambda url, timeout=15: (302, BAD_REDIRECT))
    real = ig.preflight
    monkeypatch.setattr(ig, "preflight", lambda p, home, **k: real(
        p, home, port=free_port(), get=ig._get_no_follow))
    out = S.connect_in_jarvis("fanvue", tmp_path, "human:owner")
    assert "Not opening Fanvue yet" in out["error"] and "Authentication tab" in out["error"]
    assert ig.last_attempt("fanvue", tmp_path)[0]["via"] == "jarvis"


def test_the_jarvis_card_proves_the_sign_in_with_a_real_api_call(tmp_path, monkeypatch):
    from bau import setup_steps as S
    port, http, real = free_port(), Token(), ig.preflight
    monkeypatch.setattr(ig, "preflight",
                        lambda p, home, **k: real(p, home, port=port, probe=False))

    class Client(F.FanvueClient):
        def __init__(self, home=None):
            super().__init__(home, http=http, creds=CREDS)
    monkeypatch.setattr(F, "FanvueClient", Client)
    out = S.connect_in_jarvis("fanvue", tmp_path, "human:owner")
    assert out["listener"] == f"http://127.0.0.1:{port}/"
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(out["open"]).query))
    urllib.request.urlopen(f"{q['redirect_uri']}?code=c&state={q['state']}", timeout=5).read()
    for _ in range(100):
        if ig.state("fanvue", tmp_path)["state"] == "API_VERIFIED":
            break
        time.sleep(0.05)
    assert ig.state("fanvue", tmp_path)["state"] == "API_VERIFIED"
    assert ig.known_good("fanvue", tmp_path)["via"] == "jarvis"


def test_the_page_checks_this_browser_can_reach_the_listener():
    from pathlib import Path
    html = (Path(__file__).parent.parent / "src/bau/ui/jarvis.html").read_text()
    assert 'r.result.listener + "bau-ping"' in html and "Are you on the laptop?" in html


def test_16_the_doctor_is_read_only_no_gateway_capability_is_bypassed():
    """The doctor posts nothing and holds no token; its only network call is a GET of the
    platform's public authorize page with the app's public client id."""
    import inspect
    src = inspect.getsource(ig)
    assert "access_token()" not in src and ".call(" not in src and "create_post" not in src


def test_cli_connect_doctor_and_report(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    monkeypatch.setattr(ig, "_get_no_follow", lambda url, timeout=15: (302, BAD_REDIRECT))
    monkeypatch.setitem(ig.REGISTRY["fanvue"], "port", free_port())
    rc = main(["connect", "doctor", "fanvue"])
    out = capsys.readouterr().out
    assert rc != 0 and "redirect_not_registered" in out and CREDS[1] not in out
    assert main(["connect", "status"]) == 0
    states = json.loads(capsys.readouterr().out)
    assert {s["provider"] for s in states} == {"fanvue", "tiktok"}
    assert main(["connect", "report", "fanvue"]) == 0
