"""The desktop as headquarters, the laptop as its operations station (the owner, 2026-11-15:
"Jarvis is on the desktop, the AI workstation is on the laptop, controlled by Jarvis";
docs/LAPTOP-STATION.md).

Jarvis, the models and the heavy work stay on the desktop. The laptop shows Jarvis and his
world through one SSH tunnel; it runs no Jarvis of its own and needs no models.

Desktop (``sudo bau hq on``), the second exception to "nothing listens for the outside":
- Jarvis runs for good as a service, still on 127.0.0.1 only (bau-jarvis.service, as on the
  owner's cloud server);
- SSH takes keys only, for the owner's login only, and only from home-network addresses,
  rate-limited (nftables).

Laptop (``bau station pair HOST``): its own key. The desktop lets that key do two things only
(``bau hq allow``): forward to Jarvis's port, and print Jarvis's address. No shell, no other
port, no agent or X11 forwarding. The laptop listens for nothing, so the desktop cannot push
anything to it. A user service keeps the tunnel up and reconnects after a network drop.
"""

from __future__ import annotations

import datetime as dt
import re
from importlib import resources
from pathlib import Path

JARVIS_PORT = 8766
SSHD_CONF = Path("/etc/ssh/sshd_config.d/10-bau-hq.conf")
FIREWALL = Path("/etc/nftables.conf")
MARK = Path("/etc/bau/hq")
STATION_MARK = Path("/etc/bau/station")      # `sudo bau station role on`: readable by services
UNIT = Path("/etc/systemd/system/bau-jarvis.service")
KEY_LINE = re.compile(r"^(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa) [A-Za-z0-9+/]{40,}={0,2}"
                      r"( [\w.@+-]{1,64})?$")
HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def _data(name: str) -> str:
    return (resources.files("bau.data") / "hq" / name).read_text()


# ------------------------------------------------------------------ the desktop
def sshd_conf(admin: str) -> str:
    if not USER.match(admin) or admin == "root":
        raise ValueError(f"{admin!r} is not an ordinary login name")
    return ("# BAU headquarters (bau hq on): the laptop station's key is the only way in.\n"
            "PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n"
            f"AllowUsers {admin}\nX11Forwarding no\nAllowAgentForwarding no\n"
            "PermitTunnel no\nGatewayPorts no\n"
            # Only -L tunnels (the station's one to Jarvis): no reverse listeners on this
            # computer and no Unix-socket forwards, which permitopen does not cover.
            "AllowTcpForwarding local\nAllowStreamLocalForwarding no\n")


def firewall() -> str:
    """The shipped default firewall plus SSH from home-network addresses only."""
    return _data("nftables-hq.conf")


def jarvis_unit(admin: str, home: str) -> str:
    if not USER.match(admin) or admin == "root":
        raise ValueError(f"{admin!r} is not an ordinary login name")
    return _data("bau-jarvis.service").replace("@ADMIN@", admin).replace("@HOME@", home)


def key_line(public_key: str) -> str:
    """The authorized_keys line for a station: tunnel to Jarvis only, and the only command it
    can run prints Jarvis's address."""
    key = " ".join(public_key.strip().split())
    if not KEY_LINE.match(key):
        raise ValueError("that is not one SSH public key (it starts ssh-ed25519 ...)")
    return (f'restrict,port-forwarding,permitopen="127.0.0.1:{JARVIS_PORT}",'
            f'command="/usr/local/bin/bau jarvis url" {key}')


def allow(public_key: str, authorized_keys: Path) -> str:
    line = key_line(public_key)
    authorized_keys.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    old = authorized_keys.read_text() if authorized_keys.exists() else ""
    if line not in old.splitlines():
        authorized_keys.write_text(old + ("" if not old or old.endswith("\n") else "\n")
                                   + line + "\n")
    authorized_keys.chmod(0o600)
    return line


def stations(authorized_keys: Path) -> list[str]:
    if not authorized_keys.exists():
        return []
    return [ln.split()[-1] for ln in authorized_keys.read_text().splitlines()
            if 'command="/usr/local/bin/bau jarvis url"' in ln]


# ------------------------------------------------------------------ the laptop
def _home() -> Path:
    return Path.home()


def is_station(home_dir: Path | None = None, mark: Path | None = None) -> bool:
    """This laptop is the operations station: the desktop does the work, so nothing here may
    start a second Jarvis, autopilot or money machine. The system marker (`sudo bau station
    role on`) is what services running as `bau` see; the paired login's own file counts too."""
    def there(f) -> bool:
        try:
            return f().exists()
        except (OSError, RuntimeError):      # an unreadable folder, or no home at all
            return False
    return (there(lambda: STATION_MARK if mark is None else mark)
            or there(lambda: (_home() if home_dir is None else home_dir)
                     / ".config" / "bau" / "station.yaml"))


def link_unit(user: str, host: str, key: Path) -> str:
    """A user service that keeps the tunnel to the desktop's Jarvis up."""
    if not USER.match(user) or not HOST.match(host):
        raise ValueError("give the desktop as NAME@ADDRESS, e.g. bauadmin@192.168.1.20")
    return f"""# BAU station: the tunnel to Jarvis on the desktop (bau station pair).
[Unit]
Description=BAU station: tunnel to Jarvis at {host}
After=network-online.target

[Service]
ExecStart=/usr/bin/ssh -N -T -i {key} -o IdentitiesOnly=yes -o BatchMode=yes \\
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \\
  -o StrictHostKeyChecking=accept-new \\
  -L 127.0.0.1:{JARVIS_PORT}:127.0.0.1:{JARVIS_PORT} {user}@{host}
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""


def launcher(bau: str) -> str:
    return ("[Desktop Entry]\nType=Application\nName=Jarvis HQ\n"
            "Comment=Jarvis and his world, on the desktop\n"
            f"Exec={bau} station open\nIcon=applications-system\nTerminal=false\n")


def world_url(printed: str) -> str:
    """The address the desktop printed, checked: Jarvis on this end of the tunnel, with its key,
    opening on the world. Anything else is refused, never opened."""
    url = printed.strip().splitlines()[-1].strip() if printed.strip() else ""
    m = re.fullmatch(rf"http://127\.0\.0\.1:{JARVIS_PORT}/\?k=([A-Za-z0-9_-]{{20,}})", url)
    if not m:
        raise ValueError("the desktop did not answer with Jarvis's address")
    return url + "#world"


def stamp() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
