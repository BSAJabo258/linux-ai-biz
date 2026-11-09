"""Setup steps pop up for the owner (the owner's ask, 2026-11-02: "a pop-up menu for me to
click the accept button so that it can continue"). Every setup step still waiting on this
computer appears in Jarvis by itself as a card with Accept; Accept runs it (a terminal window
for anything that needs the owner's password), and a step that is done disappears. Nothing
runs without the owner's click; owner-only values (prices) are typed by the owner, never
filled in. Fakes only. Written before the code."""

from pathlib import Path

import pytest
import yaml

from bau import setup_steps as S


class Box:
    """This computer: which services answer, what the card and the files say."""

    def __init__(self, tmp, nvidia=True, driver=False, pictures=False, search=False,
                 update="off", laws_new=False, profile_prices=None, autopilot=False):
        self.home = tmp / "home"
        (self.home / "regulations").mkdir(parents=True)
        (self.home / "regulations" / ("creator.yaml" if laws_new else "ai.yaml")).write_text(
            "[]\n")
        (self.home / "creators").mkdir()
        prof = {"id": "aria"} | ({"prices": profile_prices} if profile_prices else {})
        if profile_prices:
            prof["explicit_boundaries"] = ["no real people"]
        (self.home / "creators" / "aria.yaml").write_text(yaml.safe_dump(prof))
        self.facts = {"nvidia": nvidia, "driver": driver, "pictures": pictures,
                      "search": search, "update": update, "autopilot": autopilot,
                      "room": False}
        self.opened = []

    def probe(self, what):
        return self.facts[what]

    def terminal(self, title, command):
        self.opened.append((title, command))
        return True


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def ids(box):
    return [s.id for s in S.waiting(box.home, probe=box.probe)]


def test_everything_still_waiting_is_listed_in_order(box):
    assert ids(box) == ["laws", "nvidia", "search", "updates", "autopilot", "boundaries",
                        "prices"]


def test_done_steps_disappear(tmp_path):
    b = Box(tmp_path, driver=True, pictures=True, search=True, update="auto",
            laws_new=True, autopilot=True,
            profile_prices={"subscription": 9.99, "nude": 14.99, "xxx": 29.99})
    assert ids(b) == []


def test_pictures_wait_for_nvidias_driver_and_need_a_card(tmp_path):
    assert "pictures" not in ids(Box(tmp_path / "a", driver=False))
    assert "pictures" in ids(Box(tmp_path / "b", driver=True))
    no_card = Box(tmp_path / "c", nvidia=False)
    assert "nvidia" not in ids(no_card) and "pictures" not in ids(no_card)


def test_accept_opens_a_terminal_for_password_steps(box):
    out = S.run("nvidia", box.home, probe=box.probe, terminal=box.terminal)
    assert out["started"] and box.opened
    title, cmd = box.opened[0]
    assert "sudo bau-gpu-setup" in cmd
    out = S.run("search", box.home, probe=box.probe, terminal=box.terminal)
    assert "sudo bash" in box.opened[-1][1] and "bau-search-setup.sh" in box.opened[-1][1]


def test_the_shipped_setup_scripts_are_the_installers_own():
    root = Path(__file__).resolve().parents[1]
    for name in ("bau-pictures-setup.sh", "bau-search-setup.sh"):
        assert (root / "src/bau/data/setup" / name).read_text() == \
            (root / "installer" / name).read_text()
        assert S.script(name).exists()


def test_prices_are_set_on_the_card_only_by_the_owners_accept(box):
    fields = S.form("prices")["fields"]
    assert [f["name"] for f in fields] == ["subscription", "nude", "xxx"]
    assert all("options" not in f for f in fields)            # typed boxes, filled in, changeable
    out = S.run("prices", box.home, values={"subscription": "9.99", "nude": "14.99",
                                            "xxx": "29.99"})
    assert out["done"] and not box.opened                        # no terminal needed
    prof = yaml.safe_load((box.home / "creators" / "aria.yaml").read_text())
    assert prof["prices"] == {"subscription": 9.99, "nude": 14.99, "xxx": 29.99}
    assert "prices" not in ids(box)


def test_prices_outside_fanvues_limits_or_missing_are_refused(box):
    assert "error" in S.run("prices", box.home, values={"subscription": "1", "nude": "5",
                                                        "xxx": "5"})
    assert "error" in S.run("prices", box.home, values={"subscription": "9.99"})
    assert "prices" in ids(box)


