"""Laptop check: everything needed to decide whether BAU can go on a laptop, collected
read-only. Windows (bau-laptop-check.ps1, no Python needed) and Linux from the stick
(bau-laptop-check.sh: which drivers really load). Each writes a private full report and a
short summary that is safe to share, with a plain verdict. Written before the code."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "installer" / "bau-laptop-check.ps1"
SH = ROOT / "installer" / "bau-laptop-check.sh"
needs_pwsh = pytest.mark.skipif(not shutil.which("pwsh"), reason="needs PowerShell (pwsh)")

PRIVATE = ["SECRET-PC", "jane.doe", "AA-BB-CC-11-22-33", "192.168.1.44", "SN-998877",
           "S3XYNX0R123456"]
GOOD = {
    "os": {"Caption": "Microsoft Windows 11 Home", "OSArchitecture": "64-bit",
           "CSName": "SECRET-PC"},
    "user": "jane.doe",
    "computer": {"Manufacturer": "LENOVO", "Model": "ThinkPad E14", "TotalPhysicalMemory":
                 17179869184, "SerialNumber": "SN-998877"},
    "cpu": [{"Name": "Intel(R) Core(TM) i5-1135G7", "NumberOfCores": 4,
             "NumberOfLogicalProcessors": 8, "VirtualizationFirmwareEnabled": True}],
    "firmware": {"Type": "Uefi", "SecureBoot": True},
    "tpm": {"TpmPresent": True, "SpecVersion": "2.0"},
    "bitlocker": [{"MountPoint": "C:", "ProtectionStatus": "Off",
                   "VolumeStatus": "FullyDecrypted"}],
    "disks": [{"FriendlyName": "Samsung SSD 980", "BusType": "NVMe", "MediaType": "SSD",
               "Size": 512110190592, "SerialNumber": "S3XYNX0R123456", "PartitionStyle": "GPT"}],
    "pci": [{"Class": "Net", "FriendlyName": "Intel(R) Wi-Fi 6 AX201 160MHz",
             "InstanceId": "PCI\\VEN_8086&DEV_A0F0&SUBSYS_00748086"},
            {"Class": "Display", "FriendlyName": "Intel(R) Iris(R) Xe Graphics",
             "InstanceId": "PCI\\VEN_8086&DEV_9A49"},
            {"Class": "Net", "FriendlyName": "Realtek PCIe GbE Family Controller",
             "InstanceId": "PCI\\VEN_10EC&DEV_8168"}],
    "network": [{"Name": "Wi-Fi", "MacAddress": "AA-BB-CC-11-22-33", "IPv4": "192.168.1.44"}],
    "problem_devices": [],
    "fast_startup": True,
    "battery": [{"DesignCapacity": 57000, "FullChargeCapacity": 51300}],
}


def verdict(inv: dict) -> dict:
    """Run the script's own Get-BauSummary on a made-up inventory (no Windows needed)."""
    script = (f". '{PS1}'; $inv = Get-Content -Raw '{{p}}' | ConvertFrom-Json; "
              "Get-BauSummary $inv | ConvertTo-Json -Depth 6")
    p = Path(pytest.tmp_path_factory_dir) / "inv.json"
    p.write_text(json.dumps(inv))
    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command",
                        script.replace("{p}", str(p))], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture(autouse=True)
def _tmp(tmp_path):
    pytest.tmp_path_factory_dir = tmp_path


# ------------------------------------------------------------------ never changes anything

@pytest.mark.parametrize("path", [PS1, SH])
def test_checks_only_read(path):
    text = path.read_text()
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    forbidden = [r"\b(Set|Remove|Clear|Format|Disable|Enable|Initialize|Stop|Restart|"
                 r"Suspend|Resume|Install|Uninstall|Repair|Resize|Update)-\w+",
                 r"bcdedit\s+/set", r"reg\s+(add|delete)", r"manage-bde\s+-(on|off|lock)",
                 r"\bmkfs", r"\bwipefs\b", r"\bparted\b", r"\bdd\s+if=", r"\bsfdisk\b",
                 r"\brm\s+-rf?\s+/(?!tmp)"]
    allowed = {"Set-Content", "Set-StrictMode"}
    for pat in forbidden:
        for m in re.finditer(pat, code, re.I):
            assert m.group(0) in allowed, f"{path.name}: {m.group(0)}"


