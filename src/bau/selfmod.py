"""Jarvis's self-modification lab: he may propose and test changes to his own code.

This is not sentience and it does not make him autonomous over his own source. It gives him
a safe loop with the owner in the loop:

  read/search   only the repository's own source, tests and docs
  propose       writes a full copy in BAU_HOME/selflab, never in the repository
  test          runs pytest only in that copy, with a fixed command and a time limit
  diff          shows the owner exactly what would change
  apply         only the owner's Accept, only after the tests pass, and only if the
                repository has not changed underneath the proposal

There is no shell, no pip, no git push, no service restart and no secret files. Applying
writes the working tree; the owner still installs and restarts the live service. Every
step is in the audit chain.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .home import atomic_write_json

ALLOWED_DIRS = ("src/bau", "tests", "docs")
ALLOWED_SUFFIXES = {".py", ".html", ".css", ".js", ".md", ".yaml", ".yml", ".json", ".txt"}
BLOCKED = re.compile(r"(^|/)(\.env|\.git|\.ssh|keys?|secrets?|credentials?|tokens?|"
                     r"passwords?|approval[_-]?key)(/|\.|$)", re.I)
# The owner's rule (2026-11-11): Jarvis may fix his own code, but the files that keep him
# safe are never his to change. He may read them; a change to one is refused.
PROTECTED = frozenset({
    "src/bau/selfmod.py",              # this lab and its limits
    "src/bau/gateway.py", "src/bau/governor.py", "src/bau/policy.py", "src/bau/blast.py",
    "src/bau/audit.py", "src/bau/keys.py", "src/bau/wipe_gate.py", "src/bau/localonly.py",
    "src/bau/network.py", "src/bau/sandbox.py", "src/bau/disclosure.py", "src/bau/claims.py",
    "src/bau/sanctions.py", "src/bau/money.py", "src/bau/autopilot.py",  # its Go/Vote/Ask lanes
    # the tool menu and confirm cards, the CLI's human checks, the runtime, agent folder
    # approval, the workstation's manager rule, missions, MCP pins and the updater
    "src/bau/assistant.py", "src/bau/jarvis.py", "src/bau/cli.py", "src/bau/cli_ext.py",
    "src/bau/runtime.py", "src/bau/agentfolders.py", "src/bau/workstation.py",
    "src/bau/executive.py", "src/bau/mcp.py", "src/bau/catalog.py", "src/bau/update.py",
    "src/bau/home.py",
    "tests/conftest.py",
})
PROTECTED_DIRS = ("src/bau/security/", "src/bau/privacy/", "src/bau/data/policies/",
                  "src/bau/data/regulations/", "src/bau/ui/", "src/bau/models/")
NEW_TEST = re.compile(r"tests/test_[A-Za-z0-9_]+\.py$")
MAX_FILE = 200_000
MAX_TOTAL = 1_000_000
MAX_FILES = 12
MAX_READ = 20_000
MAX_DIFF = 24_000
MAX_OUTPUT = 20_000
TEST_TIMEOUT = 600
IGNORE = shutil.ignore_patterns(".git", ".venv", "venv", "node_modules", "__pycache__",
                                ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache",
                                "artifacts", "build", "dist", "*.iso", "*.img",
                                "*.sandbox-work", ".env", ".env.*", "*.env", "*.key",
                                "*.pem", "secrets", ".ssh")


class SelfModError(ValueError):
    pass


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _plain(raw: str) -> bool:
    """One spelling per file: no '.', '..' or empty segments (``src/bau/./gateway.py`` and
    ``src//bau/gateway.py`` would otherwise slip past the protected list)."""
    return bool(raw) and "\x00" not in raw and \
        all(seg not in ("", ".", "..") for seg in raw.split("/"))


def _safe_dir(rel: str) -> str:
    raw = str(rel or "").strip().replace("\\", "/").strip("/")
    if not raw or raw.startswith("/") or not _plain(raw):
        raise SelfModError("path must stay inside this repository")
    if BLOCKED.search(raw):
        raise SelfModError("key, secret and approval files are never read here")
    if not any(raw == d or raw.startswith(d + "/") for d in ALLOWED_DIRS):
        raise SelfModError(f"only {', '.join(ALLOWED_DIRS)} may be searched")
    return raw


def _safe(rel: str) -> str:
    """A repository-relative path under the three directories Jarvis may touch."""
    raw = str(rel or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or not _plain(raw):
        raise SelfModError("path must stay inside this repository")
    if BLOCKED.search(raw):
        raise SelfModError("key, secret and approval files are never touched")
    if not raw.startswith(tuple(d + "/" for d in ALLOWED_DIRS)):
        raise SelfModError(f"only {', '.join(ALLOWED_DIRS)} may be changed")
    if Path(raw).suffix not in ALLOWED_SUFFIXES:
        raise SelfModError(f"file type {Path(raw).suffix or '(none)'} is not edited here")
    return raw


def _changeable(rel: str) -> str:
    """A path the lab may write: _safe, and not one of the owner's protected safety files."""
    raw = _safe(rel)
    if raw in PROTECTED or raw.startswith(PROTECTED_DIRS):
        raise SelfModError(f"{raw} is a protected safety file: only the owner changes it")
    return raw


class SelfLab:
    def __init__(self, root: Path | None = None, home: Path | None = None,
                 audit: AuditLog | None = None,
                 runner: Callable[[Path, list[str], int],
                                  subprocess.CompletedProcess] | None = None):
        from .home import bau_home
        self.root = (root or Path(__file__).resolve().parents[2]).resolve()
        self.home = (home or bau_home()) / "selflab"
        self.audit = audit or AuditLog((home or bau_home()) / "audit" / "chain.jsonl")
        self.runner = runner or self._run

    # ---------------------------------------------------------------- files and proposals
    def _proposal_dir(self, pid: str) -> Path:
        if not re.fullmatch(r"sm_[0-9a-f]{8}", pid or ""):
            raise SelfModError("unknown proposal id")
        return self.home / pid

    def _load(self, pid: str) -> dict[str, Any]:
        try:
            return json.loads((self._proposal_dir(pid) / "proposal.json").read_text())
        except (OSError, ValueError) as e:
            raise SelfModError(f"unknown proposal {pid}") from e

    def _copy(self, work: Path) -> None:
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(self.root, work, ignore=IGNORE, symlinks=True)

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def status(self) -> dict[str, Any]:
        head, branch = "", ""
        try:
            head = (self.root / ".git" / "HEAD").read_text().strip()
            if head.startswith("ref: "):
                ref = head[5:]
                branch = ref.rsplit("/", 1)[-1]
                head = (self.root / ".git" / ref).read_text().strip()
        except OSError:
            pass
        last = []
        if self.home.is_dir():
            for d in sorted(self.home.glob("sm_*")):
                try:
                    p = json.loads((d / "proposal.json").read_text())
                    last.append({"proposal": d.name, "reason": p.get("reason", ""),
                                 "tested": bool(p.get("tested")),
                                 "applied": bool(p.get("applied"))})
                except (OSError, ValueError):
                    continue
        return {"root": str(self.root), "branch": branch, "head": head[:12],
                "proposals": last[-8:], "how": "read, propose, test, diff, then the owner applies"}

    def read(self, path: str, offset: int = 1, limit: int = 400) -> dict[str, Any]:
        rel = _safe(path)
        f = (self.root / rel).resolve()
        if self.root not in f.parents or not f.is_file():
            raise SelfModError(f"no file {rel}")
        if f.stat().st_size > MAX_FILE:
            raise SelfModError(f"{rel} is too large to read here")
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(offset))
        end = min(len(lines), start + max(1, min(int(limit), 1000)) - 1)
        return {"path": rel, "start": start, "end": end, "lines": len(lines),
                "text": "\n".join(lines[start - 1:end])[:MAX_READ]}

    def search(self, query: str, path: str = "src/bau") -> dict[str, Any]:
        if not query.strip() or len(query) > 200:
            raise SelfModError("give a short search term")
        base = _safe_dir(path)
        base_dir = (self.root / base).resolve()
        if base_dir != self.root and self.root not in base_dir.parents:
            raise SelfModError("path must stay inside this repository")
        try:
            pattern = re.compile(query, re.I)
        except re.error as e:
            raise SelfModError(f"bad pattern: {e}") from e
        hits, files = [], 0
        if not base_dir.is_dir():
            raise SelfModError(f"no directory {base}")
        for p in sorted(base_dir.rglob("*")):
            if files >= 5000 or len(hits) >= 80:
                break
            rel = p.relative_to(self.root).as_posix()
            real = p.resolve()
            if not p.is_file() or self.root not in real.parents or BLOCKED.search(rel) \
                    or p.suffix not in ALLOWED_SUFFIXES:
                continue
            files += 1
            try:
                if p.stat().st_size > MAX_FILE:
                    continue
                for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                    if pattern.search(line):
                        hits.append({"path": rel, "line": n, "text": line.strip()[:240]})
                        if len(hits) >= 80:
                            break
            except OSError:
                continue
        return {"query": query, "files": files, "hits": hits}

    def propose(self, files: dict[str, str], reason: str,
                proposal: str = "") -> dict[str, Any]:
        if not isinstance(files, dict) or not files:
            raise SelfModError("give at least one file and its full new text")
        if len(files) > MAX_FILES:
            raise SelfModError(f"at most {MAX_FILES} files in one proposal")
        if not reason.strip() or len(reason) > 500:
            raise SelfModError("say why this change is needed")
        clean: dict[str, str] = {}
        total = 0
        for path, text in files.items():
            rel = _changeable(str(path))
            real = (self.root / rel).resolve()
            if real != self.root.resolve() / rel:
                raise SelfModError(f"{rel}: goes through a link; not edited here")
            if not isinstance(text, str) or not text.strip():
                raise SelfModError(f"{rel}: give the full file text")
            if rel.startswith("tests/"):
                if (self.root / rel).exists():
                    raise SelfModError(f"{rel}: existing tests are not rewritten by Jarvis; "
                                       "add a new test file or let the owner edit it")
                if not NEW_TEST.fullmatch(rel):
                    raise SelfModError(f"{rel}: new tests must be tests/test_*.py")
            if "\x00" in text:
                raise SelfModError(f"{rel}: binary text is not edited here")
            total += len(text.encode())
            if len(text.encode()) > MAX_FILE or total > MAX_TOTAL:
                raise SelfModError("the proposal is too large")
            clean[rel] = text

        pd = self._proposal_dir(proposal) if proposal else \
            self.home / ("sm_" + secrets.token_hex(4))
        old = {}
        if (pd / "proposal.json").exists():
            old = self._load(pd.name)
            if old.get("cards"):
                raise SelfModError(f"{pd.name} is already on the owner's screen and cannot "
                                   "change; propose under a new id")
        pd.mkdir(parents=True, exist_ok=True)
        work = pd / "work"
        self._copy(work)
        base: dict[str, dict[str, str | None]] = {}
        for rel, text in clean.items():
            src = self.root / rel
            before = src.read_text(encoding="utf-8", errors="replace") if src.exists() else None
            base[rel] = {"sha": _sha(before) if before is not None else None}
            self._write(work / rel, text)
        rec = {"proposal": pd.name, "reason": reason, "files": clean, "base": base,
               "tested": False, "test": None, "applied": False,
               "created_at": datetime.now(UTC).isoformat(timespec="seconds")}
        rec["previous_proposals"] = old.get("previous_proposals", []) + (
            [old["proposal"]] if old and old.get("proposal") != pd.name else [])
        atomic_write_json(pd / "proposal.json", rec)
        self.audit.append("selfmod.proposed", "jarvis", {
            "proposal": pd.name, "reason": reason[:300], "files": sorted(clean)})
        return {"proposal": pd.name, "files": sorted(clean),
                "next": "run self_test, then self_diff; only the owner can apply"}

    # ---------------------------------------------------------------- tests and diff
    def _run(self, work: Path, cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
        """Jarvis's proposed code runs here, so it runs in bubblewrap: no network, no home
        folder, no BAU data, no /etc/bau; only the copy (as /work) and a read-only Python."""
        bwrap = shutil.which("bwrap")
        if not bwrap:
            return subprocess.CompletedProcess(cmd, 126, "", (
                "not run: the tests need the bubblewrap sandbox. Install it once with "
                "`sudo apt install bubblewrap`."))
        prefix = Path(sys.prefix).resolve()
        box = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
               "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
               "--setenv", "LANG", "C.UTF-8", "--setenv", "HOME", "/tmp",
               "--setenv", "TMPDIR", "/tmp", "--setenv", "BAU_HOME", "/tmp/bau",
               "--setenv", "PYTHONPATH", "/work/src", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
               "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
               "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
               "--ro-bind-try", "/etc/ld.so.cache", "/etc/ld.so.cache",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
        if not str(prefix).startswith("/usr/"):
            box += ["--ro-bind", str(prefix), str(prefix)]
        box += ["--bind", str(work), "/work", "--chdir", "/work"]
        return subprocess.run(box + cmd, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)

    def shown(self, proposal: str, kind: str) -> dict[str, Any]:
        """A card for this proposal is going on the owner's screen: from now on its files
        are frozen, and what runs or is applied is exactly what the card showed."""
        rec = self._load(proposal)
        d = self.diff(proposal)
        if d["cut"]:
            raise SelfModError("this change is too large to show in full on one card; split "
                               "it into smaller proposals")
        sha = _sha(json.dumps(rec["files"], sort_keys=True))
        rec.setdefault("cards", {})[kind] = sha
        atomic_write_json(self._proposal_dir(proposal) / "proposal.json", rec)
        return d

    def check_shown(self, proposal: str, kind: str) -> None:
        rec = self._load(proposal)
        if (rec.get("cards") or {}).get(kind) != _sha(json.dumps(rec["files"], sort_keys=True)):
            raise SelfModError("the change is not the one on your card; ask Jarvis to show "
                               "it again")

    def test(self, proposal: str, tests: list[str] | None = None) -> dict[str, Any]:
        rec = self._load(proposal)
        targets = []
        for t in tests or ["tests"]:
            rel = _safe_dir(str(t).strip())
            if rel != "tests" and not rel.startswith("tests/"):
                raise SelfModError(f"{rel}: tests must be under tests/")
            targets.append(rel)
        cmd = [sys.executable, "-m", "pytest", "-q", *targets]
        try:
            r = self.runner(self._proposal_dir(proposal) / "work", cmd, TEST_TIMEOUT)
            code, out = r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            code, out = 124, f"tests ran past {TEST_TIMEOUT} seconds"
        except OSError as e:
            code, out = 127, str(e)
        rec["tested"] = code == 0
        rec["test"] = {"command": cmd, "exit": code, "output": out[-MAX_OUTPUT:]}
        atomic_write_json(self._proposal_dir(proposal) / "proposal.json", rec)
        self.audit.append("selfmod.tested", "jarvis", {"proposal": proposal, "exit": code})
        return {"proposal": proposal, "passed": code == 0, "exit": code,
                "output": out[-6000:],
                "next": "self_diff, then ask the owner to apply" if code == 0 else
                        "fix the files and propose again"}

    def diff(self, proposal: str) -> dict[str, Any]:
        rec = self._load(proposal)
        chunks = []
        for rel, text in rec["files"].items():
            src = self.root / rel
            before = src.read_text(encoding="utf-8", errors="replace").splitlines(True) \
                if src.exists() else []
            chunks.extend(difflib.unified_diff(before, text.splitlines(True),
                                               fromfile=f"a/{rel}", tofile=f"b/{rel}"))
        diff = "".join(chunks)
        return {"proposal": proposal, "files": sorted(rec["files"]),
                "diff": diff[:MAX_DIFF], "cut": max(0, len(diff) - MAX_DIFF),
                "tested": bool(rec.get("tested"))}

    def card(self, proposal: str) -> dict[str, Any]:
        rec = self._load(proposal)
        if not rec.get("tested"):
            raise SelfModError("the tests have not passed yet; run self_test first")
        d = self.shown(proposal, "apply")
        lines = sum(1 for ln in d["diff"].splitlines()
                    if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---")))
        return {"summary": f"Apply {proposal} to my own code? {len(d['files'])} file(s), "
                           f"{lines} changed lines; tests passed.\n\n{d['diff']}"}

    def apply(self, proposal: str, by: str) -> dict[str, Any]:
        if not str(by).startswith("human:"):
            raise PermissionError("only the owner applies a self-modification")
        rec = self._load(proposal)
        if rec.get("applied"):
            raise SelfModError("this proposal was already applied")
        if not rec.get("tested") or (rec.get("test") or {}).get("exit") != 0:
            raise SelfModError("the tests have not passed; nothing is applied")
        for rel in rec["files"]:      # the record on disk is re-checked, not trusted
            _changeable(rel)
        self.check_shown(proposal, "apply")
        for rel, meta in rec["base"].items():
            src = self.root / rel
            now = src.read_text(encoding="utf-8", errors="replace") if src.exists() else None
            if (_sha(now) if now is not None else None) != meta["sha"]:
                raise SelfModError(f"{rel} changed while the proposal waited; propose again")
        for rel, text in rec["files"].items():
            self._write(self.root / rel, text)
        rec["applied"] = True
        rec["applied_by"] = by
        atomic_write_json(self._proposal_dir(proposal) / "proposal.json", rec)
        self.audit.append("selfmod.applied", by, {"proposal": proposal,
                                                   "files": sorted(rec["files"])})
        return {"proposal": proposal, "applied": sorted(rec["files"]),
                "next": "install the changed package and restart Jarvis; code changes are "
                        "not live yet"}