def test_explicit_limits_are_the_owners_words_and_never_about_minors(box):
    assert S.form("boundaries")["fields"][0]["type"] == "text"
    assert "error" in S.run("boundaries", box.home, values={"limits": "  \n "})
    assert "error" in S.run("boundaries", box.home,
                            values={"limits": "nothing with a teen"})
    out = S.run("boundaries", box.home, values={"limits": "no real people\nno violence\n"})
    assert out["done"]
    prof = yaml.safe_load((box.home / "creators" / "aria.yaml").read_text())
    assert prof["explicit_boundaries"] == ["no real people", "no violence"]
    assert "boundaries" not in ids(box)


def test_api_keys_switch_on_with_accept_and_the_owner_as_reviewer(box, monkeypatch):
    reg = box.home / "registry" / "capabilities.yaml"
    reg.parent.mkdir()
    rec = {"model_id": "glm", "name": "GLM", "version": "1", "provider": "zai",
           "source": "z.ai", "license": "terms", "commercial_use": True,
           "deployment": "hosted", "trust_level": "OFFICIAL", "privacy": "hosted",
           "api_key_env": "ZAI_KEY", "status": "REGISTERED"}
    bad = dict(rec, model_id="odd", trust_level="UNKNOWN", api_key_env="ZAI_KEY")
    reg.write_text(yaml.safe_dump({"model": {"glm": rec, "odd": bad}}))
    monkeypatch.setenv("ZAI_KEY", "x")
    assert "api_keys" in ids(box)
    with pytest.raises(PermissionError):
        S.run("api_keys", box.home, owner="process:bau")
    out = S.run("api_keys", box.home, owner="human:owner")
    assert out["switched_on"] == ["glm"] and not box.opened
    assert "api_keys" not in ids(box)        # "odd" fails the registry's checks: no card
    saved = yaml.safe_load(reg.read_text())["model"]["glm"]
    assert saved["status"] == "APPROVED" and saved["reviewed_by"] == "human:owner"
    assert yaml.safe_load(reg.read_text())["model"]["odd"]["status"] == "REGISTERED"


def test_laws_refresh_runs_here_and_keeps_the_old_copy(box):
    (box.home / "regulations" / "old.yaml").write_text("[]\n")
    out = S.run("laws", box.home, probe=box.probe, terminal=box.terminal)
    assert out["done"] and not box.opened
    assert (box.home / "regulations" / "creator.yaml").exists()
    assert not (box.home / "regulations" / "old.yaml").exists()
    kept = list(box.home.glob("regulations.before-*"))
    assert kept and (kept[0] / "old.yaml").exists()


def test_no_screen_means_the_exact_command_instead(box):
    out = S.run("updates", box.home, probe=box.probe, terminal=lambda t, c: False)
    assert "sudo bau update auto" in out["error"]


def test_unknown_step_is_refused(box):
    with pytest.raises(ValueError):
        S.run("rm -rf", box.home, probe=box.probe, terminal=box.terminal)


# ------------------------------------------------------------------ in Jarvis
def test_jarvis_pops_every_waiting_step_up_once_and_accept_runs_it(tmp_path, monkeypatch):
    from bau.assistant import Assistant
    b = Box(tmp_path)
    monkeypatch.setattr(S, "_probe", b.probe)
    monkeypatch.setattr(S, "_terminal", b.terminal)
    j = Assistant(b.home)
    first = j.setup_waiting()
    assert [p["tool"] for p in first] == ["setup_step"] * 7
    assert "Accept" in first[0]["summary"] or first[0]["summary"]
    again = j.setup_waiting()                          # not stacked twice
    assert len([p for p in j.pending.values() if p.tool == "setup_step"]) == 7
    assert {p["id"] for p in again} == {p["id"] for p in first}
    nvidia = next(p for p in first if "NVIDIA" in p["summary"])
    with pytest.raises(PermissionError):
        j.confirm(nvidia["id"], True, "jarvis")          # only the owner accepts
    out = j.confirm(nvidia["id"], True, "human:owner")
    assert out["done"] and "sudo bau-gpu-setup" in b.opened[-1][1]
    # its terminal is running: no second NVIDIA card on the next check (it would nag)
    assert not any("NVIDIA" in p["summary"] for p in j.setup_waiting())
    j.setup_started["nvidia"] -= 46 * 60                  # still not done much later: back
    assert any("NVIDIA" in p["summary"] for p in j.setup_waiting())
    prices = next(p for p in first if "prices" in p["summary"])
    assert prices["form"]["fields"][0]["type"] == "number"
    out = j.confirm(prices["id"], True, "human:owner", {"subscription": "abc"})
    assert out["retry"]                                  # still waiting until typed right
    out = j.confirm(prices["id"], True, "human:owner",
                    {"subscription": "9.99", "nude": "20", "xxx": "40"})
    assert out["done"]


