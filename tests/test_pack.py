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


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def records() -> dict[str, dict]:
    out = {}
    for mid, blob in BLOBS.items():
        rec = {**BASE, "model_id": mid, "name": mid, "api_model": mid,
               "endpoint": "http://127.0.0.1:8080", "tools": True,
               "download": {"url": f"https://example.invalid/{mid}.gguf",
                            "file": f"{mid}.gguf", "size": len(blob), "sha256": sha(blob)}}
        if "heretic" in mid:
            rec.update(trust_level="ABLITERATED", tools=False, lane="content_only",
                       use_for=["ideas"], endpoint="http://127.0.0.1:8082")
        out[mid] = rec
    return out


def make_pack(tmp_path: Path, only=None, keys=False) -> Path:
    pack = tmp_path / "stick" / "BAU-PACK"
    (pack / "models").mkdir(parents=True)
    for mid, blob in BLOBS.items():
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


def do_install(tmp_path, pack, owner, bench=good_bench, read_pass=None, run=None, **kw):
    home, audit = make_home(tmp_path)
    etc = tmp_path / "etc"
    out = P.install(pack, home, etc, ask=owner, run=run or Runner(), by="human:owner",
                    audit=audit, bench=bench, read_pass=read_pass, records=records(),
                    say=lambda *_: None, sleep=lambda _: None, **kw)
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
    assert P.find([str(tmp_path / "*" / "BAU-PACK")]) == [pack]
    assert P.find([str(tmp_path / "none" / "*")]) == []


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
    raw = CMD.read_bytes()
    assert b"\r\n" in raw and b"pause" in raw and b"bau-pack-make.ps1" in raw


@needs_pwsh
def test_windows_make_downloads_verifies_and_deletes_bad_files(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    good, bad = src / "good.gguf", src / "bad.gguf"
    good.write_bytes(b"good model")
    bad.write_bytes(b"not what was pinned")
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([
        {"Id": "good", "File": "good.gguf", "Url": good.as_uri(), "Size": 10,
         "Sha256": sha(b"good model")},
        {"Id": "bad", "File": "bad.gguf", "Url": bad.as_uri(), "Size": 19,
         "Sha256": sha(b"something else")}]))
    stick = tmp_path / "stick"
    stick.mkdir()
    cmd = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(PS1), "-Target", str(stick),
           "-Manifest", str(manifest), "-Yes"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    models = stick / "BAU-PACK" / "models"
    assert r.returncode == 1, r.stdout + r.stderr
    assert (models / "good.gguf").read_bytes() == b"good model"
    assert not (models / "bad.gguf").exists() and not list(models.glob("*.part"))
    assert "sudo bau pack install" in (stick / "BAU-PACK" / "README.txt").read_text()

    manifest.write_text(json.dumps([json.loads(manifest.read_text())[0]]))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "already" in r.stdout


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