# ------------------------------------------------------------------ the Windows check

@needs_pwsh
def test_script_parses():
    r = subprocess.run(["pwsh", "-NoProfile", "-Command",
                        f"$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
                        f"'{PS1}', [ref]$null, [ref]$e) | Out-Null; $e.Count"],
                       capture_output=True, text=True, timeout=120)
    assert r.stdout.strip() == "0", r.stdout + r.stderr


@needs_pwsh
def test_summary_is_safe_to_share():
    out = json.dumps(verdict(GOOD))
    for secret in PRIVATE:
        assert secret not in out, secret
    assert "ThinkPad E14" in out and "VEN_8086&DEV_A0F0" in out    # what's needed stays


@needs_pwsh
def test_a_good_laptop_is_ready_with_its_parts_named():
    s = verdict(GOOD)
    assert s["verdict"] == "READY"
    assert s["ram_gb"] == 16 and s["firmware"] == "UEFI"
    wifi = next(d for d in s["devices"] if "Wi-Fi" in d["name"])
    assert wifi["linux"].startswith("works")                     # Intel Wi-Fi: iwlwifi
    assert any("Fast Startup" in n for n in s["notes"])


@needs_pwsh
def test_blockers_and_warnings_are_said_plainly():
    small = {**GOOD, "computer": {**GOOD["computer"], "TotalPhysicalMemory": 4294967296}}
    assert verdict(small)["verdict"] == "NOT READY"
    assert any("memory" in b.lower() for b in verdict(small)["blockers"])
    locked = {**GOOD, "bitlocker": [{"MountPoint": "C:", "ProtectionStatus": "On",
                                     "VolumeStatus": "FullyEncrypted"}]}
    s = verdict(locked)
    assert s["verdict"] == "READY, AFTER THESE STEPS"
    assert any("BitLocker" in w and "recovery key" in w for w in s["warnings"])
    bios = {**GOOD, "firmware": {"Type": "Bios", "SecureBoot": None}}
    assert any("legacy BIOS" in w for w in verdict(bios)["warnings"])
    bcm = {**GOOD, "pci": [{"Class": "Net", "FriendlyName": "Broadcom 802.11ac",
                            "InstanceId": "PCI\\VEN_14E4&DEV_43A0"}]}
    s = verdict(bcm)
    assert any("Broadcom" in w for w in s["warnings"])
    nv = {**GOOD, "pci": GOOD["pci"] + [{"Class": "Display", "FriendlyName": "NVIDIA GeForce",
                                        "InstanceId": "PCI\\VEN_10DE&DEV_1F99"}]}
    assert any("safe graphics" in n for n in verdict(nv)["notes"])
    broken = {**GOOD, "problem_devices": [{"Name": "Unknown device",
                                           "InstanceId": "ACPI\\ABC0001"}]}
    assert any("problem" in n.lower() for n in verdict(broken)["notes"])


# ------------------------------------------------------------------ the Linux check (stick)

