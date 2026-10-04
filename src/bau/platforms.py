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
