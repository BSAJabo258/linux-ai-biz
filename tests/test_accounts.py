"""Her social accounts (src/bau/accounts.py): Jarvis prepares, the owner signs up, passwords
stay in the secrets env file and nowhere else."""

import os
import shutil
import stat
from pathlib import Path

import pytest

from bau import accounts as AC

PROFILE = Path(__file__).resolve().parents[1] / "src/bau/data/virtual_creator_profile.example.yaml"


@pytest.fixture
def home(tmp_path):
    (tmp_path / "creators").mkdir()
    shutil.copy(PROFILE, tmp_path / "creators" / "aria.yaml")
    return tmp_path


def test_a_strong_password_every_time():
    pws = {AC.password() for _ in range(50)}
    assert len(pws) == 50
    for pw in pws:
        assert len(pw) == 24 and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw)


def test_prepare_keeps_the_password_in_the_env_file_only(home):
    rec = AC.prepare(home, "reddit", "human:owner", "aria@example.com",
                     "https://www.fanvue.com/aria/fv-1")
    env = AC.read_env(home)
    pw = env["REDDIT_PASSWORD"]
    assert pw and env["REDDIT_EMAIL"] == "aria@example.com"
    assert pw not in AC._records_path(home).read_text()             # never in the records
    assert stat.S_IMODE(os.stat(AC.env_path(home)).st_mode) == 0o660   # owner and bau only
    assert rec["status"] == "prepared" and rec["link"].endswith("/fv-1")
    again = AC.prepare(home, "reddit", "human:owner")
    assert AC.read_env(home)["REDDIT_PASSWORD"] == pw and again["email"] == "aria@example.com"


def test_each_platform_gets_the_link_fanvue_advises(home):
    link = "https://www.fanvue.com/aria/fv-3"
    assert AC.prepare(home, "x", "human:owner", fanvue_link=link)["link"] == link
    ig = AC.prepare(home, "instagram", "human:owner", fanvue_link=link)
    assert ig["link"].startswith("your link page") and not ig["adult_content_allowed"]
    assert AC.prepare(home, "tiktok", "human:owner")["link"] == "her Instagram profile"


@pytest.mark.parametrize("platform", list(AC.PLATFORMS))
def test_every_bio_says_ai_and_fits(home, platform):
    import yaml

    from bau.virtual_creator import MINOR_REFERENCE
    prof = yaml.safe_load((home / "creators" / "aria.yaml").read_text())
    text = AC.bio(platform, prof)
    assert "AI" in text and len(text) <= AC.PLATFORMS[platform]["bio_max"]
    assert not MINOR_REFERENCE.search(text) and "fanvue.com" not in text   # no bare link


def test_only_the_owner_prepares_and_records(home):
    with pytest.raises(PermissionError):
        AC.prepare(home, "x", "jarvis")
    with pytest.raises(AC.AccountError):
        AC.created(home, "x", "ariavale", "human:owner")              # not prepared
    AC.prepare(home, "x", "human:owner")
    with pytest.raises(AC.AccountError):
        AC.created(home, "x", "bad handle!", "human:owner")
    rec = AC.created(home, "x", "@ariavale", "human:owner")
    assert rec["status"] == "created" and AC.read_env(home)["X_USERNAME"] == "ariavale"


def test_handles_fit_each_platform():
    for platform, (cap, dots) in AC.HANDLE.items():
        hs = AC.handles("Aria Vale", platform)
        assert hs and all(len(h) <= cap for h in hs)
        assert dots or not any("." in h for h in hs)
