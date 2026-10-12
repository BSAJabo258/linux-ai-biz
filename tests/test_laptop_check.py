"""Laptop check: everything needed to decide whether BAU can go on a laptop, collected
read-only. Windows (bau-laptop-check.ps1, no Python needed) and Linux from the stick
(bau-laptop-check.sh: which drivers really load). Each writes a private full report and a
short summary that is safe to share, with a plain verdict. Written before the code."""

import json
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
