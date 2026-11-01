"""A week of posts, approved by the owner once and posted on schedule by Ayrshare (the owner's
choice, 2026-11-01: batch approval instead of a click per post). The owner sees every post
on one card, picks TikTok's visibility (no default), and one confirm schedules them all.
Any change after the card voids it. Instagram and TikTok get sfw only, every post carries
the AI label and a disclosure, nothing refers to minors. Written before the code."""

import datetime as dt

import pytest
import yaml
from test_assistant import events, make

from bau import week

SOON = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)


class FakeAyrshare:
    def __init__(self):
        self.uploads, self.posts = [], []

    def upload(self, path):
        self.uploads.append(path.name)
        return f"https://images.example/{path.name}"

    def post(self, body):
        self.posts.append(body)
        return {"status": "scheduled", "id": f"ayr{len(self.posts)}"}


def plan(home, posts=None, name="nov-week-1"):
    media = home / "artifacts" / "media"
    media.mkdir(parents=True, exist_ok=True)
    (media / "mon.jpg").write_bytes(b"\xff\xd8\xff fake jpeg")
    (media / "tue.mp4").write_bytes(b"\x00\x00\x00 fake mp4")
    posts = posts if posts is not None else [
        {"when": SOON.isoformat(), "platform": "instagram", "tier": "sfw",
         "caption": "Cozy latte by the window. #AI virtual creator", "media": "mon.jpg"},
        {"when": (SOON + dt.timedelta(days=1)).isoformat(), "platform": "tiktok",
         "tier": "sfw", "caption": "Autumn walk, AI-generated.", "media": "tue.mp4"},
    ]
    (home / "weeks").mkdir(parents=True, exist_ok=True)
    (home / "weeks" / f"{name}.yaml").write_text(yaml.safe_dump({"posts": posts}))
    return name


def test_a_good_week_has_no_problems(tmp_path):
    assert week.problems(tmp_path, plan(tmp_path)) == []


@pytest.mark.parametrize("change,why", [
    ({"tier": "explicit"}, "sfw only"),
    ({"platform": "fanvue"}, "Fanvue"),
    ({"caption": "Day out with a 15-year-old fan. #AI"}, "minors"),
    ({"caption": "Cozy latte by the window."}, "disclosure"),
    ({"when": "2020-01-01T10:00:00Z"}, "past"),
    ({"when": "2026-12-01T10:00:00"}, "time zone"),
    ({"media": "../../etc/passwd"}, "media"),
    ({"media": "missing.jpg"}, "media"),
])
def test_bad_posts_are_refused_with_the_reason(tmp_path, change, why):
    name = plan(tmp_path)
    p = yaml.safe_load((tmp_path / "weeks" / f"{name}.yaml").read_text())
    p["posts"][0].update(change)
    (tmp_path / "weeks" / f"{name}.yaml").write_text(yaml.safe_dump(p))
    found = week.problems(tmp_path, name)
    assert found and any(why.lower() in x.lower() for x in found), found


def test_one_card_shows_every_post_and_asks_tiktok_visibility(tmp_path):
    card = week.stage(tmp_path, plan(tmp_path))
    assert "2 posts" in card["summary"]
    assert "instagram" in card["summary"] and "tiktok" in card["summary"]
    assert "Cozy latte" in card["summary"]                  # the owner sees each post
    field = card["form"]["fields"][0]
    assert field["name"] == "tiktok_visibility" and "default" not in field
    assert {o[0] for o in field["options"]} == {"public", "private", "followers", "friends"}


def test_send_schedules_every_post_with_the_ai_label(tmp_path):
    name = plan(tmp_path)
    week.stage(tmp_path, name)
    api = FakeAyrshare()
    out = week.send(tmp_path, name, "public", api, by="human:owner")
    assert out["scheduled"] == 2 and api.uploads == ["mon.jpg", "tue.mp4"]
    ig, tt = api.posts
    assert ig["platforms"] == ["instagram"] and ig["instagramOptions"]["isAIGenerated"] is True
    assert tt["tikTokOptions"] == {"isAIGenerated": True, "visibility": "public"}
    assert ig["scheduleDate"].endswith("Z") and ig["mediaUrls"][0].startswith("https://")
    assert ig["idempotencyKey"] != tt["idempotencyKey"]
    assert events(tmp_path, "week.scheduled")[0]["actor"] == "human:owner"


def test_a_change_after_the_card_voids_it(tmp_path):
    name = plan(tmp_path)
    week.stage(tmp_path, name)
    (tmp_path / "artifacts" / "media" / "mon.jpg").write_bytes(b"\xff\xd8\xff swapped")
    with pytest.raises(week.WeekError, match="changed"):
        week.send(tmp_path, name, "public", FakeAyrshare(), by="human:owner")


def test_only_a_person_sends_and_never_twice(tmp_path):
    name = plan(tmp_path)
    week.stage(tmp_path, name)
    with pytest.raises(PermissionError):
        week.send(tmp_path, name, "public", FakeAyrshare(), by="jarvis")
    with pytest.raises(week.WeekError, match="visibility"):
        week.send(tmp_path, name, "", FakeAyrshare(), by="human:owner")
    week.send(tmp_path, name, "public", FakeAyrshare(), by="human:owner")
    with pytest.raises(week.WeekError, match="already"):
        week.send(tmp_path, name, "public", FakeAyrshare(), by="human:owner")


def test_jarvis_only_stages_it_and_the_owner_picks_visibility(tmp_path, monkeypatch):
    name = plan(tmp_path)
    api = FakeAyrshare()
    monkeypatch.setattr(week, "client", lambda: api)
    a = make(tmp_path)
    out, err = a._run_tool("schedule_week", {"week": name, "tiktok_visibility": "public"})
    assert not err and out["pending_id"] in a.pending and not api.posts
    pid = out["pending_id"]
    assert a.pending[pid].args == {"week": name}            # the model cannot pick it
    assert a.confirm(pid, True, "human:owner", {})["retry"]   # owner must choose
    done = a.confirm(pid, True, "human:owner", {"tiktok_visibility": "private"})
    assert done["done"] and api.posts[1]["tikTokOptions"]["visibility"] == "private"


def test_the_ayrshare_key_goes_with_the_platform_keys():
    from bau import keys
    assert keys.route({"AYRSHARE_API_KEY": "x"})["platforms.env"] == {"AYRSHARE_API_KEY": "x"}


# Real run on Qwen3.5-4B (2026-11-01, the recorded video): "Schedule the week nov-week-1."
# The small model never found schedule_week in its menu and asked instead. Naming a week plan
# that exists now puts its card on the owner's screen at once (staging changes nothing).
def test_naming_a_week_puts_its_card_up_for_a_small_model(tmp_path):
    from bau.assistant import Assistant
    from bau.models.providers import ScriptedProvider
    name = plan(tmp_path)
    a = Assistant(tmp_path, ScriptedProvider(["It's on your screen."]),
                  {"id": "qwen-local", "deployment": "local"}, "human:owner")
    r = a.ask(f"Schedule the week {name}.")
    assert [p["tool"] for p in r.pending] == ["schedule_week"]
    assert "on the owner's screen" in str(a.provider.calls[0]["messages"][-1]["content"])
    b = Assistant(tmp_path, ScriptedProvider(["Which one?"]),
                  {"id": "qwen-local", "deployment": "local"}, "human:owner")
    assert not b.ask("Schedule the week nope-week.").pending      # only a plan that exists
