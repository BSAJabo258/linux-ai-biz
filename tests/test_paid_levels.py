"""Paid levels for the creator (the owner's plan and prices, 2026-11-01): 0 teaser (sfw,
free, Instagram/TikTok/Fanvue), 1 subscriber (suggestive, Fanvue subscription), 2 nude and
3 XXX (Fanvue pay-to-unlock). Prices are the owner's: never a default, set by a human at a
terminal, inside Fanvue's own limits (help.fanvue.com, read 2026-11-01). Written first."""

import pytest
import yaml

from bau.home import shipped_data
from bau.virtual_creator import LEVELS, CreatorError, VirtualCreator, set_prices, write_markdown

PRICES = {"subscription": 9.99, "nude": 14.99, "xxx": 29.99}
LIMITS = ["adults only, consenting, fictional persona", "no violence"]


def _profile(tmp_path, **changes):
    p = yaml.safe_load((shipped_data() / "virtual_creator_profile.example.yaml").read_text())
    p.update(changes)
    path = tmp_path / "aria.yaml"
    path.write_text(yaml.safe_dump(p))
    return path


def test_four_levels_in_order():
    assert [LEVELS[n]["name"] for n in range(4)] == ["teaser", "subscriber", "nude", "xxx"]
    assert LEVELS[0]["tier"] == LEVELS[1]["tier"] == "sfw"
    assert LEVELS[2]["tier"] == LEVELS[3]["tier"] == "explicit"
    assert all(LEVELS[n]["platforms"] == ("fanvue",) for n in (1, 2, 3))


def test_the_starter_profile_has_no_prices():          # owner's choice, never a default
    p = yaml.safe_load((shipped_data() / "virtual_creator_profile.example.yaml").read_text())
    assert "prices" not in p


def test_teaser_is_free_and_sfw_on_every_platform(tmp_path):
    vc = VirtualCreator(_profile(tmp_path))
    b = vc.batch("autumn cafe", "instagram", 2, level=0)
    assert b["level"] == 0 and b["access"] == "free" and b["tier"] == "sfw"
    assert "price_usd" not in b


def test_paid_levels_need_the_owners_price(tmp_path):
    vc = VirtualCreator(_profile(tmp_path, explicit_boundaries=LIMITS))
    for level in (1, 2, 3):
        with pytest.raises(CreatorError, match="price"):
            vc.batch("evening", "fanvue", 1, level=level)


def test_each_paid_level_carries_its_price_and_goes_only_to_fanvue(tmp_path):
    vc = VirtualCreator(_profile(tmp_path, explicit_boundaries=LIMITS, prices=PRICES))
    want = {1: ("subscription", 9.99), 2: ("unlock", 14.99), 3: ("unlock", 29.99)}
    for level, (access, price) in want.items():
        b = vc.batch("evening", "fanvue", 1, level=level)
        assert (b["access"], b["price_usd"]) == (access, price)
        md = write_markdown(b)
        assert f"${price:.2f}" in md and LEVELS[level]["name"] in md
        for platform in ("instagram", "tiktok"):
            with pytest.raises(CreatorError, match="fanvue"):
                vc.batch("evening", platform, 1, level=level)


def test_level_prompts_say_how_far_each_goes(tmp_path):
    vc = VirtualCreator(_profile(tmp_path, explicit_boundaries=LIMITS, prices=PRICES))
    one = vc.batch("evening", "fanvue", 1, level=1)["posts"][0]["visual_prompt"]
    two = vc.batch("evening", "fanvue", 1, level=2)["posts"][0]["visual_prompt"]
    three = vc.batch("evening", "fanvue", 1, level=3)["posts"][0]["visual_prompt"]
    assert "no nudity" in one
    assert "nudity" in two and "no sexual activity" in two and "local content lane" in two
    assert "no violence" in three and "local content lane" in three


def test_nude_and_xxx_need_the_owners_explicit_limits(tmp_path):
    vc = VirtualCreator(_profile(tmp_path, prices=PRICES))
    for level in (2, 3):
        with pytest.raises(CreatorError, match="explicit_boundaries"):
            vc.batch("evening", "fanvue", 1, level=level)


@pytest.mark.parametrize("bad", [{"subscription": 2.0}, {"subscription": 101},
                                 {"nude": 2.5}, {"xxx": 501}, {"xxx": "lots"}, {"tip": 5}])
def test_prices_outside_fanvues_limits_are_refused(tmp_path, bad):
    vc = VirtualCreator(_profile(tmp_path, prices={**PRICES, **bad}))
    assert any("price" in p for p in vc.problems())


def test_set_prices_keeps_the_rest_of_the_profile(tmp_path):
    path = _profile(tmp_path)
    path.write_text("# my notes stay\n" + path.read_text())
    set_prices(path, PRICES)
    assert path.read_text().startswith("# my notes stay")
    vc = VirtualCreator(path)
    assert vc.profile["prices"] == PRICES and vc.problems() == []
    set_prices(path, {**PRICES, "xxx": 34.99})                   # changing them again
    assert VirtualCreator(path).profile["prices"]["xxx"] == 34.99
    assert path.read_text().count("prices:") == 1
    with pytest.raises(CreatorError):
        set_prices(path, {"subscription": 1.0})


def test_bau_creator_prices_is_for_a_human_at_a_terminal(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    path = _profile(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["creator", "prices", str(path), "--subscription", "9.99", "--nude", "14.99",
                 "--xxx", "29.99"]) != 0                     # denied: no prices written
    assert "prices" not in VirtualCreator(path).profile
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert main(["creator", "prices", str(path), "--subscription", "9.99", "--nude", "14.99",
                 "--xxx", "29.99"]) == 0
    assert VirtualCreator(path).profile["prices"] == PRICES
    assert main(["creator", "batch", str(path), "evening", "--platform", "fanvue",
                 "--level", "1", "--count", "1"]) == 0
    assert "$9.99" in capsys.readouterr().out
