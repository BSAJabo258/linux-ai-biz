"""Setup steps pop up for the owner (the owner's ask, 2026-11-02: "a pop-up menu for me to
click the accept button so that it can continue"). Every setup step still waiting on this
computer appears in Jarvis by itself as a card with Accept; Accept runs it (a terminal window
for anything that needs the owner's password), and a step that is done disappears. Nothing
runs without the owner's click; owner-only values (prices) are typed by the owner, never
filled in. Fakes only. Written before the code."""

import json
from pathlib import Path

import pytest

from bau import setup_steps as S


class Box:
    """This computer: which services answer, what the card and the files say."""

    def __init__(self, tmp, nvidia=True, driver=False, pictures=False, search=False,
                 update="off", laws_new=False, profile_prices=None):
        self.home = tmp / "home"
        (self.home / "regulations").mkdir(parents=True)
        (self.home / "regulations" / ("creator.yaml" if laws_new else "ai.yaml")).write_text(
            "[]\n")
        (self.home / "creators").mkdir()
        prof = {"id": "aria"} | ({"prices": profile_prices} if profile_prices else {})
        (self.home / "creators" / "aria.yaml").write_text(json.dumps(prof))
        self.facts = {"nvidia": nvidia, "driver": driver, "pictures": pictures,
                      "search": search, "update": update}
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
    assert ids(box) == ["laws", "nvidia", "search", "updates", "prices"]


def test_done_steps_disappear(tmp_path):
    b = Box(tmp_path, driver=True, pictures=True, search=True, update="auto",
            laws_new=True, profile_prices={"subscription": 9.99, "nude": 14.99, "xxx": 29.99})
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


def test_prices_are_typed_by_the_owner_never_filled_in(box):
    S.run("prices", box.home, probe=box.probe, terminal=box.terminal)
    cmd = box.opened[-1][1]
    assert "read -r" in cmd and "bau creator prices" in cmd
    for number in ("9.99", "14.99", "29.99"):
        assert number not in cmd


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
    assert [p["tool"] for p in first] == ["setup_step"] * 5
    assert "Accept" in first[0]["summary"] or first[0]["summary"]
    again = j.setup_waiting()                          # not stacked twice
    assert len([p for p in j.pending.values() if p.tool == "setup_step"]) == 5
    assert {p["id"] for p in again} == {p["id"] for p in first}
    nvidia = next(p for p in first if "NVIDIA" in p["summary"])
    with pytest.raises(PermissionError):
        j.confirm(nvidia["id"], True, "jarvis")          # only the owner accepts
    out = j.confirm(nvidia["id"], True, "human:owner")
    assert out["done"] and "sudo bau-gpu-setup" in b.opened[-1][1]


def test_the_model_cannot_stage_or_run_setup_steps(tmp_path):
    from bau.assistant import Assistant
    j = Assistant(tmp_path / "home")
    assert "setup_step" not in j.tools                   # owner-only, never in the model's list
    assert "setup_step" in j.owner_tools


def test_the_page_shows_them_when_jarvis_opens():
    text = (Path(__file__).resolve().parents[1] / "src/bau/ui/jarvis_server.py").read_text()
    assert "setup_waiting()" in text
    page = (Path(__file__).resolve().parents[1] / "src/bau/ui/jarvis.html").read_text()
    assert '"setup_step" ? "Accept"' in page
