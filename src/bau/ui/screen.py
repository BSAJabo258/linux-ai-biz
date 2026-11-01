"""What the Jarvis screen's panels read and do, kept apart from the HTTP plumbing.

Every action here is the owner's, started by their click on a page only they can open
(see ``jarvis_server``): searching, inspecting a candidate, testing a model, editing a
draft. None of them approves anything; approving a model stays a typed command and checking
a stage still goes through the owner's Confirm.
"""

from __future__ import annotations

import datetime as dt
import time
import urllib.error
from typing import Any

MAX_EDIT = 200_000           # characters in one stage file edited on screen
MC_VIEWS = ("status", "regulations", "jobs", "missions", "legal-queue", "economics",
            "brain", "governor", "incidents")


def _scout(asst: Any) -> Any:
    from ..scout import Scout
    return Scout(asst.home, asst.clients.get("github"), asst.audit, asst.owner,
                 cloner=asst.clients.get("git_clone"))


def scout_summary(asst: Any) -> dict[str, Any]:
    from ..scout import rank
    sc = _scout(asst)
    rows = [c for c in rank(sc.candidates().values()) if not c.get("duplicate_of")]
    return {"candidates": [{"repo": c["full_name"], "url": c["url"],
                            "claims": c["claimed"]["description"][:200],
                            "score": c["score"], "coverage": c["evidence_coverage"],
                            "decision": c["decision"], "licence": c["license"]["status"],
                            "security": c["security"]["status"],
                            "tested": c["validation"]["status"],
                            "blocked": c["blockers"], "needs": c["needs"],
                            "unknowns": c["unknowns"],
                            "heavy": bool((c.get("resources") or {}).get("gpu_or_large_model"))}
                           for c in rows[:30]],
            "runs": [{"id": r["id"], "at": r["at"], "request": r["request"],
                      "found": r["found"], "failed": r["failed_searches"],
                      "waiting_until": r.get("rate_limited_until")}
                     for r in reversed(sc.runs()[-5:])]}


def scout_find(asst: Any, request: str) -> dict[str, Any]:
    request = request.strip()[:300]
    if not request:
        return {"error": "say what capability to look for"}
    asst.activity.emit("scout", "start", f"Searching GitHub for: {request}")
    try:
        run = _scout(asst).find(request, max_queries=6, readmes=5,
                                progress=lambda t: asst.activity.emit("scout", "progress", t))
    except ValueError as e:
        asst.activity.emit("scout", "error", str(e))
        return {"error": str(e)}
    asst.activity.emit("scout", "done", f"Found {run['found']} for: {request}")
    return {"run": run["id"], "found": run["found"], "failed": run["failed_searches"],
            "waiting_until": run["rate_limited_until"], "top": run["ranked"][:8]}


def scout_inspect(asst: Any, repo: str) -> dict[str, Any]:
    import subprocess
    asst.activity.emit("scout", "start", f"Downloading {repo} into quarantine to scan it")
    try:
        c = _scout(asst).inspect(repo)
    except (KeyError, ValueError) as e:
        asst.activity.emit("scout", "error", str(e).strip("'\""))
        return {"error": str(e).strip("'\"")}
    except subprocess.CalledProcessError:
        asst.activity.emit("scout", "error", f"could not download {repo}")
        return {"error": f"could not download {repo}"}
    asst.activity.emit("scout", "done", f"{repo}: Sentinel says {c['inspected']['verdict']}")
    return {"repo": c["full_name"], "sentinel": c["inspected"]["verdict"],
            "reasons": c["inspected"]["reasons"], "licence": c["license"],
            "decision": c["decision"], "needs": c["needs"], "blocked": c["blockers"]}


def scout_report(asst: Any, run: str | None) -> dict[str, Any]:
    from ..scout import report
    try:
        return {"markdown": report(_scout(asst), run or None)}
    except KeyError as e:
        return {"error": str(e).strip("'\"")}


