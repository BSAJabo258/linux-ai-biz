"""The desktop as headquarters, the laptop as its operations station (docs/LAPTOP-STATION.md).
A station's key may only tunnel to Jarvis and print his address; SSH opens to the home
network only; the laptop listens for nothing and opens only Jarvis's own address."""

import shutil
import subprocess
from pathlib import Path

import pytest

from bau import station as S

ROOT = Path(__file__).resolve().parents[1]
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJ6xJmQm4o8b2fUHf1kVt3aD9m7uYkQZs4rT0pLqXyZa bau-station"


def test_a_station_key_can_only_reach_jarvis(tmp_path):
    line = S.key_line(KEY)
    assert line.startswith('restrict,port-forwarding,permitopen="127.0.0.1:8766",'
                           'command="/usr/local/bin/bau jarvis url" ssh-ed25519 ')
    ak = tmp_path / ".ssh" / "authorized_keys"
    S.allow(KEY, ak)
    S.allow(KEY, ak)                                          # twice: still one line
    assert ak.read_text().count("ssh-ed25519") == 1 and oct(ak.stat().st_mode)[-3:] == "600"
    assert S.stations(ak) == ["bau-station"]
    for bad in ('command="sh" ' + KEY, KEY + "\nssh-ed25519 AAAA", "ssh-dss AAAAB3Nza",
                KEY.replace(" bau-station", ' x" y'), "", 'no-pty ' + KEY):
        with pytest.raises(ValueError):
            S.key_line(bad)


def test_ssh_takes_keys_for_the_owner_only():
    conf = S.sshd_conf("owner")
    for want in ("PasswordAuthentication no", "PermitRootLogin no", "AllowUsers owner",
                 "AllowAgentForwarding no", "X11Forwarding no", "GatewayPorts no"):
        assert want in conf
    for bad in ("root", "Owner", "a b", "x\nPermitRootLogin yes"):
        with pytest.raises(ValueError):
            S.sshd_conf(bad)


def test_the_firewall_opens_ssh_to_the_home_network_only():
    hq, default = S.firewall(), S._data("nftables-default.conf")
    assert default == (ROOT / "installer/payload/hardening/nftables.conf").read_text()
    assert hq == (ROOT / "installer/payload/hardening/nftables-hq.conf").read_text()
    added = [ln.strip() for ln in hq.splitlines()
             if ln.strip() and not ln.strip().startswith("#") and ln not in default.splitlines()]
    assert len(added) == 2 and all("tcp dport 22" in ln and "limit rate" in ln for ln in added)
    assert "192.168.0.0/16" in added[0] and "0.0.0.0/0" not in hq and "::/0" not in hq
    nft = shutil.which("nft")
    if nft:
        r = subprocess.run([nft, "-c", "-f", "-"], input=hq, capture_output=True, text=True)
        if "not permitted" in r.stderr.lower():
            pytest.skip("nft -c needs privileges here")
        assert r.returncode == 0, r.stderr


def test_jarvis_runs_for_good_on_this_computer_only():
    assert S._data("bau-jarvis.service") == (
        ROOT / "installer/payload/systemd/bau-jarvis.service").read_text()
    unit = S.jarvis_unit("owner", "/home/owner")
    assert "User=owner" in unit and "ReadWritePaths=/var/lib/bau /home/owner/.config/bau" in unit
    assert "bau jarvis --service --port 8766" in unit and "@" not in unit.split("[Service]")[1]
    with pytest.raises(ValueError):
        S.jarvis_unit("root", "/root")
    sh = (ROOT / "installer/payload/install.sh").read_text()
    assert '[[ -f /etc/bau/hq ]] && HQ=1' in sh and "nftables-hq.conf" in sh


def test_the_laptop_tunnel_reconnects_and_forwards_jarvis_only():
    unit = S.link_unit("owner", "192.168.1.20", Path("/home/me/.ssh/bau_station_ed25519"))
    assert "-L 127.0.0.1:8766:127.0.0.1:8766 owner@192.168.1.20" in unit
    for want in ("ExitOnForwardFailure=yes", "ServerAliveInterval=15", "BatchMode=yes",
                 "Restart=always", "-N -T"):
        assert want in unit
    for user, host in (("owner", "-oProxyCommand=x"), ("owner", "a b"), ("root x", "h"),
                       ("owner", "")):
        with pytest.raises(ValueError):
            S.link_unit(user, host, Path("/k"))


def test_the_laptop_opens_only_jarvis_own_address():
    printed = ("On your own computer, keep this running:\n  ssh -L 8766:127.0.0.1:8766 x@y\n"
               "then open:\n  http://127.0.0.1:8766/?k=" + "a" * 32 + "\n")   # bau jarvis url
    url = S.world_url(printed)
    assert url == "http://127.0.0.1:8766/?k=" + "a" * 32 + "#world"
    for bad in ("", "http://evil.example/?k=" + "a" * 32, "http://127.0.0.1:8766/?k=short",
                "file:///etc/passwd", "http://127.0.0.1:8766/?k=" + "a" * 32 + "&x=1"):
        with pytest.raises(ValueError):
            S.world_url(bad)


def test_station_commands(tmp_path, monkeypatch, capsys):
    from bau import cli_ext
    from bau.cli import main
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    ran = []

    def fake(*args, check=True):
        ran.append(args)
        if args[0] == "ssh-keygen":
            f = Path(args[-1])
            f.write_text("PRIVATE")
            f.with_suffix(".pub").write_text(KEY + "\n")
        out = "then open:\n  http://127.0.0.1:8766/?k=" + "b" * 32 if args[0] == "ssh" else "active"
        return subprocess.CompletedProcess(args, 0, out, "")
    monkeypatch.setattr(cli_ext, "_sh", fake)
    assert main(["station", "open"]) != 0                      # not paired yet
    assert main(["station", "pair", "owner@192.168.1.20"]) == 0
    out = capsys.readouterr().out
    assert f"sudo bau hq allow '{KEY}'" in out
    assert (tmp_path / ".config/systemd/user/bau-hq-link.service").exists()
    assert "station open" in (tmp_path / ".local/share/applications/bau-hq.desktop").read_text()
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert main(["station", "open"]) == 0 and opened[0].endswith("#world")
    assert main(["station", "pair", "owner@bad host"]) != 0
    if __import__("os").geteuid() != 0:
        assert main(["hq", "on"]) != 0                         # needs sudo
