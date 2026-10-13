"""Finishing the install by itself: on a laptop installed from the full stick, BAU's own
setup (install.sh) opens in a window at the first login, instead of the owner typing a
command in a terminal. It still asks the owner for what is theirs (the bauadmin password
for sudo, the approval-key passphrase) and comes back at the next login until BAU is
installed. The stick carries every package install.sh needs, so it first installs with no
network at all; only if that fails does it ask for Wi-Fi. Written before the code it tests."""

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
    # sudo records what it runs; --offline fails when OFFLINE_FAILS is set (older image).
    (b / "sudo").write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/sudo.log\n'
                            '[ -n "$OFFLINE_FAILS" ] && [ "$3" = --offline ] && exit 1\n'
                            'exit 0\n')
    (b / "getent").write_text(
        f'#!/bin/sh\nn=$(cat {tmp_path}/tries 2>/dev/null || echo 0)\n'
        f'echo $((n+1)) > {tmp_path}/tries\n[ "$n" -ge {online_after} ]\n')
    for f in b.iterdir():
        f.chmod(0o755)
    return b


def run(tmp_path, payload: bool, stdin: str, online_after: int = 0, offline_fails=False):
    p = tmp_path / "bau-payload"
    if payload:
        p.mkdir()
        (p / "install.sh").write_text("#!/bin/sh\n")
    b = fake_bin(tmp_path, online_after)
    return subprocess.run(["bash", str(FINISH)], input=stdin, capture_output=True, text=True,
                          env={"PATH": f"{b}:/usr/bin:/bin", "BAU_PAYLOAD": str(p),
                               **({"OFFLINE_FAILS": "1"} if offline_fails else {})},
                          timeout=30)


needs_bash = pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")


@needs_bash
def test_installs_with_no_network_first(tmp_path):
    r = run(tmp_path, payload=True, stdin="\n", online_after=99)     # never online
    assert r.returncode == 0, r.stderr
    install = str(tmp_path / "bau-payload" / "install.sh")
    assert (tmp_path / "sudo.log").read_text().split() == ["bash", install, "--offline"]
    assert "password" in r.stdout and "log out" in r.stdout.lower()
    assert "Wi-Fi" not in r.stdout                        # no network needed, none asked


@needs_bash
def test_falls_back_to_the_internet_when_the_stick_lacks_a_package(tmp_path):
    r = run(tmp_path, payload=True, stdin="\n\n\n", online_after=2, offline_fails=True)
    install = str(tmp_path / "bau-payload" / "install.sh")
    runs = (tmp_path / "sudo.log").read_text().splitlines()
    assert runs == [f"bash {install} --offline", f"bash {install}"]
    assert "Wi-Fi" in r.stdout
    later = tmp_path / "later"
    later.mkdir()
    r = run(later, payload=True, stdin="q\n", online_after=99, offline_fails=True)
    assert r.returncode == 0 and "next" in r.stdout.lower()    # it says it will come back
    assert len((later / "sudo.log").read_text().splitlines()) == 1


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
