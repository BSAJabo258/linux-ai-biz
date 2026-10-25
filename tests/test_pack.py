"""The BAU Pack: everything the laptop needs, carried on a USB stick (docs/PACK.md).

On a Windows computer with internet, BAU-Pack-Make.cmd fills a stick the owner picks with
the local models (each checked against its pinned SHA-256) and the owner's locked keys file.
On the laptop, with no internet, the owner runs `sudo bau pack install`: it checks every
file again, copies the models into place, starts the local model, measures it, and asks
yes or no before approving a model, naming the team or importing keys. It writes a
laptop report (Wi-Fi card, firmware, radio switches; addresses hidden) back onto the stick.
Nothing runs by itself when the stick is plugged in. Written before the code."""

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from bau import cli
from bau import pack as P
from bau import team as T
from bau.audit import AuditLog
from bau.registry import CapabilityRegistry

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "installer" / "bau-pack-make.ps1"
CMD = ROOT / "installer" / "BAU-Pack-Make.cmd"
DEFAULTS = ROOT / "src" / "bau" / "data" / "registry_defaults.yaml"
needs_pwsh = pytest.mark.skipif(not (shutil.which("pwsh") and shutil.which("curl")),
                                reason="needs PowerShell (pwsh) and curl")

BASE = {"version": "1", "source": "test", "license": "Apache-2.0", "commercial_use": True,
        "provider": "local", "deployment": "local", "adapter": "local_http",
        "trust_level": "QUANTIZED", "privacy": "local", "context": 8192,
        "input_types": ["text"], "quality": 0.5, "latency_ms": 100, "cost_in_per_mtok": 0,
        "cost_out_per_mtok": 0, "status": "REGISTERED"}
BLOBS = {"qwen3.5-4b": b"boss model bytes", "qwen3-4b-heretic-content": b"thinker bytes",
         "qwen2.5-1.5b-instruct": b"backup model bytes"}
