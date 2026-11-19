"""Publishing platforms: policy registry and connectors (spec §80).

A platform's AI, copyright, music, advertising and automation policies are
recorded with the date they were last verified. Publishing to a platform whose
policy record is missing or stale is blocked. Connectors are adapters; the
always-available one exports a ready-to-upload package for a human to post.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

from .home import bau_home
from .store import YamlStore

FIELDS = ["platform", "policy_version", "ai_content_policy", "copyright_policy",
          "music_policy", "advertising_policy", "commercial_content_policy", "api_policy",
          "automation_policy", "account_limits", "appeal_process", "requires_ai_label",
          "source_url", "last_verified"]


class PlatformRegistry:
    def __init__(self, home: Path | None = None, max_age_days: int = 90):
        self.store = YamlStore((home or bau_home()) / "compliance" / "platforms.yaml",
                               {"platforms": {}})
        self.max_age = max_age_days

    def upsert(self, rec: dict[str, Any]) -> dict[str, Any]:
        missing = [f for f in FIELDS if f not in rec]
        if missing:
            raise ValueError(f"missing {missing}")
        data = self.store.load()
        data["platforms"][rec["platform"]] = rec
        self.store.save(data)
        return rec

    def facts(self, platform: str, on: dt.date | None = None) -> dict[str, Any]:
        on = on or dt.date.today()
        rec = self.store.load()["platforms"].get(platform)
        if rec is None:
            return {"platform_policy_current": False, "platform_requires_ai_label": None,
                    "reason": "no policy record"}
        age = (on - dt.date.fromisoformat(str(rec["last_verified"]))).days
        return {"platform_policy_current": age <= self.max_age,
                "platform_requires_ai_label": bool(rec["requires_ai_label"]),
                "policy_age_days": age}


class FileDropConnector:
    """Writes the artifact, its provenance and its metadata into an export folder for a
    human to upload. No credentials, nothing posted automatically."""

    name = "file_drop"

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir

    def publish(self, artifact: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        dest = self.out_dir / f"{stamp}-{artifact.stem}"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact, dest / artifact.name)
        prov = artifact.with_suffix(artifact.suffix + ".provenance.json")
        if prov.exists():
            shutil.copy2(prov, dest / prov.name)
        (dest / "metadata.json").write_text(json.dumps(metadata, indent=2))
        checklist = ["Set the platform's AI / altered-content label if required",
                     "Paste the disclosure text exactly as in metadata.json",
                     "Confirm captions are attached", "Confirm music licence covers this platform"]
        (dest / "UPLOAD_CHECKLIST.txt").write_text("\n".join(f"[ ] {c}" for c in checklist))
        return {"status": "EXPORTED_FOR_MANUAL_UPLOAD", "path": str(dest)}


class APIConnector:
    """Base for platform API connectors (YouTube, marketplaces...). Needs OAuth credentials
    configured outside source code; until then it refuses rather than pretending."""

    def __init__(self, name: str, credentials_env: str):
        self.name = name
        self.credentials_env = credentials_env

    def publish(self, artifact: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        import os
        if not os.environ.get(self.credentials_env):
            raise RuntimeError(f"{self.name} connector not configured "
                               f"(set {self.credentials_env} via the secret store)")
        raise NotImplementedError(f"{self.name} API upload must be implemented against the "
                                  "platform's current API terms before use")


# ------------------------------------------------------------------ connections
# The one table of what BAU is connected to (the owner's checklist, 2026-11-18: "Do not claim a
# platform is connected merely because its API credentials exist"). Each row is read live from
# the shared credential store (credentials.py) and the policy record above; a platform is
# LIVE-VERIFIED only after a real call to it answered in this run (``check``).

# What BAU's own code can do on each platform, from the facts in each module's docstring.
CAPABILITIES = {
    "fanvue": ["sign-in", "upload pictures", "post (your Accept, or autopost)", "earnings"],
    "tiktok": ["sign-in", "upload video", "post (your Accept)", "video stats",
               "private posts only until TikTok audits the app"],
}
# Planned, not built: listed so nobody mistakes them for connected.
PLANNED = ("youtube", "instagram", "facebook", "x", "threads")


def _fanvue_row(home: Path, check: bool) -> dict[str, Any]:
    from . import fanvue
    st = fanvue.status(home, check=check)
    row = {"app_keys": st["app_keys"], "sign_in": st["sign_in"]}
    if st.get("account"):
        row["account"] = st["account"]
    if st.get("check_failed"):
        row["error"] = st["check_failed"]
    try:
        seen = json.loads((home / "economics" / "fanvue_seen.json").read_text())
        row["last_sync"] = seen.get("synced_at")
    except (OSError, ValueError):
        row["last_sync"] = None
    return row | {"fix": st.get("fix")}


def _tiktok_row(home: Path, check: bool) -> dict[str, Any]:
    from . import tiktok
    try:
        tiktok.app_credentials()
        keys = "on this computer"
    except tiktok.TikTokError:
        keys = "missing"
    store = tiktok.TokenStore(home).store
    row: dict[str, Any] = {"app_keys": keys, "sign_in": store.state()}
    if check and row["sign_in"] == "present":
        try:
            info = tiktok.TikTokClient(home).creator_info()
            row["account"] = (info.get("data") or info).get("creator_username")
        except (tiktok.TikTokError, OSError) as e:
            row["error"] = str(e)[:300]
    row["fix"] = (None if row["sign_in"] == "present" else
                  "sudo bau keys set TIKTOK_CLIENT_KEY TIKTOK_CLIENT_SECRET, then bau tiktok login"
                  if keys == "missing" else "bau tiktok login")
    return row


def connections(home: Path | None = None, check: bool = False) -> list[dict[str, Any]]:
    """Every platform, its true connection state, what BAU can do there, and what the owner
    still has to do. Nothing secret in it."""
    home = home or bau_home()
    rows = []
    for name, read in (("fanvue", _fanvue_row), ("tiktok", _tiktok_row)):
        row = {"platform": name, **read(home, check)}
        policy = PlatformRegistry(home).facts(name)
        row["policy_record"] = ("current" if policy["platform_policy_current"] else
                                policy.get("reason") or "older than 90 days")
        if row["sign_in"] == "unreadable":
            row["status"] = "BLOCKED"
        elif row["sign_in"] != "present":
            row["status"] = "OWNER-ACTION-REQUIRED"
        elif row.get("account"):
            row["status"] = "LIVE-VERIFIED"           # the platform answered, just now
        elif row.get("error"):
            row["status"] = "BLOCKED"
        else:
            row["status"] = "CONNECTED"               # signed in; not asked this time
        row["capabilities"] = CAPABILITIES[name]
        rows.append(row)
    rows += [{"platform": p, "status": "NOT IMPLEMENTED", "capabilities": [],
              "fix": "planned: no adapter yet"} for p in PLANNED]
    return rows
