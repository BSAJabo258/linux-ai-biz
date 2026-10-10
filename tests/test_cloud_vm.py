"""BAU on the owner's own cloud server (DigitalOcean droplet, Debian 13): a prepare script
for the new server, SSH as the only way in (key login only), Jarvis always on behind a
fixed key and reachable only through an SSH tunnel. Written before the code it tests."""

import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HARD = ROOT / "installer" / "payload" / "hardening"
CLOUD = ROOT / "installer" / "cloud"


# ------------------------------------------------------------------ the firewall

def test_cloud_firewall_is_the_laptop_firewall_plus_rate_limited_ssh_only():
    base = (HARD / "nftables.conf").read_text().splitlines()
    cloud = (HARD / "nftables-cloud.conf").read_text().splitlines()
    added = [ln for ln in cloud if ln not in base]
    removed = [ln for ln in base if ln not in cloud]
    assert removed == []
    rules = [ln.strip() for ln in added if ln.strip() and not ln.strip().startswith("#")]
    assert rules == ['tcp dport 22 ct state new limit rate 15/minute accept '
                     'comment "BAU cloud: SSH, key login only"']
    assert "policy drop" in "\n".join(cloud)


@pytest.mark.skipif(shutil.which("nft") is None, reason="nft not installed")
def test_cloud_firewall_parses():
    r = subprocess.run(["nft", "-c", "-f", str(HARD / "nftables-cloud.conf")],
                       capture_output=True, text=True)
    if r.returncode and "Operation not permitted" in r.stderr:
        pytest.skip("nft -c needs privileges here")
    assert r.returncode == 0, r.stderr


def test_installer_uses_the_cloud_firewall_only_when_asked_and_keeps_it():
    sh = (ROOT / "installer" / "payload" / "install.sh").read_text()
    assert "--cloud)" in sh and "/etc/bau/cloud" in sh
    assert "nftables-cloud.conf" in sh
    assert "install.cloud" in sh                    # recorded in the audit chain
    assert "bau-jarvis.service" in sh


# ------------------------------------------------------------------ preparing the server

def test_cloud_init_runs_the_prepare_script_and_holds_no_secrets():
    text = (CLOUD / "cloud-init.yaml").read_text()
    assert text.startswith("#cloud-config")
    doc = yaml.safe_load(text)
    cmds = " ".join(str(c) for c in doc["runcmd"])
    assert "installer/cloud/prepare.sh" in cmds
    assert "https://github.com/BSAJabo258/linux-ai-biz" in cmds
    for bad in ("password", "token", "api_key", "secret"):
        assert bad not in text.lower()


def test_prepare_script_locks_ssh_to_keys_and_never_locks_the_owner_out():
    sh = (CLOUD / "prepare.sh").read_text()
    assert "PasswordAuthentication no" in sh and "PermitRootLogin no" in sh
    assert "authorized_keys" in sh and "no SSH key" in sh       # refuses without a key
    assert sh.index("no SSH key") < sh.index("PermitRootLogin no")
    assert "sshd -t" in sh                                       # config checked first
    assert "make-payload.sh" in sh


def test_jarvis_service_runs_as_the_owner_on_localhost_only():
    unit = (ROOT / "installer" / "payload" / "systemd" / "bau-jarvis.service").read_text()
    assert "User=@ADMIN@" in unit and "jarvis --service" in unit
    # He calls hosted models, so outbound stays open; he listens on 127.0.0.1 only, which
    # only BAU_IN_CONTAINER could change.
    assert "BAU_IN_CONTAINER" not in unit and "ProtectSystem=strict" in unit
    hook = (ROOT / "image" / "live-build" / "config" / "hooks" / "live" /
            "0500-bau.hook.chroot").read_text()
    assert "rm -f /etc/systemd/system/bau-jarvis.service" in hook    # the live USB skips it


# ------------------------------------------------------------------ Jarvis as a service

def test_service_key_is_created_private_and_stays_the_same(tmp_path):
    from bau.ui.jarvis_server import service_key
    f = tmp_path / "jarvis.key"
    k = service_key(f)
    assert len(k) >= 32 and stat.S_IMODE(f.stat().st_mode) == 0o600
    assert service_key(f) == k


def test_service_mode_refuses_root_and_the_agent_account(monkeypatch):
    from bau.cli import main
    for who in ("root", "bau"):
        monkeypatch.setattr("getpass.getuser", lambda w=who: w)
        assert main(["jarvis", "--service"]) == 3


def test_jarvis_url_prints_the_tunnel_address(tmp_path, capsys):
    from bau.cli import main
    from bau.ui.jarvis_server import service_key
    f = tmp_path / "jarvis.key"
    k = service_key(f)
    assert main(["jarvis", "url", "--key-file", str(f)]) == 0
    out = capsys.readouterr().out
    assert f"http://127.0.0.1:8766/?k={k}" in out and "ssh -L 8766:127.0.0.1:8766" in out


def test_owner_guide_exists():
    doc = (ROOT / "docs" / "CLOUD-VM.md").read_text()
    for need in ("DigitalOcean", "ssh-keygen", "ssh -L", "install.sh --cloud",
                 "/etc/bau/models.env", "Backups"):
        assert need in doc, need
