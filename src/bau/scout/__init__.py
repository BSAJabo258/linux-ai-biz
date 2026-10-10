"""Repo Scout: find open-source projects for a capability, gather evidence, rank them.

Discovery is not installation. ``find`` only reads public metadata and READMEs; ``inspect``
downloads one repository into a quarantine folder and runs Sentinel's static scan (nothing
in it is executed); running its tests is the sandbox stage, after a signed approval.
Every run is recorded (``scout/runs.jsonl``) so later searches can be judged against what
earlier ones found, and every candidate keeps what it claims apart from what was checked.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from ..home import bau_home, shipped_data
from .evaluate import evaluate, readme_signals
from .github import GitHub, RateLimited, SourceError, normalise
from .plan import plan

NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
HEAVY = re.compile(r"(?im)^\s*[\"']?(torch|tensorflow|jax|onnxruntime-gpu|vllm|xformers|"
                   r"bitsandbytes|cupy|nvidia-[a-z0-9-]+|diffusers)\b")
KEEP = ("license", "security", "validation", "inspected", "business_value", "first_seen")


def config() -> dict[str, Any]:
    return yaml.safe_load((shipped_data() / "scout.yaml").read_text())


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class Scout:
    def __init__(self, home: Path | None = None, source: Any = None, audit: Any = None,
                 actor: str = "human:owner", cloner: Any = None):
        self.home = home or bau_home()
        self.dir = self.home / "scout"
        self.source = source or GitHub(state=self.dir / "github-rate.json")
        self.audit = audit
        self.actor = actor
        self.cloner = cloner or git_clone
        self.cfg = config()
        self.stopped: RateLimited | None = None

    # ---------------------------------------------------------------- storage
    @property
    def _cands_path(self) -> Path:
        return self.dir / "candidates.json"

    def candidates(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self._cands_path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, cands: dict[str, dict[str, Any]]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self._cands_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cands, indent=1, sort_keys=True))
        tmp.replace(self._cands_path)

    def runs(self) -> list[dict[str, Any]]:
        p = self.dir / "runs.jsonl"
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]

    def _record(self, kind: str, data: dict[str, Any]) -> None:
        if self.audit is not None:
            self.audit.append(kind, self.actor, data)

    # ---------------------------------------------------------------- discovery
    def find(self, request: str, max_queries: int = 8, per_query: int = 10,
             readmes: int = 5, provider: Any = None,
             progress: Any = None) -> dict[str, Any]:
        say = progress or (lambda text: None)    # live progress for the Jarvis screen
        p = plan(request, max_queries, provider)
        n = len(p.queries)
        store = self.candidates()
        found: dict[str, dict[str, Any]] = {}
        searches: list[dict[str, Any]] = []
        self.stopped = None                       # GitHub asked us to wait: send nothing more
        for i, q in enumerate(p.queries, 1):
            if self.stopped:
                searches.append({"q": q.q, "origin": q.origin,
                                 "skipped": f"waiting for GitHub until {self.stopped.when}"})
                say(f"Search {i} of {n}: '{q.q}' not sent (GitHub asked to wait)")
                continue
            try:
                items = self.source.search(q.q, per_query)
                searches.append({"q": q.q, "origin": q.origin, "found": len(items)})
                say(f"Search {i} of {n}: '{q.q}' found {len(items)}")
            except RateLimited as e:
                self.stopped = e
                searches.append({"q": q.q, "origin": q.origin, "error": str(e)})
                say(f"Search {i} of {n}: '{q.q}' failed: GitHub asked to wait")
                continue
            except SourceError as e:
                searches.append({"q": q.q, "origin": q.origin, "error": str(e)})
                say(f"Search {i} of {n}: '{q.q}' failed")
                continue
            for it in items:
                if not NAME.match(it["full_name"]):
                    continue
                key = it["full_name"].lower()
                c = found.get(key) or self._new(it)
                c["queries"] = sorted(set(c["queries"]) | {q.q})
                found[key] = c
        notes = self._dedupe(found)
        for c in found.values():
            old = store.get(c["id"])
            if old:
                for k in KEEP:
                    if k in old:
                        c[k] = old[k] if k != "license" else {**c[k], **{
                            x: old[k][x] for x in ("detected", "review") if x in old[k]}}
                c["queries"] = sorted(set(c["queries"]) | set(old.get("queries", [])))
            c["keywords"] = p.keywords
            evaluate(c, p.keywords, self.cfg)
        ranked = rank(found.values())
        if ranked[:readmes]:
            say("Reading the leaders' READMEs")
        for c in ranked[:readmes]:              # README claims for the leaders only
            if c.get("duplicate_of") or c["claimed"].get("readme"):
                continue
            if self.stopped:
                notes.append(f"README of {c['full_name']} not read: waiting for GitHub")
                continue
            try:
                c["claimed"]["readme"] = readme_signals(self.source.readme(c["full_name"]))
            except RateLimited as e:
                self.stopped = e
                notes.append(f"README of {c['full_name']} not read: {e}")
            except SourceError as e:
                notes.append(f"README of {c['full_name']} not read: {e}")
            evaluate(c, p.keywords, self.cfg)
        ranked = rank(found.values())
        say(f"Ranked {len(found)} candidate(s)")
        store.update(found)
        self._save(store)
        failed = [s for s in searches if "error" in s]
        run = {"id": "sc_" + secrets.token_hex(4), "at": _now(), "request": request,
               "plan": p.public(), "source": getattr(self.source, "name", "?"),
               "searches": searches, "failed_searches": len(failed),
               "skipped_searches": sum(1 for s in searches if "skipped" in s),
               "rate_limited_until": (dt.datetime.fromtimestamp(self.stopped.until, dt.UTC)
                                      .isoformat(timespec="seconds") if self.stopped else None),
               "found": len(found), "notes": notes,
               "ranked": [{"id": c["id"], "score": c["score"],
                           "coverage": c["evidence_coverage"], "decision": c["decision"]}
                          for c in ranked if not c.get("duplicate_of")][:15]}
        self.dir.mkdir(parents=True, exist_ok=True)
        with (self.dir / "runs.jsonl").open("a") as fh:
            fh.write(json.dumps(run, sort_keys=True) + "\n")
        self._record("scout.run", {"run": run["id"], "queries": len(searches),
                                   "failed": len(failed), "found": len(found)})
        return run

    def add(self, full_name: str, keywords: list[str] | None = None,
            origin: str = "owner") -> dict[str, Any]:
        """Make one named repository a candidate (for example a toolbox entry), from its
        GitHub record. One request; nothing is downloaded or run."""
        if not NAME.match(full_name) or {".", ".."} & set(full_name.split("/")):
            raise ValueError("give the repository as OWNER/NAME")
        it = normalise(self.source.repo(full_name))
        if not NAME.match(it["full_name"]):
            raise SourceError(f"GitHub returned no repository for {full_name}")
        store = self.candidates()
        old = store.get(it["full_name"].lower())
        c = self._new(it)
        if old:
            for k in KEEP:
                if k in old:
                    c[k] = old[k]
            c["queries"] = old.get("queries", [])
        c["origin"] = origin
        c["upstream"] = it["full_name"] if not it["fork"] else (old or {}).get("upstream")
        c["keywords"] = list(keywords or [])
        evaluate(c, c["keywords"], self.cfg)
        store[c["id"]] = c
        self._save(store)
        self._record("scout.added", {"repo": c["full_name"], "origin": origin})
        return c

    def _new(self, it: dict[str, Any]) -> dict[str, Any]:
        return {"id": it["full_name"].lower(), "full_name": it["full_name"],
                "url": it["url"], "upstream": None, "first_seen": _now(),
                "last_reviewed_at": _now(), "queries": [],
                "claimed": {"description": it["description"], "topics": it["topics"],
                            "homepage": it["homepage"], "readme": None},
                "metadata": {k: it[k] for k in ("language", "fork", "archived", "pushed_at",
                                                "stars", "size_kb")},
                "license": {"declared": it["license_spdx"], "source": "GitHub metadata"},
                "security": {"status": "not reviewed"},
                "validation": {"status": "not tested"}}

    def _dedupe(self, found: dict[str, dict[str, Any]], lookups: int = 5) -> list[str]:
        """Forks point at their upstream; a fork whose upstream is in the results is a
        duplicate of it. Lookups are capped: each one is a request against the limit."""
        notes = []
        for c in [c for c in found.values() if c["metadata"]["fork"]][:lookups]:
            if self.stopped:
                notes.append(f"upstream of fork {c['full_name']} not looked up: "
                             "waiting for GitHub")
                continue
            try:
                up = self.source.upstream(c["full_name"])
            except RateLimited as e:
                self.stopped = e
                notes.append(f"upstream of fork {c['full_name']} unknown: {e}")
                continue
            except SourceError as e:
                notes.append(f"upstream of fork {c['full_name']} unknown: {e}")
                continue
            c["upstream"] = up
            if up and up.lower() in found:
                c["duplicate_of"] = up.lower()
        for c in found.values():
            if c["metadata"]["fork"] and not c["upstream"]:
                c["upstream"] = None                     # unknown, not "itself"
            elif not c["metadata"]["fork"]:
                c["upstream"] = c["full_name"]
        return notes

    # ---------------------------------------------------------------- inspection
    def inspect(self, full_name: str) -> dict[str, Any]:
        """Download one repository into quarantine and scan it statically (Sentinel).
        Nothing from it is installed or run."""
        from ..security.sentinel import scan
        if not NAME.match(full_name) or {".", ".."} & set(full_name.split("/")):
            raise ValueError("give the repository as OWNER/NAME")
        store = self.candidates()
        c = store.get(full_name.lower())
        if c is None:
            raise KeyError(f"{full_name} is not a candidate yet: bau scout find first")
        size = c["metadata"].get("size_kb")
        if size is None or size > self.cfg["max_inspect_kb"]:
            raise ValueError(f"{full_name} is {size} KB; inspect takes up to "
                             f"{self.cfg['max_inspect_kb']} KB")
        dest = self.dir / "quarantine" / full_name.replace("/", "__")
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        commit = self.cloner(f"https://github.com/{c['full_name']}.git", dest)
        rep = scan(dest, commit)
        deps = []
        for f in ("requirements.txt", "pyproject.toml", "setup.cfg", "environment.yml",
                  "package.json"):
            p = dest / f
            if p.is_file():
                deps += [m.lower() for m in HEAVY.findall(p.read_text(errors="replace")[:200000])]
        c["inspected"] = {"commit": commit, "at": _now(), "verdict": rep.verdict,
                          "reasons": rep.reasons,
                          "install_hooks": [h["file"] + ": " + h["hook"]
                                            for h in rep.install_hooks][:10],
                          "risky_code": rep.risky_code[:20], "secrets": len(rep.secrets),
                          "surfaces": rep.surfaces,
                          "heavy_dependencies": sorted(set(deps))}
        c["license"]["detected"] = (rep.license["detected"][0]
                                    if len(rep.license["detected"]) == 1 else None)
        c["license"]["files"] = rep.license["files"]
        c["security"] = {"status": rep.verdict, "by": "Sentinel static scan",
                         "at": _now(), "commit": commit}
        c["last_reviewed_at"] = _now()
        evaluate(c, c.get("keywords", []), self.cfg)
        store[c["id"]] = c
        self._save(store)
        self._record("scout.inspected", {"repo": c["full_name"], "commit": commit,
                                         "verdict": rep.verdict})
        return c


def rank(cands: Any) -> list[dict[str, Any]]:
    order = {"eligible": 0, "needs review": 1, "rejected": 2}
    return sorted(cands, key=lambda c: (bool(c.get("duplicate_of")), order[c["decision"]],
                                        -c["score"], -c["evidence_coverage"]))


def git_clone(url: str, dest: Path, timeout: int = 180) -> str:
    """Shallow clone with nothing from the repository allowed to run: no hooks, no LFS
    filters, no submodules, no credential prompts, no inherited secrets."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(dest.parent),
           "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1",
           "GIT_CONFIG_NOSYSTEM": "1"}
    for k in ("HTTPS_PROXY", "https_proxy", "SSL_CERT_FILE", "GIT_SSL_CAINFO"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    base = ["git", "-c", "core.hooksPath=/dev/null", "-c", "filter.lfs.smudge=",
            "-c", "filter.lfs.process=", "-c", "filter.lfs.required=false",
            "-c", "protocol.allow=never", "-c", "protocol.https.allow=always"]
    subprocess.run(base + ["clone", "--depth", "1", "--single-branch", "--no-tags",
                           "--quiet", url, str(dest)], env=env, check=True,
                   timeout=timeout, capture_output=True)
    out = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], env=env,
                         check=True, capture_output=True, text=True, timeout=30)
    return out.stdout.strip()


