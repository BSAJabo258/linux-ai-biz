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
ROOM_FULL = 0.85        # "/" this full, with the big folders still on it: offer to make room
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
    Step("room", "Make room for Jarvis",
         "The system part of the disk is nearly full, while /home has room to spare. This "
         "moves the big folders (local models, the picture maker, the CUDA engine) into "
         "/home and links them back, so everything keeps working. Your keys and data stay "
         "where they are. A terminal opens; type your password."),
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
    Step("fanvue_app", "Connect Fanvue",
         "The money starts on Fanvue, and Jarvis can't reach it yet. Press Accept: Fanvue "
         "opens in the browser (its official connection for AI tools: no app, no keys). Sign "
         "in and press Allow."),
    Step("fanvue", "Connect Fanvue",
         "So Jarvis can put Aria's pictures on Fanvue (each one only after your Accept) and "
         "count what she earns. Fanvue opens in the browser: sign in and press Allow."),
    Step("autopost", "Let Jarvis post to Fanvue on his own",
         "Your switch: every 30 minutes the autopilot posts the next queued Fanvue post, up "
         "to your number a day, to the audience you pick. Every check (age, AI label, no "
         "minors) still runs on each post, and HOLD stops it. Not now keeps your Accept on "
         "every post. Turn it off any time: bau fanvue autopost off"),
    Step("automaton", "Start the automaton: make money or die",
         "Jarvis runs the Fanvue loop by himself: draws, captions, posts and counts the money, "
         "without asking you each time. Your numbers: how many days it gets to earn something, "
         "dollars it may spend, the share of what it really earns it may spend too (and the "
         "most), and how much it must earn before it asks to post more. Every content check "
         "still runs; HOLD or bau automaton stop ends it."),
    Step("grow", "It earned money: grow it",
         "The automaton has earned what you set. More posts a day of what is working? Type "
         "the new number; Not now keeps it as it is."),
    Step("boundaries", "Write your explicit limits",
         "What the explicit (Fanvue-only) content must never show, one limit per line. A "
         "safe starting list is filled in: change it, then Accept. Until then, Jarvis plans "
         "sfw content only."),
    Step("explicit", "Set up pictures for paid levels 2 and 3",
         "Chroma, the free picture model you chose for nude and xxx unlocks (about 23 GB "
         "download, once, checked file by file). It joins the picture maker on this computer; "
         "every picture still gets the age check and waits for your Accept. A terminal "
         "opens; type your password."),
    Step("prices", "Set your Fanvue prices",
         "Filled in from Fanvue's own advice (source under each box). Change any price, "
         "then Accept; nothing is set before that."),
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


def pictures_installed(root: Path = Path("/")) -> bool:
    """Installed counts, not running: the owner's desktop, 2026-11-10, rebooted, ComfyUI could
    not start before CUDA was ready, and the card kept asking to download it all again."""
    return ((root / "etc/systemd/system/bau-pictures.service").is_file() and
            (root / "usr/local/comfyui/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors")
            .is_file())


