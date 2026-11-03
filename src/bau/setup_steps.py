"""Setup steps that pop up for the owner (the owner's ask, 2026-11-02: "a pop-up menu for me
to click the accept button so that it can continue").

Each step knows how to tell whether it is already done on this computer. Jarvis shows every
step still waiting as a card with Accept; nothing runs without that click. A step that needs
the owner's password opens a terminal window running the exact command, so the owner sees it
and types the password there. Owner-only values (prices) are typed by the owner in that
window, never filled in. Done steps disappear the next time Jarvis checks.
"""

from __future__ import annotations

import datetime as dt
import os
import shlex
import shutil
import subprocess
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .home import shipped_data

Probe = Callable[[str], object]
Terminal = Callable[[str, str], bool]


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    why: str


STEPS = (
    Step("api_keys", "Use your API keys while online",
         "Your keys are on this computer, but the models they pay for aren't switched on, so "
         "Jarvis only uses the slower local model. Online he'll answer with them first and "
         "fall back to the local model; offline he uses the local one. A terminal opens. "
         "Note: NVIDIA's free API is a trial for testing; their terms say business use "
         "needs a paid subscription."),
    Step("laws", "Bring in the current rules",
         "Your computer still reads the rules copied at install time (YouTube and kids rules, "
         "no creator rules). This swaps in the current ones and keeps the old copy."),
    Step("nvidia", "Install NVIDIA's driver",
         "The graphics card does nothing until its driver runs: pictures and fast local "
         "models need it. A terminal opens; type your password, then restart when it says."),
    Step("pictures", "Set up pictures on this computer",
         "ComfyUI and the picture model (about 10 GB download, once). A terminal opens; type "
         "your password."),
    Step("search", "Set up private web search",
         "Jarvis's own search on this computer (SearXNG). A terminal opens; type your "
         "password."),
    Step("updates", "Turn on nightly updates",
         "BAU installs its newest tested version each night and goes back by itself if one "
         "fails. A terminal opens; type your password."),
    Step("autopilot", "Let Jarvis work on his own",
         "The autopilot: every 30 minutes Jarvis scans GitHub, inspects what he finds and "
         "votes on what to add, and asks you only about money, posting and legal. A "
         "terminal opens; type your password."),
    Step("prices", "Set your Fanvue prices",
         "Your monthly price and the two unlock prices. A terminal opens and asks you for "
         "each one; nothing is filled in for you."),
)
BY_ID = {s.id: s for s in STEPS}


def script(name: str) -> Path:
    return Path(str(resources.files("bau") / "data" / "setup" / name))


def _answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def _probe(what: str) -> object:
    """Facts about this computer, read-only."""
    if what == "nvidia":
        from .machine import _nvidia_present
        return _nvidia_present(Path("/"))
    if what == "driver":
        return shutil.which("nvidia-smi") is not None and subprocess.run(
            ["nvidia-smi"], capture_output=True, check=False).returncode == 0
    if what == "pictures":
        return _answers("http://127.0.0.1:8188/system_stats")
    if what == "search":
        return _answers("http://127.0.0.1:8888/")
    if what == "autopilot":
        return subprocess.run(["systemctl", "is-enabled", "--quiet", "bau-autopilot.timer"],
                              capture_output=True, check=False).returncode == 0
    if what == "update":
        from . import update
        return update.mode() or "off"
    raise ValueError(what)


