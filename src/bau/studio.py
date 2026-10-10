"""Video studio: AI clips from a paid provider (Higgsfield), under the owner's budget.

Money rules, in order:
1. Nothing is spent until the owner has set a monthly and a per-clip budget themselves
   (``bau video budget``) and approved the provider (``bau set-status provider higgsfield
   APPROVED``). There is no default budget.
2. Every clip is priced with the provider's own estimate first; one over the per-clip
   limit, or over what is left this month, is refused before anything is sent.
3. A clip starts only for a human (the owner's ``y`` or Confirm click). Jarvis can put a
   clip on the owner's screen, never start one. A HOLD stops new clips.
4. Completed clips are downloaded with a provenance record (AI-generated) and their cost
   goes into the ledger, which the Governor's daily spending cap watches. Failed and
   moderated clips are not charged by the provider and are not recorded as spending.
"""

from __future__ import annotations

import datetime as dt
import secrets
from pathlib import Path
from typing import Any

from .economics import Ledger
from .home import bau_home
from .media.higgsfield import FINAL, Higgsfield, HiggsfieldError, request_body
from .store import JsonlStore, YamlStore

AGENT = "studio"
PROVIDER = "higgsfield"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Studio:
    def __init__(self, home: Path | None = None, audit: Any = None, client: Any = None):
        from .audit import AuditLog
        self.home = home or bau_home()
        self.audit = audit or AuditLog(self.home / "audit" / "chain.jsonl")
        self.client = client or Higgsfield()
        self.dir = self.home / "studio"
        self.jobs_log = JsonlStore(self.dir / "jobs.jsonl")
        self.cfg_store = YamlStore(self.home / "config" / "video.yaml")

    # ---------------------------------------------------------------- the owner's budget
    def budget(self) -> dict[str, Any]:
        return self.cfg_store.load() or {}

    def set_budget(self, monthly: float, per_clip: float, by: str,
                   max_running: int = 2) -> dict[str, Any]:
        if not by.startswith("human:"):
            raise PermissionError("only the owner sets the video budget")
        if monthly < 0 or per_clip < 0 or max_running < 1:
            raise ValueError("budgets can't be negative")
        cfg = {"monthly_usd": float(monthly), "per_clip_usd": float(per_clip),
               "max_running": int(max_running), "set_by": by,
               "set_at": _now().isoformat(timespec="seconds")}
        (self.home / "config").mkdir(parents=True, exist_ok=True)
        self.cfg_store.save(cfg)
        self.audit.append("studio.budget_set", by, {"monthly_usd": cfg["monthly_usd"],
                                                    "per_clip_usd": cfg["per_clip_usd"]})
        return cfg

    def spent_this_month(self) -> float:
        start = _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return round(Ledger(self.home).spent(agent=AGENT, since=start), 4)

    def _provider_status(self) -> str:
        from .registry import CapabilityRegistry
        reg = CapabilityRegistry(self.home / "registry" / "capabilities.yaml")
        return str((reg.data["provider"].get(PROVIDER) or {}).get("status", "missing"))

    # ---------------------------------------------------------------- pricing
    def quote(self, prompt: str, model: str, duration: int, aspect_ratio: str,
              sound: str) -> dict[str, Any]:
        """What this clip would cost and whether it may run. Asks the provider for its
        estimate only once the budget and the provider are in place."""
        cfg, spent = self.budget(), self.spent_this_month()
        q: dict[str, Any] = {"model": model, "duration": duration,
                             "aspect_ratio": aspect_ratio, "sound": sound,
                             "spent_this_month": spent, "allowed": False}
        try:
            body = request_body(model, prompt, duration, aspect_ratio, sound)
        except HiggsfieldError as e:
            return {**q, "why": str(e)}
        if "monthly_usd" not in cfg:
            return {**q, "why": "no video budget yet: the owner sets one with "
                                "`bau video budget --monthly 40 --per-clip 3`"}
        left = round(cfg["monthly_usd"] - spent, 4)
        q.update(monthly_usd=cfg["monthly_usd"], per_clip_usd=cfg["per_clip_usd"],
                 left_this_month=left)
        status = self._provider_status()
        if status not in ("APPROVED", "ACTIVE"):
            return {**q, "why": f"Higgsfield is {status}: read its terms (docs/STUDIO.md), "
                                "then `bau set-status provider higgsfield APPROVED`"}
        if not getattr(self.client, "configured", True):
            return {**q, "why": "no Higgsfield key: set HIGGSFIELD_API_KEY_ID and "
                                "HIGGSFIELD_API_KEY_SECRET"}
        try:
            est = self.client.estimate(model, body)
        except HiggsfieldError as e:
            return {**q, "why": str(e)}
        q.update(usd=est["usd"], credits=est["credits"])
        if est["usd"] > cfg["per_clip_usd"]:
            return {**q, "why": f"${est['usd']:.2f} is over your per-clip limit of "
                                f"${cfg['per_clip_usd']:.2f}"}
        if est["usd"] > left:
            return {**q, "why": f"${est['usd']:.2f} is more than the ${max(left, 0):.2f} "
                                "left in this month's video budget"}
        return {**q, "allowed": True, "why": "within budget", "body": body}

    # ---------------------------------------------------------------- making clips
    def jobs(self) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for r in self.jobs_log:
            latest[r["id"]] = {**latest.get(r["id"], {}), **r}
        return sorted(latest.values(), key=lambda j: j["at"], reverse=True)

    def make(self, prompt: str, model: str, duration: int, aspect_ratio: str, sound: str,
             by: str) -> dict[str, Any]:
        """Start one clip. Only a human starts clips; the price is checked again here."""
        from .governor import hold_reason
        if not by.startswith("human:"):
            raise PermissionError("only the owner starts a paid clip")
        if hold_reason(self.home):
            raise PermissionError(f"BAU is on HOLD ({hold_reason(self.home)}); no new clips")
        running = [j for j in self.jobs() if j["status"] == "submitted"]
        if len(running) >= int(self.budget().get("max_running", 2)):
            raise PermissionError(f"{len(running)} clip(s) still in progress; wait for them")
        q = self.quote(prompt, model, duration, aspect_ratio, sound)
        if not q["allowed"]:
            raise PermissionError(q["why"])
        jid = "clip_" + secrets.token_hex(5)
        req = self.client.submit(model, q["body"], jid)          # job id = idempotency key
        job = {"id": jid, "at": _now().isoformat(timespec="seconds"), "by": by,
               "prompt": q["body"]["prompt"], "model": model, "duration": duration,
               "aspect_ratio": aspect_ratio, "sound": sound, "usd": q["usd"],
               "credits": q["credits"], "request_id": req["request_id"],
               "status_url": req.get("status_url"), "status": "submitted"}
        self.jobs_log.append(job)
        self.audit.append("studio.submitted", by, {"clip": jid, "model": model,
                                                   "usd": q["usd"],
                                                   "request_id": req["request_id"]})
        return job

    def refresh(self, max_wait: float = 0) -> list[dict[str, Any]]:
        """Check every clip in progress once (or wait up to ``max_wait`` seconds each);
        download finished ones and record their cost. Never charges a clip twice."""
        from .media.gateway import MediaGateway
        for job in [j for j in self.jobs() if j["status"] == "submitted"]:
            req = {"request_id": job["request_id"], "status_url": job.get("status_url")}
            try:
                st = self.client.wait(req, max_wait) if max_wait else self.client.status(req)
            except HiggsfieldError as e:
                state = str(e).split(":")[0]
                if state in FINAL:
                    self._finish(job, state, str(e))
                continue
            s = st.get("status")
            if s not in FINAL:
                continue
            if s != "completed" or not (st.get("video") or {}).get("url"):
                self._finish(job, s, st.get("error") or s)
                continue
            out = self.dir / "clips" / f"{job['id']}.mp4"
            gw = MediaGateway({PROVIDER: _Fetched(self.client, st["video"]["url"])})
            try:
                gw.produce("generate_video", PROVIDER, out, job["id"], job["model"],
                           source_material=[f"prompt: {job['prompt'][:200]}"])
            except HiggsfieldError as e:
                self.jobs_log.append({"id": job["id"], "note": f"download failed: {e}"})
                continue                     # kept 7+ days by Higgsfield: try again later
            Ledger(self.home).cost("api", job["usd"], agent=AGENT, job_id=job["id"],
                                   provider=PROVIDER, model=job["model"],
                                   note="Higgsfield's estimate at submission")
            self.jobs_log.append({"id": job["id"], "status": "completed", "file": str(out),
                                  "done_at": _now().isoformat(timespec="seconds")})
            self.audit.append("studio.completed", "studio", {"clip": job["id"],
                                                             "usd": job["usd"]})
        return self.jobs()

    def _finish(self, job: dict[str, Any], status: str, why: str) -> None:
        note = {"nsfw": "rejected by content moderation: not charged",
                "failed": "generation failed: not charged",
                "canceled": "canceled: not charged"}.get(status, why)
        self.jobs_log.append({"id": job["id"], "status": status, "note": note,
                              "done_at": _now().isoformat(timespec="seconds")})
        self.audit.append("studio.not_made", "studio", {"clip": job["id"], "status": status})


class _Fetched:
    """Gateway adapter for a clip the provider already made: it downloads the file."""
    name = PROVIDER
    generative = True

    def __init__(self, client: Any, url: str):
        self.client, self.url = client, url

    def run(self, verb: str, out: Path, **kw: Any) -> Path:
        return self.client.download(self.url, out)