def bench(asst: Any, model: str) -> dict[str, Any]:
    from ..models import bench as B
    asst.activity.emit("models", "start", f"Testing {model}")
    try:
        res = B.record(model, asst.owner, asst.home, asst.audit)
    except KeyError as e:
        asst.activity.emit("models", "error", str(e).strip("'\""))
        return {"error": str(e).strip("'\"")}
    except Exception as e:  # model server down, busy, bad reply: nothing recorded
        msg = f"test failed: {type(e).__name__}: {e}"[:300]
        asst.activity.emit("models", "error", msg)
        return {"error": msg}
    asst.activity.emit("models", "done", f"{model}: reply_ok {res['reply_ok']}, "
                                         f"tool_calls {res['tool_calls']}")
    return {**res, "model": model,
            "next": f"bau set-status model {model} APPROVED" if res["reply_ok"] else
            "it did not answer properly: fix the model server and test again"}


def _stage(asst: Any, workspace: str, episode: str, stage: str) -> tuple[Any, Any, Any]:
    import re

    from .. import workspace as W
    for name in (workspace, episode):          # plain folder names only, never a path
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}", name) or ".." in name:
            raise W.WorkspaceError(f"not a workspace or episode name: {name!r}")
    ws = W.open_ws(workspace, asst.home)
    ep = W.find_episode(ws, episode)
    hits = [c for c in W.contracts(ep) if c.stage[:2] == stage[:2] and stage[:2].isdigit()]
    if len(hits) != 1 or len(stage) > 40:
        raise W.WorkspaceError(f"no single stage {stage!r} in {ep.name}")
    return ws, ep, hits[0]


def stage_read(asst: Any, workspace: str, episode: str, stage: str) -> dict[str, Any]:
    from .. import workspace as W
    try:
        ws, ep, c = _stage(asst, workspace, episode, stage)
    except W.WorkspaceError as e:
        return {"error": str(e)}
    f = c.out_dir / c.outputs[0]
    if not f.exists():
        return {"error": f"{c.stage}: nothing written yet"}
    return {"stage": c.stage, "file": f.name, "text": f.read_text()[:MAX_EDIT],
            "checked": W.is_checked(c), "check": c.human_check,
            "issues": [i["detail"] for i in W.run_checks(ws, ep, c)]}


def stage_write(asst: Any, workspace: str, episode: str, stage: str,
                text: str) -> dict[str, Any]:
    """The owner edits a stage's output on screen. Only that stage's one output file is
    written, and only once it has a draft - or, for the owner's own stage, once it is the
    stage that is up. Editing a checked stage voids its check (its hash changes)."""
    from .. import workspace as W
    if len(text) > MAX_EDIT:
        return {"error": f"too long: at most {MAX_EDIT} characters"}
    try:
        ws, ep, c = _stage(asst, workspace, episode, stage)
    except W.WorkspaceError as e:
        return {"error": str(e)}
    f = c.out_dir / c.outputs[0]
    nxt = W.next_stage(ep)
    if not f.exists() and not (not c.agent and nxt is not None and nxt.stage == c.stage):
        return {"error": f"{c.stage}: nothing to edit yet - draft it first"}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    asst.audit.append("workspace.edited", asst.owner, {"workspace": ws.name,
                                                       "episode": ep.name, "stage": c.stage})
    W.rebuild_index(ws)
    asst.activity.emit("producer", "done", f"You edited {ep.name} {c.stage}")
    return {"saved": f.name, "checked": W.is_checked(c),
            "issues": [i["detail"] for i in W.run_checks(ws, ep, c)]}


def timeline(asst: Any, limit: int = 50, before: int | None = None) -> dict[str, Any]:
    """The audit chain, newest first, in short lines. The chain itself is the record."""
    from ..audit import AuditLog
    log = AuditLog(asst.home / "audit" / "chain.jsonl")
    intact, why = log.verify()
    recs = [r for r in log.records() if before is None or r["seq"] < before]
    items = []
    for r in reversed(recs[-max(1, min(limit, 200)):]):
        data = r.get("data") or {}
        summary = ", ".join(f"{k} {v}" for k, v in data.items()
                            if isinstance(v, (str, int, float, bool)))[:200]
        items.append({"seq": r["seq"], "at": r["ts"], "event": r["event"],
                      "actor": r["actor"], "summary": summary, "hash": r["hash"][:12]})
    return {"intact": intact, "check": why, "items": items}


def mission_control(asst: Any, view: str) -> Any:
    """The same read-only data Mission Control shows (``ui/server.py``)."""
    from .server import _api
    if view not in MC_VIEWS:
        raise KeyError(view)
    return _api(f"/api/{view}", asst.home)


