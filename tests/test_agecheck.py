"""Nothing childlike (the owner, 2026-11-01): every picture BAU draws is looked at by an age
model before it is kept. If it could pass for under 20, it is moved aside and never used; if
the check cannot run, the picture is not kept either. A week plan refuses any picture without a
passed check. The owner still looks at every picture: this is a second guard, not a promise.

Model: dima806/fairface_age_image_detection (Apache-2.0, FairFace age groups). Sandbox test on
2026-11-01 (BAU's runner, pinned model, all nine groups), the two real SDXL pictures:
the first try (it read young) scored 0.25 under 20 and is rejected, the fixed one 0.05
and is kept. Written before the code."""

import json

import pytest
from test_comfy import FakeComfy
from test_week import plan

from bau import week
from bau.media import comfy

ADULT = {"0-2": 0.009, "3-9": 0.004, "10-19": 0.037, "20-29": 0.687, "30-39": 0.21,
         "40-49": 0.027, "50-59": 0.01, "60-69": 0.01, "more than 70": 0.006}
YOUNG = {"0-2": 0.01, "3-9": 0.073, "10-19": 0.129, "20-29": 0.416, "30-39": 0.176,
         "40-49": 0.061, "50-59": 0.05, "60-69": 0.05, "more than 70": 0.035}


def test_under_20_adds_the_three_youngest_groups():
    assert comfy.under_20(ADULT) == pytest.approx(0.05)
    assert comfy.under_20(YOUNG) == pytest.approx(0.212)
    assert comfy.under_20(ADULT) <= comfy.MAX_UNDER_20 < comfy.under_20(YOUNG)


def test_an_adult_picture_is_kept_with_its_check_on_record(tmp_path):
    out = comfy.draw(tmp_path, "a fictional adult", "ok", opener=FakeComfy(), wait=0,
                     checker=lambda p: ADULT)
    media = tmp_path / "artifacts" / "media"
    prov = json.loads((media / "ok.png.provenance.json").read_text())
    assert out["file"] == "ok.png" and (media / "ok.png").is_file()
    assert prov["age_check"]["passed"] is True
    assert prov["age_check"]["under_20"] == pytest.approx(0.05)
    assert prov["age_check"]["model"] == comfy.AGE_MODEL


def test_a_young_looking_picture_is_moved_aside_and_never_kept(tmp_path):
    with pytest.raises(comfy.ComfyError, match="under 20"):
        comfy.draw(tmp_path, "a fictional adult", "bad", opener=FakeComfy(), wait=0,
                   checker=lambda p: YOUNG)
    assert not (tmp_path / "artifacts" / "media" / "bad.png").exists()
    assert (tmp_path / "artifacts" / "rejected" / "bad.png").is_file()
    events = [json.loads(x)["event"] for x in
              (tmp_path / "audit" / "chain.jsonl").read_text().splitlines()]
    assert "media.rejected" in events and "media.drawn" not in events


def test_no_check_means_no_picture(tmp_path):
    def broken(path):
        raise OSError("age model not installed")
    with pytest.raises(comfy.ComfyError, match="age check"):
        comfy.draw(tmp_path, "a fictional adult", "x", opener=FakeComfy(), wait=0,
                   checker=broken)
    assert not (tmp_path / "artifacts" / "media" / "x.png").exists()


def test_a_week_refuses_a_picture_without_a_passed_check(tmp_path):
    name = plan(tmp_path)
    (tmp_path / "artifacts" / "media" / "mon.jpg.provenance.json").unlink()  # no record
    found = week.problems(tmp_path, name)
    assert any("age check" in x for x in found)
    assert not any("age check" in x and "post 2" in x for x in found)  # videos: not yet
    media = tmp_path / "artifacts" / "media"
    (media / "mon.jpg.provenance.json").write_text(json.dumps(
        {"ai_generated": True, "age_check": {"passed": True, "under_20": 0.05}}))
    assert not any("age check" in x for x in week.problems(tmp_path, name))
    (media / "mon.jpg.provenance.json").write_text(json.dumps(
        {"ai_generated": True, "age_check": {"passed": False, "under_20": 0.3}}))
    assert any("age check" in x for x in week.problems(tmp_path, name))


def test_the_installer_pins_the_age_model():
    text = comfy_setup()
    assert f'AGE_REVISION="{comfy.AGE_REVISION}"' in text
    assert "1265d8e5a8a363a615898be873c224aebc6f310654bf23b1745da0975a7b7555" in text
    assert "agecheck_run.py" in text


def comfy_setup():
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "installer" / "bau-pictures-setup.sh"
            ).read_text()
