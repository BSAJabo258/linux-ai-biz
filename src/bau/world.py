"""The operations world (the owner's ask, 2026-11-15: an isometric floor of workers, from his
three reference pictures; 2026-11-17: the workers are his AI assistants, glamorous adult women
from his picture): every character on the screen is one of the owner's agents, and the room
she stands in comes only from her latest real job in ``jobs/``. An agent with no job sits in
the lounge; nothing walks, types or glows unless a job says so.

``world()`` only reads: the agent folders, the job store and HOLD. ``draw_portraits()`` (the
owner's ``bau world portraits``) paints each look once on the desktop's ComfyUI.
"""

from __future__ import annotations

import datetime as dt
import sys
import zlib
from pathlib import Path
from typing import Any

from .home import bau_home

# Rooms on the floor (docs/visual/VISUAL_ART_DIRECTION.md), with who really works in each. The
# department names are the owner's (2026-11-20); Review and Delivered make the Delivery and
# Review Center.
# ``hq`` is Jarvis's core; agents with no job wait in its lounge.
ROOMS = (("hq", "Headquarters", "Jarvis's core; agents with nothing to do wait in its lounge"),
         ("research", "Research library", "the researcher, and Jarvis when she researches"),
         ("forge", "Development Forge", "any agent without a room of its own"),
         ("testing", "Testing lab", "Jarvis when her autopilot tests a tool in the sandbox"),
         ("innovation", "Innovation Workshop", "Jarvis when she scans or inspects a project"),
         ("studio", "Creative Studio", "the producer, and Jarvis when she drafts"),
         ("finance", "Finance Office", "the finance agent: the daily earnings report"),
         ("market", "Market", "the marketing agent: the week's promotion plan"),
         ("approvals", "Review: waiting for you", "an agent whose job waits for your approval"),
         ("repair", "Stopped", "an agent whose job failed, was interrupted or paused"),
         ("delivery", "Delivered", "an agent whose job finished in the last 24 hours"))
# Where an agent works while its job runs; any other agent works in the Forge.
DESK = {"researcher": "research", "producer": "studio", "finance": "finance",
        "marketer": "market"}
LOOK = {"researcher": "researcher", "producer": "producer", "jarvis": "jarvis"}
# Any other agent gets one of these looks, always the same one for the same name.
OTHER_LOOKS = ("engineer", "coordinator", "analyst", "architect")
# Painted portraits of each look (the owner's picture, 2026-11-17), shown in her record card.
# Drawn by ComfyUI's sfw lane (media/comfy.py: minors refused, the age check, provenance), then
# moved out of artifacts/media at once: the Fanvue queue picks from there, and these are never
# posted. Fictional adult women, none drawn from a real person.
PORTRAIT_LOOKS = ("jarvis", "researcher", "producer", "engineer", *OTHER_LOOKS[1:])
PORTRAIT_WHO = {
    "jarvis": "long straight black hair, tan skin, black glossy two-piece with glowing cyan "
              "trim and a cyan choker, holding a holographic tablet, the team's leader",
    "researcher": "dark hair in a high bun, glasses, brown skin, royal blue glossy two-piece, "
                  "reading at a computer desk",
    "producer": "long wavy red hair, fair skin, red glossy two-piece, holding a camera",
    "engineer": "long blonde hair, glasses, black and gold glossy two-piece, gold armbands, "
                "at a workstation",
    "coordinator": "long black hair, violet glossy two-piece and thigh-high violet boots, "
                   "holding a holographic tablet",
    "analyst": "big dark curly hair, deep brown skin, gold glossy two-piece, holding a "
               "holographic tablet",
    "architect": "long platinum hair, fair skin, white glossy two-piece with cyan trim, "
                 "holding a holographic tablet",
}
PORTRAIT_STYLE = ("digital painting, glamorous adult woman in her late twenties, {who}, "
                  "futuristic operations office at night, holographic screens, city skyline "
                  "windows, purple and blue neon light, confident smile, from the waist up, "
                  "highly detailed")