def report(sc: Scout, run_id: str | None = None, top: int = 10) -> str:
    """A plain-words Markdown report of one run (the latest by default)."""
    runs = sc.runs()
    run = next((r for r in runs if r["id"] == run_id), None) if run_id else (
        runs[-1] if runs else None)
    if run is None:
        raise KeyError("no such scout run" if run_id else "no scout runs yet")
    cands = sc.candidates()
    out = [f"# Repo Scout: {run['request']}", "",
           f"Run {run['id']} at {run['at']} on {run['source']}. {run['found']} repositories "
           f"found by {len(run['searches'])} searches"
           + (f"; **{run['failed_searches']} search(es) failed**" if run["failed_searches"]
              else "")
           + (f"; **GitHub asked BAU to wait until {run['rate_limited_until']}, so "
              f"{run.get('skipped_searches', 0)} search(es) were not sent**"
              if run.get("rate_limited_until") else "") + ".", "",
           "Nothing here was installed or run. Scores use only facts that exist; "
           "*coverage* is how much of the scoring had evidence at all.", "",
           "## Searches", "", "| Search | Why | Result |", "|---|---|---|"]
    for s in run["searches"]:
        out.append(f"| {s['q']} | {s['origin']} | "
                   + (f"FAILED: {s['error']}" if "error" in s else
                      f"NOT SENT: {s['skipped']}" if "skipped" in s else f"{s['found']} found")
                   + " |")
    out += ["", "## Ranked candidates", ""]
    for i, r in enumerate(run["ranked"][:top], 1):
        c = cands.get(r["id"])
        if c is None:
            continue
        lic = c["license"]
        why = [f"found by {len(c['queries'])} search(es)",
               f"licence {lic.get('detected') or lic.get('declared') or 'unknown'} "
               f"({lic['status']})",
               f"maintenance {c['maintenance'] or 'unknown'}"]
        if c.get("integration_method"):
            why.append(f"likely {c['integration_method']}")
        out += [f"### {i}. [{c['full_name']}]({c['url']}) - {c['decision'].upper()}", "",
                f"{c['claimed']['description'] or '(no description)'}", "",
                f"Score {c['score']} / 100, evidence coverage {c['evidence_coverage']}%. "
                + "; ".join(why) + ".", ""]
        if c["blockers"]:
            out.append("- **Blocked:** " + "; ".join(c["blockers"]))
        if c["needs"]:
            out.append("- **Before it could be used:** " + "; ".join(c["needs"]))
        if c["unknowns"]:
            out.append("- **Unknown (not scored):** " + ", ".join(
                u.replace("_", " ") for u in c["unknowns"]))
        res = c.get("resources")
        if res and res["gpu_or_large_model"]:
            out.append(f"- **Heavy:** needs a GPU or a large model ({res['from']})")
        if c.get("duplicate_of"):
            out.append(f"- Fork of {c['duplicate_of']}")
        out.append("")
    if run["notes"]:
        out += ["## Notes", ""] + [f"- {n}" for n in run["notes"]] + [""]
    out += ["## What is not verified", "",
            "- Descriptions, topics and README lines are the projects' own claims.",
            "- Licences are as declared to GitHub until `bau scout inspect` reads the files,"
            " and need a human legal review before commercial use.",
            "- Security is unknown until `bau scout inspect` (Sentinel static scan); "
            "behaviour is unknown until tested in the sandbox.",
            "- Business value is the owner's judgement and is never guessed.", ""]
    return "\n".join(out)