def _probe(what: str) -> object:
    """Facts about this computer, read-only."""
    if what == "nvidia":
        from .machine import _nvidia_present
        return _nvidia_present(Path("/"))
    if what == "driver":
        return shutil.which("nvidia-smi") is not None and subprocess.run(
            ["nvidia-smi"], capture_output=True, check=False).returncode == 0
    if what == "pictures":
        return _answers("http://127.0.0.1:8188/system_stats") or pictures_installed()
    if what == "search":
        return _answers("http://127.0.0.1:8888/")
    if what == "autopilot":
        return subprocess.run(["systemctl", "is-enabled", "--quiet", "bau-autopilot.timer"],
                              capture_output=True, check=False).returncode == 0
    if what == "room":   # True when "/" is nearly full and /home is a separate, bigger part
        import os
        try:
            root, home = os.stat("/"), os.stat("/home")
        except OSError:
            return False
        if root.st_dev == home.st_dev:
            return False
        used = shutil.disk_usage("/")
        big = [d for d in ("/var/lib/bau/models", "/usr/local/comfyui", "/opt/llama.cpp-cuda")
               if os.path.isdir(d) and not os.path.ismount(d)]
        return used.used / used.total > ROOM_FULL and bool(big)
    if what == "explicit":
        from .media import comfy
        return comfy.chroma_ready()
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
    if step == "room":                    # shown only while "/" is nearly full
        return None if not probe("room") else False
    if step == "search":
        return bool(probe("search"))
    if step == "updates":
        return probe("update") == "auto"
    if step == "autopilot":
        return bool(probe("autopilot"))
    if step == "fanvue_app":              # the money loop's first link (found 2026-11-10)
        from . import fanvue, fanvue_mcp
        if _profile(home) is None or fanvue.TokenStore(home).load() is not None:
            return None
        return fanvue_mcp.Store(home).connected()
    if step == "fanvue":                  # the developer-app way: a terminal command only
        return None
    if step in ("automaton", "grow"):     # after Fanvue is connected and autopost is chosen
        from . import automaton, fanvue
        if (fanvue.TokenStore(home).load() is None
                or not (fanvue.autopost_choice(home) or {}).get("on")):
            return None
        if step == "automaton":
            return bool(automaton.load(home).get("started_at"))
        return None if not automaton.status(home).get("grow_ready") else False
    if step == "autopost":                # once Fanvue is connected, until he chooses
        from . import fanvue
        if fanvue.TokenStore(home).load() is None:
            return None
        return fanvue.autopost_choice(home) is not None
    if step == "explicit":                # after pictures and the owner's explicit limits
        import yaml
        prof = _profile(home)
        limits = prof and (yaml.safe_load(prof.read_text()) or {}).get("explicit_boundaries")
        if not limits or _done("pictures", home, probe) is not True:
            return None
        return bool(probe("explicit"))
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
    if step == "fanvue_app":
        return "bau fanvue connect"
    if step == "nvidia":
        return "sudo bau-gpu-setup"
    if step == "pictures":
        return f"sudo bash {q(str(script('bau-pictures-setup.sh')))}"
    if step == "room":
        return f"sudo bash {q(str(script('bau-make-room.sh')))}"
    if step == "explicit":
        return f"sudo bash {q(str(script('bau-explicit-setup.sh')))}"
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


# Filled-in boxes (the owner's choice, 2026-11-09: "fill them out"). Every value comes from
# Fanvue's own help pages, read 2026-11-09, and the source shows under the box. Nothing is
# set until the owner presses Accept, and every box can be changed first.
#   https://help.fanvue.com/en/articles/16233102-subscription-pricing-retention-guide
#     "$9.99-$15 performing best across the platform on average"; "If you're new, start on
#     the lower end and lean on PPV"; "Post daily, or at minimum every other day"
#   https://help.fanvue.com/en/articles/16237634-ppv-media-a-creator-s-strategy-guide
#     "$10-15 is a sensible floor for your cheapest PPV item"; "end it in .99"
SUB_GUIDE = "https://help.fanvue.com/en/articles/16233102-subscription-pricing-retention-guide"
PPV_GUIDE = "https://help.fanvue.com/en/articles/16237634-ppv-media-a-creator-s-strategy-guide"
SUGGESTED = {
    "subscription": (9.99, "Fanvue: $9.99 to $15 does best; new creators start at the "
                           "lower end. " + SUB_GUIDE),
    "nude": (10.99, "Fanvue: $10 to $15 is a sensible floor for the cheapest PPV, "
                    "ending in .99. " + PPV_GUIDE),
    "xxx": (14.99, "Fanvue: price by what's inside; the most explicit level gets the top "
                   "of the $10 to $15 floor. " + PPV_GUIDE),
    "per_day": (1, "Fanvue: post daily, or at least every other day. " + SUB_GUIDE),
    "audience": ("subscribers", "Keeps subscriber posts behind the subscription. Fanvue "
                                "gives no advice on this one: change it if you want free "
                                "followers to see them."),
    "limits": ("Adults only, consenting, fictional persona\n"
               "No real person's likeness\nNo non-consent or coercion\n"
               "No violence, blood or injury\nNo incest or family role-play\nNo animals\n"
               "No drugs or alcohol in sexual content",
               "A safe starting list in plain words. Add or remove lines; minors are "
               "always refused whatever this says."),
}


