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
      /dev/sdb1) printf 'sdb1 part\\nsdb disk\\n' ;;
    esac ;;
  -dno) echo "$FAKE_TRAN" ;;
esac
"""


FAKE_FINDMNT = """#!/bin/sh
case "$*" in
  "-no SOURCE /") echo "${FAKE_ROOT:-/dev/mapper/root}" ;;
  "-no SOURCE /run/live/medium") [ -n "${FAKE_MEDIUM:-}" ] && echo "$FAKE_MEDIUM" || exit 1 ;;
  "-rno TARGET") printf '/\\n/run/live/medium\\n/run/live/persistence/dm-0\\n/home\\n' ;;
esac
"""


def guard(tmp_path, tran, **fake):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    log = tmp_path / "log"
    (bin_dir / "lsblk").write_text(FAKE_LSBLK)
    (bin_dir / "findmnt").write_text(FAKE_FINDMNT)
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
           "BAU_PROC_SWAPS": str(swaps), **fake}
    r = subprocess.run(["sh", str(GUARD)], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return log.read_text().splitlines() if log.exists() else []


def test_on_a_usb_stick_it_writes_less_and_stops_swapping_onto_it(tmp_path):
    calls = guard(tmp_path, "usb")
    assert "mount -o remount,noatime,commit=60 /" in calls
    assert "swapoff /dev/dm-1" in calls                      # swap on the same stick
    assert not any("zram0" in c or "nvme0n1p3" in c for c in calls)  # nothing else
    assert any(c.startswith("sysctl -q vm.dirty_writeback_centisecs=") for c in calls)


DIRTY = ("sysctl -q vm.dirty_background_bytes=16777216 vm.dirty_bytes=50331648")


def test_on_a_usb_stick_it_writes_in_small_steps(tmp_path):
    # With 8 GB of memory Linux gathers over a gigabyte of unwritten data and then writes
    # it to the stick in one go (a model download, the pack); everything that must read
    # from the stick meanwhile, the whole desktop, waits and seems dead.
    assert DIRTY in guard(tmp_path, "usb")


def test_the_live_stick_eases_its_storage_too(tmp_path):
    # On the live stick / is an overlay in memory, but the system and the encrypted
    # storage are both on the stick it started from.
    calls = guard(tmp_path, "usb", FAKE_ROOT="overlay", FAKE_MEDIUM="/dev/sdb1")
    assert DIRTY in calls
    assert "mount -o remount,noatime,commit=60 /run/live/persistence/dm-0" in calls
    assert not any(c.endswith(" /") for c in calls) and not any("swapoff" in c for c in calls)


def test_a_live_system_started_from_a_drive_changes_nothing(tmp_path):
    assert guard(tmp_path / "a", "nvme", FAKE_ROOT="overlay", FAKE_MEDIUM="/dev/sdb1") == []
    assert guard(tmp_path / "b", "usb", FAKE_ROOT="overlay") == []      # no medium found


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


# ------------------------------------------------------------------ the owner's crashes
# On the owner's Dell XPS 13 9380 the desktop died a few minutes after unlocking: the
# taskbar went first, then everything. The two known causes on that laptop are both
# switched off at boot: the screen's power saving (PSR on Intel graphics freezes parts of
# the picture) and power saving on the USB-C / Thunderbolt ports (a stick behind them
# drops out, and nothing more can be loaded from it). The health console on Ctrl+Alt+F9
# keeps running even when the stick is gone, so the next crash leaves proof on screen.

STEADY = ("i915.enable_psr=0", "usbcore.autosuspend=-1", "pcie_port_pm=off")
CONSOLE = CONF / "includes.chroot" / "usr" / "local" / "sbin" / "bau-health-console"
CONSOLE_UNIT = UNIT.parent / "bau-health-console.service"


def test_the_stick_and_the_installed_laptop_boot_steady():
    live = (ROOT / "image" / "live-build" / "auto" / "config").read_text()
    append = live.split("--bootappend-live", 1)[1].split("\n", 1)[0]
    preseed = (CONF / "includes.installer" / "preseed.cfg").read_text()
    opts = [ln for ln in preseed.splitlines()
            if ln.startswith("d-i debian-installer/add-kernel-opts")]
    assert len(opts) == 1
    for o in STEADY:
        assert o in append, o
        assert o in opts[0], o


def test_health_console_runs_on_its_own_screen_and_comes_back():
    unit = CONSOLE_UNIT.read_text()
    assert "ExecStart=/usr/local/sbin/bau-health-console" in unit
    assert "TTYPath=/dev/tty9" in unit and "StandardOutput=tty" in unit
    assert "Restart=always" in unit
    hook = (CONF / "hooks" / "live" / "0500-bau.hook.chroot").read_text()
    assert "systemctl enable bau-health-console.service" in hook
    assert "bau-health-console" in hook and "chmod 0755" in hook


def fake_machine(tmp_path, mem_kb=5_000_000, stick=True, temp=52000, dirty_kb=2048):
    proc, sys_ = tmp_path / "proc", tmp_path / "sys"
    proc.mkdir(parents=True)
    (proc / "meminfo").write_text(f"MemTotal: 7900000 kB\nMemAvailable: {mem_kb} kB\n"
                                  f"Dirty: {dirty_kb} kB\nWriteback: 1024 kB\n")
    (proc / "loadavg").write_text("0.52 0.40 0.31 1/300 4242\n")
    (proc / "cmdline").write_text("boot=live " + " ".join(STEADY) + "\n")
    wl = sys_ / "class" / "net" / "wlp2s0"
    (wl / "wireless").mkdir(parents=True)
    (wl / "operstate").write_text("down\n")
    drv = sys_ / "bus" / "pci" / "drivers" / "ath10k_pci"
    drv.mkdir(parents=True)
    (wl / "device").mkdir()
    (wl / "device" / "driver").symlink_to(drv)
    rf = sys_ / "class" / "rfkill" / "rfkill0"
    rf.mkdir(parents=True)
    (rf / "type").write_text("wlan\n")
    (rf / "soft").write_text("1\n")
    (rf / "hard").write_text("0\n")
    tz = sys_ / "class" / "thermal" / "thermal_zone0"
    tz.mkdir(parents=True)
    (tz / "temp").write_text(f"{temp}\n")
    if stick:
        (sys_ / "block" / "sdb").mkdir(parents=True)
    else:
        (sys_ / "block").mkdir(parents=True)
    fake_dmesg = tmp_path / "dmesg"
    fake_dmesg.write_text("#!/bin/sh\necho 'ath10k_pci 0000:02:00.0: firmware crashed!'\n")
    fake_dmesg.chmod(0o755)
    return {"BAU_PROC": str(proc), "BAU_SYS": str(sys_), "BAU_STICK": "sdb",
            "BAU_DMESG": str(fake_dmesg)}


def console(tmp_path, **kw):
    env = {**os.environ, **fake_machine(tmp_path, **kw)}
    r = subprocess.run(["bash", str(CONSOLE), "--once"], capture_output=True, text=True,
                       env=env, timeout=20)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_health_console_tells_why_wifi_is_off_and_shows_the_vitals(tmp_path):
    out = console(tmp_path)
    assert "wlp2s0" in out and "ath10k_pci" in out
    assert "switched off" in out                        # rfkill soft block, in plain words
    assert "firmware crashed" in out                    # the kernel's own Wi-Fi lines
    assert "4882 MB free" in out and "52" in out        # memory and heat
    assert "i915.enable_psr=0" in out                   # the steady options are in use
    assert "STICK GONE" not in out
    assert "3 MB waiting to be written" in out


def test_health_console_shows_when_writing_to_the_stick_holds_everything_up(tmp_path):
    out = console(tmp_path, dirty_kb=600_000)
    assert "DISK BUSY" in out and "586 MB" in out


def test_health_console_shouts_when_the_stick_drops_out_or_memory_runs_out(tmp_path):
    out = console(tmp_path / "a", stick=False)
    assert "STICK GONE" in out and "photo" in out
    out = console(tmp_path / "b", mem_kb=200_000, temp=97000)
    assert "MEMORY ALMOST FULL" in out and "HOT" in out


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="needs shellcheck")
def test_health_console_shellcheck():
    r = subprocess.run(["shellcheck", str(CONSOLE)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


# ------------------------------------------------------------------ sound and Bluetooth
# The owner's laptop had no sound and Bluetooth "pops up but does nothing". The stick is
# built with recommends off, and Debian 13.7's own package data (checked 2026-10-20 with
# apt in a clean trixie) shows these only arrive as Recommends/Suggests, so they were
# never installed: alsa-ucm-conf and alsa-topology-conf (libasound2-data Recommends; "absolutely
# necessary to make some sound hardware work"), libspa-0.2-bluetooth (wireplumber Suggests;
# PipeWire's Bluetooth audio).

def test_stick_carries_sound_routing_and_bluetooth_audio():
    for pkg in ("alsa-ucm-conf", "alsa-topology-conf", "libspa-0.2-bluetooth"):
        assert pkg in LISTED, pkg


# ------------------------------------------------------------------ memory on the live stick
# The owner's stick in a VM (2026-10-20): "/" is a 3.7 GB RAM overlay; filling it stopped
# even a 94 KB install ("not enough free space in /var/cache/apt/archives").

def test_the_local_model_goes_first_when_memory_runs_out():
    unit = (CONF / "includes.chroot" / "etc" / "systemd" / "system" / "bau-llm.service").read_text()
    assert "OOMScoreAdjust=500" in unit


def test_installs_do_not_keep_a_second_copy_in_memory():
    conf = CONF / "includes.chroot" / "etc" / "apt" / "apt.conf.d" / "90bau-no-cache"
    assert 'APT::Keep-Downloaded-Packages "false";' in conf.read_text()


def test_install_to_disk_is_on_the_live_desktop_and_only_there():
    bin_ = CONF / "includes.chroot" / "usr" / "local" / "bin" / "bau-install-to-disk"
    text = bin_.read_text()
    assert "NEVER pick this one" in text and "systemctl reboot" in text
    assert 'if [[ ${answer} == y ]]' in text                 # restarts only on the owner's y
    assert not any(w in text for w in ("mkfs", "wipefs", "parted", "dd if="))   # changes nothing
    apps = CONF / "includes.chroot" / "usr" / "share" / "applications"
    app = apps / "bau-install-to-disk.desktop"
    assert "Exec=bau-install-to-disk" in app.read_text()
    hook = (CONF / "hooks" / "live" / "0500-bau.hook.chroot").read_text()
    assert "/usr/local/bin/bau-install-to-disk" in hook       # made runnable in the image
    l2d = (CONF.parent / "live-to-disk.sh").read_text()
    assert "bau-install-to-disk.desktop" in l2d               # gone once BAU is on a disk


# ------------------------------------------------------------------ the boss answers in time
# The owner's pack install said "qwen3.5-4b did not answer". Reproduced 2026-10-21 with the
# stick's own llama-server (v0.6.0, d812350) and the pinned GGUF: Qwen3.5 thinks by default
# and spent all 1024 tokens of "Say hello" thinking (190 s, empty reply). With
# LLAMA_ARG_REASONING=off (the server's env for --reasoning off) BAU's own benchmark gave
# reply_ok and tool_calls true in 15 s.

def test_the_local_model_server_does_not_think_out_loud():
    unit = (CONF / "includes.chroot" / "etc" / "systemd" / "system" / "bau-llm.service").read_text()
    assert "Environment=LLAMA_ARG_REASONING=off" in unit
    # systemd.exec: "Settings from these files override settings made with Environment=",
    # so the owner can still turn thinking on in /etc/bau/llm.env.
    assert "EnvironmentFile=/etc/bau/llm.env" in unit


def test_the_prompt_cache_cannot_take_the_whole_laptop():
    unit = (CONF / "includes.chroot" / "etc" / "systemd" / "system" / "bau-llm.service").read_text()
    assert "Environment=LLAMA_ARG_CACHE_RAM=1024" in unit     # default would be 8192 MiB


# ------------------------------------------------------------------ the model leaves a core free
# Measured 2026-10-21 with the stick's llama-server (v0.6.0, d812350), Qwen3.5-4B Q4_K_M, on
# 4 cores: alone it wrote 6.2 tokens/s. With the Jarvis page open and "thinking" (Chromium
# drawing its animations) the server's default of every core fell to 0.19 tokens/s, 30 times
# slower; with one core left free (-t 3) it wrote 3.2 tokens/s. --poll 0 did not help.

START = CONF / "includes.chroot" / "usr" / "local" / "bin" / "bau-llm-start"


def _threads(tmp_path, cores, logical, preset=None, nvidia=False, device=None):
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    rows = "\n".join(f"{c % cores},0" for c in range(logical))
    (fake / "lscpu").write_text(f"#!/bin/sh\necho '# Core,Socket'\nprintf '%s\\n' '{rows}'\n")
    server = tmp_path / "llama-server"
    server.write_text('#!/bin/sh\necho "threads=${LLAMA_ARG_THREADS} args=$*"\n'
                      'echo "device=${LLAMA_ARG_DEVICE:-}"\n')
    for f in (fake / "lscpu", server):
        f.chmod(0o755)
    proc = tmp_path / "nvidia-version"
    if nvidia:
        proc.write_text("NVRM version: NVIDIA UNIX x86_64 Kernel Module  550.163.01\n")
    elif proc.exists():
        proc.unlink()
    env = {"PATH": f"{fake}:/usr/bin:/bin", "BAU_LLAMA_SERVER": str(server),
           "BAU_NVIDIA_PROC": str(proc)}
    if preset:
        env["LLAMA_ARG_THREADS"] = preset
    if device is not None:
        env["LLAMA_ARG_DEVICE"] = device
    out = subprocess.run(["bash", str(START), "--port", "8080"], env=env,
                         capture_output=True, text=True, check=True).stdout.strip()
    first, _, dev = out.partition("\ndevice=")
    _threads.device = dev
    return first


def test_the_model_leaves_one_core_for_the_desktop_and_jarvis(tmp_path):
    assert _threads(tmp_path, cores=4, logical=8) == "threads=3 args=--port 8080"  # XPS 9380
    assert _threads(tmp_path, cores=1, logical=2) == "threads=1 args=--port 8080"  # never 0
    assert _threads(tmp_path, cores=4, logical=8, preset="4") == "threads=4 args=--port 8080"
    unit = (CONF / "includes.chroot" / "etc" / "systemd" / "system" / "bau-llm.service").read_text()
    assert "ExecStart=/usr/local/bin/bau-llm-start " in unit
    hook = (CONF / "hooks" / "live" / "0500-bau.hook.chroot").read_text()
    assert "/usr/local/bin/bau-llm-start" in hook                 # made runnable in the image


# ------------------------------------------------------------------ the graphics card, only NVIDIA
# The desktop (RTX 3060, owner's report 2026-10-23) runs the model on the card through
# llama.cpp's Vulkan backend. llama-server's default is "-ngl auto" on any Vulkan device it
# finds (v0.6.0 --help), so without NVIDIA's driver loaded BAU says LLAMA_ARG_DEVICE=none:
# the laptop's built-in graphics would be slower than its processor, not faster.

def test_the_card_is_used_only_when_the_nvidia_driver_is_loaded(tmp_path):
    _threads(tmp_path, cores=4, logical=8)                       # laptop, no NVIDIA driver
    assert _threads.device == "none"
    _threads(tmp_path, cores=12, logical=20, nvidia=True)        # desktop, driver loaded
    assert _threads.device == ""                                 # llama-server's own auto + fit
    _threads(tmp_path, cores=4, logical=8, device="Vulkan0")     # the owner's llm.env wins
    assert _threads.device == "Vulkan0"


def test_the_model_engine_carries_the_graphics_card_backend():
    # llama.cpp's Vulkan backend (docs/build.md: libvulkan-dev glslc spirv-headers,
    # -DGGML_VULKAN=1), built as its own loadable part next to the processor ones
    # (GGML_BACKEND_DL), so the same engine runs the laptop (no card) and the desktop.
    inside = (CONF.parents[1] / "inside.sh").read_text()
    assert "-DGGML_VULKAN=ON" in inside and "-DGGML_BACKEND_DL=ON" in inside
    assert all(p in inside for p in ("libvulkan-dev", "glslc", "spirv-headers"))
    assert "libggml-vulkan.so" in inside                    # the build fails without it
    assert "libvulkan1" in LISTED                            # what that part needs to load