PORTRAIT_NEGATIVE = ("child, childlike, minor, teen, young-looking, school uniform, nudity, "
                     "nipples, explicit, character sheet, real person, celebrity, text, "
                     "watermark, logo")
# The neon headquarters (the owner's picture of 2026-11-20, "BAUBSA JARVIS - Virtual Operations
# World"): each assistant painted in that style in four poses, one per state of her real job
# (``POSE``), drawn with ``bau world portraits --style neon``. Swimsuit or clubwear level, never
# nudity; this screen is never posted. Her look is the same as in her sprite and portrait.
NEON_WHO = {
    "jarvis": "long straight black hair, tan skin, black glossy two-piece with glowing cyan "
              "trim, a glowing cyan choker and armbands",
    "researcher": "dark hair in a high bun, glasses, brown skin, royal blue glossy two-piece",
    "producer": "long wavy red hair, fair skin, red glossy two-piece and a red choker",
    "engineer": "long blonde hair, glasses, black and gold glossy two-piece, gold armbands",
    "coordinator": "long black hair, light olive skin, violet glossy two-piece, violet "
                   "thigh-high boots",
    "analyst": "big dark curly hair, deep brown skin, gold glossy two-piece",
    "architect": "long platinum hair, fair skin, white glossy two-piece with cyan trim",
}
NEON_POSES = {"idle": "standing relaxed with one hand on her hip, looking at the viewer",
              "working": "seated at a glowing holographic desk, typing, focused on the screens",
              "waiting": "looking at the viewer and raising one hand to call someone over",
              "done": "smiling and holding up a glowing tablet showing a green check mark"}
NEON_STYLE = ("highly detailed digital painting, glamorous adult woman in her late twenties, "
              "{who}, {pose}, inside a neon cyberpunk headquarters at night, tall windows with "
              "a city skyline, purple cyan pink and gold neon light, reflections on glossy "
              "surfaces, from the knees up, sharp focus")
POSE = {"working": "working", "waiting for you": "waiting", "done": "done"}   # else idle
# The roles in the owner's picture. BAU has an agent folder for some of them only: a role with
# none is "not set up yet". Nothing here ever says "online": no record says it.
PICTURE_ROLES = ("architect", "researcher", "developer", "tester", "coordinator")
LIGHT = {"working": "working", "waiting for you": "waiting", "done": "done", "idle": "free",
         "assigned": "free"}
# Jarvis's face on her screen (the owner's ask, 2026-11-18: "a real life looking AI model
# replacing the orb"): a photographic portrait of an ORIGINAL fictional adult woman with
# Jarvis's look, drawn on this computer. Never a real person or a celebrity's likeness.
AVATAR_LOOK = "avatar"
AVATAR_PROMPT = ("professional studio portrait photograph of an original fictional adult woman "
                 "in her early thirties, long straight black hair, warm tan skin, hazel eyes, "
                 "natural makeup, black fitted blazer over a dark top with a thin glowing cyan "
                 "accent, calm confident smile, looking at the camera, head and shoulders, "
                 "dark navy background with soft cyan rim light, 85mm lens, shallow depth of "
                 "field, natural skin texture, photorealistic, sharp focus")
AVATAR_NEGATIVE = ("child, childlike, minor, teen, young-looking, school uniform, nudity, "
                   "cleavage, explicit, celebrity, famous person, cartoon, anime, painting, "
                   "illustration, 3d render, doll, plastic skin, deformed, extra fingers, text, "
                   "watermark, logo")
# Jarvis's autopilot jobs (autopilot.GO) and the room each is done in.
JOB_ROOM = {"scan": "innovation", "inspect": "innovation", "blueprint": "innovation",
            "sandbox_test": "testing", "research": "research", "learn": "research",
            "draft": "studio"}