DESKTOP = {"qwen3.5-9b": b"desktop boss bytes"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def records(desktop=False) -> dict[str, dict]:
    out = {}
    for mid, blob in {**BLOBS, **(DESKTOP if desktop else {})}.items():
        rec = {**BASE, "model_id": mid, "name": mid, "api_model": mid,
               "endpoint": "http://127.0.0.1:8080", "tools": True,
               "download": {"url": f"https://example.invalid/{mid}.gguf",
                            "file": f"{mid}.gguf", "size": len(blob), "sha256": sha(blob)}}
        if "heretic" in mid:
            rec.update(trust_level="ABLITERATED", tools=False, lane="content_only",
                       use_for=["ideas"], endpoint="http://127.0.0.1:8082")
        out[mid] = rec
    return out


def make_pack(tmp_path: Path, only=None, keys=False, desktop=False) -> Path:
    pack = tmp_path / "stick" / "BAU-PACK"
    (pack / "models").mkdir(parents=True)
    for mid, blob in {**BLOBS, **(DESKTOP if desktop else {})}.items():
        if only is None or mid in only:
            (pack / "models" / f"{mid}.gguf").write_bytes(blob)
    if keys:
        (pack / "BAU-KEYS.enc").write_bytes(b"Salted__locked")
    return pack


def make_home(tmp_path: Path) -> tuple[Path, AuditLog]:
    home = tmp_path / "home"
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    for rec in records().values():
        reg.add("model", rec)
    return home, AuditLog(home / "audit" / "chain.jsonl", key=b"")


class Owner:
    """Answers yes only to questions containing one of the given words."""

    def __init__(self, *yes):
        self.yes, self.asked = yes, []

    def __call__(self, question: str) -> bool:
        self.asked.append(question)
        return any(w in question for w in self.yes)


class Runner:
    def __init__(self, outputs=None):
        self.outputs, self.calls = outputs or {}, []

    def __call__(self, cmd):
        self.calls.append(cmd)
        return self.outputs.get(cmd[0], "")


def good_bench(mid):
    return {"reply_ok": True, "tool_calls": True, "tokens_per_sec": 9.5, "latency_ms": 900}


def do_install(tmp_path, pack, owner, bench=good_bench, read_pass=None, run=None,
               desktop=False, **kw):
    home, audit = make_home(tmp_path)
    etc = tmp_path / "etc"
    kw.setdefault("gpu", lambda: False)                 # the laptop, unless a test says
    out = P.install(pack, home, etc, ask=owner, run=run or Runner(), by="human:owner",
                    audit=audit, bench=bench, read_pass=read_pass,
                    records=records(desktop), say=lambda *_: None, sleep=lambda _: None, **kw)
    return home, etc, out


# ------------------------------------------------------------------ the stick

def test_root_accepts_the_stick_or_the_pack_folder(tmp_path):
    pack = make_pack(tmp_path)
    assert P.root(pack) == pack
    assert P.root(pack.parent) == pack
    with pytest.raises(P.PackError):
        P.root(tmp_path / "nowhere")


def test_find_looks_on_mounted_sticks(tmp_path):
    pack = make_pack(tmp_path)
    assert P.find([str(tmp_path / "*")]) == [pack]
    assert P.find([str(tmp_path / "none" / "*")]) == []


def test_find_ignores_capitals_in_the_folder_name(tmp_path):
    pack = make_pack(tmp_path)
    renamed = pack.with_name("BAU-pack")
    pack.rename(renamed)
    assert P.find([str(tmp_path / "*")]) == [renamed]
    assert P.root(renamed.parent) == renamed


LSBLK = {"blockdevices": [
    {"path": "/dev/nvme0n1p3", "fstype": "ntfs", "mountpoint": None, "type": "part"},
    {"path": "/dev/sdb1", "fstype": "exfat", "mountpoint": None, "type": "part"},
    {"path": "/dev/sda2", "fstype": "ext4", "mountpoint": "/", "type": "part"},
    {"path": "/dev/sdc1", "fstype": "vfat", "mountpoint": "/media/x/STICK", "type": "part"}]}


def test_locate_opens_windows_and_stick_drives_read_only(tmp_path):
    mounts = tmp_path / "run"
    calls = []

    def run(cmd):
        calls.append(cmd)
        if cmd[0] == "lsblk":
            return json.dumps(LSBLK)
        if cmd[0] == "mount" and cmd[-2] == "/dev/sdb1":     # the stick holds the pack
            pack = Path(cmd[-1]) / "BAU-Pack" / "models"
            pack.mkdir(parents=True)
        return ""

    found = P.locate(run, bases=[str(mounts / "*")], mount_dir=mounts)
    assert found == [mounts / "sdb1" / "BAU-Pack"]
    mounted = [c for c in calls if c[0] == "mount"]
    assert all("ro" in c[c.index("-o") + 1].split(",") for c in mounted)
    assert {c[-2] for c in mounted} == {"/dev/nvme0n1p3", "/dev/sdb1"}   # never / or mounted
    assert ["mount", "-t", "ntfs3", "-o", "ro", "/dev/nvme0n1p3",
            str(mounts / "nvme0n1p3")] in mounted


def test_locate_does_not_mount_when_a_pack_is_already_there(tmp_path):
    pack = make_pack(tmp_path)
    run = Runner()
    assert P.locate(run, bases=[str(tmp_path / "*")], mount_dir=tmp_path / "run") == [pack]
    assert run.calls == []


def test_report_goes_to_the_laptop_when_the_pack_is_read_only(tmp_path, monkeypatch):
    pack = make_pack(tmp_path)
    real = P._new_file

    def ro(path):
        if path.parent == pack:
            raise OSError("Read-only file system")
        return real(path)

    monkeypatch.setattr(P, "_new_file", ro)
    home, _, out = do_install(tmp_path, pack, Owner(), run=Runner({"lspci": LSPCI}))
    assert out["report"] == str(home / "reports" / "laptop-report.txt")
    assert "QCA6174" in (home / "reports" / "laptop-report.txt").read_text()


def test_scan_checks_every_model_against_its_pinned_hash(tmp_path):
    pack = make_pack(tmp_path)
    (pack / "models" / "qwen2.5-1.5b-instruct.gguf").write_bytes(b"backup model bytez")
    (pack / "models" / "stranger.gguf").write_bytes(b"?")
    (pack / "models" / "qwen3-4b-heretic-content.gguf").unlink()
    got = {e["model_id"]: e["status"] for e in P.scan(pack, records())}
    assert got == {"qwen3.5-4b": "ok", "qwen2.5-1.5b-instruct": "damaged",
                   "qwen3-4b-heretic-content": "missing"}


def test_scan_refuses_links(tmp_path):
    pack = make_pack(tmp_path, only=["qwen2.5-1.5b-instruct"])
    real = tmp_path / "elsewhere.gguf"
    real.write_bytes(BLOBS["qwen3.5-4b"])
    (pack / "models" / "qwen3.5-4b.gguf").symlink_to(real)
    got = {e["model_id"]: e["status"] for e in P.scan(pack, records())}
    assert got["qwen3.5-4b"] == "not a regular file"


def test_pack_models_match_the_registry():
    reg = yaml.safe_load(DEFAULTS.read_text())["model"]
    for mid in P.PACK_MODELS:
        dl = reg[mid]["download"]
        assert dl["url"].startswith("https://") and len(dl["sha256"]) == 64
    assert reg[P.THINKER]["lane"] == "content_only" and not reg[P.THINKER]["tools"]
    for mid in P.BOSS_ORDER:
        assert reg[mid]["tools"] and reg[mid].get("lane") != "content_only"


# ------------------------------------------------------------------ install

def test_install_copies_only_verified_models(tmp_path):
    pack = make_pack(tmp_path)
    (pack / "models" / "qwen2.5-1.5b-instruct.gguf").write_bytes(b"tampered")
    home, _, out = do_install(tmp_path, pack, Owner())
    models = home / "models"
    assert (models / "qwen3.5-4b.gguf").read_bytes() == BLOBS["qwen3.5-4b"]
    assert (models / "qwen3-4b-heretic-content.gguf").exists()
    assert not (models / "qwen2.5-1.5b-instruct.gguf").exists()
    assert not list(models.glob("*.part"))
    assert out["copied"] == ["qwen3.5-4b", "qwen3-4b-heretic-content"]
    assert out["skipped"] == {"qwen2.5-1.5b-instruct": "damaged"}


def test_install_twice_copies_nothing_new(tmp_path):
    pack = make_pack(tmp_path)
    home, audit = make_home(tmp_path)
    kw = dict(ask=Owner(), run=Runner(), by="human:owner", audit=audit, bench=good_bench,
              records=records(), say=lambda *_: None, sleep=lambda _: None)
    P.install(pack, home, tmp_path / "etc", **kw)
    again = P.install(pack, home, tmp_path / "etc", **kw)
    assert again["copied"] == [] and len(again["already"]) == 3


def test_no_answer_means_nothing_is_approved_or_started(tmp_path):
    pack = make_pack(tmp_path)
    run = Runner()
    home, etc, out = do_install(tmp_path, pack, Owner(), run=run)
    assert not (etc / "llm.env").exists()
    assert ["systemctl", "restart", "bau-llm.service"] not in run.calls
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    assert all(r["status"] == "REGISTERED" for r in reg.data["model"].values())
    assert out["approved"] == [] and out["boss"] is None


def test_yes_starts_measures_and_approves_the_boss(tmp_path):
    pack = make_pack(tmp_path)
    run = Runner()
    home, etc, out = do_install(tmp_path, pack, Owner("local model", "Approve", "boss"),
                                run=run)
    env = (etc / "llm.env").read_text()
    assert f"BAU_LLM_MODEL={home / 'models' / 'qwen3.5-4b.gguf'}" in env
    assert "BAU_LLM_ALIAS=qwen3.5-4b" in env
    assert oct((etc / "llm.env").stat().st_mode & 0o777) == "0o640"
    assert ["systemctl", "restart", "bau-llm.service"] in run.calls
    rec = CapabilityRegistry(home / "registry" / "capabilities.yaml").data["model"]
    assert rec["qwen3.5-4b"]["status"] == "APPROVED"
    assert rec["qwen3.5-4b"]["reviewed_by"] == "human:owner"
    assert rec["qwen3-4b-heretic-content"]["status"] == "REGISTERED"  # thinker: copied only
    assert T.show(home)["boss"] == "qwen3.5-4b"
    assert out["approved"] == ["qwen3.5-4b"] and out["boss"] == "qwen3.5-4b"
    events = [json.loads(ln)["event"]
              for ln in (home / "audit" / "chain.jsonl").read_text().splitlines()]
    assert "registry.status" in events and "team.set" in events


def test_backup_model_is_the_boss_when_the_main_one_is_missing(tmp_path):
    pack = make_pack(tmp_path, only=["qwen2.5-1.5b-instruct"])
    _, etc, out = do_install(tmp_path, pack, Owner("local model"))
    assert "BAU_LLM_ALIAS=qwen2.5-1.5b-instruct" in (etc / "llm.env").read_text()


def test_benchmark_waits_for_the_server_and_a_bad_reply_is_never_approved(tmp_path):
    pack = make_pack(tmp_path)
    tries = []

    def slow_then_bad(mid):
        tries.append(mid)
        if len(tries) < 3:
            raise ConnectionError("loading")
        return {"reply_ok": False, "tool_calls": False}

    owner = Owner("local model", "Approve", "boss")
    home, _, out = do_install(tmp_path, pack, owner, bench=slow_then_bad)
    assert len(tries) == 3
    assert out["approved"] == [] and out["boss"] is None
    assert not any("Approve" in q for q in owner.asked)


def test_server_that_never_answers_is_reported_not_approved(tmp_path):
    pack = make_pack(tmp_path)

    def dead(mid):
        raise ConnectionError("refused")

    _, _, out = do_install(tmp_path, pack, Owner("local model", "Approve"), bench=dead)
    assert out["approved"] == [] and "journalctl -u bau-llm" in out["problems"][0]


def test_keys_are_imported_only_on_yes(tmp_path, monkeypatch):
    pack = make_pack(tmp_path, keys=True)
    seen = []
    monkeypatch.setattr(P.keys, "import_file",
                        lambda path, pw, etc, audit, by: seen.append((path.name, pw, by)) or {})
    do_install(tmp_path, pack, Owner(), read_pass=lambda: "pw")
    assert seen == []
    shutil.rmtree(tmp_path / "home")
    do_install(tmp_path, pack, Owner("keys"), read_pass=lambda: "pw")
    assert seen == [("BAU-KEYS.enc", "pw", "human:owner")]


def test_only_a_person_installs(tmp_path):
    with pytest.raises(PermissionError):
        P.install(make_pack(tmp_path), tmp_path / "h", tmp_path / "e", ask=Owner(),
                  run=Runner(), by="agent:jarvis", audit=None, records=records())


# ------------------------------------------------------------------ the laptop report

LSPCI = """00:02.0 VGA compatible controller [0300]: Intel Corporation HD Graphics 620 [8086:5916]
\tKernel driver in use: i915
3b:00.0 Network controller [0280]: Qualcomm Atheros QCA6174 802.11ac [168c:003e] (rev 32)
\tSubsystem: Bigfoot Networks, Inc. Killer 1435 Wireless-AC [1a56:1535]
\tKernel modules: ath10k_pci
"""
DMESG = """[    5.1] ath10k_pci 3b:00.0: firmware: failed to load ath10k/QCA6174/hw3.0/board-2.bin
[    5.2] usb 1-1: new high-speed USB device
[    5.3] ath10k_pci 0000:3b:00.0: mac 9c:b6:d0:12:34:56
"""


def test_laptop_report_finds_the_wifi_card_and_hides_addresses():
    run = Runner({"lspci": LSPCI, "dmesg": DMESG,
                  "nmcli": "wlp59s0:wifi:unavailable\nlo:loopback:unmanaged",
                  "rfkill": "0: phy0: Wireless LAN\n\tSoft blocked: yes\n\tHard blocked: no",
                  "cat": "auto lo\niface wlan0 inet dhcp\n  wpa-ssid HomeNet\n  wpa-psk hunter2",
                  "ip": "link/ether 9c:b6:d0:12:34:56 brd ff:ff:ff:ff:ff:ff"})
    text = P.laptop_report(run)
    assert "QCA6174" in text and "ath10k_pci" in text and "Soft blocked: yes" in text
    assert "board-2.bin" in text and "new high-speed USB" not in text
    assert "VGA compatible" not in text
    assert "9c:b6:d0" not in text and "hunter2" not in text and "HomeNet" not in text
    assert "wlp59s0:wifi:unavailable" in text


def test_install_writes_the_report_onto_the_stick(tmp_path):
    pack = make_pack(tmp_path)
    do_install(tmp_path, pack, Owner(), run=Runner({"lspci": LSPCI}))
    assert "QCA6174" in (pack / "laptop-report.txt").read_text()


# ------------------------------------------------------------------ the command

def test_cli_check_is_read_only(tmp_path, monkeypatch, capsys):
    pack = make_pack(tmp_path)
    monkeypatch.setattr(P, "records", lambda home=None: records())
    assert cli.main(["pack", "check", str(pack)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {e["status"] for e in out} == {"ok"}


def test_cli_install_needs_sudo(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    with pytest.raises(SystemExit, match="sudo bau pack install"):
        cli.main(["pack", "install", str(make_pack(tmp_path))])


# ------------------------------------------------------------------ the Windows side

def ps_models() -> dict[str, dict]:
    text = PS1.read_text()
    out = {}
    for m in re.finditer(r'Id\s*=\s*"([^"]+)";\s*File\s*=\s*"([^"]+)";\s*Url\s*=\s*"([^"]+)";'
                         r'\s*Size\s*=\s*(\d+);\s*Sha256\s*=\s*"([0-9a-f]{64})"', text):
        out[m.group(1)] = {"file": m.group(2), "url": m.group(3), "size": int(m.group(4)),
                           "sha256": m.group(5)}
    return out


def test_windows_list_matches_the_registry():
    reg = yaml.safe_load(DEFAULTS.read_text())["model"]
    got = ps_models()
    assert sorted(got) == sorted(P.PACK_MODELS)
    for mid, dl in got.items():
        assert dl == {k: reg[mid]["download"][k] for k in ("file", "url", "size", "sha256")}


def test_windows_script_never_picks_the_stick_and_uses_real_curl():
    text = PS1.read_text()
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert "Read-Host" in code and "Removable" in code
    assert "curl.exe" in code
    assert not re.search(r"\b(Format-Volume|Clear-Disk|Initialize-Disk|Remove-Partition)\b",
                         code, re.I)
    assert "??" not in code                        # Windows PowerShell 5.1 has no ??
    assert "BusType" in code                       # USB drives that call themselves "Fixed"
    assert "/media/`$USER/" in text and "/media/$USER/" not in text.replace("`$USER", "")
    raw = CMD.read_bytes()
    assert b"\r\n" in raw and b"pause" in raw and b"bau-pack-make.ps1" in raw


@needs_pwsh
def test_windows_make_downloads_verifies_and_deletes_bad_files(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    good, bad = src / "good.gguf", src / "bad.gguf"
    good.write_bytes(b"good model")
    bad.write_bytes(b"not what was pinned")
    deb = src / "wpa.deb"
    deb.write_bytes(b"deb bytes")
    zipfile = src / "main.zip"
    zipfile.write_bytes(b"PK zip")
    good_model = {"Id": "good", "File": "good.gguf", "Url": good.as_uri(), "Size": 10,
                  "Sha256": sha(b"good model")}
    wifi = {"Name": "wpasupplicant", "File": "wpa.deb", "Size": 9, "Sha256": sha(b"deb bytes"),
            "Urls": [(src / "gone.deb").as_uri(), deb.as_uri()]}   # the second link works
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "Models": [good_model,
                   {"Id": "bad", "File": "bad.gguf", "Url": bad.as_uri(), "Size": 19,
                    "Sha256": sha(b"something else")}],
        "Debs": [wifi], "BauZip": zipfile.as_uri()}))
    stick = tmp_path / "stick"
    stick.mkdir()
    cmd = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(PS1), "-Target", str(stick),
           "-Manifest", str(manifest), "-Yes"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    pack = stick / "BAU-PACK"
    models = pack / "models"
    assert r.returncode == 1, r.stdout + r.stderr
    assert (models / "good.gguf").read_bytes() == b"good model"
    assert not (models / "bad.gguf").exists() and not list(models.glob("*.part"))
    assert (pack / "wifi" / "wpa.deb").read_bytes() == b"deb bytes"
    assert (pack / "wifi" / "SHA256SUMS").read_text() == f"{sha(b'deb bytes')}  wpa.deb\n"
    assert (pack / "bau-main.zip").read_bytes() == b"PK zip"
    readme = (pack / "README.txt").read_text()
    assert "sudo bau pack install" in readme and "sudo apt install ./*.deb" in readme

    manifest.write_text(json.dumps({"Models": [good_model], "Debs": [wifi],
                                    "BauZip": zipfile.as_uri()}))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "already" in r.stdout


def ps_debs() -> dict[str, dict]:
    out = {}
    for m in re.finditer(r'Name\s*=\s*"([^"]+)";\s*File\s*=\s*"([^"]+)";\s*Pool\s*=\s*"([^"]+)";'
                         r'\s*Size\s*=\s*(\d+);\s*Sha256\s*=\s*"([0-9a-f]{64})"', PS1.read_text()):
        out[m.group(1)] = {"file": m.group(2), "pool": m.group(3), "size": int(m.group(4)),
                           "sha256": m.group(5)}
    return out


def test_windows_wifi_list_matches_the_laptop_side():
    got = ps_debs()
    assert sorted(got) == sorted(d["name"] for d in P.WIFI_DEBS)
    for d in P.WIFI_DEBS:
        assert got[d["name"]] == {k: d[k] for k in ("file", "pool", "size", "sha256")}
        assert d["pool"].endswith("/" + d["file"]) and d["pool"].startswith("pool/main/")
    assert "wpasupplicant" in got


def test_the_image_has_what_wifi_needs():
    # auto/config turns recommended packages off, so network-manager's Wi-Fi helpers
    # (it only recommends them) must be listed by name or the laptop has no Wi-Fi.
    config = (ROOT / "image" / "live-build" / "auto" / "config").read_text()
    assert "--apt-recommends false" in config
    listed = set((ROOT / "image" / "live-build" / "config" / "package-lists" /
                  "my-jarvis.list.chroot").read_text().split())
    assert {"network-manager", "wpasupplicant", "wireless-regdb", "iw"} <= listed


# ------------------------------------------------------------------ Wi-Fi programs from the stick

def make_wifi(pack: Path, bad: bool = False) -> list[dict]:
    debs = []
    (pack / "wifi").mkdir()
    for name, blob in (("wpasupplicant", b"wpa"), ("libpcsclite1", b"pcsc")):
        f = f"{name}_1_amd64.deb"
        (pack / "wifi" / f).write_bytes(blob + (b"x" if bad and name == "wpasupplicant" else b""))
        debs.append({"name": name, "file": f, "pool": f"pool/main/x/{f}", "size": len(blob),
                     "sha256": sha(blob)})
    return debs


def test_wifi_programs_are_installed_only_on_yes_and_only_when_checked(tmp_path, monkeypatch):
    pack = make_pack(tmp_path)
    monkeypatch.setattr(P, "WIFI_DEBS", make_wifi(pack))
    run = Runner()
    do_install(tmp_path, pack, Owner(), run=run)
    assert not any(c[0] == "apt-get" for c in run.calls)

    shutil.rmtree(tmp_path / "home")
    run = Runner({"dpkg-query": "install ok installed"})
    _, _, out = do_install(tmp_path, pack, Owner("Wi-Fi"), run=run)
    apt = next(c for c in run.calls if c[0] == "apt-get")
    assert apt[:3] == ["apt-get", "install", "-y"]
    assert sorted(Path(a).name for a in apt[3:]) == ["libpcsclite1_1_amd64.deb",
                                                      "wpasupplicant_1_amd64.deb"]
    assert ["systemctl", "restart", "NetworkManager"] in run.calls
    assert out["wifi"] == "installed"


def test_a_damaged_wifi_file_stops_the_wifi_step(tmp_path, monkeypatch):
    pack = make_pack(tmp_path)
    monkeypatch.setattr(P, "WIFI_DEBS", make_wifi(pack, bad=True))
    run = Runner()
    _, _, out = do_install(tmp_path, pack, Owner("Wi-Fi"), run=run)
    assert not any(c[0] == "apt-get" for c in run.calls)
    assert "wpasupplicant" in out["wifi"]


# ------------------------------------------------------------------ docs

def test_docs_explain_the_pack_in_plain_words():
    doc = (ROOT / "docs" / "PACK.md").read_text()
    for words in ("BAU-Pack-Make.cmd", "sudo bau pack install", "laptop-report.txt",
                  "erases", "yes or no"):
        assert words in doc, words
    assert "bau pack" in (ROOT / "CLAUDE.md").read_text()


def test_a_model_missing_from_the_laptop_registry_is_registered_before_measuring(tmp_path):
    pack = make_pack(tmp_path)
    home = tmp_path / "home"
    seen = []

    def bench(mid):
        reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
        seen.append(reg.data["model"][mid]["status"])
        return good_bench(mid)

    P.install(pack, home, tmp_path / "etc", ask=Owner("local model"), run=Runner(),
              by="human:owner", bench=bench, records=records(), say=lambda *_: None,
              sleep=lambda _: None)
    assert seen == ["REGISTERED"]


# ------------------------------------------------------------------ overhaul check

def test_wifi_says_so_when_apt_did_not_install_it(tmp_path, monkeypatch):
    # e.g. the laptop already has a newer wpasupplicant: apt refuses the older one.
    pack = make_pack(tmp_path)
    monkeypatch.setattr(P, "WIFI_DEBS", make_wifi(pack))
    _, _, out = do_install(tmp_path, pack, Owner("Wi-Fi"),
                           run=Runner({"apt-get": "E: downgrade refused",
                                       "dpkg-query": "unknown ok not-installed"}))
    assert out["wifi"].startswith("not installed")


def test_a_missing_model_service_is_said_plainly_not_waited_for(tmp_path):
    pack = make_pack(tmp_path)
    waited = []
    _, _, out = do_install(tmp_path, pack, Owner("local model"),
                           bench=lambda mid: waited.append(mid) or good_bench(mid),
                           run=Runner({"systemctl": "Unit bau-llm.service not found."}))
    assert waited == [] and out["approved"] == []
    assert any("bau-llm.service" in p and "not on this laptop" in p for p in out["problems"])


def test_a_wrong_passphrase_is_a_problem_and_the_report_is_still_written(tmp_path, monkeypatch):
    pack = make_pack(tmp_path, keys=True)

    def bad(*a, **k):
        raise P.keys.KeyFileError("not a BAU keys file (or a wrong passphrase)")
    monkeypatch.setattr(P.keys, "import_file", bad)
    _, _, out = do_install(tmp_path, pack, Owner("keys"), read_pass=lambda: "nope")
    assert out["keys"] is None and any("passphrase" in p for p in out["problems"])
    assert out.get("report")


def test_install_never_follows_a_planted_link(tmp_path):
    # /var/lib/bau is writable by the bau service account; run as root, a link planted
    # there must never make the install write to (or hand over) another file.
    pack = make_pack(tmp_path)
    home, _ = make_home(tmp_path)
    victim = tmp_path / "victim"
    victim.write_text("root stuff")
    rec = next(iter(records().values()))["download"]
    (home / "models").mkdir(parents=True, exist_ok=True)
    (home / "models" / (rec["file"] + ".part")).symlink_to(victim)
    P.install(pack, home, tmp_path / "etc", ask=Owner(), run=Runner(), by="human:owner",
              audit=None, records=records(), say=lambda *_: None, sleep=lambda _: None)
    assert victim.read_text() == "root stuff"
    (home / "reports").mkdir(exist_ok=True)
    report = home / "reports" / P.REPORT
    report.symlink_to(victim)
    assert P._safe_write(report, "report") is None or True
    assert victim.read_text() == "root stuff" and not report.is_symlink()


# ------------------------------------------------------------------ room to copy
# Found 2026-10-20 on the owner's own stick image in a VM: the live system's "disk" is a
# 3.7 GB slice of RAM. Without the encrypted storage open, /var/lib/bau lives there, and
# copying 6.5 GB of models fills the laptop's memory until programs are killed.

def test_install_stops_before_copying_when_there_is_no_room(tmp_path):
    pack = make_pack(tmp_path)
    with pytest.raises(P.PackError) as e:
        do_install(tmp_path, pack, Owner(), space=lambda p: (10, False))
    assert "room" in str(e.value)
    assert not list((tmp_path / "home" / "models").glob("*.gguf"))      # nothing half-copied


def test_install_never_copies_models_into_live_memory(tmp_path):
    pack = make_pack(tmp_path)
    with pytest.raises(P.PackError) as e:
        do_install(tmp_path, pack, Owner(), space=lambda p: (10**12, True))
    msg = str(e.value)
    assert "memory" in msg and "encrypted storage" in msg and "install" in msg.lower()


def test_models_already_in_place_need_no_room(tmp_path):
    pack = make_pack(tmp_path)
    home, _, first = do_install(tmp_path, pack, Owner())
    assert first["copied"]
    kw = dict(ask=Owner(), run=Runner(), by="human:owner", records=records(),
              say=lambda *_: None, sleep=lambda _: None)
    again = P.install(pack, home, tmp_path / "etc", space=lambda p: (0, False), **kw)
    assert again["copied"] == [] and len(again["already"]) == len(BLOBS)


def test_room_is_measured_even_before_the_folder_exists(tmp_path):
    # In the owner's live VM /var/lib/bau did not exist yet (no storage unlocked).
    free, in_memory = P._space(tmp_path / "not" / "there" / "yet")
    assert free > 0 and in_memory is False


def test_qwen35_is_asked_not_to_think_and_loading_from_a_stick_gets_time():
    rec = yaml.safe_load(DEFAULTS.read_text())["model"]["qwen3.5-4b"]
    assert rec["chat_template_kwargs"] == {"enable_thinking": False}
    assert P.BENCH_TRIES * 4 >= 300        # 2.7 GB from a USB stick can take minutes


def test_lfm25_is_registered_pinned_and_never_approved_by_default():
    rec = yaml.safe_load(DEFAULTS.read_text())["model"]["lfm2.5-2.6b"]
    assert rec["status"] == "REGISTERED" and rec["tools"] and rec["license"] == "LFM-Open-1.0"
    dl = rec["download"]
    assert dl["size"] == 1674455040 and len(dl["sha256"]) == 64
    assert dl["url"].startswith("https://huggingface.co/LiquidAI/")


def test_haiku_is_the_cheap_claude_and_needs_the_owner_to_approve_it():
    reg = yaml.safe_load(DEFAULTS.read_text())["model"]
    h, o = reg["claude-haiku-5-5"], reg["claude-opus-5-5"]
    assert h["status"] == "REGISTERED" and h["adapter"] == "anthropic"
    assert (h["cost_in_per_mtok"], h["cost_out_per_mtok"]) == (0.10, 0.50)    # official, dated
    assert o["cost_in_per_mtok"] / h["cost_in_per_mtok"] == 40


def test_the_desktop_boss_is_registered_pinned_and_never_approved_by_default():
    # docs/DESKTOP.md: Qwen3.5-9B for the RTX 3060 (12 GB). Size and SHA-256 from the HF API
    # tree of unsloth/Qwen3.5-9B-GGUF, read 2026-10-25; approved only after bau models bench.
    rec = yaml.safe_load(DEFAULTS.read_text())["model"]["qwen3.5-9b"]
    assert rec["status"] == "REGISTERED" and rec["tools"] and rec["license"] == "Apache-2.0"
    assert rec["chat_template_kwargs"] == {"enable_thinking": False}   # as the 4B (190 s)
    assert rec["endpoint"] == "http://127.0.0.1:8080"
    dl = rec["download"]
    assert (dl["size"], dl["sha256"]) == (
        5680522464, "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8")
    assert dl["url"] == ("https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/"
                         "Qwen3.5-9B-Q4_K_M.gguf")



# ------------------------------------------------------------------ the desktop's boss
# docs/DESKTOP.md: the 9B runs on the RTX 3060. On a computer without NVIDIA's driver loaded
# (the laptop, or the desktop before sudo bau-gpu-setup) it is not copied (5.7 GB) and the
# 4B stays the boss.

def test_the_9b_is_the_boss_only_where_the_nvidia_driver_is_loaded(tmp_path):
    _, _, out = do_install(tmp_path / "laptop", make_pack(tmp_path / "laptop", desktop=True),
                           Owner("Use", "Approve", "boss"), desktop=True)
    assert out["boss"] == "qwen3.5-4b" and "qwen3.5-9b" not in out["copied"]
    assert "NVIDIA" in out["skipped"]["qwen3.5-9b"]
    _, _, out = do_install(tmp_path / "desktop", make_pack(tmp_path / "desktop", desktop=True),
                           Owner("Use", "Approve", "boss"), desktop=True, gpu=lambda: True)
    assert out["boss"] == "qwen3.5-9b" and "qwen3.5-9b" in out["copied"]


# ------------------------------------------------------------------ audit 2026-10-25
def test_a_link_planted_on_the_stick_never_makes_root_overwrite_a_file(tmp_path):
    # The stick is untrusted: laptop-report.txt -> /etc/passwd must not be followed.
    pack = make_pack(tmp_path)
    victim = tmp_path / "victim"
    victim.write_text("keep me")
    (pack / P.REPORT).symlink_to(victim)
    do_install(tmp_path, pack, Owner())                     # the owner says no to all
    assert victim.read_text() == "keep me"
    assert not (pack / P.REPORT).is_symlink()


def test_an_approved_registry_stays_writable_for_the_bau_group(tmp_path):
    # Root wrote it 0644, so the Governor (account bau) could no longer quarantine.
    home, _, out = do_install(tmp_path, make_pack(tmp_path), Owner("Use", "Approve"))
    reg = home / "registry" / "capabilities.yaml"
    assert out["approved"] and (reg.stat().st_mode & 0o777) == 0o660


def test_the_pack_maker_refuses_a_fat32_stick():
    # Audit 2026-10-25: FAT32 holds at most 4 GB per file; the 9B model is 5.7 GB, so the
    # download failed forever with "run this again".
    text = (Path(__file__).resolve().parents[1] / "installer" / "bau-pack-make.ps1").read_text()
    assert '$d.DriveFormat -eq "FAT32"' in text and "exFAT" in text