def _fill(field: dict[str, object]) -> dict[str, object]:
    value, why = SUGGESTED[str(field["name"])]
    return {**field, "value": value, "why": why}


def form(step: str) -> dict[str, object] | None:
    """The boxes on the card, filled in with SUGGESTED; the owner's Accept is the choice."""
    if step == "prices":
        from .virtual_creator import PRICE_LIMITS
        names = {"subscription": "Monthly subscription", "nude": "Level 2 (nude) unlock",
                 "xxx": "Level 3 (xxx) unlock"}
        return {"fields": [_fill({"name": k, "type": "number", "min": lo, "max": hi,
                                  "label": f"{names[k]} in dollars (${lo:.2f} to ${hi:.2f})"})
                           for k, (lo, hi) in PRICE_LIMITS.items()]}
    if step == "autopost":
        from .fanvue import AUDIENCES, MAX_PER_DAY
        return {"fields": [
            _fill({"name": "audience", "label": "Who sees the posts?",
                   "options": [[k, v] for k, v in AUDIENCES.items()]}),
            _fill({"name": "per_day", "type": "number", "min": 1, "max": MAX_PER_DAY,
                   "label": f"Posts a day (1 to {MAX_PER_DAY})"})]}
    if step == "automaton":               # the owner's own numbers: no suggestions
        return {"fields": [
            {"name": "days", "type": "number", "min": 1, "max": 365,
             "label": "Days it gets to earn something, or it dies"},
            {"name": "budget", "type": "number", "min": 0,
             "label": "Dollars it may spend from its start (0: free tools only)"},
            {"name": "reinvest", "type": "number", "min": 0, "max": 100,
             "label": "Percent of what it really earns it may spend too"},
            {"name": "cap", "type": "number", "min": 0,
             "label": "Most dollars of its earnings it may spend"},
            {"name": "grow_at", "type": "number", "min": 0,
             "label": "Dollars earned before it asks to post more (0: never)"}]}
    if step == "grow":
        from .fanvue import MAX_PER_DAY
        return {"fields": [{"name": "per_day", "type": "number", "min": 1,
                            "max": MAX_PER_DAY, "label": f"Posts a day (up to {MAX_PER_DAY})"}]}
    if step == "boundaries":
        return {"fields": [_fill({"name": "limits", "type": "text",
                                  "label": "Your explicit limits, one per line"})]}
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
    if step in ("automaton", "grow"):
        from . import automaton, fanvue
        v = values or {}
        try:
            if step == "grow":
                s = automaton.grow(home, owner, int(float(v.get("per_day", 0))))
                return {"done": True, "said": f"Growing: {s['per_day']} posts a day now."}
            choice = fanvue.autopost_choice(home) or {}
            s = automaton.start(home, owner, str(choice.get("audience", "")),
                                int(choice.get("per_day", 0)), float(v["budget"]),
                                int(float(v["days"])), reinvest_pct=float(v["reinvest"]),
                                reinvest_cap_usd=float(v["cap"]),
                                grow_at_usd=float(v["grow_at"]))
        except (KeyError, ValueError, TypeError, PermissionError) as e:
            return {"error": f"fill in every box: {e}" if isinstance(e, KeyError) else str(e)}
        return {"done": True, "said": f"The automaton is running: {s['die_after_days']} days "
                                      "to earn something. Tier: " + s["tier"] + "."}
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
