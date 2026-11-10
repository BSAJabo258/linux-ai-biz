"""Moving the owner's API keys from their other computer to the BAU laptop, safely.

An export script on the other computer (Windows: bau-keys-export.ps1 with a double-click
launcher; Mac/Linux: bau-keys-export.sh) finds API keys in environment variables and in
.env files the owner names, shows only their names, and locks them into one file
(BAU-KEYS.enc, AES-256 with a passphrase the owner chooses, openssl's format). On the
laptop `sudo bau keys import BAU-KEYS.enc` puts each key in /etc/bau/models.env or
platforms.env (root:bau 0640). Values are never printed, logged or audited: names only.
Written before the code."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from bau import keys as K
from bau.audit import AuditLog

ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "installer" / "bau-keys-export.ps1"
SH = ROOT / "installer" / "bau-keys-export.sh"
CMD = ROOT / "installer" / "BAU-Keys-Export.cmd"
PASS = "correct horse battery staple"
SECRETS = {"ANTHROPIC_API_KEY": "sk-ant-TEST-1234567890", "ZAI_API_KEY": "zai-TEST-abc",
           "TIKTOK_CLIENT_KEY": "tt-TEST-key", "TIKTOK_CLIENT_SECRET": "tt-TEST-secret"}
needs_openssl = pytest.mark.skipif(not shutil.which("openssl"), reason="needs openssl")
needs_pwsh = pytest.mark.skipif(not (shutil.which("pwsh") and shutil.which("openssl")),
                                reason="needs PowerShell (pwsh) and openssl")


def plain(**extra) -> str:
    lines = [K.HEADER] + [f"{k}={v}" for k, v in {**SECRETS, **extra}.items()]
    return "\n".join(lines) + "\n"


def lock(text: str, path: Path, passphrase: str = PASS) -> Path:
    """Encrypt the way both export scripts do (openssl enc, AES-256-CBC, PBKDF2)."""
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", str(K.ITERATIONS),
                    "-md", "sha256", "-salt", "-out", str(path), "-pass", "env:P"],
                   input=text.encode(), env={**os.environ, "P": passphrase}, check=True)
    return path


def env_file(path: Path) -> dict:
    out = {}
    for ln in path.read_text().splitlines():
        k, sep, v = ln.partition("=")
        if sep and not k.startswith("#"):
            out[k] = v.strip('"')
    return out


# ------------------------------------------------------------------ the laptop side

@needs_openssl
def test_import_puts_each_key_where_bau_reads_it(tmp_path):
    etc = tmp_path / "etc"
    audit = AuditLog(tmp_path / "audit" / "chain.jsonl", key=b"")
    res = K.import_file(lock(plain(), tmp_path / "BAU-KEYS.enc"), PASS, etc, audit)
    models, platforms = env_file(etc / "models.env"), env_file(etc / "platforms.env")
    assert models == {"ANTHROPIC_API_KEY": SECRETS["ANTHROPIC_API_KEY"],
                      "ZAI_API_KEY": SECRETS["ZAI_API_KEY"]}
    assert platforms == {"TIKTOK_CLIENT_KEY": "tt-TEST-key",
                         "TIKTOK_CLIENT_SECRET": "tt-TEST-secret"}
    for f in ("models.env", "platforms.env"):
        assert oct((etc / f).stat().st_mode & 0o777) == "0o640"
    assert res["written"]["models.env"] == ["ANTHROPIC_API_KEY", "ZAI_API_KEY"]
    shown = json.dumps(res) + (tmp_path / "audit" / "chain.jsonl").read_text()
    for v in SECRETS.values():
        assert v not in shown                                  # names only, never values
    assert any(r["event"] == "keys.imported" for r in audit.records())


@needs_openssl
def test_import_keeps_what_is_already_there_and_replaces_only_what_it_brings(tmp_path):
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "models.env").write_text("# my notes\nELEVENLABS_API_KEY=el-1\nZAI_API_KEY=old\n")
    K.import_file(lock(plain(), tmp_path / "k.enc"), PASS, etc, None)
    text = (etc / "models.env").read_text()
    assert "# my notes" in text and "ELEVENLABS_API_KEY=el-1" in text
    assert env_file(etc / "models.env")["ZAI_API_KEY"] == "zai-TEST-abc"
    assert text.count("ZAI_API_KEY=") == 1


@needs_openssl
def test_wrong_passphrase_or_a_strange_file_changes_nothing(tmp_path):
    etc = tmp_path / "etc"
    enc = lock(plain(), tmp_path / "k.enc")
    with pytest.raises(K.KeyFileError, match="passphrase"):
        K.import_file(enc, "wrong passphrase", etc, None)
    with pytest.raises(K.KeyFileError):
        K.import_file(lock("ANTHROPIC_API_KEY=x\n", tmp_path / "no-header.enc"), PASS, etc,
                      None)
    assert not etc.exists() or not any(etc.iterdir())


def test_only_plain_key_names_and_one_line_values_are_accepted():
    good = K.parse(K.HEADER + "\nexport NVIDIA_API_KEY='nv-1'\n\n# note\nHF_TOKEN=\"hf 2\"\n")
    assert good == {"NVIDIA_API_KEY": "nv-1", "HF_TOKEN": "hf 2"}
    for bad in ("lower_case=1", "WITH SPACE=1", "PATH=/usr/bin", "LD_PRELOAD=/x.so",
                "=nothing"):
        with pytest.raises(K.KeyFileError):
            K.parse(K.HEADER + "\n" + bad + "\n")


def test_a_bad_line_is_named_by_its_number_never_by_its_text():
    # A key spread over several lines (a PEM) leaves a line with no "=": the error must
    # not print the start of that line, which is part of a secret.
    pem_line = "MIIE" + "x" * 40                 # looks like the middle of a PEM key
    for bad in (pem_line, pem_line + "==", "lower_case=" + pem_line):
        with pytest.raises(K.KeyFileError) as e:
            K.parse(K.HEADER + "\nGOOD_API_KEY=1\n" + bad + "\n")
        assert pem_line[:12] not in str(e.value) and "line 3" in str(e.value)


# ------------------------------------------------------------------ the other computer

def _check_export(r, out: Path, tmp_path: Path):
    assert r.returncode == 0, r.stdout + r.stderr
    for name in SECRETS:
        assert name in r.stdout                                # the owner sees the names
    for v in SECRETS.values():
        assert v not in r.stdout and v not in r.stderr         # never the values
    assert v.encode() not in out.read_bytes()                  # and the file is locked
    etc = tmp_path / "etc"
    K.import_file(out, PASS, etc, None)
    models = env_file(etc / "models.env")
    assert models["ANTHROPIC_API_KEY"] == SECRETS["ANTHROPIC_API_KEY"]
    assert models["NVIDIA_API_KEY"] == "nv-from-file"          # from a .env file too
    assert "HOME" not in models and "PATH" not in models       # only keys, nothing else


def _dotenv(tmp_path: Path) -> Path:
    p = tmp_path / "project.env"
    p.write_text('export NVIDIA_API_KEY="nv-from-file"\nDEBUG=1\n')
    return p


@needs_pwsh
def test_windows_export_round_trip(tmp_path):
    out = tmp_path / "BAU-KEYS.enc"
    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(PS1),
                        "-Out", str(out), "-From", str(_dotenv(tmp_path)), "-Yes"],
                       env={**os.environ, **SECRETS, "BAU_KEYS_PASSPHRASE": PASS},
                       capture_output=True, text=True, timeout=120)
    _check_export(r, out, tmp_path)


@needs_pwsh
def test_windows_export_the_documented_way_reads_the_env_and_never_overwrites_it(tmp_path):
    # Usage in the script: bau-keys-export.ps1 [path\\to\\.env ...] - a bare path is a
    # file to read, never the output (it used to replace the .env with the locked file).
    env = _dotenv(tmp_path)
    before = env.read_bytes()
    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(PS1), str(env),
                        "-Yes"],
                       env={**os.environ, **SECRETS, "BAU_KEYS_PASSPHRASE": PASS},
                       capture_output=True, text=True, timeout=120, cwd=tmp_path)
    assert env.read_bytes() == before
    _check_export(r, tmp_path / "BAU-KEYS.enc", tmp_path)


@needs_openssl
def test_mac_linux_export_round_trip(tmp_path):
    out = tmp_path / "BAU-KEYS.enc"
    r = subprocess.run(["bash", str(SH), "--out", str(out), "--yes", str(_dotenv(tmp_path))],
                       env={**os.environ, **SECRETS, "BAU_KEYS_PASSPHRASE": PASS},
                       capture_output=True, text=True, timeout=60)
    _check_export(r, out, tmp_path)


def test_export_scripts_change_nothing_on_the_other_computer():
    code = "\n".join(ln for ln in PS1.read_text().splitlines()
                     if not ln.lstrip().startswith("#"))
    for m in re.finditer(r"\b(Set|Remove|Clear|Disable|Enable|Stop|Install|Uninstall)-\w+",
                         code, re.I):
        assert m.group(0) in {"Set-Content", "Set-StrictMode"}, m.group(0)
    for path in (PS1, SH):
        text = path.read_text()
        assert "SetEnvironmentVariable" not in text and "setx" not in text.lower()
    raw = CMD.read_bytes()
    assert b"\r\n" in raw and b"pause" in raw and b"bau-keys-export.ps1" in raw


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="needs shellcheck")
def test_shellcheck():
    r = subprocess.run(["shellcheck", str(SH)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


# ------------------------------------------------------------------ the command, shipping, docs

@needs_openssl
def test_cli_import_and_list_show_names_only(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    monkeypatch.setenv("BAU_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASS)
    etc = tmp_path / "etc"
    enc = lock(plain(), tmp_path / "BAU-KEYS.enc")
    assert main(["keys", "import", str(enc), "--etc", str(etc)]) == 0
    out = capsys.readouterr().out
    assert "ANTHROPIC_API_KEY" in out and SECRETS["ANTHROPIC_API_KEY"] not in out
    assert main(["keys", "list", "--etc", str(etc)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert "ZAI_API_KEY" in listed["models.env"]
    assert SECRETS["ZAI_API_KEY"] not in json.dumps(listed)


def test_ships_with_openssl_and_is_explained():
    mk = (ROOT / "installer" / "make-payload.sh").read_text()
    for f in ("bau-keys-export.ps1", "bau-keys-export.sh", "BAU-Keys-Export.cmd"):
        assert f in mk, f
    assert re.search(r"^openssl$", (ROOT / "image" / "live-build" / "config" / "package-lists"
                                    / "my-jarvis.list.chroot").read_text(), re.M)
    install = (ROOT / "installer" / "payload" / "install.sh").read_text()
    assert " openssl" in install
    # Keys imported before install.sh made the bau group are handed to it afterwards.
    assert 'chown root:bau "$f"' in install
    assert "/etc/bau/models.env /etc/bau/platforms.env" in install
    doc = (ROOT / "docs" / "KEYS.md").read_text()
    assert "BAU-Keys-Export.cmd" in doc and "sudo bau keys import" in doc
    assert "never" in doc.lower()


def test_no_passphrase_is_a_plain_message_not_a_traceback(monkeypatch, tmp_path):
    # 2026-10-27: Ctrl+D at the passphrase question ended in an EOFError traceback.
    import argparse

    from bau import cli_ext
    def eof(prompt=""):
        raise EOFError
    monkeypatch.setattr("getpass.getpass", eof)
    a = argparse.Namespace(keys_cmd="import", file=str(tmp_path / "BAU-KEYS.enc"),
                           etc=str(tmp_path / "etc"))
    with pytest.raises(SystemExit, match="no passphrase given, so nothing was imported"):
        cli_ext.cmd_keys(a)
    assert not (tmp_path / "etc").exists()
