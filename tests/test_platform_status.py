"""`bau platform status` (the owner's checklist, 2026-11-18): one table of every platform, read
live. "Do not claim a platform is connected merely because its API credentials exist", and
LIVE-VERIFIED only when the platform itself answered."""

import json

from bau import fanvue as F
from bau import platforms as P
from bau import tiktok as T


def rows(home, **kw):
    return {r["platform"]: r for r in P.connections(home, **kw)}


def keys(monkeypatch):
    for k, v in {"FANVUE_CLIENT_ID": "cid", "FANVUE_CLIENT_SECRET": "cs",
                 "TIKTOK_CLIENT_KEY": "tk", "TIKTOK_CLIENT_SECRET": "ts"}.items():
        monkeypatch.setenv(k, v)


def test_app_keys_alone_are_not_a_connection(tmp_path, monkeypatch):
    keys(monkeypatch)
    r = rows(tmp_path)
    assert r["fanvue"]["app_keys"] == "on this computer"
    assert r["fanvue"]["status"] == "OWNER-ACTION-REQUIRED" and r["fanvue"]["fix"] == \
        "bau fanvue login"
    assert r["tiktok"]["status"] == "OWNER-ACTION-REQUIRED" and r["tiktok"]["fix"] == \
        "bau tiktok login"
    assert all(r[p]["status"] == "NOT IMPLEMENTED" for p in P.PLANNED)


def test_signed_in_is_connected_and_only_a_real_answer_is_live_verified(tmp_path, monkeypatch):
    keys(monkeypatch)
    F.TokenStore(tmp_path).save({"access_token": "a", "refresh_token": "r", "expires_in": 3600})
    assert rows(tmp_path)["fanvue"]["status"] == "CONNECTED"          # not asked this time
    monkeypatch.setattr(F.FanvueClient, "me", lambda self: {"handle": "aria"})
    r = rows(tmp_path, check=True)["fanvue"]
    assert r["status"] == "LIVE-VERIFIED" and r["account"] == "aria"


def test_a_platform_that_refuses_the_check_is_blocked_with_its_reason(tmp_path, monkeypatch):
    keys(monkeypatch)
    T.TokenStore(tmp_path).save({"access_token": "a", "refresh_token": "r",
                                 "expires_in": 3600, "refresh_expires_in": 9999})

    def refused(self):
        raise T.TikTokError("access_token_invalid")
    monkeypatch.setattr(T.TikTokClient, "creator_info", refused)
    r = rows(tmp_path, check=True)["tiktok"]
    assert r["status"] == "BLOCKED" and "access_token_invalid" in r["error"]


def test_an_unreadable_sign_in_is_blocked_not_missing(tmp_path, monkeypatch):
    keys(monkeypatch)
    F.TokenStore(tmp_path).save({"access_token": "a", "refresh_token": "r", "expires_in": 3600})

    def denied(self, *a, **k):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(type(tmp_path), "read_text", denied)
    r = rows(tmp_path)["fanvue"]
    assert r["status"] == "BLOCKED" and r["fix"].startswith("sudo chgrp -R bau")


def test_the_command_shows_no_secret(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    keys(monkeypatch)
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    F.TokenStore(tmp_path).save({"access_token": "SECRET-AT", "refresh_token": "SECRET-RT",
                                 "expires_in": 3600})
    assert main(["platform", "status"]) == 0
    out = capsys.readouterr().out
    assert "SECRET" not in out and "cs" not in json.dumps(
        [r.get("app_keys") for r in json.loads(out)])