def usage_summary(asst: Any) -> dict[str, Any]:
    """The usage meter: tokens and dollars per model, limits, warnings (no secrets)."""
    from ..usage import Usage
    return Usage(asst.home).summary()


def studio_summary(asst: Any, refresh: bool = True) -> dict[str, Any]:
    """Budget, this month's spending and the clips; checks clips in progress once."""
    st = asst.studio()
    before = {j["id"]: j["status"] for j in st.jobs()}
    jobs = st.refresh() if refresh else st.jobs()
    for j in jobs:                          # say so once, when a clip changes state
        if before.get(j["id"]) == "submitted" and j["status"] != "submitted":
            asst.activity.emit("studio", "done" if j["status"] == "completed" else "error",
                               f"Clip {j['id']}: " + ("ready" if j["status"] == "completed"
                                                      else j.get("note") or j["status"]))
    return {"budget": st.budget(), "spent_this_month": st.spent_this_month(),
            "clips": [{k: j.get(k) for k in ("id", "at", "status", "model", "duration",
                                              "aspect_ratio", "usd", "prompt", "note")}
                      for j in jobs[:20]]}


def studio_stage(asst: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Put one priced clip on the owner's screen (the same card Jarvis would stage)."""
    try:
        duration = int(data.get("duration", 5))
    except (TypeError, ValueError):
        return {"error": "duration must be a whole number of seconds"}
    out, err = asst._run_tool("make_video", {
        "prompt": str(data.get("prompt", "")), "model": str(data.get("model", "")),
        "duration": duration, "aspect_ratio": str(data.get("aspect_ratio", "")),
        "sound": str(data.get("sound", ""))})
    if err:
        return {"error": out.get("error", "could not price that clip")}
    p = asst.pending.get(out["pending_id"])
    return {"pending": [p.public()] if p else []}


def studio_clip(asst: Any, clip_id: str) -> Any:
    """The saved file of one finished clip - only from the studio's own folder."""
    import re
    if not re.fullmatch(r"clip_[0-9a-f]{10}", clip_id):
        return None
    f = asst.home / "studio" / "clips" / f"{clip_id}.mp4"
    return f if f.is_file() else None


# ------------------------------------------------------------------ God's Eye
# Aircraft are shown only for wide named regions (never a box around one place), and every
# query is recorded with its purpose. Results are kept five minutes so the public sources
# (USGS, OpenSky, CelesTrak) are asked at most once per view in that time.
GODSEYE_REGIONS = {      # (lat min, lon min, lat max, lon max)
    "usa-east": (24.0, -90.0, 47.0, -66.0), "usa-west": (31.0, -125.0, 49.0, -102.0),
    "florida": (24.5, -87.6, 31.0, -80.0), "new-york-area": (39.5, -75.5, 42.0, -71.5),
    "caribbean": (10.0, -90.0, 27.0, -59.0), "uk-ireland": (49.5, -11.0, 59.0, 2.0),
    "europe": (35.0, -10.0, 60.0, 30.0), "japan": (30.0, 129.0, 46.0, 146.0),
}
GODSEYE_TTL = 300
MAX_POINTS = 400


def godseye_query(asst: Any, layer: str, purpose: str, window: str = "all_day",
                  region: str = "", group: str = "stations") -> dict[str, Any]:
    """One public layer, ready to plot. Raises ValueError / SpatialRefused on a bad ask."""
    from ..spatial import GodsEye
    if layer not in ("earthquakes", "aircraft", "satellites"):
        raise ValueError("layer must be earthquakes, aircraft or satellites")
    if layer == "aircraft" and region not in GODSEYE_REGIONS:
        raise ValueError(f"choose a region: {', '.join(GODSEYE_REGIONS)}")
    key = (layer, window if layer == "earthquakes" else region if layer == "aircraft"
           else group)
    waits = asst.__dict__.setdefault("_godseye_wait", {})
    if waits.get(layer, 0) > time.time():
        until = dt.datetime.fromtimestamp(waits[layer], dt.UTC).strftime("%H:%M UTC")
        raise ValueError(f"the {layer} source asked BAU to wait until {until}; "
                         "nothing was sent")
    cache = asst.__dict__.setdefault("_godseye", {})
    hit = cache.get(key)
    if hit and time.monotonic() - hit[0] < GODSEYE_TTL:
        return {**hit[1], "cached": True}
    ge = GodsEye(opener=asst.clients.get("spatial_opener"))
    asst.activity.emit("godseye", "start", f"Reading public {layer} data")
    if layer == "earthquakes":
        raw = ge.earthquakes(purpose, window)
        pts = [{"lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1],
                "mag": f["properties"]["mag"], "label": str(f["properties"].get("place", ""))}
               for f in raw["features"] if f["properties"].get("mag") is not None]
        pts.sort(key=lambda p: -p["mag"])
        out = {"points": pts[:MAX_POINTS], "list": [], "total": len(pts)}
    elif layer == "aircraft":
        raw = ge.aircraft(purpose, GODSEYE_REGIONS[region])
        pts = [{"lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1],
                "label": f"{_flight(f['properties']['callsign'])} · "
                         f"{f['properties']['origin_country']}",
                "alt": f["properties"]["altitude_m"]} for f in raw["features"]]
        out = {"points": pts[:MAX_POINTS], "list": [], "region": region, "total": len(pts)}
    else:
        raw = ge.satellites(purpose, group)
        out = {"points": [], "note": "orbital elements only: positions are not computed",
               "list": [{"name": f["properties"]["OBJECT_NAME"],
                         "norad": f["properties"]["NORAD_CAT_ID"],
                         "inclination": f["properties"]["INCLINATION"],
                         "orbits_per_day": f["properties"]["MEAN_MOTION"]}
                        for f in raw["features"]][:MAX_POINTS], "total": len(raw["features"])}
    meta = raw["bau"]
    result = {"layer": layer, "count": out.pop("total"), "licence": meta["licence"],
              "retrieved_at": meta["retrieved_at"], **out}
    asst.audit.append("godseye.query", asst.owner, {"layer": layer, "option": key[1],
                                                    "purpose": purpose[:200],
                                                    "count": result["count"]})
    asst.activity.emit("godseye", "done", f"{result['count']} {layer}")
    cache[key] = (time.monotonic(), result)
    return result


def _flight(callsign: str) -> str:
    """Airline flights keep their flight number (ICAO airline code + digits); anything else
    - a private registration such as N4791E - can point to one person and is not named."""
    import re
    cs = (callsign or "").strip().upper()
    return cs if re.fullmatch(r"[A-Z]{3}\d{1,4}[A-Z]{0,2}", cs) else "private aircraft"


def godseye_layer(asst: Any, data: dict[str, Any]) -> dict[str, Any]:
    layer = str(data.get("layer", ""))
    if "bbox" in data:
        raise ValueError("aircraft are shown by named region only, never a box you draw")
    return godseye_query(asst, layer, f"Owner viewing public {layer} data on the Jarvis "
                         "screen", str(data.get("window", "all_day")),
                         str(data.get("region", "")), str(data.get("group", "stations")))


def godseye_screen(asst: Any, data: dict[str, Any]) -> dict[str, Any]:
    from ..spatial import SpatialRefused
    try:
        return godseye_layer(asst, data)
    except (ValueError, SpatialRefused) as e:
        return {"error": str(e)}
    except urllib.error.HTTPError as e:
        if e.code == 429:                      # "slow down": honour it, like Repo Scout
            try:
                wait = max(60, min(3600, int(e.headers.get("Retry-After", 600))))
            except (TypeError, ValueError, AttributeError):
                wait = 600
            layer = str(data.get("layer", ""))
            asst.__dict__.setdefault("_godseye_wait", {})[layer] = time.time() + wait
            until = dt.datetime.fromtimestamp(time.time() + wait, dt.UTC).strftime("%H:%M UTC")
            asst.activity.emit("godseye", "error", f"{layer} source asked BAU to wait")
            return {"error": f"the {layer} source asked BAU to wait until {until} "
                             "(too many requests); BAU sends nothing before then"}
        return {"error": f"the public source refused (HTTP {e.code})"}
    except OSError as e:                       # the public source didn't answer
        asst.activity.emit("godseye", "error", "a public data source didn't answer")
        return {"error": f"the public source didn't answer: {str(e)[:120]}"}


def godseye_world() -> dict[str, Any]:
    import json
    from importlib import resources
    return json.loads((resources.files("bau") / "data" / "world-land.json").read_text())
