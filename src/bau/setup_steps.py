"""Setup steps that pop up for the owner (the owner's ask, 2026-11-02: "a pop-up menu for me
to click the accept button so that it can continue").

Each step knows how to tell whether it is already done on this computer. Jarvis shows every
step still waiting as a card with Accept; nothing runs without that click. A step that needs
the owner's password opens a terminal window running the exact command, so the owner sees it
and types the password there. Everything else happens on the card itself (the owner's ask,
2026-11-03: "only the very necessary clicks"): owner-only values (prices, explicit limits)
are typed by the owner in the card's boxes, never filled in. Done steps disappear the next
time Jarvis checks.
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
    Step("fanvue", "Connect Fanvue",
         "So Jarvis can put Aria's pictures on Fanvue (each one only after your Accept) and "
         "count what she earns. Fanvue opens in the browser: sign in and press Allow."),
    Step("autopost", "Let Jarvis post to Fanvue on his own",
         "Your switch: every 30 minutes the autopilot posts the next queued Fanvue post, up "
         "to your number a day, to the audience you pick. Every check (age, AI label, no "
         "minors) still runs on each post, and HOLD stops it. Not now keeps your Accept on "
         "every post. Turn it off any time: bau fanvue autopost off"),
    Step("boundaries", "Write your explicit limits",
         "What the explicit (Fanvue-only) content must never show, one limit per line, in "
         "your words. Until you write them, Jarvis plans sfw content only."),
    Step("prices", "Set your Fanvue prices",
         "Type your monthly price and the two unlock prices in the boxes; nothing is filled "
         "in for you."),
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
    if step == "fanvue":                  # only once the app's keys are on this computer
        from . import fanvue
        try:
            fanvue.app_credentials()
        except fanvue.FanvueError:
            return None
        return fanvue.TokenStore(home).load() is not None
    if step == "autopost":                # once Fanvue is connected, until he chooses
        from . import fanvue
        if fanvue.TokenStore(home).load() is None:
            return None
        return fanvue.autopost_choice(home) is not None
    if step in ("boundaries", "prices"):
        import yaml
        prof = _profile(home)
        if prof is None:
            return None
        key = "explicit_boundaries" if step == "boundaries" else "prices"
        return bool((yaml.safe_load(prof.read_text()) or {}).get(key))
    raise ValueError(step)


def _unused_keys(home: Path) -> list[str]:
    """Hosted models whose API key is on this computer but which are not approved yet."""
    import os

    from . import localonly
    from .registry import CapabilityRegistry, validate
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
                and rec.get("status") not in ("APPROVED", "ACTIVE")
                # one the registry's own checks would refuse never gets a card
                and not validate("model", dict(rec, status="APPROVED"))):
            out.append(mid)
    return out


def waiting(home: Path, probe: Probe | None = None) -> list[Step]:
    probe = probe or _probe
    return [s for s in STEPS if _done(s.id, home, probe) is False]


def _command(step: str, home: Path) -> str:
    q = shlex.quote
    if step == "fanvue":
        return "bau fanvue login"
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
    raise ValueError(step)


def _refresh_laws(home: Path) -> None:
    """The shipped rules replace the install-time copy; the old copy is kept beside it."""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for sub in ("regulations", "policies"):
        cur, src = home / sub, shipped_data() / sub
        if cur.exists():
            cur.rename(home / f"{sub}.before-{stamp}")
        shutil.copytree(src, cur)


def form(step: str) -> dict[str, object] | None:
    """The boxes the owner types into on the card. Empty: nothing is ever filled in."""
    if step == "prices":
        from .virtual_creator import PRICE_LIMITS
        names = {"subscription": "Monthly subscription", "nude": "Level 2 (nude) unlock",
                 "xxx": "Level 3 (xxx) unlock"}
        return {"fields": [{"name": k, "type": "number", "min": lo, "max": hi,
                            "label": f"{names[k]} in dollars (${lo:.2f} to ${hi:.2f})"}
                           for k, (lo, hi) in PRICE_LIMITS.items()]}
    if step == "autopost":
        from .fanvue import AUDIENCES, MAX_PER_DAY
        return {"fields": [
            {"name": "audience", "label": "Who sees the posts?",
             "options": [[k, v] for k, v in AUDIENCES.items()]},
            {"name": "per_day", "type": "number", "min": 1, "max": MAX_PER_DAY,
             "label": f"Posts a day (1 to {MAX_PER_DAY})"}]}
    if step == "boundaries":
        return {"fields": [{"name": "limits", "type": "text",
                            "label": "Your explicit limits, one per line"}]}
    return None


def approve_keys(home: Path, owner: str) -> tuple[list[str], dict[str, str]]:
    """The owner's Accept switches on the hosted models whose keys are here (what
    `bau set-status model ID APPROVED` does, with the owner as the reviewer)."""
    import yaml

    from .registry import CapabilityRegistry, validate
    if not owner.startswith("human:"):
        raise PermissionError("only the owner switches models on")
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    done, refused = [], {}
    for mid in _unused_keys(home):
        new = dict(reg.data["model"][mid], status="APPROVED", reviewed_by=owner,
                   reviewed_at=dt.datetime.now(dt.UTC).isoformat())
        if errs := validate("model", new):
            refused[mid] = "; ".join(errs)
        else:
            reg.data["model"][mid] = new
            done.append(mid)
    reg.path.write_text(yaml.safe_dump(reg.data, sort_keys=True))
    return done, refused


def run(step: str, home: Path, probe: Probe | None = None,
        terminal: Terminal | None = None, owner: str = "",
        values: dict[str, object] | None = None) -> dict[str, object]:
    """Only after the owner pressed Accept; `values` are what the owner typed on the card."""
    if step not in BY_ID:
        raise ValueError(f"no setup step {step!r}")
    if step == "laws":
        _refresh_laws(home)
        return {"done": True, "said": "The current rules are in; the old copy is kept."}
    if step == "api_keys":
        on, refused = approve_keys(home, owner)
        said = ("Switched on: " + ", ".join(on) + ". ") if on else ""
        said += "".join(f"Not switched on, {m}: {why}. " for m, why in refused.items())
        return {"done": bool(on), "switched_on": on, "refused": refused,
                "said": said.strip() or "Nothing to switch on."}
    if step == "autopost":
        from . import fanvue
        v = values or {}
        try:
            rec = fanvue.set_autopost(home, True, owner, str(v.get("audience", "")),
                                      int(float(v.get("per_day", 0))))
        except (ValueError, TypeError) as e:
            return {"error": str(e)}
        return {"done": True, "said": f"Autopost on: up to {rec['per_day']} a day to "
                                      f"{fanvue.AUDIENCES[rec['audience']].lower()}."}
    if step in ("prices", "boundaries"):
        from . import virtual_creator as V
        prof, values = _profile(home), values or {}
        if prof is None:
            return {"error": "no creator profile yet"}
        try:
            if step == "prices":
                V.set_prices(prof, {k: float(values[k]) for k in V.PRICE_LIMITS})
            else:
                V.set_explicit_boundaries(prof, str(values.get("limits", "")).splitlines())
        except (KeyError, ValueError, TypeError, V.CreatorError) as e:
            return {"error": str(e)}
        return {"done": True, "said": "Saved in your creator profile."}
    cmd = _command(step, home)
    if not (terminal or _terminal)(f"BAU setup: {BY_ID[step].title}", cmd):
        return {"error": f"No screen to open a terminal on. In a terminal, run: {cmd}"}
    return {"started": True, "said": "A terminal window opened. Follow it there; this card "
                                     "goes away once the step is done."}