def _terminal(title: str, command: str) -> bool:
    """A terminal window on the owner's screen running the command; False without one."""
    term = shutil.which("xfce4-terminal")
    if not term or not os.environ.get("DISPLAY"):
        return False
    wrapped = (f"{command}; echo; read -r -p 'Done. Press Enter to close this window. ' _")
    subprocess.Popen([term, "--title", title, "-x", "bash", "-c", wrapped],
                     start_new_session=True, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    return True


def _profile(home: Path) -> Path | None:
    found = sorted((home / "creators").glob("*.yaml")) if (home / "creators").is_dir() else []
    return found[0] if found else None


def _done(step: str, home: Path, probe: Probe) -> bool | None:
    """True done, False waiting, None not for this computer."""
    if step == "api_keys":
        return None if not _unused_keys(home) else False
    if step == "laws":                    # an empty or missing copy reads the shipped rules
        regs = home / "regulations"
        if not regs.is_dir() or not any(regs.glob("*.yaml")):
            return True
        return (regs / "creator.yaml").exists()
    if step == "nvidia":
        return None if not probe("nvidia") else bool(probe("driver"))
    if step == "pictures":
        return None if not (probe("nvidia") and probe("driver")) else bool(probe("pictures"))
    if step == "search":
        return bool(probe("search"))
    if step == "updates":
        return probe("update") == "auto"
    if step == "autopilot":
        return bool(probe("autopilot"))
    if step == "prices":
        import yaml
        prof = _profile(home)
        if prof is None:
            return None
        return bool((yaml.safe_load(prof.read_text()) or {}).get("prices"))
    raise ValueError(step)


def _unused_keys(home: Path) -> list[str]:
    """Hosted models whose API key is on this computer but which are not approved yet."""
    import os

    from . import localonly
    from .registry import CapabilityRegistry
    if localonly.mode(home) == "local-only":
        return []
    p = home / "registry" / "capabilities.yaml"
    if not p.exists():
        return []
    out = []
    for mid, rec in sorted(CapabilityRegistry(p).data.get("model", {}).items()):
        key = rec.get("api_key_env")
        if (key and os.environ.get(key) and rec.get("deployment") != "local"
                and rec.get("lane") != "content_only"
                and rec.get("status") not in ("APPROVED", "ACTIVE")):
            out.append(mid)
    return out


def waiting(home: Path, probe: Probe | None = None) -> list[Step]:
    probe = probe or _probe
    return [s for s in STEPS if _done(s.id, home, probe) is False]


def _command(step: str, home: Path) -> str:
    q = shlex.quote
    if step == "api_keys":
        return "; ".join(f"bau set-status model {q(m)} APPROVED" for m in _unused_keys(home))
    if step == "nvidia":
        return "sudo bau-gpu-setup"
    if step == "pictures":
        return f"sudo bash {q(str(script('bau-pictures-setup.sh')))}"
    if step == "search":
        return f"sudo bash {q(str(script('bau-search-setup.sh')))}"
    if step == "updates":
        return "sudo bau update auto"
    if step == "autopilot":
        return f"sudo bash {q(str(script('bau-autopilot-setup.sh')))}"
    if step == "prices":
        prof = q(str(_profile(home)))
        return ("read -r -p 'Monthly subscription in dollars: ' s; "
                "read -r -p 'Level 2 (nude) unlock in dollars: ' n; "
                "read -r -p 'Level 3 (xxx) unlock in dollars: ' x; "
                f'bau creator prices {prof} --subscription "$s" --nude "$n" --xxx "$x"')
    raise ValueError(step)


def _refresh_laws(home: Path) -> None:
    """The shipped rules replace the install-time copy; the old copy is kept beside it."""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for sub in ("regulations", "policies"):
        cur, src = home / sub, shipped_data() / sub
        if cur.exists():
            cur.rename(home / f"{sub}.before-{stamp}")
        shutil.copytree(src, cur)


def run(step: str, home: Path, probe: Probe | None = None,
        terminal: Terminal | None = None) -> dict[str, object]:
    """Only after the owner pressed Accept."""
    if step not in BY_ID:
        raise ValueError(f"no setup step {step!r}")
    if step == "laws":
        _refresh_laws(home)
        return {"done": True, "said": "The current rules are in; the old copy is kept."}
    cmd = _command(step, home)
    if not (terminal or _terminal)(f"BAU setup: {BY_ID[step].title}", cmd):
        return {"error": f"No screen to open a terminal on. In a terminal, run: {cmd}"}
    return {"started": True, "said": "A terminal window opened. Follow it there; this card "
                                     "goes away once the step is done."}
