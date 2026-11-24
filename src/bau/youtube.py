"""YouTube Shorts: the owner's channel signs in once; a clip goes up only on the owner's Accept
(the clips card, src/bau/clips.py), with the privacy the owner picks on that card (no default).
See docs/CLIPS.md.

Facts read 2026-11-24 on Google's own pages:
  OAuth for desktop apps (developers.google.com/identity/protocols/oauth2/native-app, updated
    2026-11-19): authorize https://accounts.google.com/o/oauth2/v2/auth; token
    https://oauth2.googleapis.com/token with client_id, client_secret, code, code_verifier,
    grant_type, redirect_uri; a loopback redirect such as http://127.0.0.1:9004; the redirect
    "must exactly match one of the authorized redirect URIs for the OAuth 2.0 client".
  Refresh tokens (developers.google.com/identity/protocols/oauth2, updated 2026-11-19): a
    project whose consent screen is "External" and "Testing" gets refresh tokens that expire
    in 7 days; a token unused for six months, or revoked, stops working.
  videos.insert (updated 2026-11-23): scope https://www.googleapis.com/auth/youtube.upload;
    1 unit of the Video Uploads quota; "Videos uploaded from unverified API projects aren't
    restricted to private viewing mode".
  Resumable upload (updated 2026-11-12): POST
    https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status
    with Authorization, Content-Type application/json; charset=UTF-8, X-Upload-Content-Length,
    X-Upload-Content-Type and a video resource; 200 with a Location header = the session URI;
    PUT the bytes there; 201 Created returns the video resource.
  Shorts (support.google.com/youtube/answer/15424877): a square or vertical video up to three
    minutes is a Short.
  The video resource (updated 2026-11-23) has status.selfDeclaredMadeForKids and
    paidProductPlacementDetails.hasPaidProductPlacement; the page did not say the latter can be
    set on insert, so a paid clip's disclosure is written in its title and description instead
    (clips.py, the FTC's endorsement guides: us-ftc-endorsement-guides).
"""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .credentials import CredentialError, Store
from .fanvue import pkce_pair  # S256, base64url without padding
from .tiktok import _env_file, oauth_callback

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = ("https://www.googleapis.com/upload/youtube/v3/videos"
              "?uploadType=resumable&part=snippet,status")
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
PORT = 3457
PRIVACY = {"public": "Public", "unlisted": "Unlisted (only people with the link)",
           "private": "Private (only you)"}
GAMING = "20"                                      # YouTube's "Gaming" video category
SHORT_MAX_SECONDS = 180


class YouTubeError(RuntimeError):
    pass


class Http:
    """Request with the answer's headers: the upload's session address comes in Location."""

    def request(self, method: str, url: str, headers: dict[str, str], body: bytes | None = None,
                timeout: int = 600) -> tuple[int, dict[str, str], bytes]:
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def app_credentials(env_file: Path = Path("/etc/bau/platforms.env")) -> tuple[str, str]:
    env = {**_env_file(env_file), **os.environ}
    cid, secret = env.get("YOUTUBE_CLIENT_ID"), env.get("YOUTUBE_CLIENT_SECRET")
    if not cid or not secret:
        raise YouTubeError("YouTube's app keys are not on this computer: make a Desktop app "
                           "client in Google Cloud (docs/CLIPS.md), then "
                           "sudo bau keys set YOUTUBE_CLIENT_ID YOUTUBE_CLIENT_SECRET")
    return cid, secret


