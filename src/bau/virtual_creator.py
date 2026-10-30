"""Plan consistent social content for a fictional adult virtual creator.

This module creates human-reviewable prompts and copy. It does not generate media,
publish posts, or claim that a platform or jurisdiction's rules have been satisfied.

Two tiers: ``sfw`` works for every platform; ``explicit`` only for adult platforms with
age-verified audiences (``EXPLICIT_PLATFORMS``) and only when the owner has written the
profile's own ``explicit_boundaries``. Explicit batches are marked for the local content lane
model (docs/VIRTUAL-CREATOR.md); Jarvis's tool asks for ``sfw`` only. Profiles and batches
never live inside a workspace, where the kids channel is.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import yaml

PROFILE_SCHEMA = "bau.virtual-creator/v1"
MAX_BATCH = 30
ID = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
PLATFORMS = ("instagram", "tiktok", "youtube", "x", "fanvue", "patreon", "other")
# Platforms where the owner may plan explicit adult content. Mainstream platforms
# (Instagram, TikTok, YouTube, X, Patreon) only ever get the sfw tier.
EXPLICIT_PLATFORMS = ("fanvue",)
TIERS = ("sfw", "explicit")
SHOT_TYPES = ("portrait", "lifestyle", "behind-the-scenes", "story", "short-video")
MINOR_REFERENCE = re.compile(
    r"\b(?:child(?:ren)?|kid(?:s)?|teen(?:ager)?s?|minor(?:s)?|underage|schoolgirl|"
    r"schoolboy|high[- ]school|middle[- ]school|freshman|barely[- ]legal|jailbait|loli|"
    r"lolita|shota|young[- ]looking|little[- ]girl|little[- ]boy|petite[- ]teen|"
    r"student[- ]uniform|babysitter)\b|\b(?:1[0-9]|[0-9])\s*[- ]?"
    r"year[- ]old\b", re.IGNORECASE)


class CreatorError(ValueError):
    """The virtual creator profile or requested batch is invalid."""


class VirtualCreator:
    def __init__(self, profile_path: Path):
        self.profile_path = Path(profile_path)
        try:
            self.profile: dict[str, Any] = yaml.safe_load(
                self.profile_path.read_text(encoding="utf-8")) or {}
        except OSError as exc:
            raise CreatorError(f"cannot read profile {self.profile_path}: {exc}") from exc

    def problems(self) -> list[str]:
        p = self.profile
        if not isinstance(p, dict):
            return ["profile must be a YAML mapping"]
        problems = []
        if p.get("schema") != PROFILE_SCHEMA:
            problems.append(f"schema must be {PROFILE_SCHEMA}")
        if not ID.fullmatch(str(p.get("id", ""))):
            problems.append("id must be short, lowercase, and use letters, digits, or hyphens")
        for field in ("name", "bio", "niche", "voice", "style"):
            if not isinstance(p.get(field), str) or not p[field].strip():
                problems.append(f"{field} must be a non-empty string")
            elif MINOR_REFERENCE.search(p[field]):
                problems.append(f"{field} must not refer to minors or youth-coded roles")
        try:
            age = int(p.get("age", 0))
        except (TypeError, ValueError):
            age = 0
        if age < 21:
            problems.append("age must be explicitly set to 21 or older")
        if p.get("fictional") is not True:
            problems.append("fictional must be true; profiles cannot represent real people")
        if p.get("ai_disclosure") is not True:
            problems.append("ai_disclosure must be true for transparent virtual-creator content")
        appearance = p.get("appearance")
        if not isinstance(appearance, list) or len(appearance) < 4 or not all(
                isinstance(item, str) and item.strip() for item in appearance):
            problems.append("appearance needs at least four stable visual traits")
        elif any(MINOR_REFERENCE.search(item) for item in appearance):
            problems.append("appearance must not refer to minors or youth-coded roles")
        boundaries = p.get("boundaries")
        if not isinstance(boundaries, list) or not boundaries or not all(
                isinstance(item, str) and item.strip() for item in boundaries):
            problems.append("boundaries must list content and likeness limits")
        elif any(MINOR_REFERENCE.search(item) for item in boundaries):
            problems.append("boundaries must not describe content involving minors")
        if "explicit_boundaries" in p:
            explicit = p["explicit_boundaries"]
            if not isinstance(explicit, list) or not explicit or not all(
                    isinstance(item, str) and item.strip() for item in explicit):
                problems.append("explicit_boundaries must list the owner's explicit-tier limits")
            elif any(MINOR_REFERENCE.search(item) for item in explicit):
                problems.append("explicit_boundaries must not describe content involving minors")
        if "workspaces" in self.profile_path.resolve().parts:
            problems.append("keep creator profiles out of workspaces (the kids channel lives "
                            "there); use BAU_HOME/creators")
        platform_rules = p.get("platform_rules", {})
        if not isinstance(platform_rules, dict):
            problems.append("platform_rules must map platform names to owner-reviewed rules")
        else:
            for platform, rules in platform_rules.items():
                if platform not in PLATFORMS:
                    problems.append(f"unknown platform {platform!r}; use {', '.join(PLATFORMS)}")
                if not isinstance(rules, list) or not rules or not all(
                        isinstance(rule, str) and rule.strip() for rule in rules):
                    problems.append(f"platform_rules.{platform} needs at least one rule")
        return problems

    def _ready(self) -> None:
        issues = self.problems()
        if issues:
            raise CreatorError("profile needs attention: " + "; ".join(issues))

    def identity_lock(self) -> str:
        self._ready()
        p = self.profile
        traits = "; ".join(" ".join(x.split()) for x in p["appearance"])
        return (f"{p['name']} is a fictional {int(p['age'])}-year-old adult virtual creator. "
                f"Keep the same identity in every asset: {traits}. Signature style: {p['style']}. "
                "Do not imitate a real person or introduce age ambiguity.")

    def batch(self, theme: str, platform: str, count: int = 7,
              shot_types: list[str] | None = None, tier: str = "sfw") -> dict[str, Any]:
        self._ready()
        if platform not in PLATFORMS:
            raise CreatorError(f"unknown platform {platform!r}; use {', '.join(PLATFORMS)}")
        if tier not in TIERS:
            raise CreatorError(f"tier must be one of: {', '.join(TIERS)}")
        if tier == "explicit":
            if platform not in EXPLICIT_PLATFORMS:
                raise CreatorError(f"explicit content only goes to adult platforms "
                                   f"({', '.join(EXPLICIT_PLATFORMS)}); {platform} gets sfw")
            if not self.profile.get("explicit_boundaries"):
                raise CreatorError("write explicit_boundaries in the profile before planning "
                                   "explicit content")
        theme = " ".join(theme.split())
        if not theme:
            raise CreatorError("describe a campaign theme")
        if MINOR_REFERENCE.search(theme):
            raise CreatorError("adult creator themes cannot refer to minors or youth-coded roles")
        if not 1 <= count <= MAX_BATCH:
            raise CreatorError(f"count must be between 1 and {MAX_BATCH}")
        kinds = shot_types or list(SHOT_TYPES)
        if not kinds or any(k not in SHOT_TYPES for k in kinds):
            raise CreatorError(f"shot_types must use: {', '.join(SHOT_TYPES)}")

        p = self.profile
        rules = p.get("platform_rules", {}).get(platform, [])
        identity = self.identity_lock()
        limits = p["boundaries"] + (p["explicit_boundaries"] if tier == "explicit" else [])
        tier_line = ("Tier: explicit adult content for an age-verified adult platform. Draft "
                     "with the local content lane model only." if tier == "explicit" else
                     "Tier: sfw. Suitable for mainstream platforms; no nudity or sexual "
                     "activity.")
        posts = []
        for i in range(count):
            kind = kinds[i % len(kinds)]
            angle = ["introduce a detail", "share a point of view", "show a change of setting",
                     "tell a short behind-the-scenes moment", "invite a thoughtful reply"]
            posts.append({
                "number": i + 1,
                "format": kind,
                "visual_prompt": (
                    f"{identity}\nCampaign theme: {theme}.\nShot: {kind}. "
                    f"Creative angle: {angle[i % len(angle)]}.\n{tier_line}\n"
                    f"Wardrobe and pose must stay within these boundaries: "
                    f"{'; '.join(limits)}.\n"
                    "Use original, non-branded styling. Make this asset distinct from the other "
                    "posts in the batch while retaining the identity lock. Follow all owner-"
                    "reviewed platform rules listed below."
                ),
                "caption_draft": (
                    f"Write a {p['voice']} caption for {p['name']} about {theme}. "
                    "Keep the fictional adult persona's voice consistent and include a clear "
                    "AI-generated persona disclosure. Do not claim a real human experience."
                ),
                "review": ["confirm the generated asset matches the identity lock",
                           "check platform_rules and current platform policy",
                           "review caption and AI disclosure before posting"],
            })
        return {
            "profile": p["id"], "platform": platform, "theme": theme, "tier": tier,
            "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "identity_lock": identity, "platform_rules": rules,
            "posts": posts,
            "notice": "Draft prompts only. Verify current platform rules and review each item "
                      "before generation or publication.",
        }


def write_markdown(batch: dict[str, Any]) -> str:
    lines = [f"# {batch['profile']} content batch", "",
             f"Platform: {batch['platform']}  ", f"Tier: {batch['tier']}  ",
             f"Theme: {batch['theme']}", "",
             "> Draft prompts only. Review the current platform policy and every item "
             "before generation or publication.", "",
             "## Identity lock", "", batch["identity_lock"], ""]
    if batch["platform_rules"]:
        lines += ["## Owner-configured platform rules", ""]
        lines += [f"- {rule}" for rule in batch["platform_rules"]]
        lines.append("")
    for post in batch["posts"]:
        lines += [f"## Post {post['number']}: {post['format']}", "",
                  "### Visual prompt", "", post["visual_prompt"], "",
                  "### Caption brief", "", post["caption_draft"], "",
                  "### Review", ""]
        lines += [f"- [ ] {item}" for item in post["review"]]
        lines.append("")
    return "\n".join(lines)
