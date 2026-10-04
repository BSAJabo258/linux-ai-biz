"""Network and endpoint trust (spec §52-53).

Network trust decides which permission levels may run right now. Coffee-shop
Wi-Fi is UNTRUSTED: reads and local work continue, anything that changes the
outside world waits. Endpoint pins are optional and per service - never pin
blindly (spec §53).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import shutil
import socket
import ssl
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .home import bau_home
from .store import YamlStore


class Trust(StrEnum):
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"
    UNTRUSTED = "UNTRUSTED"
    LIMITED = "LIMITED"
    TRUSTED = "TRUSTED"
    VERIFIED = "VERIFIED"


ORDER = [Trust.OFFLINE, Trust.UNKNOWN, Trust.UNTRUSTED, Trust.LIMITED, Trust.TRUSTED,
         Trust.VERIFIED]

# Minimum network trust per permission level (spec §49 x §52).
MIN_TRUST = {
    "READ_ONLY": Trust.UNTRUSTED,
    "LOW_RISK": Trust.UNTRUSTED,
    "REVERSIBLE": Trust.LIMITED,
    "APPROVAL_REQUIRED": Trust.LIMITED,
    "HIGH_IMPACT": Trust.TRUSTED,
    "CRITICAL": Trust.TRUSTED,
}


def _h(v: str) -> str:
    return hashlib.sha256(v.strip().lower().encode()).hexdigest()[:16]


@dataclass
class NetworkFacts:
    online: bool
    wifi_ssid: str | None = None
    gateway_mac: str | None = None
    vpn_active: bool = False
    wired: bool = False


def detect() -> NetworkFacts:
    """Best-effort local detection; anything not determinable stays None."""
    online = _reachable("1.1.1.1", 53)
    ssid = None
    if shutil.which("iwgetid"):
        r = subprocess.run(["iwgetid", "-r"], capture_output=True, text=True, check=False)
        ssid = r.stdout.strip() or None
    vpn = any(Path("/sys/class/net").glob("wg*")) or any(Path("/sys/class/net").glob("tun*"))
    wired = False
    for p in Path("/sys/class/net").glob("*"):
        state = p / "operstate"
        if (p.name.startswith(("en", "eth")) and not (p / "wireless").exists()
                and state.exists() and state.read_text().strip() == "up"):
            wired = True
    gw_mac = None
    try:
        gw_ip = None
        for line in Path("/proc/net/route").read_text().splitlines()[1:]:
            f = line.split()
            if f[1] == "00000000":
                gw_ip = socket.inet_ntoa(bytes.fromhex(f[2])[::-1])
        if gw_ip:
            for line in Path("/proc/net/arp").read_text().splitlines()[1:]:
                f = line.split()
                if f[0] == gw_ip:
                    gw_mac = f[3]
    except OSError:
        pass
    return NetworkFacts(online=online, wifi_ssid=ssid, gateway_mac=gw_mac, vpn_active=vpn,
                        wired=wired)


def _reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class TrustPolicy:
    """Known networks are stored as hashes (SSID + gateway MAC), never in clear."""

    def __init__(self, path: Path | None = None):
        self.store = YamlStore(path or (bau_home() / "security" / "networks.yaml"),
                               {"trusted": [], "limited": []})

    def remember(self, facts: NetworkFacts, level: str) -> None:
        if level not in ("trusted", "limited"):
            raise ValueError("level must be trusted or limited")
        data = self.store.load()
        fp = self.fingerprint(facts)
        if fp is None:
            raise ValueError("cannot fingerprint this network (no SSID/gateway)")
        for k in ("trusted", "limited"):
            data[k] = [x for x in data.get(k, []) if x != fp]
        data[level].append(fp)
        self.store.save(data)

    @staticmethod
    def fingerprint(f: NetworkFacts) -> str | None:
        if not (f.wifi_ssid or f.gateway_mac):
            return None
        return _h(f"{f.wifi_ssid or ''}|{f.gateway_mac or ''}")

    def classify(self, f: NetworkFacts) -> Trust:
        if not f.online:
            return Trust.OFFLINE
        data = self.store.load()
        fp = self.fingerprint(f)
        if fp and fp in data.get("trusted", []):
            return Trust.VERIFIED if f.vpn_active else Trust.TRUSTED
        if fp and fp in data.get("limited", []):
            return Trust.TRUSTED if f.vpn_active else Trust.LIMITED
        if f.vpn_active:
            return Trust.LIMITED          # unknown network, but traffic is tunnelled
        if f.wifi_ssid:
            return Trust.UNTRUSTED        # unknown Wi-Fi: coffee-shop rule
        return Trust.UNKNOWN


def allows(trust: Trust, level: str) -> bool:
    return ORDER.index(trust) >= ORDER.index(MIN_TRUST.get(level, Trust.TRUSTED))


# ------------------------------------------------------------------ endpoints

class EndpointRegistry:
    """Service identity registry with optional certificate pinning (spec §53)."""

    def __init__(self, path: Path | None = None):
        self.store = YamlStore(path or (bau_home() / "security" / "endpoints.yaml"),
                               {"endpoints": {}})

    def add(self, service: str, domain: str, pins: list[str] | None = None,
            backup_pins: list[str] | None = None, rotation_policy: str = "") -> dict[str, Any]:
        data = self.store.load()
        if pins and not backup_pins:
            raise ValueError("a pinned endpoint needs a backup pin (spec §53)")
        rec = {"service": service, "domain": domain, "tls_policy": "verify",
               "pins": pins or [], "backup_pins": backup_pins or [],
               "rotation_policy": rotation_policy, "last_verified": None}
        data["endpoints"][service] = rec
        self.store.save(data)
        return rec

    def verify(self, service: str, fetch_cert=None) -> dict[str, Any]:
        data = self.store.load()
        rec = data["endpoints"][service]
        der = (fetch_cert or _peer_cert)(rec["domain"])
        fp = hashlib.sha256(der).hexdigest()
        allowed = rec["pins"] + rec["backup_pins"]
        ok = not allowed or fp in allowed
        rec["last_verified"] = dt.datetime.now(dt.UTC).isoformat() if ok else rec[
            "last_verified"]
        rec["last_fingerprint"] = fp
        self.store.save(data)
        return {"service": service, "ok": ok, "fingerprint": fp,
                "pinned": bool(allowed)}


def _peer_cert(domain: str, port: int = 443) -> bytes:
    ctx = ssl.create_default_context()  # chain + hostname validation always on
    with socket.create_connection((domain, port), timeout=10) as sock, \
            ctx.wrap_socket(sock, server_hostname=domain) as tls:
        der = tls.getpeercert(binary_form=True)
    if not der:
        raise ssl.SSLError("no peer certificate")
    return der
