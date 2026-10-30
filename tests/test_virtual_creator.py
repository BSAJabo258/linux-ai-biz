import pytest
import yaml

from bau.assistant import Assistant
from bau.home import shipped_data
from bau.virtual_creator import CreatorError, VirtualCreator


def _profile(tmp_path, **changes):
    p = yaml.safe_load((shipped_data() / "virtual_creator_profile.example.yaml").read_text())
    p.update(changes)
    path = tmp_path / "creators" / "aria.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(p))
    return path


def test_starter_profile_is_valid_and_drafts_sfw(tmp_path):
    vc = VirtualCreator(_profile(tmp_path))
    assert vc.problems() == []
    batch = vc.batch("autumn city fashion", "instagram", 3)
    assert batch["tier"] == "sfw" and len(batch["posts"]) == 3
    assert "Tier: sfw" in batch["posts"][0]["visual_prompt"]


def test_explicit_needs_owner_boundaries_and_an_adult_platform(tmp_path):
    with pytest.raises(CreatorError, match="explicit_boundaries"):
        VirtualCreator(_profile(tmp_path)).batch("evening", "fanvue", tier="explicit")
    vc = VirtualCreator(_profile(tmp_path, explicit_boundaries=["adults only, consenting"]))
    for platform in ("instagram", "tiktok", "youtube", "x", "patreon"):
        with pytest.raises(CreatorError, match="adult platforms"):
            vc.batch("evening", platform, tier="explicit")
    batch = vc.batch("evening", "fanvue", 2, tier="explicit")
    prompt = batch["posts"][0]["visual_prompt"]
    assert "local content lane" in prompt and "adults only, consenting" in prompt


@pytest.mark.parametrize("word", ["barely legal", "schoolgirl", "loli", "young-looking",
                                  "17 year old"])
def test_youth_coded_words_are_refused_in_every_tier(tmp_path, word):
    vc = VirtualCreator(_profile(tmp_path, explicit_boundaries=["adults only"]))
    with pytest.raises(CreatorError, match="minors"):
        vc.batch(f"{word} theme", "fanvue", tier="explicit")
    bad = VirtualCreator(_profile(tmp_path, explicit_boundaries=[f"{word} roleplay"]))
    assert any("minors" in p for p in bad.problems())


def test_profiles_stay_out_of_workspaces(tmp_path):
    path = _profile(tmp_path)
    inside = tmp_path / "workspaces" / "kids-channel" / "aria.yaml"
    inside.parent.mkdir(parents=True)
    inside.write_text(path.read_text())
    assert any("workspaces" in p for p in VirtualCreator(inside).problems())


def test_jarvis_tool_only_drafts_sfw(tmp_path):
    _profile(tmp_path, explicit_boundaries=["adults only"])
    a = Assistant(home=tmp_path)
    assert a.t_creator_batch("aria", "evening", "fanvue", 1)["tier"] == "sfw"
    assert "tier" not in a.tools["creator_batch"].schema["properties"]
