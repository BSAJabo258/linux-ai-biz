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
                 "AllowAgentForwarding no", "X11Forwarding no", "GatewayPorts no",
                 "AllowTcpForwarding local", "AllowStreamLocalForwarding no"):
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
    assert "sed -n 's/^admin=//p' /etc/bau/hq" in sh             # Jarvis stays the HQ login's


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

    def fake(*args, check=True, timeout=None):
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
    assert ("systemctl", "--user", "restart", "bau-hq-link.service") in ran   # a new desktop
    ssh = next(a for a in ran if a[0] == "ssh")
    assert "ServerAliveInterval=5" in ssh
    assert main(["station", "pair", "owner@bad host"]) != 0
    if __import__("os").geteuid() != 0:
        assert main(["hq", "on"]) != 0                         # needs sudo


# The owner's desktop, 2026-11-16: the menu's Jarvis held port 8766, so bau-jarvis.service
# restarted 626 times ("Address already in use"). With headquarters on, `bau jarvis` opens
# the one that runs for good instead of starting a second.
def test_with_headquarters_on_the_menu_opens_the_jarvis_that_runs_for_good(tmp_path,
                                                                          monkeypatch, capsys):
    from bau import cli_ext, station
    from bau.cli import main
    mark = tmp_path / "hq"
    mark.write_text("admin=owner\non=2026-11-17T00:42:49+00:00\n")
    monkeypatch.setattr(station, "MARK", mark)
    keyf = tmp_path / "jarvis.key"
    state = {"now": "active"}
    monkeypatch.setattr(cli_ext, "_sh", lambda *a, check=True, timeout=None:
                        subprocess.CompletedProcess(a, 0, state["now"] + "\n", ""))
    monkeypatch.setattr("bau.assistant.build_assistant",
                        lambda **k: (_ for _ in ()).throw(AssertionError("second Jarvis")))
    opened = []
    monkeypatch.setattr(cli_ext, "_open_browser", opened.append)
    assert main(["jarvis", "--key-file", str(keyf)]) == 0
    assert opened[0].startswith("http://127.0.0.1:8766/?k=")
    assert keyf.read_text().strip() in opened[0]
    state["now"] = "activating"
    assert main(["jarvis", "--key-file", str(keyf)]) != 0          # says how to start him
    assert "systemctl restart bau-jarvis.service" in capsys.readouterr().err


def test_hq_on_checks_jarvis_really_started_and_status_reads_the_admin(tmp_path, monkeypatch):
    from bau import cli_ext
    seen = []
    monkeypatch.setattr(cli_ext, "_sh", lambda *a, check=True, timeout=None:
                        subprocess.CompletedProcess(a, 0, "activating\n", ""))
    assert cli_ext._jarvis_started(sleep=seen.append) == "activating" and seen == [4]
    mark = tmp_path / "hq"
    monkeypatch.setenv("SUDO_USER", "someone")
    assert cli_ext._hq_admin(mark) == "someone"
    mark.write_text("admin=bauadmin\non=x\n")
    assert cli_ext._hq_admin(mark) == "bauadmin"


SS_LINE = 'LISTEN 0 5 127.0.0.1:8766 0.0.0.0:* users:(("python3",pid=1234,fd=3))\n'


# The owner's desktop, 2026-11-16: the service hit "Address already in use" 626 times, each
# a long traceback. Now one plain line names who holds the port, and systemd gives up.
def test_who_holds_jarvis_port_comes_from_ss_never_a_guess(monkeypatch):
    from bau import cli_ext
    out = {"r": subprocess.CompletedProcess([], 0, SS_LINE, "")}
    ran = []

    def fake_sh(*a, check=True, timeout=None):
        ran.append((a, timeout))
        if isinstance(out["r"], Exception):
            raise out["r"]
        return out["r"]
    monkeypatch.setattr(cli_ext, "_sh", fake_sh)
    assert cli_ext._port_holder(8766) == "python3 (pid 1234)"
    assert ran[0] == (("ss", "-ltnpH", "sport = :8766"), 3)
    assert cli_ext._taken_by(8766) == "; 127.0.0.1:8766 is taken by python3 (pid 1234)"
    out["r"] = subprocess.CompletedProcess([], 0, "LISTEN 0 5 127.0.0.1:8766 0.0.0.0:*\n", "")
    assert cli_ext._port_holder(8766) == "another program"     # not root: no process shown
    out["r"] = subprocess.CompletedProcess([], 1, "", "ss: failed")
    assert cli_ext._port_holder(8766) == "another program"
    out["r"] = FileNotFoundError("ss")
    assert cli_ext._port_holder(8766) == "another program"
    out["r"] = subprocess.CompletedProcess([], 0, "", "")
    assert cli_ext._port_holder(8766) is None                  # nothing listens there
    assert cli_ext._taken_by(8766) == ""


def test_a_taken_port_gives_one_plain_line_not_a_traceback(tmp_path, monkeypatch, capsys):
    import errno

    from bau import cli_ext
    from bau.cli import main

    class FakeJarvis:
        provider = None

        def warm(self):
            pass
    monkeypatch.setattr(cli_ext.getpass, "getuser", lambda: "owner")
    monkeypatch.setattr("bau.assistant.load_env_file", lambda *a, **k: None)
    monkeypatch.setattr("bau.assistant.build_assistant", lambda **k: FakeJarvis())
    out = {"r": subprocess.CompletedProcess([], 0, SS_LINE, "")}
    monkeypatch.setattr(cli_ext, "_sh", lambda *a, check=True, timeout=None: out["r"])
    err = {"e": OSError(errno.EADDRINUSE, "Address already in use")}

    def fake_serve(*a, **k):
        raise err["e"]
    monkeypatch.setattr("bau.ui.jarvis_server.serve", fake_serve)
    args = ["jarvis", "--service", "--port", "8766", "--key-file", str(tmp_path / "k")]
    assert main(args) == cli_ext.EXIT_BLOCKED
    said = capsys.readouterr().err
    assert "Jarvis's address 127.0.0.1:8766 is already taken by python3 (pid 1234)." in said
    assert "Ctrl+C" in said and "sudo systemctl restart bau-jarvis.service" in said
    assert "Traceback" not in said and len(said.strip().splitlines()) == 1
    out["r"] = subprocess.CompletedProcess([], 0, "", "")      # gone by the time ss looks
    assert main(args) == cli_ext.EXIT_BLOCKED
    assert "is already taken by another program." in capsys.readouterr().err
    err["e"] = OSError(errno.EADDRNOTAVAIL, "Cannot assign requested address")
    with pytest.raises(OSError):
        main(args)                                             # other errors still raise


def test_a_taken_port_does_not_restart_jarvis_forever():
    unit = S._data("bau-jarvis.service")
    head = unit.split("[Service]")[0]
    assert "StartLimitIntervalSec=120" in head and "StartLimitBurst=5" in head
    assert "Restart=on-failure" in unit
