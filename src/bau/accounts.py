"""The creator's social accounts, prepared by Jarvis (the owner, 2026-11-20: "Jarvis to be able
to ... make sure that accounts are set up ... automate the creation and setup"). See
docs/ACCOUNTS.md.

Jarvis prepares everything an account needs: name, handle choices, a bio with the AI label,
the right link for that platform, a safe-for-work profile picture and a strong password,
saved in the secrets env file the system reads. The owner does the human step on the
platform's own sign-up page (email or phone code, CAPTCHA): platforms forbid accounts made
by software, and a banned account would cut the traffic the business lives on.

Where each platform's link goes, from Fanvue's own guides (read 2026-11-20):
  help.fanvue.com/en/articles/9526985-promoting-your-fanvue-page: "Twitter and Reddit allow
    adult content; Instagram, TikTok, and YouTube don't." "On the platforms that don't allow
    direct adult-content links, use a Link Tree-style tool".
  help.fanvue.com/en/articles/16238089-getting-fans-to-your-fanvue-socials-link-in-bio: "Put
    your Fanvue link in your bio on every platform you post to." "Never post a bare Fanvue
    link directly in a caption or comment ... or you risk getting your social account
    suspended."
  help.fanvue.com/en/articles/7860771-growing-on-tiktok: "Route followers through Instagram to
    Fanvue, since TikTok doesn't allow direct adult-content links."
  TikTok (tiktok.com/community-guidelines, read 2026-11-20): "We require clear labeling when
    AI or editing is used to realistically depict people or scenes."
The platforms' own rule pages for Reddit and X refused to load on 2026-11-20 (403/402/refused);
check them before posting there.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import secrets
import string
from pathlib import Path
from typing import Any

import yaml

from .home import bau_home

AI_TAG = "AI-generated creator (fictional)"
PLATFORMS: dict[str, dict[str, Any]] = {
    "reddit": {"name": "Reddit", "signup": "https://www.reddit.com/register/",
               "tracking": "Reddit", "bio_max": 200, "link": "fanvue",
               "adult_ok": True},
    "x": {"name": "X", "signup": "https://x.com/i/flow/signup", "tracking": "X",
          "bio_max": 160, "link": "fanvue", "adult_ok": True},
    "instagram": {"name": "Instagram", "signup": "https://www.instagram.com/accounts/emailsignup/",
                  "tracking": "Instagram", "bio_max": 150, "link": "link page",
                  "adult_ok": False},
    "tiktok": {"name": "TikTok", "signup": "https://www.tiktok.com/signup",
               "tracking": "TikTok", "bio_max": 80, "link": "instagram", "adult_ok": False},
}
ENV_FILE = "accounts.env"
FILE_MODE, DIR_MODE = 0o660, 0o2770


class AccountError(ValueError):
    pass


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _records_path(home: Path) -> Path:
    return home / "accounts" / "accounts.yaml"


def records(home: Path | None = None) -> dict[str, Any]:
    p = _records_path(home or bau_home())
    return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}


def _save_records(home: Path, data: dict[str, Any]) -> None:
    p = _records_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=True))


# ---------------------------------------------------------------- the secrets env file
def env_path(home: Path | None = None) -> Path:
    return (home or bau_home()) / "secrets" / ENV_FILE


def read_env(home: Path | None = None) -> dict[str, str]:
    p = env_path(home)
    out: dict[str, str] = {}
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip("'\"")
    return out


def _write_env(home: Path, values: dict[str, str]) -> None:
    p = env_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p.parent, DIR_MODE)
    except OSError:
        pass
    lines = ["# BAU: the creator's social accounts (bau accounts). Never shown on screen or in "
             "logs; never in the repo."]
    lines += [f"{k}='{v}'" for k, v in sorted(values.items())]
    tmp = p.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.chmod(tmp, FILE_MODE)
    tmp.replace(p)


def _key(platform: str, what: str) -> str:
    return f"{platform.upper()}_{what.upper()}"


def password() -> str:
    """24 characters: letters, digits and symbols, from the system's secure random source."""
    pool = string.ascii_letters + string.digits + "!#%+-=?@_"
    while True:
        pw = "".join(secrets.choice(pool) for _ in range(24))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!#%+-=?@_" for c in pw)):
            return pw