WORKING = {"RUNNING"}
STOPPED = {"PAUSED", "WAITING_FOR_NETWORK", "INTERRUPTED", "FAILED", "ROLLED_BACK"}
RECENT = dt.timedelta(hours=24)          # a finished job stays in its room this long
QUIET = dt.timedelta(minutes=30)         # a running job with no checkpoint this long is flagged
def _when(s: str) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def place(name: str, job: Any, now: dt.datetime) -> tuple[str, str]:
    """(room, state) for an agent from its latest job; ``job`` None means it has none."""
    if job is None:
        return "hq", "idle"
    at = _when(job.updated_at)
    fresh = at is not None and now - at < RECENT
    if job.status == "PENDING":       # recorded and given to her, not started: at Headquarters
        return "hq", "assigned"
    if job.status in WORKING:         # started: she has walked to her department's desk
        return DESK.get(name, "forge"), "working"
    # Finished but its result failed the check: the owner reviews it, it is not delivered.
    if job.status == "WAITING_FOR_APPROVAL" or (
            job.status == "COMPLETED" and getattr(job, "verification", "") == "FAILED"):
        return "approvals", "waiting for you"
    if job.status in STOPPED:
        return "repair", job.status.lower().replace("_", " ")
    if job.status == "COMPLETED" and fresh:
        return "delivery", "done"
    return "hq", "idle"


def lifecycle(job: Any, mission: dict[str, Any] | None) -> list[dict[str, str]]:
    """The steps of one real task, each read from its job record and its mission, never
    guessed (the owner's world spec, 2026-11-19): done, now, waiting (for the owner),
    stopped, or not needed. Nothing here is a timer or an animation of its own."""
    st, ver = job.status, getattr(job, "verification", "UNCHECKED")
    ended = st in ("COMPLETED", "FAILED", "CANCELLED", "ROLLED_BACK")
    started = st != "PENDING"
    tools = ", ".join(getattr(job, "tools", []) or []) or "none recorded"

    def step(name: str, state: str, detail: str) -> dict[str, str]:
        return {"step": name, "state": state, "detail": detail}
    out = [step("Recorded", "done", f"job {job.job_id}: {job.objective[:120]}"),
           step("Dispatched", "done" if started else "now",
                f"to {_agent_name(job.agent)}" if started else "waiting to start")]
    if st in ("RUNNING",):
        out.append(step("Working", "now", "at her desk; every tool through the gateway"))
    elif started:
        out.append(step("Working", "done" if ended else "stopped",
                        st.lower().replace("_", " ")))
    if st == "COMPLETED":
        out.append(step("Result", "done", f"tools used: {tools}"))
        out.append(step("Checked (manager)", {"VERIFIED": "done", "FAILED": "stopped"}.get(
            ver, "not needed"), {"VERIFIED": "every fact backed by what the tools returned",
                                 "FAILED": job.next_action or "a fact no tool backs",
                                 }.get(ver, "this kind of job is not checked")))
    elif ended:
        out.append(step("Result", "stopped", "; ".join(job.errors[-1:]) or st.lower()))
    if ended:
        mst = (mission or {}).get("status")
        if ver == "FAILED" or mst == "PAUSED":
            out.append(step("Your review", "waiting",
                            "read the result, then plan it again or drop it"))
        elif st == "COMPLETED":
            out.append(step("Your review", "not needed",
                            "no outside effect: posting, money and the like always wait "
                            "for your Accept"))
        out.append(step("Delivered", "done" if st == "COMPLETED" and ver == "VERIFIED"
                        else "stopped" if st != "COMPLETED" else "waiting",
                        "in the mission's report" if job.mission_id else "kept with the job"))
    return out


def look(name: str) -> str:
    """Her character on the sprite sheet: her own, or always the same one of the others."""
    return LOOK.get(name) or OTHER_LOOKS[zlib.crc32(name.encode()) % len(OTHER_LOOKS)]


def _agent_name(job_agent: str) -> str:
    return job_agent.removeprefix("folder:")


