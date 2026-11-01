"""Automatic updates on the owner's desktop (the owner's choice, 2026-11-01: "fully automatic").
Once a night the desktop fetches the wheel CI built from a green main, checks its SHA-256,
installs it, restarts Mission Control and checks it answers; if anything fails it puts the
previous wheel back by itself. Off until the owner turns it on (no default). Fakes only: no
network, no pip, no systemctl. Written before the code."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from bau import update as U


def zwheel(tag, updater=True):
    """A tiny wheel-shaped zip; real builds carry bau/update.py, the stick's first one did not."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("bau/__init__.py", tag)
        if updater:
            z.writestr("bau/update.py", "")
    return buf.getvalue()


WHEEL = zwheel("new")
NAME = "bau-0.3.0-py3-none-any.whl"
COMMIT = "a" * 40


def manifest(**over):
    m = {"commit": COMMIT, "wheel": NAME, "sha256": hashlib.sha256(WHEEL).hexdigest(),
         "built": "2026-11-01T23:00:00Z"}
    return {**m, **over}


class Net:
    def __init__(self, man=None, body=WHEEL):
        self.man, self.body, self.urls = man or manifest(), body, []

    def __call__(self, req, timeout=0):
        url = getattr(req, "full_url", req)
        self.urls.append(url)
        assert url.startswith(U.RELEASE)
        return _Resp(json.dumps(self.man).encode() if url.endswith("bau-update.json")
                     else self.body)


class _Resp:
    def __init__(self, data):
        self.data = data

    def read(self, n=-1):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Box:
    """The desktop: its commands are recorded; fail_on makes one kind of command fail."""

    def __init__(self, tmp, fail_on=()):
        self.cmds, self.fail_on = [], set(fail_on)
        self.state, self.conf = tmp / "update", tmp / "update.conf"
        self.first = tmp / "payload-wheels"
        self.first.mkdir()
        (self.first / "bau-0.2.0-py3-none-any.whl").write_bytes(zwheel("old"))

    new_installed = False

    def run(self, cmd):
        self.cmds.append(cmd)
        installing = "install" in cmd and str(cmd[-1]).endswith(".whl")
        if installing:                        # the download waits in update/incoming
            self.new_installed = "incoming" in Path(cmd[-1]).parts
        kind = ("pip-new" if installing and self.new_installed else "pip-old" if installing
                else "import" if "-c" in cmd else cmd[0] if cmd[0] == "systemctl" else "other")
        if kind == "import" and not self.new_installed:
            return 0                          # the previous build always worked
        return 1 if kind in self.fail_on else 0

    def go(self, net=None, mode="auto", ui_ok=True):
        if mode:
            self.conf.write_text(f"mode={mode}\n")
        return U.run(opener=net or Net(), runner=self.run, state_dir=self.state,
                     conf=self.conf, first_dir=self.first, audit=self.audited.append,
                     ui_check=lambda: ui_ok or not self.new_installed, sleep=lambda s: None)

    audited: list = []


@pytest.fixture
def box(tmp_path):
    b = Box(tmp_path)
    b.audited = []
    return b


def pips(box):
    return [Path(c[-1]).name for c in box.cmds if "install" in c and str(c[-1]).endswith(".whl")]


def test_off_until_the_owner_turns_it_on(box):
    net = Net()
    assert box.go(net, mode=None)["result"] == "off"
    assert box.go(net, mode="off")["result"] == "off"
    assert not net.urls and not box.cmds


def test_a_new_tested_build_is_installed_and_kept(box):
    out = box.go()
    assert out["result"] == "installed" and out["commit"] == COMMIT
    assert pips(box) == [NAME]
    pip = next(c for c in box.cmds if "install" in c)
    assert "--no-index" in pip and "--no-deps" in pip and "--force-reinstall" in pip
    assert ["systemctl", "restart", "bau-ui.service"] in box.cmds
    assert (box.state / "current" / NAME).read_bytes() == WHEEL
    assert json.loads((box.state / "state.json").read_text())["commit"] == COMMIT
    assert box.audited[-1][0] == "update.installed"
    assert U.status(box.state, box.conf)["last"]["result"] == "installed"


def test_the_same_build_twice_does_nothing(box):
    box.go()
    box.cmds.clear()
    assert box.go()["result"] == "up to date" and not box.cmds


@pytest.mark.parametrize("bad", [{"sha256": "0" * 64}, {"sha256": "nope"}, {"commit": "main"},
                                 {"wheel": "../evil.whl"}, {"wheel": "other-1.0-py3-none-any.whl"}])
def test_a_wrong_or_odd_manifest_is_refused_before_anything_installs(box, bad):
    out = box.go(Net(manifest(**bad)))
    assert out["result"] == "refused" and not pips(box)
    assert box.audited[-1][0] == "update.refused"


def test_a_failed_health_check_puts_the_previous_build_back(box):
    box.fail_on = {"import"}
    out = box.go()
    assert out["result"] == "rolled back"
    assert pips(box) == [NAME, "bau-0.2.0-py3-none-any.whl"]    # the stick's own wheel
    assert not (box.state / "current" / NAME).exists()
    assert box.audited[-1][0] == "update.rolled_back"
    assert U.status(box.state, box.conf)["last"]["result"] == "rolled back"


def test_mission_control_not_answering_also_rolls_back(box):
    assert box.go(ui_ok=False)["result"] == "rolled back"


def test_after_one_good_update_the_kept_build_is_the_one_to_go_back_to(box):
    box.go()
    box.cmds.clear()
    box.fail_on = {"import"}
    new2 = zwheel("new2")
    out = box.go(Net(manifest(commit="b" * 40, sha256=hashlib.sha256(new2).hexdigest()),
                     body=new2))
    assert out["result"] == "rolled back"
    back = [c[-1] for c in box.cmds if "install" in c and str(c[-1]).endswith(".whl")][-1]
    assert Path(back) == box.state / "current" / NAME and Path(back).read_bytes() == WHEEL


