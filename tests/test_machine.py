"""bau hw profile / fit: measured, never assumed (owner's directive 2026-10-26: find the
card's memory on the computer itself; keep system memory and card memory apart)."""

import subprocess

from bau import machine

GiB = 1 << 30
# The desktop's check report (2026-10-23): 16 GB, RTX 3060 12 GB.
# The device ID below is example data, not a fact about the owner's card.
SMI = ("NVIDIA GeForce RTX 3060, 12288, 410, 11878, 550.163.01, 8.6, 0x250310DE, "
       "00000000:01:00.0, 41, 17.52, 170.00, 3, P8\n")


def _root(tmp_path, nvidia=True, driver=True, mem_kb=16 * 1024 * 1024, avail_kb=None):
    r = tmp_path / "root"
    (r / "etc").mkdir(parents=True)
    (r / "etc/os-release").write_text('PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\n')
    (r / "proc/driver/nvidia").mkdir(parents=True)
    (r / "proc/meminfo").write_text(f"MemTotal: {mem_kb} kB\n"
                                    f"MemAvailable: {avail_kb or mem_kb - 4 * 1024 * 1024} kB\n"
                                    "SwapTotal: 0 kB\n")
    (r / "proc/cpuinfo").write_text("model name\t: 12th Gen Intel(R) Core(TM) i7-12700F\n")
    if driver:
        (r / "proc/driver/nvidia/version").write_text("NVRM version: 550.163.01\n")
    dev = r / "sys/bus/pci/devices/0000:01:00.0"
    dev.mkdir(parents=True)
    (dev / "vendor").write_text("0x10de\n" if nvidia else "0x8086\n")
    (dev / "class").write_text("0x030000\n")
    (dev / "device").write_text("0x2503\n")
    (dev / "subsystem_vendor").write_text("0x1043\n")
    (dev / "subsystem_device").write_text("0x87f3\n")
    return r


def _run(smi=SMI):
    def run(args, **kw):
        if args[0] == "nvidia-smi":
            if smi is None:
                raise FileNotFoundError(args[0])
            out = smi if any(a.startswith("--query-gpu") for a in args) else \
                "| NVIDIA-SMI 550.163.01   Driver Version: 550.163.01   CUDA Version: 12.4 |\n"
            return subprocess.CompletedProcess(args, 0, out, "")
        if args[0] == "mokutil":
            return subprocess.CompletedProcess(args, 0, "SecureBoot enabled\n", "")
        if args[0] == "lscpu":
            return subprocess.CompletedProcess(args, 0, "# core,socket\n0,0\n0,0\n1,0\n", "")
        raise FileNotFoundError(args[0])
    return run


def test_card_memory_comes_from_nvidia_smi_and_stays_apart_from_system_memory(tmp_path):
    p = machine.profile(tmp_path, root=_root(tmp_path), run=_run(), engine=tmp_path / "no")
    card = p["gpu"]["cards"][0]
    assert card["name"] == "NVIDIA GeForce RTX 3060"
    assert card["memory_total"] == 12 * GiB and card["compute_cap"] == "8.6"
    assert p["memory"]["total"] == 16 * GiB
    assert p["gpu"]["driver_cuda"] == "12.4" and p["cpu"]["cores"] == 2
    s = machine.summary(p)
    assert s["memory_gb"]["total"] == 16.0
    assert s["graphics_card"][0]["card_memory_gb"] == 12.0


def test_no_driver_means_unknown_not_a_guess(tmp_path):
    p = machine.profile(tmp_path, root=_root(tmp_path, driver=False), run=_run(smi=None),
                        engine=tmp_path / "no")
    assert p["gpu"]["nvidia_card"] and p["gpu"]["cards"] == []
    assert "unknown" in p["gpu"]["note"] and "is not installed" in p["gpu"]["note"]
    assert machine.fits(6 * GiB, p)["where"] == "unknown"


def test_a_missing_tool_is_not_a_missing_part(tmp_path):
    p = machine.profile(tmp_path, root=_root(tmp_path, nvidia=False, driver=False),
                        run=_run(smi=None), engine=tmp_path / "no")
    assert p["gpu"]["nvidia_card"] is False
    assert p["cpu"]["model"].startswith("12th Gen")


