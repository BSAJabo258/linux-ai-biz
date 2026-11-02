"""The Wi-Fi rescue (the owner's ask, 2026-11-02: something to download that keeps trying
different fixes until the Wi-Fi works, offline). The real script runs here against fake system
commands: a fake MT7921 whose Wi-Fi comes back only after a given fix. Nothing on this
computer is changed. Written before the kit workflow."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "installer" / "bau-wifi-rescue.sh"


def fake_box(tmp: Path, works_after: str, aspm=True, card=True):
    """Fake commands. `works_after`: the marker a fix leaves that brings the Wi-Fi back."""
    bin_ = tmp / "bin"
    bin_.mkdir(parents=True)
    state = tmp / "state"
    state.mkdir()
    lspci = ("03:00.0 Network controller [0280]: MEDIATEK Corp. MT7921 [14c3:7961]" if card
             else "no card")
    cmds = {
        "id": 'echo 0',
        "sleep": 'true',
        "lspci": f'echo "{lspci}"',
        "rfkill": f'touch {state}/radio',
        "modprobe": f'[ "$1" = "-r" ] || touch {state}/reload',
        "modinfo": "echo disable_aspm:disable PCI ASPM support" if aspm else "true",
        "systemctl": f'echo "$*" >> {state}/systemctl; touch {state}/nm',
        "iw": f'touch {state}/region',
        "dpkg": f'touch {state}/dpkg',
        "ip": 'echo "default via 192.168.1.1 dev wlp3s0"',
        "ping": 'exit 0',
        "nmcli": f'''case "$*" in
  *"TYPE,STATE device"*)
    if [ -e {state}/{works_after} ]; then echo wifi:connected; else echo wifi:disconnected; fi ;;
  *"connection show"*) echo "Home:802-11-wireless" ;;
  *) true ;;
esac''',
    }
    for name, body in cmds.items():
        p = bin_ / name
        p.write_text("#!/bin/sh\n" + body + "\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    fw = tmp / "fw"
    fw.mkdir()
    for f in ("WIFI_RAM_CODE_MT7961_1.bin", "WIFI_MT7961_patch_mcu_1_2_hdr.bin"):
        (fw / f).write_bytes(b"fw")
    env = {**os.environ, "PATH": f"{bin_}:/usr/bin:/bin", "BAU_WIFI_ETC": str(tmp / "etc"),
           "BAU_WIFI_FW_DIR": str(fw), "BAU_WIFI_LOG": str(tmp / "log"), "BAU_WIFI_WAIT": "5"}
    return env, state, tmp / "etc"


def run(env):
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60)


def test_it_stops_at_the_first_fix_that_brings_the_wifi_back(tmp_path):
    env, state, etc = fake_box(tmp_path, works_after="nm")      # NetworkManager restarted
    r = run(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'Fixed: the Wi-Fi works after "turn the card\'s power saving off"' in r.stdout
    conf = (etc / "NetworkManager/conf.d/bau-mt7921-powersave.conf").read_text()
    assert "wifi.powersave=2" in conf and "driver:mt7921e" in conf
    assert not (etc / "modprobe.d/bau-mt7921.conf").exists()   # stopped before ASPM


def test_aspm_is_turned_off_only_when_the_driver_has_the_option(tmp_path):
    env, state, etc = fake_box(tmp_path / "a", works_after="never")
    r = run(env)
    assert r.returncode == 1 and "Still no Wi-Fi after every fix" in r.stdout
    assert "disable_aspm=1" in (etc / "modprobe.d/bau-mt7921.conf").read_text()
    env, state, etc = fake_box(tmp_path / "b", works_after="never", aspm=False)
    r = run(env)
    assert "no disable_aspm option; skipped" in r.stdout
    assert not (etc / "modprobe.d/bau-mt7921.conf").exists()


def test_it_says_so_when_the_card_is_not_there(tmp_path):
    env, *_ = fake_box(tmp_path, works_after="never", card=False)
    r = run(env)
    assert r.returncode == 1 and "No MediaTek MT7921 card" in r.stdout


def test_missing_firmware_is_installed_only_from_the_pinned_deb(tmp_path):
    env, state, etc = fake_box(tmp_path, works_after="dpkg")
    for f in Path(env["BAU_WIFI_FW_DIR"]).iterdir():
        f.unlink()
    r = run(env)                                               # no .deb next to the script
    assert "is not next to this script" in r.stdout and not (state / "dpkg").exists()


def test_the_script_is_pinned_and_never_edits_the_boot_loader():
    text = SCRIPT.read_text()
    assert 'FW_SHA256="957f82d72d413f4577f45bfad03237b1dd6f8693eddc226ac452f9c5d4187012"' in text
    assert "sha256sum -c" in text and "firmware-mediatek_20250410-2_all.deb" in text
    assert "grub" not in text.lower()
    assert "modinfo -p" in text


@pytest.mark.parametrize("name", ["wifi-kit.yml"])
def test_the_kit_is_built_from_the_pinned_debian_file(name):
    wf = (ROOT / ".github" / "workflows" / name).read_text()
    assert "firmware-mediatek_20250410-2_all.deb" in wf and "sha256sum -c" in wf
    assert "bau-wifi-rescue.sh" in wf and "bau-wifi-kit" in wf
