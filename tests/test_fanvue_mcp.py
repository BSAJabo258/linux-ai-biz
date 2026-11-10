"""Fanvue's official connection (src/bau/fanvue_mcp.py, the owner's choice 2026-11-10): BAU
registers itself, the owner signs in and presses Allow, tokens are kept private and renewed,
and Fanvue's MCP server answers in JSON or as an event stream. Fake Fanvue only."""

import json
import stat
import urllib.parse

import pytest

from bau import fanvue_mcp as M
from bau.fanvue import FanvueError


class FakeFanvue:
    def __init__(self, sse=False):
        self.calls, self.sse, self.n = [], sse, 0

    def __call__(self, url, body, headers):
        self.calls.append((url, body, headers))
        if url.endswith("/reg"):
            reg = json.loads(body)
            assert reg["token_endpoint_auth_method"] == "none"
            return 201, {}, json.dumps({"client_id": "bau-client"}).encode()
        if url.endswith("/oauth2/token"):
            f = dict(urllib.parse.parse_qsl(body.decode()))
            assert f["client_id"] == "bau-client" and f["resource"] == M.MCP_URL
            self.n += 1
            return 200, {}, json.dumps({"access_token": f"tok{self.n}",
                                        "refresh_token": f"ref{self.n}",
                                        "expires_in": 3600}).encode()
        msg = json.loads(body)
        assert headers["Authorization"].startswith("Bearer tok")
        if "id" not in msg:
            return 202, {}, b""
        result = {"initialize": {"protocolVersion": M.PROTOCOL_VERSION},
                  "tools/list": {"tools": [{"name": "custom__create-image-post"}]},
                  "tools/call": {"content": [{"type": "text", "text": "posted"}]}}[msg["method"]]
        out = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        if self.sse:
            return 200, {"content-type": "text/event-stream", "mcp-session-id": "s1"}, \
                f"event: message\ndata: {json.dumps(out)}\n\n".encode()
        return 200, {"content-type": "application/json", "mcp-session-id": "s1"}, \
            json.dumps(out).encode()


def connected(tmp_path, fake):
    opened = []

    def allow(url, state, port, timeout):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(opened[0]).query))
        assert q["code_challenge_method"] == "S256" and q["resource"] == M.MCP_URL
        assert q["redirect_uri"] == "http://127.0.0.1:3457/callback"
        return {"code": "c0de", "state": q["state"]}
    return M.connect(tmp_path, open_browser=opened.append, post=fake, wait=allow)


def test_sign_in_registers_bau_once_and_keeps_the_tokens_private(tmp_path):
    fake = FakeFanvue()
    st = connected(tmp_path, fake)
    assert st["client_id"] == "bau-client" and st["access_token"] == "tok1"
    p = M.Store(tmp_path).path
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    connected(tmp_path, fake)                                  # again: no second registration
    assert sum(u.endswith("/reg") for u, _, _ in fake.calls) == 1


def test_a_wrong_state_or_a_refusal_stops_the_sign_in(tmp_path):
    with pytest.raises(FanvueError, match="state"):
        M.connect(tmp_path, open_browser=lambda u: None, post=FakeFanvue(),
                  wait=lambda *a: {"code": "x", "state": "forged"})
    with pytest.raises(FanvueError, match="access_denied"):
        M.connect(tmp_path, open_browser=lambda u: None, post=FakeFanvue(),
                  wait=lambda u, s, p, t: {"error": "access_denied", "state": s})


def test_an_old_token_is_renewed_and_the_new_refresh_token_kept(tmp_path):
    fake = FakeFanvue()
    connected(tmp_path, fake)
    st = M.Store(tmp_path).load()
    M.Store(tmp_path).save({**st, "expires_at": 0})
    assert M.access_token(tmp_path, fake) == "tok2"
    assert M.Store(tmp_path).load()["refresh_token"] == "ref2"


@pytest.mark.parametrize("sse", [False, True])
def test_the_server_answers_in_json_or_as_an_event_stream(tmp_path, sse):
    fake = FakeFanvue(sse)
    connected(tmp_path, fake)
    c = M.FanvueMcp(tmp_path, fake)
    c.initialize()
    assert [t["name"] for t in c.list_tools()] == ["custom__create-image-post"]
    assert c.call("custom__create-image-post", {})["text"] == "posted"
    assert fake.calls[-1][2]["Mcp-Session-Id"] == "s1"


def test_not_connected_says_how(tmp_path):
    with pytest.raises(FanvueError, match="bau fanvue connect"):
        M.FanvueMcp(tmp_path).list_tools()


def test_the_listener_ignores_a_stray_request_and_waits_for_fanvues_reply():
    import threading
    import urllib.request
    port = 34571
    out = {}
    t = threading.Thread(target=lambda: out.update(M._wait("", "s", port, 20)))
    t.start()
    for path in ("/favicon.ico", "/callback?code=c0de&state=s"):
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2).read()
                break
            except OSError:
                import time
                time.sleep(0.05)
    t.join(10)
    assert out == {"code": "c0de", "state": "s"}