def test_the_model_cannot_stage_or_run_setup_steps(tmp_path):
    from bau.assistant import Assistant
    j = Assistant(tmp_path / "home")
    assert "setup_step" not in j.tools                   # owner-only, never in the model's list
    assert "setup_step" in j.owner_tools


def test_the_page_shows_them_when_jarvis_opens():
    text = (Path(__file__).resolve().parents[1] / "src/bau/ui/jarvis_server.py").read_text()
    assert "setup_waiting()" in text
    page = (Path(__file__).resolve().parents[1] / "src/bau/ui/jarvis.html").read_text()
    assert '/^(setup_step|autopilot_answer|fanvue_review)$/.test(showing.tool) ? "Accept"' in page
    # typed boxes on cards come filled in from Fanvue's advice, and the greeting never takes
    # the keyboard from them
    assert "if (f.value !== undefined) { box.value = f.value; box.oninput(); }" in page
    assert 'el(f.type === "number" ? "input" : "textarea", "typed")' in page
    assert 'if (!$("confirm").classList.contains("show")) $("text").focus();' in page


def test_the_autopilot_setup_script_carries_the_installers_units():
    root = Path(__file__).resolve().parents[1]
    text = S.script("bau-autopilot-setup.sh").read_text()
    for unit in ("bau-autopilot.service", "bau-autopilot.timer"):
        body = (root / "installer/payload/systemd" / unit).read_text()
        assert f"/etc/systemd/system/{unit} <<'UNIT'\n{body}UNIT\n" in text
    assert "bau-autopilot.timer" in (root / "installer/payload/install.sh").read_text()


def test_not_now_keeps_a_setup_card_down_instead_of_popping_straight_back(tmp_path, monkeypatch):
    # Found by the screen audit (2026-11-08): the declined card was back seconds later.
    from bau.assistant import SETUP_SNOOZE_S, Assistant
    b = Box(tmp_path)
    monkeypatch.setattr(S, "_probe", b.probe)
    j = Assistant(b.home)
    nvidia = next(p for p in j.setup_waiting() if "NVIDIA" in p["summary"])
    j.confirm(nvidia["id"], False, "human:owner")
    assert not any("NVIDIA" in p["summary"] for p in j.setup_waiting())
    j.setup_snoozed["nvidia"] -= SETUP_SNOOZE_S + 1        # hours later, still not done: back
    assert any("NVIDIA" in p["summary"] for p in j.setup_waiting())


def test_the_cards_come_filled_in_from_fanvues_own_advice():
    # the owner, 2026-11-09: "fill them out"; Accept is still the choice
    from bau import virtual_creator as V
    from bau.fanvue import AUDIENCES, MAX_PER_DAY
    prices = {f["name"]: f for f in S.form("prices")["fields"]}
    assert {k: f["value"] for k, f in prices.items()} == {
        "subscription": 9.99, "nude": 10.99, "xxx": 14.99}
    assert not V.price_problems({k: f["value"] for k, f in prices.items()})  # Fanvue limits
    assert all("help.fanvue.com" in f["why"] for f in prices.values())       # the source is shown
    auto = {f["name"]: f for f in S.form("autopost")["fields"]}
    assert auto["audience"]["value"] in AUDIENCES and 1 <= auto["per_day"]["value"] <= MAX_PER_DAY
    limits = S.form("boundaries")["fields"][0]["value"].splitlines()
    assert not any(V.MINOR_REFERENCE.search(x) for x in limits)   # the save would refuse them


def test_accepting_the_filled_in_prices_and_limits_saves_them(tmp_path):
    import shutil
    home = tmp_path / "home"
    (home / "creators").mkdir(parents=True)
    shutil.copy(Path(S.__file__).parent / "data/virtual_creator_profile.example.yaml",
                home / "creators/aria.yaml")
    vals = {f["name"]: str(f["value"]) for f in S.form("prices")["fields"]}
    assert S.run("prices", home, values=vals)["done"]
    lim = {"limits": S.form("boundaries")["fields"][0]["value"]}
    assert S.run("boundaries", home, values=lim)["done"]
    text = (home / "creators/aria.yaml").read_text()
    assert "subscription: 9.99" in text and "No real person's likeness" in text