class YouTubeClient:
    def __init__(self, home: Path | None = None, http: Http | None = None,
                 creds: tuple[str, str] | None = None, sleep: Any = time.sleep):
        self.store = Store("youtube", home)
        self.http = http or Http()
        self._creds = creds
        self.sleep = sleep

    @property
    def creds(self) -> tuple[str, str]:
        if self._creds is None:
            self._creds = app_credentials()
        return self._creds

    def connected(self) -> bool:
        return self.store.state() == "present"

    # -------------------------------------------------------- sign-in
    def authorize_url(self, redirect: str, state: str, challenge: str) -> str:
        return AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.creds[0], "redirect_uri": redirect, "response_type": "code",
            "scope": SCOPE, "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent"})

    def _token(self, form: dict[str, str], keep_refresh: str = "") -> dict[str, Any]:
        cid, secret = self.creds
        code, _, raw = self.http.request(
            "POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"},
            urllib.parse.urlencode({"client_id": cid, "client_secret": secret, **form}).encode())
        data = json.loads(raw or b"{}")
        if code != 200 or "access_token" not in data:
            raise YouTubeError("Google refused the sign-in: "
                               f"{data.get('error_description') or data.get('error') or code}")
        refresh = data.get("refresh_token") or keep_refresh   # a refresh keeps the old one
        if not refresh:
            raise YouTubeError("Google gave no refresh token: sign in again (bau youtube login)")
        self.store.save({"access_token": data["access_token"], "refresh_token": refresh,
                         "scope": data.get("scope", SCOPE),
                         "expires_at": time.time() + int(data.get("expires_in", 0)) - 60})
        return data

    def exchange(self, code: str, redirect: str, verifier: str) -> dict[str, Any]:
        return self._token({"code": code, "code_verifier": verifier,
                            "grant_type": "authorization_code", "redirect_uri": redirect})

    def access_token(self) -> str:
        try:
            tok = self.store.load()
        except CredentialError as e:
            raise YouTubeError(str(e)) from None
        if tok is None:
            raise YouTubeError("YouTube is not connected: run bau youtube login")
        if time.time() < tok["expires_at"]:
            return tok["access_token"]
        with self.store.refresh_lock():
            tok = self.store.load() or tok
            if time.time() < tok["expires_at"]:
                return tok["access_token"]
            return self._token({"grant_type": "refresh_token",
                                "refresh_token": tok["refresh_token"]},
                               keep_refresh=tok["refresh_token"])["access_token"]

    # -------------------------------------------------------- upload
    def upload_short(self, video: Path, title: str, description: str, tags: list[str],
                     privacy: str, made_for_kids: bool) -> dict[str, Any]:
        """Resumable upload, one PUT; a 5xx is retried twice from where YouTube says it is.
        Privacy and the made-for-kids answer are the owner's, from the card (no defaults)."""
        if privacy not in PRIVACY:
            raise YouTubeError("the owner picks public, unlisted or private")
        body = video.read_bytes()
        meta = {"snippet": {"title": title[:100], "description": description[:5000],
                            "tags": tags[:30], "categoryId": GAMING},
                "status": {"privacyStatus": privacy,
                           "selfDeclaredMadeForKids": bool(made_for_kids)}}
        code, head, raw = self.http.request("POST", UPLOAD_URL, {
            "Authorization": f"Bearer {self.access_token()}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(len(body)), "X-Upload-Content-Type": "video/mp4"},
            json.dumps(meta).encode())
        session = head.get("location")
        if code != 200 or not session:
            raise YouTubeError(f"YouTube did not start the upload (HTTP {code}): "
                               f"{raw[:300].decode(errors='replace')}")
        sent = 0
        for attempt in range(3):
            headers = {"Authorization": f"Bearer {self.access_token()}",
                       "Content-Type": "video/mp4"}
            if sent:
                headers["Content-Range"] = f"bytes {sent}-{len(body) - 1}/{len(body)}"
            code, head, raw = self.http.request("PUT", session, headers, body[sent:])
            if code in (200, 201):
                vid = json.loads(raw or b"{}").get("id")
                if not vid:
                    break
                return {"id": vid, "url": f"https://www.youtube.com/shorts/{vid}",
                        "privacy": privacy}
            if code < 500 or attempt == 2:
                break
            self.sleep(2 * (attempt + 1))
            code, head, _ = self.http.request("PUT", session, {           # where is it now?
                "Authorization": f"Bearer {self.access_token()}",
                "Content-Range": f"bytes */{len(body)}"}, b"")
            rng = head.get("range", "")
            sent = int(rng.rsplit("-", 1)[1]) + 1 if rng else 0
        raise YouTubeError(f"YouTube did not take the video (HTTP {code}): "
                           f"{raw[:300].decode(errors='replace')}")


def login(client: YouTubeClient, port: int = PORT, open_browser: Any = None,
          timeout: int = 300) -> dict[str, Any]:
    """The owner's browser signs in to Google and comes back to 127.0.0.1:<port>."""
    redirect = f"http://127.0.0.1:{port}"
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)

    def finish(got: dict[str, str]) -> dict[str, Any]:
        if not secrets.compare_digest(got.get("state", ""), state):
            raise YouTubeError("state mismatch - sign-in stopped")
        if "code" not in got:
            raise YouTubeError(f"Google said no: {got.get('error', 'no code')}")
        return client.exchange(got["code"], redirect, verifier)
    return oauth_callback("YouTube", port, "/", client.authorize_url(redirect, state, challenge),
                          open_browser or (lambda u: print(f"Open this link to connect YouTube:"
                                                           f"\n{u}")), timeout, finish)
