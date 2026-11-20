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


def _paired_station(tmp_path, monkeypatch, link="active", ssh=None):
    """A paired laptop with a fake _sh: `link` is what systemctl says, `ssh` what ssh gives."""
    from bau import cli_ext
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg = tmp_path / ".config/bau/station.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("desktop: owner@192.168.1.20\n")
    ran, opened = [], []

    def fake(*args, check=True, timeout=None):
        ran.append(args)
        if args[0] == "ssh":
            return ssh or subprocess.CompletedProcess(
                args, 0, "then open:\n  http://127.0.0.1:8766/?k=" + "b" * 32, "")
        return subprocess.CompletedProcess(args, 0 if link == "active" else 3, link + "\n", "")
    monkeypatch.setattr(cli_ext, "_sh", fake)
    monkeypatch.setattr("webbrowser.open", opened.append)
    return ran, opened


def test_open_with_the_link_down_says_why_and_never_tries_ssh(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    ran, opened = _paired_station(tmp_path, monkeypatch, link="inactive")
    assert main(["station", "open"]) != 0
    err = capsys.readouterr().err
    assert "link to the desktop is down (inactive)" in err
    for cause in ("off or asleep", "cable or hotspot", "sudo bau hq allow",
                  "bau station status", "systemctl --user restart bau-hq-link.service"):
        assert cause in err
    assert not any(a[0] == "ssh" for a in ran) and opened == []


def test_open_accepts_a_new_desktop_key_and_opens_the_world(tmp_path, monkeypatch):
    from bau.cli import main
    ran, opened = _paired_station(tmp_path, monkeypatch)
    assert main(["station", "open"]) == 0
    ssh = next(a for a in ran if a[0] == "ssh")
    assert "StrictHostKeyChecking=accept-new" in ssh and "BatchMode=yes" in ssh
    assert opened == ["http://127.0.0.1:8766/?k=" + "b" * 32 + "#world"]


def test_open_when_ssh_fails_shows_its_last_line_and_the_causes(tmp_path, monkeypatch, capsys):
    from bau.cli import main
    failed = subprocess.CompletedProcess(
        ["ssh"], 255, "", "debug: trying\nssh: connect to host 192.168.1.20 port 22: "
                         "Connection timed out\n")
    ran, opened = _paired_station(tmp_path, monkeypatch, ssh=failed)
    assert main(["station", "open"]) != 0
    err = capsys.readouterr().err
    assert "ssh said: ssh: connect to host 192.168.1.20 port 22: Connection timed out" in err
    assert "debug: trying" not in err and "off or asleep" in err and opened == []


def test_status_names_the_desktop_and_the_link_in_plain_words(tmp_path, monkeypatch, capsys):
    import json

    from bau.cli import main
    _paired_station(tmp_path, monkeypatch, link="inactive")
    assert main(["station", "status"]) != 0
    got = json.loads(capsys.readouterr().out)
    assert got["desktop"] == "owner@192.168.1.20" and got["tunnel"] == "inactive"
    assert got["link"] == "the link to the desktop owner@192.168.1.20 is down (inactive)"


def test_the_launcher_keeps_its_errors_on_screen():
    text = S.launcher("/usr/local/bin/bau")
    assert "Terminal=true" in text and "Terminal=false" not in text
    assert 'Exec=sh -c "/usr/local/bin/bau station open || ' in text and "read -r _" in text
    assert "Name=Jarvis HQ" in text and "station open" in text


def test_the_launcher_uses_the_installed_bau_not_a_stale_copy_on_path(tmp_path, monkeypatch):
    # The owner's desktop: an old ~/.local/bin/bau (2026-11-14) came first on PATH; the
    # launcher must not bake it in when /usr/local/bin/bau is installed.
    from bau import cli, cli_ext
    from bau.cli import main
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    installed = tmp_path / "usr-local-bin-bau"
    installed.write_text("#!/bin/sh\n")
    monkeypatch.setattr(cli, "INSTALLED_BAU", str(installed))
    monkeypatch.setattr(cli_ext, "shutil_which", lambda n: "/home/x/.local/bin/bau")

    def fake(*args, check=True, timeout=None):
        if args[0] == "ssh-keygen":
            Path(args[-1]).write_text("PRIVATE")
            Path(args[-1]).with_suffix(".pub").write_text(KEY + "\n")
        return subprocess.CompletedProcess(args, 0, "active", "")
    monkeypatch.setattr(cli_ext, "_sh", fake)
    desk = tmp_path / ".local/share/applications/bau-hq.desktop"
    assert main(["station", "pair", "owner@192.168.1.20"]) == 0
    assert str(installed) in desk.read_text() and ".local/bin/bau" not in desk.read_text()
    installed.unlink()                                       # not installed: PATH's bau
    assert main(["station", "pair", "owner@192.168.1.20"]) == 0
    assert "/home/x/.local/bin/bau" in desk.read_text()


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


# The owner's desktop: internet by USB from a tablet, a cable to the laptop (192.168.77.1).
# The first address of `hostname -I` may be the tablet's, which changes on every replug.
def test_hq_on_names_every_address_to_pair_with():
    from bau import cli_ext
    out = cli_ext._pair_next("bauadmin", "192.168.42.17 192.168.77.1 fe80::1 2600:abcd::5\n")
    assert out["addresses"] == ["192.168.42.17", "192.168.77.1", "2600:abcd::5"]
    assert out["next"] == [f"on the laptop: bau station pair bauadmin@{a}"
                           for a in out["addresses"]]
    assert "192.168.77.x" in out["hint"] and "replug" in out["hint"]
    assert cli_ext._pair_next("bauadmin", "fe80::2 2600::1 10.0.0.5")["addresses"] == \
        ["10.0.0.5", "2600::1"]                                       # IPv4 first
    assert cli_ext._pair_next("bauadmin", "")["next"] == \
        ["on the laptop: bau station pair bauadmin@THIS-COMPUTER"]


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


# ------------------------------------------------------------------ station mode (2026-11-18)
# Nothing knew the laptop was the station: its menu Jarvis took the tunnel's port, and its
# autopilot repeated the desktop's GitHub scans. `sudo bau station role on` is the switch.
def test_a_station_is_the_system_marker_or_a_paired_login(tmp_path):
    mark, home = tmp_path / "station", tmp_path / "home"
    assert not S.is_station(home, mark)
    mark.write_text("on=x\n")
    assert S.is_station(home, mark)
    mark.unlink()
    (home / ".config" / "bau").mkdir(parents=True)
    (home / ".config" / "bau" / "station.yaml").write_text("desktop: bauadmin@192.168.77.1\n")
    assert S.is_station(home, mark)


def station_on(tmp_path, monkeypatch):
    mark = tmp_path / "etc-bau-station"
    mark.write_text("on=2026-11-18T00:00:00+00:00\n")
    monkeypatch.setattr(S, "STATION_MARK", mark)
    return mark


def test_role_on_and_off_switch_the_marker_and_the_desktops_timers(tmp_path, monkeypatch,
                                                                    capsys):
    from bau import cli_ext
    from bau.cli import main
    mark = tmp_path / "etc" / "bau" / "station"
    monkeypatch.setattr(S, "STATION_MARK", mark)
    ran = []
    monkeypatch.setattr(cli_ext, "_sh", lambda *a, check=True, timeout=None:
                        ran.append((a, check)) or subprocess.CompletedProcess(a, 0, "", ""))
    monkeypatch.setattr(cli_ext.os, "geteuid", lambda: 1000)
    assert main(["station", "role", "on"]) == cli_ext.EXIT_BLOCKED      # needs sudo
    assert "sudo bau station role on" in capsys.readouterr().err
    assert not mark.exists() and ran == []
    monkeypatch.setattr(cli_ext.os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli_ext, "_human", lambda: "human:bauadmin")
    assert main(["station", "role", "on"]) == 0
    assert mark.read_text().startswith("on=") and S.is_station(tmp_path / "none", mark)
    assert ran == [(("systemctl", "disable", "--now", "bau-autopilot.timer",
                     "bau-scout-watch.timer"), False)]
    assert main(["station", "role", "off"]) == 0
    assert not mark.exists()
    assert ran[-1] == (("systemctl", "enable", "--now", "bau-autopilot.timer",
                        "bau-scout-watch.timer"), False)
    capsys.readouterr()
    monkeypatch.setattr(cli_ext, "_sh", lambda *a, check=True, timeout=None:
                        subprocess.CompletedProcess(a, 1, "", "Failed to connect to bus"))
    assert main(["station", "role", "on"]) == cli_ext.EXIT_ERROR      # never claims "off"
    assert "could not switch them off: Failed to connect to bus" in capsys.readouterr().out
    mark.unlink()
    hq = tmp_path / "hq"
    hq.write_text("admin=bauadmin\n")
    monkeypatch.setattr(S, "MARK", hq)
    assert main(["station", "role", "on"]) == cli_ext.EXIT_BLOCKED    # the desktop is not one
    assert "headquarters" in capsys.readouterr().err and not mark.exists()


def test_pair_names_the_role_switch_as_the_next_step(tmp_path, monkeypatch, capsys):
    from bau import cli_ext
    from bau.cli import main
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    def fake(*args, check=True, timeout=None):
        if args[0] == "ssh-keygen":
            Path(args[-1]).write_text("PRIVATE")
            Path(args[-1]).with_suffix(".pub").write_text(KEY + "\n")
        return subprocess.CompletedProcess(args, 0, "active", "")
    monkeypatch.setattr(cli_ext, "_sh", fake)
    assert main(["station", "pair", "bauadmin@192.168.77.1"]) == 0
    out = capsys.readouterr().out
    assert "sudo bau station role on" in out and "systemctl disable" not in out


def test_on_a_station_bau_jarvis_opens_the_desktops_and_never_starts_one(tmp_path,
                                                                         monkeypatch):
    from bau import cli_ext
    from bau.cli import main
    station_on(tmp_path, monkeypatch)
    monkeypatch.setattr("bau.assistant.build_assistant",
                        lambda **k: (_ for _ in ()).throw(AssertionError("second Jarvis")))
    monkeypatch.setattr("bau.ui.jarvis_server.serve",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("bound a port")))
    opened = []
    monkeypatch.setattr(cli_ext, "cmd_station", lambda a: opened.append(a.station_cmd) or 0)
    assert main(["jarvis"]) == 0 and opened == ["open"]
    assert main(["jarvis", "--no-browser"]) == 0 and opened == ["open", "open"]


