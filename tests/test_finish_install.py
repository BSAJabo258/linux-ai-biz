"""Finishing the install by itself: on a laptop installed from the full stick, BAU's own
setup (install.sh) opens in a window at the first login, instead of the owner typing a
command in a terminal. It still asks the owner for what is theirs (the bauadmin password
for sudo, the approval-key passphrase), waits for the internet it needs, and comes back at
the next login until BAU is installed. Written before the code it tests."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FINISH = ROOT / "installer" / "firstboot" / "finish-install.sh"
FIRSTBOOT = ROOT / "installer" / "firstboot" / "firstboot-setup.sh"
AUTOSTART = "/etc/xdg/autostart/bau-finish-install.desktop"


def fake_bin(tmp_path: Path, online_after: int = 0) -> Path:
    """sudo records what it was asked to run; getent fails `online_after` times first."""
    b = tmp_path / "bin"
    b.mkdir()
    (b / "sudo").write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/sudo.log\n')
    (b / "getent").write_text(
        f'#!/bin/sh\nn=$(cat {tmp_path}/tries 2>/dev/null || echo 0)\n'
        f'echo $((n+1)) > {tmp_path}/tries\n[ "$n" -ge {online_after} ]\n')
    for f in b.iterdir():
        f.chmod(0o755)
    return b


def run(tmp_path, payload: bool, stdin: str, online_after: int = 0):
    p = tmp_path / "bau-payload"
    if payload:
        p.mkdir()
        (p / "install.sh").write_text("#!/bin/sh\n")
    b = fake_bin(tmp_path, online_after)
    return subprocess.run(["bash", str(FINISH)], input=stdin, capture_output=True, text=True,
                          env={"PATH": f"{b}:/usr/bin:/bin", "BAU_PAYLOAD": str(p)},
                          timeout=30)


needs_bash = pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")


@needs_bash
def test_runs_bau_setup_with_sudo_so_the_owner_types_the_password(tmp_path):
    r = run(tmp_path, payload=True, stdin="\n")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "sudo.log").read_text().split() == [
        "bash", str(tmp_path / "bau-payload" / "install.sh")]
    assert "password" in r.stdout and "log out" in r.stdout.lower()


@needs_bash
def test_waits_for_the_internet_and_can_be_left_for_later(tmp_path):
    r = run(tmp_path, payload=True, stdin="\n\n\n", online_after=2)
    assert "Wi-Fi" in r.stdout and (tmp_path / "sudo.log").exists()
    later = tmp_path / "later"
    later.mkdir()
    r = run(later, payload=True, stdin="q\n", online_after=99)
    assert r.returncode == 0 and not (later / "sudo.log").exists()
    assert "next" in r.stdout.lower()                 # it says it will come back


@needs_bash
def test_does_nothing_without_a_payload(tmp_path):
    r = run(tmp_path, payload=False, stdin="")
    assert r.returncode == 0 and not (tmp_path / "sudo.log").exists()


def test_never_handles_a_secret_itself():
    text = FINISH.read_text()
    assert "sudo -S" not in text and "| sudo" not in text and "passwd" not in text


def test_first_boot_opens_it_at_login_and_install_sh_stops_it():
    fb = FIRSTBOOT.read_text()
    assert AUTOSTART in fb and "finish-install.sh" in fb and "xfce4-terminal" in fb
    # The one-stick notice gives the plain command (the wipe-gate record is optional).
    one_stick = fb.split("if [ -f /opt/bau-payload/install.sh ]", 1)[1].split("else", 1)[0]
    assert "sudo bash /opt/bau-payload/install.sh\n" in one_stick
    install = (ROOT / "installer" / "payload" / "install.sh").read_text()
    assert f"rm -f {AUTOSTART}" in install


def test_the_stick_carries_it():
    sh = (ROOT / "image" / "build-live.sh").read_text()
    assert "installer/firstboot/finish-install.sh" in sh
    doc = (ROOT / "docs" / "LIVE-USB.md").read_text()
    assert "opens by itself" in doc


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="needs shellcheck")
def test_shellcheck():
    r = subprocess.run(["shellcheck", str(FINISH), str(FIRSTBOOT)], capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stdout