def test_fit_estimates_card_split_memory_and_no(tmp_path):
    p = machine.profile(tmp_path, root=_root(tmp_path), run=_run(), engine=tmp_path / "no")
    p["disk"] = {"free": 500 * GiB}
    assert machine.fits(5_680_522_464, p)["where"] == "card"            # Qwen3.5-9B
    assert machine.fits(9_828_981_664, p)["where"] == "card"            # 3.8-27B Q2_K_XL
    # 3.8-27B IQ3_XXS: next to the desktop's own screen (410 MB used) it is too close to
    # call on the card alone; only `bau models lab` on the desktop settles it.
    assert machine.fits(10_934_860_704, p)["where"] == "card+memory"
    assert machine.fits(16_601_176_704, p)["where"] == "card+memory"    # 35B-A3B Q3
    assert machine.fits(48 * GiB, p)["where"] == "no"
    assert machine.fits(6 * GiB, p)["estimate"] is True
    p["disk"] = {"free": 5 * GiB}
    assert machine.fits(6 * GiB, p)["disk_ok"] is False


def test_laptop_without_a_card_runs_small_models_in_memory(tmp_path):
    p = machine.profile(tmp_path, root=_root(tmp_path, nvidia=False, driver=False,
                                             mem_kb=8 * 1024 * 1024, avail_kb=6 * 1024 * 1024),
                        run=_run(smi=None), engine=tmp_path / "no")
    assert machine.fits(2_740_937_888, p)["where"] == "memory"          # Qwen3.5-4B
    assert machine.fits(5_680_522_464, p)["where"] == "no"


def test_profile_lists_key_names_only(tmp_path, monkeypatch):
    monkeypatch.setattr("bau.keys.names", lambda: {"models.env": ["ZAI_API_KEY"]})
    p = machine.profile(tmp_path, root=_root(tmp_path), run=_run(), engine=tmp_path / "no")
    assert p["key_names"] == {"models.env": ["ZAI_API_KEY"]}


def test_fetch_refuses_when_the_disk_is_too_small(tmp_path, monkeypatch, capsys):
    import argparse

    from bau import cli_ext
    from bau.runtime import seed_registry
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    seed_registry(tmp_path)
    monkeypatch.setattr(machine, "_disk", lambda p: {"path": str(p), "free": 1 * GiB})
    called = []
    monkeypatch.setattr("bau.models.fetch.fetch", lambda *a, **k: called.append(1))
    rc = cli_ext.cmd_models(argparse.Namespace(models_cmd="fetch", model="qwen3.5-9b",
                                               dir=str(tmp_path / "m")))
    assert rc != 0 and not called
    assert "not enough free disk space" in capsys.readouterr().err


def test_card_details_device_id_temperature_power_and_secure_boot(tmp_path):
    p = machine.profile(tmp_path, root=_root(tmp_path), run=_run(), engine=tmp_path / "no")
    card = p["gpu"]["cards"][0]
    assert card["temperature_c"] == 41 and card["power_w"] == 17.52
    assert card["power_limit_w"] == 170 and card["utilization_pct"] == 3
    assert card["pstate"] == "P8" and card["pci_bus_id"] == "00000000:01:00.0"
    assert p["gpu"]["pci"] == [{"address": "0000:01:00.0", "id": "10de:2503",
                                "subsystem": "1043:87f3"}]
    assert p["secure_boot"] == "SecureBoot enabled"
    s = machine.summary(p)
    assert s["pci_ids"] == ["10de:2503"] and s["graphics_card"][0]["temperature_c"] == 41
    assert set(p["frameworks"]["python"]) == {"tensorflow", "torch", "tensorrt"}


def test_secure_boot_is_read_from_the_firmware_without_mokutil(tmp_path):
    # The stick has no mokutil (seen 2026-10-27): bau hw said null with Secure Boot on.
    root = _root(tmp_path)
    var = root / machine.SECURE_BOOT_VAR
    var.parent.mkdir(parents=True, exist_ok=True)
    none = lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("mokutil"))  # noqa: E731
    var.write_bytes(bytes([6, 0, 0, 0, 1]))
    assert machine._secure_boot(none, root) == "SecureBoot enabled"
    var.write_bytes(bytes([6, 0, 0, 0, 0]))
    assert machine._secure_boot(none, root) == "SecureBoot disabled"
    var.unlink()
    assert machine._secure_boot(none, root) is None


def test_an_older_driver_that_lacks_a_field_says_unknown(tmp_path):
    old = "NVIDIA GeForce RTX 3060, 12288, 410, 11878, 550.163.01, 8.6, 0x250310DE, x, [N/A]\n"
    p = machine.profile(tmp_path, root=_root(tmp_path), run=_run(smi=old),
                        engine=tmp_path / "no")
    card = p["gpu"]["cards"][0]
    assert card["temperature_c"] is None and card["power_w"] is None
    assert card["memory_total"] == 12 * GiB