def test_on_a_station_the_autopilot_runs_nothing(tmp_path, monkeypatch, capsys):
    from bau import autopilot, autopilot_jobs, fanvue
    from bau.cli import main
    station_on(tmp_path, monkeypatch)
    def boom(*a, **k):
        raise AssertionError("ran on the station")
    for mod, name in ((autopilot, "run"), (autopilot_jobs, "seed"), (fanvue, "autopost_tick")):
        monkeypatch.setattr(mod, name, boom)
    assert main(["autopilot", "run"]) == 0
    assert "This laptop is a station" in capsys.readouterr().out


def test_install_keeps_the_work_timers_off_on_a_station():
    sh = (ROOT / "installer" / "payload" / "install.sh").read_text()
    assert "[[ -f /etc/bau/station ]] && work_timers=()" in sh
    enable = sh[sh.index("systemctl enable bau-recover.service"):]
    enable = enable[:enable.index("bau-ui.service")]
    assert "bau-autopilot.timer" not in enable and "bau-scout-watch.timer" not in enable


# ------------------------------------------------------------------ remote desktop
XRDP = ROOT / "tests" / "data" / "xrdp"      # Debian 13's xrdp 0.10.1-3.1+deb13u2, as shipped


def test_remote_desktop_opens_3389_to_the_home_network_only_and_closes_again():
    rules = S._data("nftables-remote-desktop.rules")
    assert rules == (ROOT / "installer/payload/hardening/nftables-remote-desktop.rules").read_text()
    for base in (S._data("nftables-hq.conf"), S._data("nftables-default.conf")):
        on = S.with_remote_desktop(base)
        added = [ln.strip() for ln in on.splitlines() if ln.strip() and
                 not ln.strip().startswith("#") and ln not in base.splitlines()]
        assert len(added) == 2 and all("tcp dport 3389" in ln and "limit rate" in ln
                                       for ln in added)
        assert "0.0.0.0/0" not in on and "::/0" not in on
        assert on.index("tcp dport 3389") < on.index('counter comment "dropped inbound"')
        assert S.with_remote_desktop(on) == on                       # added once
        assert S.without_remote_desktop(on) == base                  # and taken away
    assert "tcp dport 3389" not in S.firewall() and "tcp dport 3389" in S.firewall(True)
    nft = shutil.which("nft") or ("/usr/sbin/nft" if Path("/usr/sbin/nft").exists() else None)
    if nft:
        # nft -c needs network admin rights; a private user and network namespace gives them
        # without root (checked on the desktop 2026-11-20: a planted typo fails there).
        cmd = [nft, "-c", "-f", "-"]
        r = subprocess.run(cmd, input=S.firewall(True), capture_output=True, text=True)
        if "not permitted" in r.stderr.lower() and shutil.which("unshare"):
            r = subprocess.run(["unshare", "-rn", *cmd], input=S.firewall(True),
                               capture_output=True, text=True)
        if "not permitted" in r.stderr.lower() or r.returncode and "unshare" in r.stderr:
            pytest.skip("nft -c needs privileges here")
        assert r.returncode == 0, r.stderr


