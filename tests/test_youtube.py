"""YouTube Shorts (src/bau/youtube.py): the owner's channel signs in once, a clip goes up only
with the owner's privacy and made-for-kids answers. A fake Google: no network, no keys."""

import json
import time

import pytest

from bau import youtube as Y


class FakeGoogle:
    def __init__(self, put_codes=(201,)):
        self.calls, self.put_codes = [], list(put_codes)

    def request(self, method, url, headers, body=None, timeout=600):
        self.calls.append((method, url, headers, body))
        if url == Y.TOKEN_URL:
            form = dict(p.split("=", 1) for p in body.decode().split("&"))
            out = {"access_token": "at-" + form["grant_type"], "expires_in": 3599,
                   "scope": Y.SCOPE}
            if form["grant_type"] == "authorization_code":
                out["refresh_token"] = "rt-1"           # Google sends it on the first sign-in
            return 200, {}, json.dumps(out).encode()
        if method == "POST" and url == Y.UPLOAD_URL:
            return 200, {"location": "https://upload.example/session-1"}, b""
        if method == "PUT":
            if headers.get("Content-Range", "").startswith("bytes */"):
                return 308, {"range": "bytes=0-3"}, b""          # 4 bytes arrived
            code = self.put_codes.pop(0)
            return code, {}, (json.dumps({"id": "vid123"}).encode() if code == 201 else b"")
        raise AssertionError(url)


def client(tmp_path, http):
    return Y.YouTubeClient(tmp_path, http, creds=("cid", "secret"), sleep=lambda s: None)


def test_sign_in_saves_the_refresh_token_and_a_refresh_keeps_it(tmp_path):
    g = FakeGoogle()
    c = client(tmp_path, g)
    c.exchange("code-1", "http://127.0.0.1:3457", "verifier")
    tok = c.store.load()
    assert tok["refresh_token"] == "rt-1" and c.connected()
    tok["expires_at"] = time.time() - 1                         # the hour is up
    c.store.save(tok)
    assert c.access_token() == "at-refresh_token"
    assert c.store.load()["refresh_token"] == "rt-1"            # Google does not send a new one
    form = g.calls[-1][3].decode()
    assert "client_secret=secret" in form and "grant_type=refresh_token" in form


def test_the_authorize_link_asks_only_to_upload_and_for_offline_access(tmp_path):
    url = client(tmp_path, FakeGoogle()).authorize_url("http://127.0.0.1:3457", "s", "ch")
    assert url.startswith(Y.AUTH_URL) and "youtube.upload" in url
    assert "access_type=offline" in url and "code_challenge_method=S256" in url


def test_a_short_goes_up_with_the_owners_answers(tmp_path):
    g = FakeGoogle()
    c = client(tmp_path, g)
    c.exchange("code-1", "http://127.0.0.1:3457", "v")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"VIDEODATA")
    out = c.upload_short(clip, "Kai GTA 6 #ad", "Paid clip", ["GTA6"], "unlisted",
                         made_for_kids=False)
    assert out == {"id": "vid123", "url": "https://www.youtube.com/shorts/vid123",
                   "privacy": "unlisted"}
    start = next(x for x in g.calls if x[0] == "POST" and x[1] == Y.UPLOAD_URL)
    meta = json.loads(start[3])
    assert meta["status"] == {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False}
    assert start[2]["X-Upload-Content-Length"] == str(len(b"VIDEODATA"))
    with pytest.raises(Y.YouTubeError):
        c.upload_short(clip, "t", "d", [], "", made_for_kids=False)   # no default privacy


def test_an_interrupted_upload_resumes_where_youtube_says(tmp_path):
    g = FakeGoogle(put_codes=(503, 201))
    c = client(tmp_path, g)
    c.exchange("code-1", "http://127.0.0.1:3457", "v")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"VIDEODATA")
    assert c.upload_short(clip, "t", "d", [], "public", made_for_kids=False)["id"] == "vid123"
    last = [x for x in g.calls if x[0] == "PUT"][-1]
    assert last[2]["Content-Range"] == "bytes 4-8/9" and last[3] == b"ODATA"


def test_without_app_keys_it_says_how_to_add_them(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    with pytest.raises(Y.YouTubeError, match="sudo bau keys set YOUTUBE_CLIENT_ID"):
        Y.app_credentials(tmp_path / "no.env")
