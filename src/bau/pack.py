"""The BAU Pack: the laptop's models and keys, carried on a USB stick (docs/PACK.md).

A computer with internet fills the stick (installer/BAU-Pack-Make.cmd): ``BAU-PACK/models``
holds the local models, each checked against the SHA-256 pinned in the registry, and
``BAU-PACK/BAU-KEYS.enc`` the owner's locked keys, if they made one. On the laptop the
owner runs ``sudo bau pack install``. It is never started by plugging the stick in: a stick
anyone can write to must not run anything by itself.

The install checks every file again while copying it, so a damaged or swapped file never
reaches the model folder. Everything that changes what BAU runs - starting the local model,
approving it after a real benchmark, naming the team's boss, importing keys - waits for the
owner's yes. The thinker (the uncensored model) is only copied: it stays sealed in the
content lane and is approved separately. Last, a laptop report (network card, firmware,
radio switches, with addresses and Wi-Fi names hidden) is written back onto the stick so
Wi-Fi problems can be looked at from another computer.
"""

from __future__ import annotations

import datetime as dt
import glob
import hashlib
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from . import keys
from .home import shipped_data

PACK_DIR = "BAU-PACK"
THINKER = "qwen3-4b-heretic-content"
BOSS_ORDER = ("qwen3.5-4b", "qwen2.5-1.5b-instruct")
PACK_MODELS = ("qwen3.5-4b", THINKER, "qwen2.5-1.5b-instruct")
SEARCH = ("/media/*/*/BAU-PACK", "/media/*/BAU-PACK", "/mnt/*/BAU-PACK")
REPORT = "laptop-report.txt"
CHUNK = 1 << 20
BENCH_TRIES = 30

Ask = Callable[[str], bool]
Run = Callable[[list[str]], str]


class PackError(RuntimeError):
    pass


# ------------------------------------------------------------------ the stick
def root(path: Path | str) -> Path:
    """The BAU-PACK folder, given it or the stick it is on."""
    p = Path(path)
    for cand in (p, p / PACK_DIR):
        if (cand / "models").is_dir():
            return cand
    raise PackError(f"no BAU Pack at {p} (expected a {PACK_DIR} folder with models in it)")


def find(patterns: tuple[str, ...] | list[str] = SEARCH) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        for hit in sorted(glob.glob(pat)):
            if (Path(hit) / "models").is_dir() and Path(hit) not in out:
                out.append(Path(hit))
    return out


def records(home: Path | None = None) -> dict[str, dict[str, Any]]:
    """The pack's model records: shipped defaults, with the laptop's own registry on top."""
    shipped = yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text())["model"]
    out = {m: shipped[m] for m in PACK_MODELS if m in shipped}
    reg = (home / "registry" / "capabilities.yaml") if home else None
    if reg and reg.exists():
        mine = (yaml.safe_load(reg.read_text()) or {}).get("model") or {}
        out.update({m: mine[m] for m in PACK_MODELS if (mine.get(m) or {}).get("download")})
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while b := f.read(CHUNK):
            h.update(b)
    return h.hexdigest()


def _status(path: Path, dl: dict[str, Any], check_hash: bool) -> str:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return "not a regular file"
    if not path.exists():
        return "missing"
    if dl.get("size") and path.stat().st_size != int(dl["size"]):
        return "damaged"
    if check_hash and _sha256(path) != dl["sha256"]:
        return "damaged"
    return "ok"


def scan(pack: Path, recs: dict[str, dict[str, Any]], check_hash: bool = True
         ) -> list[dict[str, Any]]:
    """Each pack model with its status: ok, missing, damaged or not a regular file.
    Files the registry does not pin are ignored, never copied."""
    out = []
    for mid, rec in recs.items():
        dl = rec.get("download") or {}
        if not (dl.get("file") and len(str(dl.get("sha256", ""))) == 64):
            continue
        path = pack / "models" / dl["file"]
        out.append({"model_id": mid, "file": dl["file"], "size": dl.get("size"),
                    "status": _status(path, dl, check_hash)})
    return out


def _copy_verified(src: Path, dst: Path, want: str) -> bool:
    """Copy while hashing; the file lands under its name only if the hash matches."""
    part = dst.with_name(dst.name + ".part")
    h = hashlib.sha256()
    try:
        with src.open("rb") as fi, part.open("wb") as fo:
            while b := fi.read(CHUNK):
                fo.write(b)
                h.update(b)
        if h.hexdigest() != want:
            return False
        part.replace(dst)
        return True
    finally:
        part.unlink(missing_ok=True)