def test_xrdp_takes_tls_only_and_only_the_owner():
    ini = S.xrdp_ini((XRDP / "xrdp.ini").read_text())
    assert "\nsecurity_layer=tls\n" in ini and "security_layer=negotiate" not in ini
    ses = S.sesman_ini((XRDP / "sesman.ini").read_text())
    for line in ("AllowRootLogin=false", f"TerminalServerUsers={S.RDP_GROUP}",
                 "AlwaysGroupCheck=true"):
        assert f"\n{line}\n" in ses
    with pytest.raises(ValueError):                                  # a different xrdp
        S.xrdp_ini("[Globals]\nport=3389\n")


def test_the_installer_keeps_the_remote_desktop_rule_like_bau_does(tmp_path):
    sh = (ROOT / "installer/payload/install.sh").read_text()
    assert "[[ -f /etc/bau/remote-desktop ]]" in sh and "nftables-remote-desktop.rules" in sh
    awk = shutil.which("awk")
    if not awk:
        pytest.skip("no awk")
    rules = tmp_path / "r.rules"
    rules.write_text(S._data("nftables-remote-desktop.rules"))
    prog = ('/counter comment "dropped inbound"/ { while ((getline l < f) > 0) print l } '
            '{ print }')
    assert prog in sh.replace("\\\n    ", "")
    out = subprocess.run([awk, "-v", f"f={rules}", prog], input=S._data("nftables-hq.conf"),
                         capture_output=True, text=True).stdout
    assert out == S.firewall(True)
