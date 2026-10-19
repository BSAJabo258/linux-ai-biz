"""A system that lives on a USB stick must not wear the stick out, and sticks must open by
themselves. The owner's laptop runs BAU installed onto a USB stick; after about 15 minutes
files stopped working and the screen went black. Sticks overheat or drop out under an
operating system's constant writes, and Linux then switches the disk to read-only.

bau-usb-guard (every boot) eases the load when / is on a USB disk: noatime and fewer
flushes, no swap on the stick (zram in memory instead). The image also opens sticks and
Windows drives by itself (Thunar's volume manager, exFAT, NTFS). Written before the code."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "image" / "live-build" / "config"
GUARD = CONF / "includes.chroot" / "usr" / "local" / "sbin" / "bau-usb-guard"
UNIT = CONF / "includes.chroot" / "etc" / "systemd" / "system" / "bau-usb-guard.service"
LISTED = set((CONF / "package-lists" / "my-jarvis.list.chroot").read_text().split())

FAKE_LSBLK = """#!/bin/sh
case "$1" in
  -nrso) case "$3" in
      /dev/mapper/root) printf 'root crypt\\nsda3 part\\nsda disk\\n' ;;
      /dev/dm-1) printf 'dm-1 lvm\\nsda3 part\\nsda disk\\n' ;;
      /dev/nvme0n1p3) printf 'nvme0n1p3 part\\nnvme0n1 disk\\n' ;;
    esac ;;
  -dno) echo "$FAKE_TRAN" ;;
esac
"""


def guard(tmp_path, tran):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "log"
    (bin_dir / "lsblk").write_text(FAKE_LSBLK)
    (bin_dir / "findmnt").write_text("#!/bin/sh\necho /dev/mapper/root\n")
    for name in ("mount", "swapoff", "sysctl"):
        (bin_dir / name).write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\n')
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    swaps = tmp_path / "swaps"
    swaps.write_text("Filename Type Size Used Priority\n"
                     "/dev/dm-1 partition 999 0 -2\n"
                     "/dev/zram0 partition 999 0 100\n"
                     "/dev/nvme0n1p3 partition 999 0 -3\n")
    env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin", "FAKE_TRAN": tran,
           "BAU_PROC_SWAPS": str(swaps)}
    r = subprocess.run(["sh", str(GUARD)], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return log.read_text().splitlines() if log.exists() else []


def test_on_a_usb_stick_it_writes_less_and_stops_swapping_onto_it(tmp_path):
    calls = guard(tmp_path, "usb")
    assert "mount -o remount,noatime,commit=60 /" in calls
    assert "swapoff /dev/dm-1" in calls                      # swap on the same stick
    assert not any("zram0" in c or "nvme0n1p3" in c for c in calls)  # nothing else
    assert any(c.startswith("sysctl -q vm.dirty_writeback_centisecs=") for c in calls)


def test_on_the_laptops_own_drive_it_changes_nothing(tmp_path):
    assert guard(tmp_path, "nvme") == []


def test_guard_is_installed_enabled_and_kept_on_the_laptop():
    hook = (CONF / "hooks" / "live" / "0500-bau.hook.chroot").read_text()
    assert "systemctl enable bau-usb-guard.service" in hook
    assert "bau-usb-guard" not in (ROOT / "image" / "live-build" / "live-to-disk.sh").read_text()
    unit = UNIT.read_text()
    assert "ExecStart=/usr/local/sbin/bau-usb-guard" in unit and "Type=oneshot" in unit


def test_swap_goes_to_memory_and_logs_stay_small():
    assert "systemd-zram-generator" in LISTED
    zram = (CONF / "includes.chroot" / "etc" / "systemd" / "zram-generator.conf").read_text()
    assert "[zram0]" in zram and "zstd" in zram and "swap-priority = 100" in zram
    journal = (CONF / "includes.chroot" / "etc" / "systemd" / "journald.conf.d" /
               "bau.conf").read_text()
    assert "SystemMaxUse=" in journal and "volatile" not in journal  # crashes stay readable
    policy = json.loads((CONF / "includes.chroot" / "etc" / "firefox" / "policies" /
                         "policies.json").read_text())
    pref = policy["policies"]["Preferences"]["browser.cache.disk.enable"]
    assert pref["Value"] is False


def test_sticks_and_windows_drives_open_by_themselves():
    assert {"thunar-volman", "gvfs-backends", "exfatprogs", "ntfs-3g",
            "xfce4-power-manager"} <= LISTED


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="needs shellcheck")
def test_shellcheck():
    r = subprocess.run(["shellcheck", str(GUARD)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_the_owners_laptop_gets_sound_bluetooth_and_cooling():
    # Dell XPS 13 9380 (owner's laptop check, 2026-10): the image is built without
    # recommended packages, so these were missing - no sound server (Jarvis's voice), no
    # Bluetooth (the owner's speaker and controller), no Intel thermal daemon, no Intel
    # video decoding. Firmware for its Killer/QCA6174 Wi-Fi and Bluetooth is firmware-atheros.
    need = {"pipewire", "pipewire-pulse", "wireplumber", "pipewire-alsa", "alsa-utils",
            "pavucontrol", "bluez", "blueman", "thermald", "intel-media-va-driver",
            "firmware-atheros", "firmware-sof-signed", "firmware-intel-graphics"}
    assert need <= LISTED, need - LISTED