@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")
def test_linux_check_writes_a_shareable_summary(tmp_path):
    r = subprocess.run(["bash", str(SH), str(tmp_path)], capture_output=True, text=True,
                       timeout=180)
    assert r.returncode == 0, r.stderr
    summary = (tmp_path / "BAU-LAPTOP-SUMMARY-LINUX.txt").read_text()
    for heading in ("Memory", "Firmware", "Devices and their drivers", "Missing firmware",
                    "Radios"):
        assert heading in summary, heading
    assert not re.search(r"\b([0-9a-f]{2}:){5}[0-9a-f]{2}\b", summary, re.I)   # no MACs
    assert (tmp_path / "BAU-LAPTOP-FULL-LINUX.txt").is_file()


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="needs shellcheck")
def test_linux_check_passes_shellcheck():
    r = subprocess.run(["shellcheck", str(SH)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


# ------------------------------------------------------------------ shipped and explained

def test_both_checks_ship_on_the_stick_and_are_explained():
    mk = (ROOT / "installer" / "make-payload.sh").read_text()
    assert "bau-laptop-check.ps1" in mk and "bau-laptop-check.sh" in mk
    doc = (ROOT / "docs" / "LAPTOP-CHECK.md").read_text()
    assert "bau-laptop-check.ps1" in doc and "BAU-LAPTOP-SUMMARY" in doc
    assert "ExecutionPolicy Bypass" in doc


# ------------------------------------------------------------------ double-click on Windows
# The owner's first try "nothing worked": a .ps1 opens in Notepad on double-click, and a
# window that closes at once shows nothing. The launcher asks for administrator rights,
# runs the check, keeps the window open and opens the summary.

CMD = ROOT / "installer" / "BAU-Laptop-Check.cmd"


def test_double_click_launcher_runs_the_check_as_administrator_and_waits():
    raw = CMD.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")    # batch needs CRLF
    text = raw.decode("ascii")
    assert "-Verb RunAs" in text and "net session" in text           # asks for admin
    assert "-ExecutionPolicy Bypass" in text and "%~dp0bau-laptop-check.ps1" in text
    assert "notepad" in text and "pause" in text                     # window stays open


def test_windows_errors_stay_quiet():
    # Non-terminating errors (no BitLocker, no battery) must not fill the window with red.
    text = PS1.read_text()
    assert "$ErrorActionPreference = \"Stop\"" in text.split("function Invoke-BauSafe", 1)[1][:200]


def test_launcher_ships_and_is_explained():
    assert "BAU-Laptop-Check.cmd" in (ROOT / "installer" / "make-payload.sh").read_text()
    doc = (ROOT / "docs" / "LAPTOP-CHECK.md").read_text()
    assert "BAU-Laptop-Check.cmd" in doc and "Run anyway" in doc


# ------------------------------------------------------------------ the owner's real laptop
# First real run (2026-10-12, Dell XPS 13 9380) said READY, but its NVMe disk sits behind
# Intel RST ("RAID On"), which the Linux installer usually cannot see; the device list was
# full of VPN, Hyper-V and Bluetooth-profile entries that are software, not hardware.

XPS = {**GOOD,
       "computer": {**GOOD["computer"], "Manufacturer": "Dell Inc.", "Model": "XPS 13 9380",
                    "TotalPhysicalMemory": 8385855488},
       "disks": [{"FriendlyName": "SanDisk Cruzer Glide", "BusType": "USB",
                  "MediaType": "Unspecified", "Size": 123010547712, "PartitionStyle": "MBR"},
                 {"FriendlyName": "SSDPEKKF512G8 NVMe INTEL 512GB", "BusType": "RAID",
                  "MediaType": "SSD", "Size": 512110190592, "PartitionStyle": "GPT"}],
       "pci": [{"Class": "Display", "FriendlyName": "Intel(R) UHD Graphics 620",
                "InstanceId": "PCI\\VEN_8086&DEV_3EA0&SUBSYS_08E1"},
               {"Class": "Net", "FriendlyName": "Killer Wireless-n/a/ac 1435 Wireless",
                "InstanceId": "PCI\\VEN_168C&DEV_003E&SUBSYS_14351A56"},
               {"Class": "Net", "FriendlyName": "WAN Miniport (IP)",
                "InstanceId": "SWD\\MSRRAS\\MS_NDISWANIP"},
               {"Class": "Net", "FriendlyName": "TAP-ProtonVPN Windows Adapter V9",
                "InstanceId": "ROOT\\NET\\0000"},
               {"Class": "Bluetooth", "FriendlyName": "Soundcore Icon+",
                "InstanceId": "BTHENUM\\DEV_0C2E3D"},
               {"Class": "Bluetooth", "FriendlyName": "Qualcomm QCA61x4A Bluetooth",
                "InstanceId": "USB\\VID_0489&PID_E0A2\\5&1"},
               {"Class": "Camera", "FriendlyName": "Integrated Webcam",
                "InstanceId": "USB\\VID_0C45&PID_6723&MI_00\\6&1"},
               {"Class": "Biometric", "FriendlyName": "Goodix fingerprint",
                "InstanceId": "USB\\VID_27C6&PID_5385\\UID0"}]}


@needs_pwsh
def test_disk_behind_intel_rst_must_be_switched_to_ahci_first():
    s = verdict(XPS)
    assert s["verdict"] == "READY, AFTER THESE STEPS"
    w = next(w for w in s["warnings"] if "AHCI" in w)
    assert "RAID" in w and "Safe Mode" in w                 # or Windows stops starting


@needs_pwsh
def test_only_real_hardware_is_listed_and_judged():
    s = verdict(XPS)
    names = [d["name"] for d in s["devices"]]
    assert not any(n.startswith(("WAN Miniport", "TAP-", "Soundcore")) for n in names)
    by = {d["name"]: d["linux"] for d in s["devices"]}
    assert by["Qualcomm QCA61x4A Bluetooth"].startswith("works")
    assert by["Integrated Webcam"].startswith("usually works")
    assert "fingerprint" in by["Goodix fingerprint"] and "not needed" in by["Goodix fingerprint"]
    assert any("8 GB" in n and "small" in n for n in s["notes"])     # local models: small only
    usb = next(d for d in s["disks"] if d["bus"] == "USB")
    assert "not this one" in usb["note"]                             # never install on the stick


# ------------------------------------------------------------------ the owner's desktop
# Next machine: a desktop with a 12 GB graphics card and a spare 1 TB drive. Before any
# design, the check must name the card, its memory (Windows' own AdapterRAM stops at 4 GB,
# so the registry or nvidia-smi is read), its driver, which disk Windows starts from and
# which disk is free for BAU.

DESKTOP = {**GOOD,
           "computer": {**GOOD["computer"], "Manufacturer": "Micro-Star International",
                        "Model": "MS-7C56", "TotalPhysicalMemory": 34359738368},
           "cpu": [{"Name": "AMD Ryzen 7 5800X 8-Core Processor", "NumberOfCores": 8,
                    "NumberOfLogicalProcessors": 16, "VirtualizationFirmwareEnabled": True}],
           "battery": [],
           "disks": [{"FriendlyName": "Samsung SSD 970 EVO 500GB", "BusType": "NVMe",
                      "MediaType": "SSD", "Size": 500107862016, "SerialNumber": "S3XYNX0R123456",
                      "PartitionStyle": "GPT", "IsBoot": True, "IsSystem": True},
                     {"FriendlyName": "WDC WDS100T2B0A", "BusType": "SATA", "MediaType": "SSD",
                      "Size": 1000204886016, "PartitionStyle": "GPT", "IsBoot": False,
                      "IsSystem": False}],
           "pci": [{"Class": "Display", "FriendlyName": "NVIDIA GeForce RTX 3060",
                    "InstanceId": "PCI\\VEN_10DE&DEV_2504&SUBSYS_397D1462"},
                   {"Class": "Net", "FriendlyName": "Realtek PCIe 2.5GbE Family Controller",
                    "InstanceId": "PCI\\VEN_10EC&DEV_8125"}],
           "gpus": [{"Name": "NVIDIA GeForce RTX 3060", "VramBytes": 12884901888,
                     "DriverVersion": "32.0.15.6094", "ComputeCap": "8.6",
                     "NvidiaDriver": "560.94"}]}


@needs_pwsh
def test_desktop_graphics_card_is_named_with_its_real_memory():
    s = verdict(DESKTOP)
    g = s["gpus"][0]
    assert g["name"] == "NVIDIA GeForce RTX 3060" and g["vendor"] == "NVIDIA"
    assert g["vram_gb"] == 12 and g["compute"] == "8.6" and g["driver"] == "560.94"
    assert any("12 GB" in n and "graphics card" in n and "bau models bench" in n
               for n in s["notes"])                           # what fits, never "works"
    assert s["model"].startswith("Micro-Star") and s["battery_health_percent"] is None


@needs_pwsh
def test_desktop_says_which_disk_has_windows_and_which_is_free():
    s = verdict(DESKTOP)
    by = {d["name"]: d["note"] for d in s["disks"]}
    assert "Windows starts from this disk" in by["Samsung SSD 970 EVO 500GB"]
    assert "no Windows" in by["WDC WDS100T2B0A"]
    assert s["install_disk"] == "WDC WDS100T2B0A"             # the free 1 TB drive
    assert s["verdict"] == "READY"


@needs_pwsh
def test_nvidia_with_secure_boot_and_no_wifi_are_explained():
    s = verdict(DESKTOP)                                      # GOOD has Secure Boot on
    assert any("NVIDIA" in n and "Secure Boot" in n for n in s["notes"])
    assert any("Ethernet" in n for n in s["notes"])          # no Wi-Fi card in this desktop
    # older reports without the new fields still work
    plain = verdict(GOOD)
    assert plain["gpus"] == [] or all("vram_gb" in g for g in plain["gpus"])


@needs_pwsh
def test_desktop_summary_stays_safe_to_share():
    out = json.dumps(verdict(DESKTOP))
    assert "S3XYNX0R123456" not in out


def test_desktop_double_click_launcher_uses_the_same_check():
    raw = (ROOT / "installer" / "BAU-Desktop-Check.cmd").read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("ascii")
    assert "-Verb RunAs" in text and "%~dp0bau-laptop-check.ps1" in text
    assert "BAU-Desktop-Check" in text and "pause" in text
    assert "BAU-Desktop-Check.cmd" in (ROOT / "installer" / "make-payload.sh").read_text()
    assert "BAU-Desktop-Check.cmd" in (ROOT / "docs" / "LAPTOP-CHECK.md").read_text()


def test_windows_check_reads_real_graphics_memory():
    text = PS1.read_text()
    assert "HardwareInformation.qwMemorySize" in text and "nvidia-smi" in text
    assert "IsBoot" in text


# The owner's desktop report (2026-10-23) listed one RTX 3060 twice: Windows keeps an old
# driver entry under the display class with the same name. A card is counted at most as
# many times as Windows says that card is plugged in.
GPU_STUBS = """
function Get-PnpDevice {{ param([switch]$PresentOnly, $Class, $ErrorAction)
    1..{present} | ForEach-Object {{
        [pscustomobject]@{{ FriendlyName = 'NVIDIA GeForce RTX 3060' }} }} }}
function Get-ChildItem {{ param($Path, $ErrorAction)
    '0000', '0001' | ForEach-Object {{ [pscustomobject]@{{ PSChildName = $_; PSPath = $_ }} }} }}
function Get-ItemProperty {{ param($Path, $ErrorAction)
    [pscustomobject]@{{ DriverDesc = 'NVIDIA GeForce RTX 3060'; DriverVersion = '32.0.15.7657';
                        'HardwareInformation.qwMemorySize' = [uint64]12884901888 }} }}
"""


@needs_pwsh
@pytest.mark.parametrize("present", [1, 2])
def test_a_graphics_card_is_listed_once_per_card_plugged_in(present):
    script = (f". '{PS1}'; " + GPU_STUBS.format(present=present) +
              "@(Invoke-BauGpus).Count")
    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == str(present)


@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")
def test_linux_check_has_a_graphics_section(tmp_path):
    subprocess.run(["bash", str(SH), str(tmp_path)], capture_output=True, text=True,
                   timeout=180)
    summary = (tmp_path / "BAU-LAPTOP-SUMMARY-LINUX.txt").read_text()
    assert "Graphics card" in summary


@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")
def test_linux_check_reports_sound_and_bluetooth_with_the_fix(tmp_path):
    fake = tmp_path / "bin"                    # a dpkg that has none of them installed
    fake.mkdir()
    (fake / "dpkg-query").write_text("#!/bin/sh\nexit 1\n")
    (fake / "dpkg-query").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"}
    subprocess.run(["bash", str(SH), str(tmp_path)], capture_output=True, text=True,
                   timeout=180, env=env)
    summary = (tmp_path / "BAU-LAPTOP-SUMMARY-LINUX.txt").read_text()
    assert "Sound:" in summary and "Bluetooth:" in summary
    assert "sudo apt install" in summary
    for pkg in ("alsa-ucm-conf", "alsa-topology-conf", "libspa-0.2-bluetooth"):
        assert pkg in summary, pkg