def _owned_by_bau(path: Path, mode: int) -> None:
    os.chmod(path, mode)
    if os.geteuid() == 0:
        try:
            shutil.chown(path, "root" if path.suffix == ".env" else "bau", "bau")
        except (LookupError, OSError):
            pass


# ------------------------------------------------------------------ install
def install(path: Path | str, home: Path, etc: Path, ask: Ask, run: Run, by: str,
            audit: Any = None, bench: Callable[[str], dict[str, Any]] | None = None,
            read_pass: Callable[[], str] | None = None,
            records: dict[str, dict[str, Any]] | None = None,
            say: Callable[..., None] = print,
            sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    if not by.startswith("human:"):
        raise PermissionError("only the owner installs a BAU Pack")
    pack = root(path)
    recs = records if records is not None else _pack_records(home)
    out: dict[str, Any] = {"pack": str(pack), "copied": [], "already": [], "skipped": {},
                           "approved": [], "boss": None, "keys": None, "problems": []}
    models = home / "models"
    models.mkdir(parents=True, exist_ok=True)

    say("Checking the models on the stick (each against its pinned SHA-256)...")
    for e in scan(pack, recs, check_hash=False):
        mid, dl = e["model_id"], recs[e["model_id"]]["download"]
        dst = models / dl["file"]
        if e["status"] != "ok":
            out["skipped"][mid] = e["status"]
            say(f"  {mid}: {e['status']} - not copied")
        elif _status(dst, dl, True) == "ok":
            out["already"].append(mid)
            say(f"  {mid}: already in place")
        elif _copy_verified(pack / "models" / dl["file"], dst, dl["sha256"]):
            _owned_by_bau(dst, 0o640)
            out["copied"].append(mid)
            say(f"  {mid}: copied and checked")
        else:
            out["skipped"][mid] = "damaged"
            say(f"  {mid}: damaged on the stick - not copied (make the pack again)")
    if audit is not None:
        audit.append("pack.copied", by, {"copied": out["copied"], "skipped": out["skipped"]})

    have = set(out["copied"]) | set(out["already"])
    boss = next((m for m in BOSS_ORDER if m in have), None)
    if boss and ask(f"Use {boss} as the local model Jarvis runs on (starts it now)?"):
        _register(home, boss, recs[boss])
        _start(boss, recs[boss], models, etc, run, say)
        res = _measure(boss, bench or _bench(home, by, audit), say, sleep)
        if res is None:
            out["problems"].append(f"{boss} did not answer; look at: journalctl -u bau-llm")
        elif not res.get("reply_ok"):
            out["problems"].append(f"{boss} did not answer properly, so it is not approved")
        elif ask(f"Approve {boss} for Jarvis on this laptop?"):
            approve(home, boss, by, audit, recs[boss], res)
            out["approved"].append(boss)
            if ask(f"Make {boss} the team's boss (it runs Jarvis and the agents)?"):
                from . import team
                team.set_team(home, by, audit, boss=boss)
                out["boss"] = boss
    if THINKER in have:
        say(f"The thinker ({THINKER}) is copied. It stays sealed (no tools, never kids); "
            "docs/PACK.md says how to start and approve it.")

    enc = pack / "BAU-KEYS.enc"
    if enc.is_file() and ask("Import your keys from BAU-KEYS.enc (asks for its passphrase)?"):
        if read_pass is None:
            raise PackError("no way to ask for the passphrase")
        out["keys"] = keys.import_file(enc, read_pass(), etc, audit, by)

    try:
        (pack / REPORT).write_text(laptop_report(run))
        out["report"] = str(pack / REPORT)
        say(f"Laptop report written to the stick: {REPORT}")
    except OSError as e:
        out["problems"].append(f"could not write {REPORT} on the stick: {e}")
    return out


_pack_records = records


def _register(home: Path, mid: str, rec: dict[str, Any]) -> None:
    """The benchmark reads the laptop's registry: add the record if it is not there yet."""
    from .registry import CapabilityRegistry
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    if mid not in reg.data["model"]:
        reg.add("model", {**rec, "status": "REGISTERED"})


def _start(mid: str, rec: dict[str, Any], models: Path, etc: Path, run: Run,
           say: Callable[..., None]) -> None:
    etc.mkdir(parents=True, exist_ok=True)
    env = etc / "llm.env"
    env.write_text(f"BAU_LLM_MODEL={models / rec['download']['file']}\n"
                   f"BAU_LLM_ALIAS={rec.get('api_model') or mid}\n")
    _owned_by_bau(env, 0o640)
    say(f"Starting {mid}...")
    run(["systemctl", "restart", "bau-llm.service"])


def _bench(home: Path, by: str, audit: Any) -> Callable[[str], dict[str, Any]]:
    from .models import bench as B
    return lambda mid: B.record(mid, by, home, audit)


def _measure(mid: str, bench: Callable[[str], dict[str, Any]], say: Callable[..., None],
             sleep: Callable[[float], None]) -> dict[str, Any] | None:
    say(f"Measuring {mid} on this laptop (it can take a minute to load)...")
    for _ in range(BENCH_TRIES):
        try:
            res = bench(mid)
        except Exception:                     # still loading, or not started
            sleep(4)
            continue
        say(f"  answered: {'yes' if res.get('reply_ok') else 'no'}; used a tool: "
            f"{'yes' if res.get('tool_calls') else 'no'}; speed: "
            f"{res.get('tokens_per_sec')} words-ish per second")
        return res
    return None


def approve(home: Path, mid: str, by: str, audit: Any, rec: dict[str, Any],
            measured: dict[str, Any]) -> None:
    """The owner's yes, recorded as `bau set-status model MID APPROVED` would."""
    from .registry import CapabilityRegistry, validate
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    cur = reg.data["model"].get(mid) or rec
    new = dict(cur, benchmark=cur.get("benchmark") or measured, status="APPROVED",
               reviewed_by=by, reviewed_at=dt.datetime.now(dt.UTC).isoformat())
    errs = validate("model", new)
    if errs:
        raise ValueError("; ".join(errs))
    reg.data["model"][mid] = new
    reg.path.parent.mkdir(parents=True, exist_ok=True)
    reg.path.write_text(yaml.safe_dump(reg.data, sort_keys=True))
    if audit is not None:
        audit.append("registry.status", by, {"kind": "model", "key": mid,
                                             "status": "APPROVED"})


# ------------------------------------------------------------------ the laptop report
MAC = re.compile(r"\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b", re.I)
SECRET = re.compile(r"psk|ssid|password|passphrase|wep-key|wpa-", re.I)
NOISE = re.compile(r"ath1[01]k|ath9k|iwlwifi|rtw|rtl8|brcm|wlan|wifi|wireless|firmware|"
                   r"80211|mt76", re.I)
SECTIONS = (
    ("Network devices", ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"]),
    ("Radio switches", ["rfkill", "list"]),
    ("Network cards", ["lspci", "-nnk"]),
    ("Links", ["ip", "-br", "link"]),
    ("Firmware packages", ["dpkg-query", "-W", "-f=${Package} ${Version}\\n", "firmware-*"]),
    ("Atheros QCA6174 firmware files", ["ls", "/lib/firmware/ath10k/QCA6174/hw3.0/"]),
    ("Kernel messages about Wi-Fi and firmware", ["dmesg"]),
    ("/etc/network/interfaces", ["cat", "/etc/network/interfaces"]),
    ("Kernel", ["uname", "-r"]),
)


def _cards(text: str) -> str:
    blocks, cur = [], []
    for line in text.splitlines():
        if line and not line[0].isspace():
            cur = [line]
            blocks.append(cur)
        elif cur:
            cur.append(line)
    keep = [b for b in blocks if re.search(r"Network controller|Ethernet controller", b[0])]
    return "\n".join("\n".join(b) for b in keep)


def _redact(text: str) -> str:
    lines = ["[line hidden]" if SECRET.search(ln) else MAC.sub("xx:xx:xx:xx:xx:xx", ln)
             for ln in text.splitlines()]
    return "\n".join(lines)


def laptop_report(run: Run) -> str:
    """What the laptop says about its network hardware. Safe to share: MAC addresses,
    Wi-Fi names and passwords are hidden."""
    out = [f"BAU laptop report, {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}"]
    for title, cmd in SECTIONS:
        text = run(cmd) or ""
        if cmd[0] == "lspci":
            text = _cards(text)
        elif cmd[0] == "dmesg":
            text = "\n".join([ln for ln in text.splitlines() if NOISE.search(ln)][-40:])
        elif cmd[0] == "cat":
            text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
        out += ["", f"== {title} ==", _redact(text.strip()) or "(nothing)"]
    return "\n".join(out) + "\n"


def run_cmd(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"(not available: {e})"
    return (r.stdout + r.stderr).strip()