def test_no_build_to_go_back_to_means_no_update(box):
    for f in box.first.iterdir():
        f.unlink()
    out = box.go()
    assert out["result"] == "refused" and "go back" in out["why"] and not pips(box)


def test_an_update_that_cannot_be_put_back_is_said_plainly(box):
    box.fail_on = {"pip-old"}
    out = box.go(ui_ok=False)
    assert out["result"] == "broken" and "sudo" in out["why"]
    assert box.audited[-1][0] == "update.broken"


def test_mode_is_written_only_as_auto_or_off(tmp_path):
    conf = tmp_path / "update.conf"
    U.set_mode("auto", conf)
    assert U.mode(conf) == "auto"
    U.set_mode("off", conf)
    assert U.mode(conf) == "off"
    with pytest.raises(ValueError):
        U.set_mode("sometimes", conf)
    conf.write_text("mode=yes please\n")
    assert U.mode(conf) is None


def test_the_briefing_mentions_last_nights_update(tmp_path, monkeypatch):
    state = tmp_path / "update"
    state.mkdir()
    monkeypatch.setattr(U, "STATE", state)
    from bau.assistant import Assistant
    j = Assistant(tmp_path / "home")
    assert j.facts()["update"] is None                    # nothing happened: nothing said
    U._record(state, {"result": "rolled back", "commit": COMMIT, "why": "import failed"})
    f = j.facts()
    assert f["update"]["result"] == "rolled back"
    text = j.plain_briefing(f)
    assert "update" in text and "previous version" in text


# ------------------------------------------------------------------ the pieces around it
ROOT = Path(__file__).resolve().parents[1]


def test_ci_builds_the_wheel_only_from_a_green_main():
    wf = (ROOT / ".github" / "workflows" / "update-wheel.yml").read_text()
    assert "workflow_run" in wf and "workflows: [ci]" in wf
    assert "github.event.workflow_run.conclusion == 'success'" in wf
    assert "github.event.workflow_run.head_branch == 'main'" in wf
    assert "github.event.workflow_run.event == 'push'" in wf
    assert "head_sha" in wf and "bau-update.json" in wf and "contents: write" in wf
    # The owner's first run (2026-11-01) hit the gap while the release was deleted and made
    # again: 404. Files are replaced in place, the wheel before the record that names it.
    assert "release delete" not in wf
    assert wf.index("dist/bau-*.whl --clobber") < wf.index("dist/bau-update.json --clobber")


def test_the_timer_runs_nightly_as_root_and_install_enables_it():
    unit = (ROOT / "installer" / "payload" / "systemd" / "bau-update.service").read_text()
    timer = (ROOT / "installer" / "payload" / "systemd" / "bau-update.timer").read_text()
    assert "ExecStart=/opt/bau/venv/bin/bau update now" in unit and "User=" not in unit
    assert "OnCalendar=" in timer and "Persistent=true" in timer
    install = (ROOT / "installer" / "payload" / "install.sh").read_text()
    assert "bau-update.timer" in install


def test_the_one_time_setup_for_an_installed_desktop_checks_and_matches():
    first = (ROOT / "installer" / "bau-update-first.sh").read_text()
    assert "sha256sum -c" in first and "/run/live/medium" in first
    assert "bau update auto" in first and "bau update keep" in first
    for unit in ("bau-update.service", "bau-update.timer"):
        text = (ROOT / "installer" / "payload" / "systemd" / unit).read_text()
        assert f"/etc/systemd/system/{unit} <<'UNIT'\n{text}UNIT\n" in first


def test_bau_update_status_and_root_only_changes(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    monkeypatch.setattr(U, "STATE", tmp_path / "u")
    monkeypatch.setattr(U, "CONF", tmp_path / "update.conf")
    monkeypatch.setattr("bau.update.status", lambda s=None, c=None: {"mode": U.mode(
        tmp_path / "update.conf") or "not chosen"})
    assert main(["update", "status"]) == 0
    assert "not chosen" in capsys.readouterr().out
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    with pytest.raises(SystemExit, match="sudo"):
        main(["update", "auto"])


# The owner's desktop, 2026-11-01: an update went back to the stick's own build, which has no
# updater, so `bau update` was gone and nothing could update again.
def test_never_goes_back_to_a_build_without_the_updater(box):
    (box.first / "bau-0.2.0-py3-none-any.whl").write_bytes(zwheel("stick", updater=False))
    out = box.go()
    assert out["result"] == "refused" and "bau-update-first.sh" in out["why"]
    assert not pips(box)


def test_mission_control_is_only_required_if_it_was_running(box):
    box.fail_on = {"systemctl"}                     # bau-ui not active before the update
    assert box.go(ui_ok=False)["result"] == "installed"


def test_keep_records_the_setup_build_as_the_way_back(tmp_path):
    w = tmp_path / NAME
    w.write_bytes(WHEEL)
    U.keep(w, COMMIT, tmp_path / "u")
    assert (tmp_path / "u" / "current" / NAME).read_bytes() == WHEEL
    assert U.status(tmp_path / "u", tmp_path / "c")["installed_commit"] == COMMIT
    old = tmp_path / "bau-0.2.0-py3-none-any.whl"
    old.write_bytes(zwheel("stick", updater=False))
    with pytest.raises(ValueError):
        U.keep(old, COMMIT, tmp_path / "u")
    with pytest.raises(ValueError):
        U.keep(w, "main", tmp_path / "u")
