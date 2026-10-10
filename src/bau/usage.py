"""Usage meter: what every model call cost in tokens and dollars, free models included.

Every call Jarvis (and the workspaces and Scout he runs) makes to a model is written to
``usage/calls.jsonl``: which model answered, tokens in and out, the price from its registry
record, how long it took, and whether it failed or was busy. Paid calls also go into the
ledger once, so the Governor's daily spending cap counts them.

The owner may set daily limits (tokens and/or dollars) with ``bau usage limits``; there are
none by default. When one is reached Jarvis says so instead of calling the model. Rate-limit
headers a hosted model sends (``x-ratelimit-*``) and GitHub's waits recorded by Repo Scout
are shown as they were received; nothing here guesses a provider's limits.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .home import bau_home
from .models.providers import ModelResponse, Provider, ProviderError
from .store import JsonlStore, YamlStore

WARN_AT = 0.8


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class UsageLimit(ProviderError):
    """A daily limit the owner set is reached; the message is safe to show and speak."""


def _blank() -> dict[str, Any]:
    return {"calls": 0, "tokens_in": 0, "tokens_out": 0, "tokens": 0, "usd": 0.0,
            "errors": 0}


def _add(t: dict[str, Any], r: dict[str, Any]) -> None:
    t["calls"] += 1
    t["tokens_in"] += r["tokens_in"]
    t["tokens_out"] += r["tokens_out"]
    t["tokens"] += r["tokens_in"] + r["tokens_out"]
    t["usd"] = round(t["usd"] + r["usd"], 6)
    t["errors"] += 0 if r["ok"] else 1


class Usage:
    def __init__(self, home: Path | None = None, audit: Any = None):
        self.home = home or bau_home()
        self.audit = audit
        self.log = JsonlStore(self.home / "usage" / "calls.jsonl")
        self.cfg = YamlStore(self.home / "config" / "usage.yaml")

    # ---------------------------------------------------------------- the owner's limits
    def limits(self) -> dict[str, Any]:
        return self.cfg.load() or {}

    def set_limits(self, daily_tokens: int | None, daily_usd: float | None,
                   by: str) -> dict[str, Any]:
        if not by.startswith("human:"):
            raise PermissionError("only the owner sets usage limits")
        if (daily_tokens is not None and daily_tokens < 1) or \
                (daily_usd is not None and daily_usd < 0):
            raise ValueError("limits must be positive (leave one out for no limit)")
        cfg = {"daily_tokens": daily_tokens, "daily_usd": daily_usd, "set_by": by,
               "set_at": _now().isoformat(timespec="seconds")}
        (self.home / "config").mkdir(parents=True, exist_ok=True)
        self.cfg.save(cfg)
        from .audit import AuditLog
        audit = self.audit or AuditLog(self.home / "audit" / "chain.jsonl")
        audit.append("usage.limits_set", by, {"daily_tokens": daily_tokens,
                                              "daily_usd": daily_usd})
        return cfg

    # ---------------------------------------------------------------- recording
    def record(self, model: str, provider: str, tokens_in: int, tokens_out: int,
               usd: float = 0.0, *, agent: str = "jarvis", ok: bool = True,
               error: str = "", ms: int = 0, limits: dict[str, str] | None = None,
               when: dt.datetime | None = None) -> dict[str, Any]:
        err = str(error)[:200]
        return self.log.append({
            "ts": (when or _now()).isoformat(timespec="seconds"), "model": model or "?",
            "provider": provider or "", "agent": agent, "tokens_in": int(tokens_in or 0),
            "tokens_out": int(tokens_out or 0), "usd": round(float(usd or 0), 6),
            "ok": ok, "busy": not ok and ("busy" in err or "429" in err), "error": err,
            "ms": ms, "limits": limits or {}})

    def _since(self, start: dt.datetime) -> list[dict[str, Any]]:
        return [r for r in self.log if dt.datetime.fromisoformat(r["ts"]) >= start]

    def today(self, now: dt.datetime | None = None) -> dict[str, Any]:
        now = now or _now()
        t = _blank()
        for r in self._since(now.replace(hour=0, minute=0, second=0, microsecond=0)):
            _add(t, r)
        return t

    def over_limit(self, now: dt.datetime | None = None) -> str | None:
        lim, t = self.limits(), None
        for key, used_key, unit in (("daily_tokens", "tokens", "tokens"),
                                    ("daily_usd", "usd", "dollars")):
            if lim.get(key) is None:
                continue
            t = t or self.today(now)
            if t[used_key] >= lim[key]:
                used = f"{t[used_key]:,}" if unit == "tokens" else f"${t[used_key]:.2f}"
                cap = f"{lim[key]:,}" if unit == "tokens" else f"${lim[key]:.2f}"
                return (f"We've reached today's limit you set: {used} of {cap} {unit}. "
                        "I'll be back tomorrow (UTC), or raise it with `bau usage limits`.")
        return None

    # ---------------------------------------------------------------- the meter
    def summary(self, now: dt.datetime | None = None) -> dict[str, Any]:
        now = now or _now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today, week = _blank(), _blank()
        models: dict[str, dict[str, Any]] = {}
        for r in self._since(now - dt.timedelta(days=7)):
            _add(week, r)
            m = models.setdefault(r["model"], {"model": r["model"], **_blank(), "busy": 0,
                                               "today_tokens": 0, "last_error": "",
                                               "last_used": "", "limits": {},
                                               "provider": r["provider"]})
            _add(m, r)
            m["busy"] += 1 if r.get("busy") else 0
            m["last_used"] = r["ts"]
            m["provider"] = r["provider"] or m["provider"]
            if r.get("error"):
                m["last_error"] = r["error"]
            if r.get("limits"):
                m["limits"] = r["limits"]
            if dt.datetime.fromisoformat(r["ts"]) >= start:
                _add(today, r)
                m["today_tokens"] += r["tokens_in"] + r["tokens_out"]
        by_model = sorted(models.values(), key=lambda m: -m["calls"])
        github = self.github(now)
        return {"today": today, "week": week, "by_model": by_model,
                "limits": {k: v for k, v in self.limits().items()
                           if k in ("daily_tokens", "daily_usd")},
                "github": github, "warnings": self._warnings(today, by_model, github)}

    def _warnings(self, today: dict[str, Any], by_model: list[dict[str, Any]],
                  github: dict[str, Any]) -> list[str]:
        out = []
        lim = self.limits()
        for key, used_key, fmt in (("daily_tokens", "tokens", "{:,}"),
                                   ("daily_usd", "usd", "${:.2f}")):
            cap = lim.get(key)
            if not cap:
                continue
            share = today[used_key] / cap
            used, of = fmt.format(today[used_key]), fmt.format(cap)
            if share >= 1:
                out.append(f"Today's {used_key} limit is reached ({used} of {of}): Jarvis "
                           "waits until tomorrow (UTC) or `bau usage limits`.")
            elif share >= WARN_AT:
                out.append(f"Today's {used_key}: {share:.0%} of your daily limit "
                           f"({used} of {of}).")
        for m in by_model:
            h = m["limits"]
            for kind in ("requests", "tokens"):
                if str(h.get(f"x-ratelimit-remaining-{kind}", "")).strip() == "0":
                    reset = h.get(f"x-ratelimit-reset-{kind}")
                    out.append(f"{m['model']}: no {kind} left until the reset"
                               + (f" ({reset})" if reset else "") + ".")
            if m["busy"] >= 3:
                out.append(f"{m['model']} was busy {m['busy']} times this week; "
                           "its backups answered or the turn failed.")
        for bucket, g in github.items():
            if g["waiting_until"]:
                out.append(f"GitHub asked BAU to wait until {g['waiting_until']} ({bucket} "
                           "limit); Repo Scout sends nothing until then.")
        return out

    def github(self, now: dt.datetime | None = None) -> dict[str, Any]:
        """What GitHub last said about its limits (written by Repo Scout)."""
        try:
            st = json.loads((self.home / "scout" / "github-rate.json").read_text())
        except (OSError, ValueError):
            return {}
        ts = (now or _now()).timestamp()
        out = {}
        for bucket, b in st.items():
            if not isinstance(b, dict):
                continue
            until = float(b.get("blocked_until") or 0)
            out[bucket] = {"remaining": b.get("remaining"), "waiting_until": (
                dt.datetime.fromtimestamp(until, dt.UTC).strftime("%H:%M UTC")
                if until > ts else None)}
        return out


class Metered(Provider):
    """Wraps the provider Jarvis uses: checks the owner's daily limits before a call,
    then records the call (which model answered, tokens, price, failures) after it."""

    def __init__(self, inner: Provider, usage: Usage, price: Callable[[str], dict[str, Any]],
                 default_id: str = "", agent: str = "jarvis"):
        self.inner, self.usage, self.price = inner, usage, price
        self.default_id, self.agent = default_id, agent

    @property
    def answered_by(self) -> str | None:
        return getattr(self.inner, "answered_by", None)

    def complete(self, system, messages, tools=None, max_tokens=16000) -> ModelResponse:
        from .economics import Ledger
        from .models.router import estimate_usd
        stop = self.usage.over_limit()
        if stop:
            raise UsageLimit(stop)
        t0 = time.monotonic()
        try:
            resp = self.inner.complete(system, messages, tools, max_tokens)
        except (ProviderError, OSError) as e:
            if self._failures():
                raise                        # each backup that failed is already recorded
            mid = self.default_id or getattr(self.inner, "model", "?")
            self.usage.record(mid, self.price(mid).get("provider", ""), 0, 0, agent=self.agent,
                              ok=False, error=str(e) or type(e).__name__,
                              ms=int((time.monotonic() - t0) * 1000))
            raise
        self._failures()
        mid = self.answered_by or self.default_id or resp.model
        rec = self.price(mid)
        usd = estimate_usd(rec, resp.tokens_in, resp.tokens_out)
        self.usage.record(mid, rec.get("provider", ""), resp.tokens_in, resp.tokens_out, usd,
                          agent=self.agent, ms=int((time.monotonic() - t0) * 1000),
                          limits=getattr(self.inner, "last_limits", None))
        if usd:
            Ledger(self.usage.home).cost("model", usd, agent=self.agent,
                                         provider=rec.get("provider", ""), model=mid,
                                         tokens_in=resp.tokens_in, tokens_out=resp.tokens_out)
        return resp

    def _failures(self) -> int:
        """Models in a backup chain that failed before one answered (or all failed)."""
        failed = getattr(self.inner, "last_failed", None) or []
        for name, err in failed:
            self.usage.record(name, self.price(name).get("provider", ""), 0, 0,
                              agent=self.agent, ok=False, error=err)
        return len(failed)

    def tool_result_message(self, results):
        return self.inner.tool_result_message(results)

    def health(self):
        return self.inner.health()
