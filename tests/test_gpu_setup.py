"""The desktop's graphics driver (docs/DESKTOP.md): `sudo bau-gpu-setup` on the installed
desktop. Debian 13's closed NVIDIA driver 550.163.01 (the open flavour no longer compiles on
kernel 6.12.100+, wiki.debian.org/NvidiaGraphicsDrivers, read 2026-10-25), built by dkms on
this computer so its signing key is this computer's own; with Secure Boot on, the owner
enrolls that key once (wiki.debian.org/SecureBoot). Every step waits for the owner's y.
Package names resolved with apt in a clean debian:trixie (13.7) on 2026-10-25. Written
before the script."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "image" / "live-build" / "config" / "includes.chroot" / "usr" / "local"
          / "sbin" / "bau-gpu-setup")
PACKAGES = ["linux-image-amd64", "linux-headers-amd64", "nvidia-kernel-dkms", "nvidia-driver",
            "nvidia-vulkan-icd", "mokutil"]


def fake_machine(tmp_path, nvidia=True, secure_boot=True, enrolled=False, live=False,
                 nonfree=True, pending=False, online=True):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "calls.log"

    def cmd(name, body):
        f = bin_ / name
        f.write_text(f"#!/bin/sh\necho \"{name} $*\" >> {log}\n{body}\n")
        f.chmod(0o755)

    cmd("id", 'echo 0')
    cmd("getent", "echo '151.101.2.132 deb.debian.org'" if online else "exit 2")
    cmd("apt-get", "exit 0")
    cmd("apt-cache", "echo 'nvidia-driver:'; echo '  Candidate: 550.163.01-2'" if nonfree
        else "echo 'nvidia-driver:'; echo '  Candidate: (none)'")
    sb = "SecureBoot enabled" if secure_boot else "SecureBoot disabled"
    # mokutil 0.7.2's own words (strings of /usr/bin/mokutil in debian:trixie, 2026-10-25)
    test_key = ("echo \"$2 is already in db\"; exit 1" if enrolled
                else "echo \"$2 is already in the enrollment request\"; exit 1" if pending
                else "echo \"$2 is not enrolled\"; exit 0")
    cmd("mokutil", f'case "$1" in --sb-state) echo "{sb}";; --test-key) {test_key};; '
        '*) exit 0;; esac')
    cmd("dkms", "exit 0")
    cmd("systemctl", "exit 0")
    sysfs = tmp_path / "sys"
    dev = sysfs / "0000:01:00.0"
    dev.mkdir(parents=True)
    (dev / "vendor").write_text("0x10de\n" if nvidia else "0x8086\n")
    (dev / "class").write_text("0x030000\n")
    (tmp_path / "dkms").mkdir()
    (tmp_path / "dkms" / "mok.pub").write_text("cert")
    live_dir = tmp_path / "live-medium"
    if live:
        live_dir.mkdir()
    env = {"PATH": f"{bin_}:/usr/bin:/bin", "BAU_SYSFS": str(sysfs),
           "BAU_LIVE_MEDIUM": str(live_dir), "BAU_DKMS_PUB": str(tmp_path / "dkms" / "mok.pub"),
           "BAU_APT_SOURCES": str(tmp_path / "bau-nonfree.sources")}
    return env, log


def run(env, answers=""):
    return subprocess.run(["bash", str(SCRIPT)], env=env, input=answers, capture_output=True,
                          text=True, timeout=60)


def calls(log):
    return log.read_text().splitlines() if log.exists() else []


def test_nothing_is_installed_without_the_owners_yes(tmp_path):
    env, log = fake_machine(tmp_path)
    r = run(env, "n\n")
    assert r.returncode != 0 or "nothing was changed" in r.stdout.lower()
    assert not any(c.startswith("apt-get install") for c in calls(log))


def test_yes_installs_the_closed_driver_with_matching_kernel_headers(tmp_path):
    env, log = fake_machine(tmp_path, secure_boot=False)
    r = run(env, "y\n")
    assert r.returncode == 0, r.stdout + r.stderr
    inst = [c for c in calls(log) if c.startswith("apt-get install")]
    assert len(inst) == 1 and all(p in inst[0].split() for p in PACKAGES)
    assert "nvidia-open-kernel-dkms" not in inst[0]                 # broken on 6.12.100+
    assert "restart" in r.stdout.lower()
    assert not any(c.startswith("mokutil --import") for c in calls(log))


def test_secure_boot_on_asks_to_enroll_this_computers_key_once(tmp_path):
    env, log = fake_machine(tmp_path, secure_boot=True, enrolled=False)
    r = run(env, "y\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert any(c.startswith(f"mokutil --import {env['BAU_DKMS_PUB']}") for c in calls(log))
    assert "Enroll MOK" in r.stdout and "password" in r.stdout.lower()


def test_an_enrolled_key_is_not_enrolled_again(tmp_path):
    env, log = fake_machine(tmp_path, secure_boot=True, enrolled=True)
    run(env, "y\n")
    assert not any(c.startswith("mokutil --import") for c in calls(log))


def test_a_key_waiting_for_the_blue_screen_is_not_imported_twice(tmp_path):
    env, log = fake_machine(tmp_path, secure_boot=True, pending=True)
    r = run(env, "y\n")
    assert not any(c.startswith("mokutil --import") for c in calls(log))
    assert "Enroll MOK" in r.stdout


def test_no_nvidia_card_means_nothing_to_do(tmp_path):
    env, log = fake_machine(tmp_path, nvidia=False)
    r = run(env, "y\n")
    assert r.returncode != 0 and "no nvidia" in r.stdout.lower()
    assert not any(c.startswith("apt-get") for c in calls(log))


def test_refuses_on_the_live_stick(tmp_path):
    # The driver and its key belong on the installed drive; the live system forgets both.
    env, log = fake_machine(tmp_path, live=True)
    r = run(env, "y\n")
    assert r.returncode != 0 and "install bau to a disk first" in r.stdout.lower()
    assert not any(c.startswith("apt-get") for c in calls(log))


def test_adds_debians_non_free_area_only_when_it_is_missing(tmp_path):
    env, _ = fake_machine(tmp_path, nonfree=False)
    run(env, "y\n")
    src = Path(env["BAU_APT_SOURCES"]).read_text()
    assert "non-free" in src and "trixie-security" in src
    assert "/usr/share/keyrings/debian-archive-keyring.gpg" in src     # signed, as Debian's
    (tmp_path / "b").mkdir()
    env2, _ = fake_machine(tmp_path / "b", nonfree=True)
    run(env2, "y\n")
    assert not Path(env2["BAU_APT_SOURCES"]).exists()


def test_the_script_is_on_the_stick_and_runnable():
    hook = (SCRIPT.parents[4] / "hooks" / "live" / "0500-bau.hook.chroot").read_text()
    assert "/usr/local/sbin/bau-gpu-setup" in hook
    assert os.access(SCRIPT, os.X_OK)


def test_no_internet_is_said_plainly_before_anything_runs(tmp_path):
    # The owner's desktop, 2026-10-27: offline, apt only warned and then said "Unable to
    # locate package nvidia-driver" four times.
    env, log = fake_machine(tmp_path, online=False)
    r = run(env, "y\n")
    assert r.returncode != 0 and "No internet" in r.stdout and "network cable" in r.stdout
    assert not any(c.startswith("apt-get") for c in calls(log))


def offline_pack(tmp_path, env, files=None, kernel="6.12.113+deb13-amd64"):
    import hashlib
    pack = tmp_path / "stick" / "BAU-PACK" / "nvidia"
    pack.mkdir(parents=True)
    (pack / "KERNEL").write_text("6.12.113+deb13-amd64\n")
    files = files or {"nvidia-driver_550.163.01-2_amd64.deb": b"driver",
                      "dkms_3.2.2-1~deb13u1_all.deb": b"dkms"}
    pins = tmp_path / "pins"
    pins.write_text("".join(f"{hashlib.sha256(v).hexdigest()}  {k}\n" for k, v in files.items()))
    for k, v in files.items():
        (pack / k).write_bytes(v)
    bin_ = Path(env["PATH"].split(":")[0])
    (bin_ / "uname").write_text(f"#!/bin/sh\necho {kernel}\n")
    (bin_ / "uname").chmod(0o755)
    return {**env, "BAU_NVIDIA_PACK": str(pack), "BAU_OFFLINE_PINS": str(pins)}, pack


def test_offline_the_driver_comes_from_the_pack_checked_against_the_pins(tmp_path):
    # 2026-10-28: the desktop's Wi-Fi kept dropping, so the pack carries the driver. The real
    # files were installed this way on the stick's own system with the network off.
    env, log = fake_machine(tmp_path, online=False)
    env, pack = offline_pack(tmp_path, env)
    r = run(env, "y\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "uses the driver files on the stick" in r.stdout
    inst = [c for c in calls(log) if c.startswith("apt-get")]
    assert inst and all("update" not in c for c in inst)              # nothing from the internet
    assert f"{pack}/nvidia-driver_550.163.01-2_amd64.deb" in inst[0]
    assert "linux-image-amd64" not in inst[0]                         # no new kernel offline


def test_offline_a_damaged_file_or_another_kernel_changes_nothing(tmp_path):
    env, log = fake_machine(tmp_path, online=False)
    env, pack = offline_pack(tmp_path, env)
    (pack / "dkms_3.2.2-1~deb13u1_all.deb").write_bytes(b"swapped")
    r = run(env, "y\n")
    assert r.returncode != 0 and "missing or damaged" in r.stdout
    assert not any(c.startswith("apt-get") for c in calls(log))
    (tmp_path / "k").mkdir()
    env2, log2 = fake_machine(tmp_path / "k", online=False)
    env2, _ = offline_pack(tmp_path / "k", env2, kernel="6.12.120+deb13-amd64")
    r = run(env2, "y\n")
    assert r.returncode != 0 and "built for Linux 6.12.113" in r.stdout
    assert not any(c.startswith("apt-get") for c in calls(log2))


def test_the_script_and_the_windows_pack_pin_the_same_driver_files():
    import re
    ps1 = (ROOT / "installer" / "bau-pack-make.ps1").read_text()
    win = set(re.findall(r'File = "([^"]+)"; Archive = "[^"]+"; Pool = "[^"]+"; Size = \d+; '
                         r'Sha256 = "([0-9a-f]{64})"', ps1))
    script = SCRIPT.read_text()
    block = script.split("OFFLINE_PINS=(", 1)[1].split(")", 1)[0]
    pins = {(f, h) for h, f in re.findall(r'"([0-9a-f]{64})  ([^"]+)"', block)}
    assert len(pins) == 63 and pins == win
    assert '$BauNvidiaKernel = "6.12.113+deb13-amd64"' in ps1
    assert 'OFFLINE_KERNEL="6.12.113+deb13-amd64"' in script