# ---------------------------------------------------------------- preparing an account
# Handle limits as the sign-up pages enforce them (length, and dots only where allowed); the
# page itself still says when one is taken or refused.
HANDLE = {"reddit": (20, False), "x": (15, False), "instagram": (30, True),
          "tiktok": (24, True)}


def handles(name: str, platform: str = "instagram") -> list[str]:
    base = re.sub(r"[^a-z0-9]+", "", name.lower()) or "aria"
    first = re.sub(r"[^a-z0-9]+", "", name.lower().split()[0]) if name.split() else base
    rest = base[len(first):] or "ai"
    cap, dots = HANDLE[platform]
    ideas = [f"{base}ai", f"{first}.{rest}.ai" if dots else f"{first}_{rest}_ai",
             f"{base}_official", f"its{base}", f"{base}_ai"]
    return [h for h in dict.fromkeys(ideas) if len(h) <= cap][:4]


def bio(platform: str, prof: dict[str, Any]) -> str:
    name = prof.get("name", "Aria")
    tail = {"reddit": "18+ only. My private page is in my profile link 💋",
            "x": "18+ only. Exclusive sets at the link 👇",
            "instagram": "Link in bio for more ✨",
            "tiktok": "More on my Instagram ✨"}[platform]
    text = f"{name} · {AI_TAG} · {tail}"
    cap = PLATFORMS[platform]["bio_max"]
    if len(text) > cap:
        text = f"{name} · AI creator (fictional) · {tail}"
    return text[:cap]


def _profile_picture(home: Path) -> str | None:
    """A level 0 (safe-for-work) picture with a passed age check, for the profile."""
    from .fanvue import Queue
    q = Queue(home)
    for item in reversed(q.items()):
        if item["level"] == 0 and not q.check(item["picture"], "", 0):
            return str(q.picture(item))
    return None


def prepare(home: Path | None, platform: str, by: str, email: str = "",
            fanvue_link: str = "") -> dict[str, Any]:
    """Everything for one account, ready to paste. Keeps an existing password."""
    if not by.startswith("human:"):
        raise PermissionError("only the owner prepares an account")
    if platform not in PLATFORMS:
        raise AccountError(f"no such platform {platform!r}; known: {', '.join(PLATFORMS)}")
    home = home or bau_home()
    from .creator_feed import _profile
    found = _profile(home)
    if found is None:
        raise AccountError("no creator profile: bau creator init")
    prof = found[1]
    env = read_env(home)
    if _key(platform, "password") not in env:
        env[_key(platform, "password")] = password()
    if email:
        env[_key(platform, "email")] = email
    _write_env(home, env)
    data = records(home)
    rec = data.get(platform, {})
    p = PLATFORMS[platform]
    link = {"fanvue": fanvue_link or "your Fanvue tracking link (bau fanvue links)",
            "link page": "your link page (it links to " + (fanvue_link or "Fanvue") + ")",
            "instagram": "her Instagram profile"}[p["link"]]
    rec.update({"platform": p["name"], "status": rec.get("status", "prepared"),
                "display_name": prof.get("name", "Aria"),
                "handles": handles(prof.get("name", "Aria"), platform),
                "bio": bio(platform, prof), "link": link, "signup": p["signup"],
                "profile_picture": _profile_picture(home), "email": email or rec.get("email",
                                                                                  ""),
                "adult_content_allowed": p["adult_ok"], "prepared_at": _now()})
    data[platform] = rec
    _save_records(home, data)
    return rec


def created(home: Path | None, platform: str, handle: str, by: str) -> dict[str, Any]:
    """The owner made the account on the platform's page."""
    if not by.startswith("human:"):
        raise PermissionError("only the owner records an account")
    home = home or bau_home()
    data = records(home)
    if platform not in data:
        raise AccountError(f"prepare it first: bau accounts prepare {platform}")
    handle = handle.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9._]{2,40}", handle):
        raise AccountError("give the handle as it shows on the platform, e.g. ariavale")
    data[platform].update(status="created", handle=handle, created_at=_now())
    _save_records(home, data)
    env = read_env(home)
    env[_key(platform, "username")] = handle
    _write_env(home, env)
    return data[platform]
