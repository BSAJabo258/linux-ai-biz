"""The creator's feed fills itself (src/bau/creator_feed.py): while the owner's Fanvue autopost
is on, the autopilot draws pictures, has the local model write captions and queues them, as
many as his number a day. Fake picture drawer and scripted model only."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from bau import autopilot as A
from bau import autopilot_jobs as J
from bau import creator_feed as C
from bau import fanvue as F
from bau.models.providers import ScriptedProvider

PROFILE = Path(__file__).resolve().parents[1] / "src/bau/data/virtual_creator_profile.example.yaml"


@pytest.fixture
def home(tmp_path, monkeypatch):
    (tmp_path / "creators").mkdir()
    shutil.copy(PROFILE, tmp_path / "creators" / "aria.yaml")
    monkeypatch.setattr(J, "_scout", lambda h: None)
    from bau.scout import watch as W
    monkeypatch.setattr(W, "load", lambda: {"categories": {}})
    return tmp_path


def fake_draw(drawn):
    def draw(home, prompt, name, **kw):
        drawn.append(prompt)
        data = name.encode() * 3
        media = home / "artifacts" / "media"
        media.mkdir(parents=True, exist_ok=True)
        (media / f"{name}.png").write_bytes(data)
        (media / f"{name}.png.provenance.json").write_text(json.dumps({
            "ai_generated": True, "file_sha256": hashlib.sha256(data).hexdigest(),
            "age_check": {"passed": True}}))
        return {"file": f"{name}.png"}
    return draw


def test_nothing_is_made_while_autopost_is_off(home):
    assert C.fill(home) == 0 and J.seed(home) == 0


def test_the_feed_stocks_his_number_a_day_and_each_job_queues_a_labelled_post(home,
                                                                                monkeypatch):
    F.set_autopost(home, True, "human:owner", "subscribers", 3)
    assert J.seed(home) == 3 and C.fill(home) == 0          # not twice
    drawn, model = [], ScriptedProvider(["Slow morning, warm coffee, new knit."] * 3)

    def handler(task):
        return C.make_post(home, task, draw=fake_draw(drawn),
                           factory=lambda m, h: (model, {}))
    from bau import team
    monkeypatch.setattr(team, "show", lambda h: {"boss": "qwen3.5-9b"})
    A.run(home, {"draft": handler}, max_steps=5)
    assert F.Queue(home).pending() == []                  # nothing posts before the owner says
    items = F.Queue(home).review()
    assert len(items) == 3 and all(i["level"] == 1 for i in items)   # subscribers -> level 1
    assert items[0]["caption"].startswith("Slow morning") and F.AI_LABEL in items[0]["caption"]
    assert all("25-year-old adult woman" in p for p in drawn)          # the profile's age
    assert C.fill(home) == 0                                          # stocked: nothing more


def test_a_caption_about_minors_is_refused_and_nothing_is_queued(home, monkeypatch):
    from bau import team
    monkeypatch.setattr(team, "show", lambda h: {"boss": "qwen3.5-9b"})
    model = ScriptedProvider(["cute schoolgirl look"])
    task = {"detail": {"job": "fanvue_post", "theme": "autumn walk", "level": 0,
                       "shot": "medium"}}
    with pytest.raises(ValueError, match="minors"):
        C.make_post(home, task, draw=fake_draw([]), factory=lambda m, h: (model, {}))
    assert F.Queue(home).pending() == [] and F.Queue(home).review() == []


def test_without_a_local_model_the_caption_is_a_plain_line(home, monkeypatch):
    from bau import team
    monkeypatch.setattr(team, "show", lambda h: {"boss": None})
    task = {"detail": {"job": "fanvue_post", "theme": "rooftop at golden hour", "level": 0,
                       "shot": "medium"}}
    out = C.make_post(home, task, draw=fake_draw([]))
    assert out["ok"] and F.Queue(home).review()[0]["caption"].startswith(
        "Rooftop at golden hour.")


def test_the_autopilot_runs_the_draft_job_through_its_real_handler(home, monkeypatch):
    from bau.media import comfy
    monkeypatch.setattr(comfy, "draw", fake_draw([]))
    from bau import team
    monkeypatch.setattr(team, "show", lambda h: {"boss": None})
    F.set_autopost(home, True, "human:owner", "followers-and-subscribers", 1)
    J.seed(home)
    A.run(home, J.handlers(home), max_steps=3)
    assert [i["level"] for i in F.Queue(home).review()] == [0]


def test_every_level_has_its_own_prompt_sections_and_no_youth_words():
    from bau.virtual_creator import MINOR_REFERENCE
    tiers = C.tiers()
    assert set(tiers) == {0, 1, 2, 3}
    for level, t in tiers.items():
        assert {"setting", "pose", "light", "camera"} <= set(t["sections"])
        lines = [x for v in t["sections"].values() for x in v] + [t["negative"]]
        assert not any(MINOR_REFERENCE.search(x) for x in lines), level
    assert "nude" in tiers[0]["negative"] and "nude" in tiers[1]["negative"]   # sfw levels
    assert "lingerie" in tiers[0]["negative"]          # the free teaser stays everyday wear
    for level in (2, 3):                               # one fictional adult, alone
        assert "second person" in tiers[level]["negative"]


def test_each_picture_uses_its_levels_prompt_and_negative(home, monkeypatch):
    from bau import team
    monkeypatch.setattr(team, "show", lambda h: {"boss": None})
    seen = []

    def draw(home_, prompt, name, **kw):
        seen.append((prompt, kw["negative"]))
        return fake_draw([])(home_, prompt, name)
    parts = C.pick(1)
    task = {"detail": {"job": "fanvue_post", "theme": "x", "level": 1, "shot": "medium",
                       "parts": parts}}
    C.make_post(home, task, draw=draw)
    prompt, negative = seen[0]
    assert "25-year-old adult woman" in prompt                      # the identity lock first
    assert all(v in prompt for v in parts.values())
    assert C.tiers()[1]["negative"] in negative and "child" in negative


def test_the_owner_accepts_or_drops_each_picture_on_its_card(home, monkeypatch):
    from bau import team
    from bau.assistant import Assistant
    monkeypatch.setattr(team, "show", lambda h: {"boss": None})
    for theme in ("a", "b"):
        C.make_post(home, {"detail": {"job": "fanvue_post", "theme": theme, "level": 0,
                                      "shot": "medium", "parts": C.pick(0)}},
                    draw=fake_draw([]))
    j = Assistant(home)
    cards = [p for p in j.setup_waiting() if p["tool"] == "fanvue_review"]
    assert len(cards) == 2 and all(c["preview"] for c in cards)      # the picture is shown
    assert len([p for p in j.setup_waiting() if p["tool"] == "fanvue_review"]) == 2  # once
    with pytest.raises(PermissionError):
        j.confirm(cards[0]["id"], True, "jarvis")                     # only the owner
    assert j.confirm(cards[0]["id"], True, "human:owner")["done"]
    j.confirm(cards[1]["id"], False, "human:owner")
    q = F.Queue(home)
    assert len(q.pending()) == 1 and q.review() == []                 # one posts, one dropped
    assert [i["status"] for i in q.items()].count("DROPPED") == 1


def test_with_chroma_and_his_limits_the_feed_takes_turns_through_the_paid_levels(home,
                                                                                    monkeypatch):
    import yaml

    from bau import team
    from bau.media import comfy
    p = home / "creators" / "aria.yaml"
    prof = yaml.safe_load(p.read_text())
    prof["explicit_boundaries"] = ["No animals", "No real person's likeness"]
    prof["prices"] = {"subscription": 9.99, "nude": 10.99, "xxx": 14.99}
    p.write_text(yaml.safe_dump(prof))
    monkeypatch.setattr(team, "show", lambda h: {"boss": None})
    monkeypatch.setattr(comfy, "chroma_ready", lambda: False)
    F.set_autopost(home, True, "human:owner", "subscribers", 3)
    assert C.fill(home) == 3
    assert {t["detail"]["level"] for t in A._load(home)["tasks"]} == {1}    # no Chroma: sfw only
    st = A._load(home)
    st["tasks"] = []                                  # start the day again, now with Chroma
    A._save(home, st)
    monkeypatch.setattr(comfy, "chroma_ready", lambda: True)
    assert C.fill(home) == 3
    tasks = [t for t in A._load(home)["tasks"] if t["kind"] == "draft"]
    assert sorted(t["detail"]["level"] for t in tasks) == [1, 2, 3]
    seen = []

    def draw(home_, prompt, name, **kw):
        seen.append(kw)
        out = fake_draw([])(home_, prompt, name)
        prov = home_ / "artifacts" / "media" / f"{name}.png.provenance.json"
        prov.write_text(json.dumps({**json.loads(prov.read_text()), "lane": kw["lane"]}))
        return out
    t3 = next(t for t in tasks if t["detail"]["level"] == 3)
    C.make_post(home, t3, draw=draw)
    assert seen[0]["lane"] == "explicit"
    assert "animals" in seen[0]["negative"] and "child" in seen[0]["negative"]
    item = F.Queue(home).review()[0]
    assert item["level"] == 3 and item["price_cents"] == 1499 and item["status"] == "REVIEW"


def test_the_paid_levels_setup_card_comes_after_pictures_and_his_limits(tmp_path):
    from bau import setup_steps as S
    facts = {"nvidia": True, "driver": True, "pictures": True, "explicit": False}
    probe = facts.__getitem__
    (tmp_path / "creators").mkdir()
    (tmp_path / "creators" / "aria.yaml").write_text("id: aria\n")
    assert S._done("explicit", tmp_path, probe) is None          # no limits written yet
    (tmp_path / "creators" / "aria.yaml").write_text(
        "id: aria\nexplicit_boundaries: [No animals]\n")
    assert S._done("explicit", tmp_path, probe) is False         # waiting: the card shows
    facts["explicit"] = True
    assert S._done("explicit", tmp_path, probe) is True
    assert "bau-explicit-setup.sh" in S._command("explicit", tmp_path)