def world(home: Path | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    from . import agentfolders as AF
    from .governor import hold_reason
    from .jobs import JobStore
    home = home or bau_home()
    now = now or dt.datetime.now(dt.UTC)
    from .jarvis import _latest as latest_missions
    missions = latest_missions(home)
    latest: dict[str, Any] = {}
    for job in JobStore(home).all():
        name = _agent_name(job.agent)
        old = latest.get(name)
        if old is None or (job.updated_at or "") >= (old.updated_at or ""):
            latest[name] = job
    agents = []
    names = AF.names(home)
    for name in names + sorted(set(latest) - set(names)):
        try:
            a = AF.load(name, home)
            info = {"description": a.description, "brain": a.brain, "tools": a.tools,
                    "mcp": a.mcp, "approval": AF.approval(a, home)}
        except (AF.AgentFolderError, FileNotFoundError, KeyError):
            info = {"description": "not an agent folder (a registry agent)", "brain": None,
                    "tools": [], "mcp": [], "approval": "unknown"}
        job = latest.get(name)
        room, state = place(name, job, now)
        rec: dict[str, Any] = {"name": name, **info, "room": room, "state": state,
                               "job": None}
        if job is not None:
            at = _when(job.updated_at)
            rec["job"] = {"job_id": job.job_id, "mission_id": job.mission_id,
                          "objective": job.objective[:300], "status": job.status,
                          "model": job.model, "updated_at": job.updated_at,
                          "steps_done": len(job.completed_steps),
                          "steps_left": len(job.remaining_steps),
                          "cost_usd": round(job.cost_usd, 4), "errors": job.errors[-3:],
                          "artifacts": job.artifacts[-5:], "next_action": job.next_action,
                          "verification": getattr(job, "verification", "UNCHECKED"),
                          "tools": list(getattr(job, "tools", []) or []),
                          "lifecycle": lifecycle(job, missions.get(job.mission_id))}
            if state == "working" and at is not None and now - at > QUIET:
                rec["quiet_minutes"] = int((now - at).total_seconds() // 60)
        rec["look"] = look(name)
        agents.append(rec)
    agents.insert(0, jarvis(home, now))
    for rec in agents:
        rec["portrait"] = portrait_file(home, rec["look"]) is not None
        rec["pose"] = POSE.get(rec["state"], "idle")
        rec["neon"] = portrait_file(home, f"neon-{rec['look']}-{rec['pose']}") is not None
    held = hold_reason(home)
    counts = {r: sum(1 for a in agents if a["room"] == r) for r, _, _ in ROOMS}
    sys_ = system(home)
    me = agents[0]
    return {"rooms": [{"id": r, "name": n, "who": w} for r, n, w in ROOMS], "agents": agents,
            "hold": held, "counts": counts, "at": now.isoformat(timespec="seconds"),
            "tasks": [{"agent": a["name"], "state": a["state"], "task": a["job"]["objective"]}
                      for a in agents if a["job"] and a["state"] in ("assigned", "working",
                                                                     "waiting for you")],
            "system": sys_, "roster": roster(home, agents, sys_),
            "now": {"state": me["state"], "task": me["job"]["objective"]}
            if me["job"] and me["state"] in ("working", "waiting for you") else None,
            "how_to_read": "each character is an agent; her room is her latest job's state"}


def roster(home: Path, agents: list[dict[str, Any]], sys_: dict[str, Any]) -> list[dict[str, Any]]:
    """The agents panel of the neon headquarters: the picture's roles, then BAU's other agents,
    the autopilot and the automaton, each with the state its record gives and a light."""
    from . import automaton
    by = {a["name"]: a for a in agents if a["name"] != "jarvis"}
    rows = []
    for name in (*PICTURE_ROLES, *(n for n in by if n not in PICTURE_ROLES)):
        a = by.get(name)
        if a is None:
            rows.append({"name": name, "state": "not set up yet", "light": "off"})
        elif a["state"] == "idle" and a["approval"] not in ("approved", "unknown"):
            rows.append({"name": name, "state": a["approval"], "light": "off"})
        else:
            rows.append({"name": name, "state": "free" if a["state"] == "idle" else a["state"],
                         "light": "stopped" if a["room"] == "repair" else LIGHT[a["state"]]})
    ap = sys_["autopilot"]
    rows.append({"name": "autopilot", **(
        {"state": "paused by you", "light": "waiting"} if ap["paused"] else
        {"state": f"working: {ap['running']} running", "light": "working"} if ap["running"] else
        {"state": f"nothing running, {ap['queued']} queued", "light": "free"})})
    st = automaton.status(home)
    rows.append({"name": "automaton", **(
        {"state": "not started", "light": "off"} if not st.get("started_at") else
        {"state": "dead (only you can revive it)", "light": "stopped"} if st.get("dead") else
        {"state": f"running, {st['tier'].replace('_', ' ')}", "light": "working"} if st.get("on")
        else {"state": "stopped", "light": "off"})})
    return rows


def system(home: Path) -> dict[str, Any]:
    """The status panel (the owner's picture, 2026-11-17), from records only: whether this
    computer is headquarters, how many laptop stations may reach Jarvis, and the autopilot.
    A station is "paired" when its key is allowed; whether it is connected right now is not
    known here, so it is never said."""
    from . import autopilot
    from . import station as S
    try:
        paired = len(S.stations(Path.home() / ".ssh" / "authorized_keys"))
    except OSError:
        paired = 0
    st = autopilot.status(home)
    from . import money
    try:
        cash = money.summary(home)
    except Exception:  # noqa: BLE001 - the panel never breaks the world; the command says why
        cash = None
    out = {"headquarters": S.MARK.exists(), "station": S.is_station(),
           "stations_paired": paired, "money": cash,
           "autopilot": {"paused": bool(st.get("paused")), "running": st.get("running", 0),
                         "queued": st.get("queued", 0),
                         "waiting_for_you": st.get("waiting_owner", 0)}}
    out["problems"] = problems(home, out)
    return out


def problems(home: Path, s: dict[str, Any]) -> list[str]:
    """What is wrong, from the same records the panel shows; none means "all systems healthy".
    On a laptop station the money and the autopilot run on the desktop, so they are not its own."""
    from .governor import hold_reason
    out = []
    held = hold_reason(home)
    if held:
        out.append(f"HOLD: {held}")
    if not s["station"]:
        if s["autopilot"]["paused"]:
            out.append("the autopilot is paused (bau autopilot resume)")
        m = s["money"]
        if m is None:
            out.append("the money machine could not be read (bau money)")
        elif m["ready"] != m["of"]:
            out.append(f"money machine: {m['ready']} of {m['of']} links ready; "
                       f"next: {m['next']} (bau money)")
    return out


def jarvis(home: Path, now: dt.datetime) -> dict[str, Any]:
    """Jarvis herself: her autopilot's latest task (autopilot.py) puts her in the room where
    that kind of job is done; with none running she is at her core."""
    from . import autopilot
    tasks = autopilot._load(home).get("tasks", [])
    live = [t for t in tasks if t.get("state") in ("running", "waiting_owner")]
    t = max(live, key=lambda t: t.get("started") or t.get("created") or "", default=None)
    if t is None:
        ended = [t for t in tasks if t.get("state") in ("done", "failed") and t.get("finished")]
        t = max(ended, key=lambda t: t["finished"], default=None)
        if t is not None and (_when(t["finished"]) is None or now - _when(t["finished"]) > RECENT):
            t = None
    room, state = "hq", "idle"
    if t is not None:
        room, state = {"running": (JOB_ROOM.get(t["kind"], "hq"), "working"),
                       "waiting_owner": ("approvals", "waiting for you"),
                       "done": ("delivery", "done"),
                       "failed": ("repair", "failed")}[t["state"]]
    return {"name": "jarvis", "look": "jarvis", "room": room, "state": state,
            "description": "Jarvis: her autopilot works its own queue (bau autopilot)",
            "brain": "the boss model", "tools": [], "mcp": [], "approval": "built in",
            "job": None if t is None else {
                "job_id": t["id"], "mission_id": "", "objective": t.get("title", "")[:300],
                "status": t["state"].upper(), "model": None,
                "updated_at": t.get("finished") or t.get("started") or t.get("created"),
                "steps_done": 0, "steps_left": 0, "cost_usd": 0.0, "errors": [],
                "artifacts": [], "next_action": t.get("note") or None}}


NEON_NAMES = {f"neon-{k}-{p}" for k in PORTRAIT_LOOKS for p in NEON_POSES}


def portrait_file(home: Path, look: str) -> Path | None:
    """Her painted portrait, if one was drawn; only the fixed looks (and ``neon-LOOK-POSE``),
    never a path from a request."""
    if look not in PORTRAIT_LOOKS and look != AVATAR_LOOK and look not in NEON_NAMES:
        return None
    f = home / "world" / "portraits" / f"{look}.png"
    return f if f.is_file() else None


class PicturesNotRunning(RuntimeError):
    """ComfyUI does not answer on this computer; nothing was drawn."""


PICTURES_NOT_RUNNING = (
    "the picture setup (ComfyUI) is not running on this computer: nothing answers on "
    "127.0.0.1:8188. Start it with: sudo systemctl start bau-pictures.service (not set up "
    "yet: sudo bash /opt/bau-payload/bau-pictures-setup.sh, docs/PICTURES.md). Nothing was drawn.")


def pictures_running() -> bool:
    """ComfyUI answers on this computer (the same check as the pictures setup card)."""
    from .setup_steps import _answers
    return _answers("http://127.0.0.1:8188/system_stats")


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def draw_portraits(home: Path, looks: list[str] | None = None, again: bool = False,
                   drawer: Any = None, ready: Any = None,
                   say: Any = _say, style: str = "classic",
                   poses: list[str] | None = None) -> list[dict[str, Any]]:
    """Paint each look's portrait on this computer's ComfyUI (the owner's command). One that
    exists is kept unless ``again``; a failed one is reported and the rest go on. With the
    real drawer, ComfyUI must answer first (``ready``), else PicturesNotRunning, nothing drawn;
    each portrait is said as it goes (on the owner's desktop it printed nothing).
    ``style="neon"``: the neon headquarters, one picture per look and pose (``NEON_POSES``)."""
    from .audit import AuditLog
    from .media import comfy
    if ready is None and drawer is None:
        ready = pictures_running
    if ready is not None and not ready():
        raise PicturesNotRunning(PICTURES_NOT_RUNNING)
    drawer = drawer or comfy.draw
    out_dir = home / "world" / "portraits"
    out_dir.mkdir(parents=True, exist_ok=True)
    done = []
    todo = looks or list(PORTRAIT_LOOKS)
    if style == "neon":
        todo = [f"neon-{k}-{p}" for k in todo for p in (poses or NEON_POSES)]
    for i, look in enumerate(todo, 1):
        say(f"painting {look} ({i}/{len(todo)})...")
        result = _draw_one(home, look, again, drawer, comfy, out_dir, AuditLog)
        say(f"  {look}: {result}")
        done.append({"look": look, "result": result})
    return done


def _draw_one(home: Path, look: str, again: bool, drawer: Any, comfy: Any, out_dir: Path,
              audit: Any) -> str:
    if look not in PORTRAIT_LOOKS and look != AVATAR_LOOK and look not in NEON_NAMES:
        return "unknown look"
    if portrait_file(home, look) and not again:
        return "already drawn"
    name = f"world-portrait-{look}"
    if look in NEON_NAMES:
        who, pose = look[5:].rsplit("-", 1)
        prompt, negative = (NEON_STYLE.format(who=NEON_WHO[who], pose=NEON_POSES[pose]),
                            PORTRAIT_NEGATIVE)
    else:
        prompt, negative = ((AVATAR_PROMPT, AVATAR_NEGATIVE) if look == AVATAR_LOOK else
                            (PORTRAIT_STYLE.format(who=PORTRAIT_WHO[look]), PORTRAIT_NEGATIVE))
    try:
        drawer(home, prompt, name, negative=negative, width=832, height=1216)
    except (comfy.ComfyError, OSError) as e:      # ComfyUI gone mid-way: say so, go on
        return f"not drawn: {e}"
    media = home / "artifacts" / "media"
    (media / f"{name}.png").replace(out_dir / f"{look}.png")    # never left for Fanvue
    prov = media / f"{name}.png.provenance.json"
    if prov.exists():
        prov.replace(out_dir / f"{look}.png.provenance.json")
    audit(home / "audit" / "chain.jsonl").append("world.portrait", "bau", {"look": look})
    return "drawn"
