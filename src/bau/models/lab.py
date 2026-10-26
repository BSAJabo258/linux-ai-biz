"""The model lab: one fixed test for every model, measured on this computer.

``bau models lab MODEL`` runs ``data/model_lab.yaml`` against a model that is already
running: questions with known answers, tool calls checked against their schemas (name,
required arguments, types, allowed values, nothing extra), JSON replies, longer and longer
prompts, and, only with ``--run-code``, two small coding fixes checked by running their
tests. It measures time to the first word and words per second (llama-server's own
``timings``), the model server's peak memory (``VmHWM`` in /proc) and the card's peak
memory (``nvidia-smi``, sampled while it runs). Each result is stored with the suite's
fingerprint and the model file's SHA-256, so ``bau models compare A B`` compares like with
like (a compressed file against a bigger one, or two models).

The lab never approves anything and never swaps the working model: the owner reads the
result and decides (``bau set-status``). Model replies are only graded, never followed.
Code a model writes runs only with ``--run-code``: a single function, checked first for
imports and dangerous names, in a separate Python with no environment, no writable files,
and limits on time and memory.
"""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from ..home import shipped_data
from .providers import Provider, ProviderError, ToolSpec

SUITE = "model_lab.yaml"
FORBIDDEN = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars",
             "getattr", "setattr", "delattr", "input", "breakpoint", "exit", "quit"}
WORDS_PER_TOKEN = 0.75


def suite(path: Path | None = None) -> tuple[dict[str, Any], str]:
    raw = (path or shipped_data() / SUITE).read_bytes()
    return yaml.safe_load(raw), hashlib.sha256(raw).hexdigest()[:16]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().strip("*`").strip()


# ---------------------------------------------------------------- graders
def check_args(spec: dict[str, Any], args: dict[str, Any]) -> list[str]:
    """What is wrong with a tool call's arguments against its JSON schema (subset)."""
    props, problems = spec.get("properties", {}), []
    for k in spec.get("required", []):
        if k not in args:
            problems.append(f"missing {k}")
    for k, v in args.items():
        p = props.get(k)
        if p is None:
            if spec.get("additionalProperties") is False:
                problems.append(f"unknown argument {k}")
            continue
        want = p.get("type")
        ok = {"string": isinstance(v, str), "integer": isinstance(v, int) and not
              isinstance(v, bool), "number": isinstance(v, int | float) and not
              isinstance(v, bool), "boolean": isinstance(v, bool)}.get(want, True)
        if not ok:
            problems.append(f"{k} should be {want}")
        if "enum" in p and v not in p["enum"]:
            problems.append(f"{k} must be one of {p['enum']}")
    return problems


def _json(text: str) -> Any:
    m = re.search(r"\{.*\}", text or "", re.S)
    return json.loads(m.group(0)) if m else None


def safe_function(code: str, name: str) -> str | None:
    """None if the code is one plain function called ``name``; otherwise why not."""
    code = re.sub(r"^```\w*\n|```\s*$", "", code.strip(), flags=re.M)
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"not valid Python ({e.msg})"
    defs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(tree.body) != 1 or not defs or defs[0].name != name:
        return f"the reply must be exactly one function called {name}"
    for n in ast.walk(tree):
        if isinstance(n, ast.Import | ast.ImportFrom | ast.Global | ast.Nonlocal |
                      ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef):
            return f"{type(n).__name__} is not allowed"
        if isinstance(n, ast.Name) and n.id in FORBIDDEN:
            return f"{n.id} is not allowed"
        if isinstance(n, ast.Attribute) and n.attr.startswith("_"):
            return f"attribute {n.attr} is not allowed"
    return None


# Set inside the child before the model's code (preexec_fn is not safe while the Peaks
# thread runs). Ours, not the model's: the model's code itself may not import anything.
LIMITS = ("import resource\n"
          "for _r, _n in ((resource.RLIMIT_CPU, 5), (resource.RLIMIT_AS, 512 << 20),\n"
          "               (resource.RLIMIT_FSIZE, 0), (resource.RLIMIT_NOFILE, 16)):\n"
          "    resource.setrlimit(_r, (_n, _n))\n"
          "del resource, _r, _n\n")


def run_function(code: str, test: str) -> tuple[bool, str]:
    code = re.sub(r"^```\w*\n|```\s*$", "", code.strip(), flags=re.M)
    with tempfile.TemporaryDirectory() as d:
        try:
            p = subprocess.run([sys.executable, "-I", "-S", "-c",
                                LIMITS + code + "\n\n" + test],
                               cwd=d, env={}, capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            return False, "took too long"
    if p.returncode == 0:
        return True, "tests pass"
    last = (p.stderr or "").strip().splitlines()[-1:]
    return False, last[0][:200] if last else f"stopped (signal {-p.returncode})" \
        if p.returncode < 0 else f"failed ({p.returncode})"


# ---------------------------------------------------------------- watching memory
class Peaks:
    """The card's peak memory while the lab runs (nvidia-smi every half second)."""

    def __init__(self, run: Callable[..., Any] = subprocess.run):
        self.run, self.vram, self._stop = run, None, threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _sample(self) -> None:
        try:
            p = self.run(["nvidia-smi", "--query-gpu=memory.used",
                          "--format=csv,noheader,nounits"], capture_output=True, text=True,
                         timeout=5)
            used = max(int(float(x)) for x in p.stdout.split()) << 20
            self.vram = max(self.vram or 0, used)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass

    def _loop(self) -> None:
        while not self._stop.wait(0.5):
            self._sample()

    def __enter__(self) -> Peaks:
        self._sample()
        self._t.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._stop.set()
        self._t.join(timeout=2)


def server_peak_ram(proc: Path = Path("/proc"), name: str = "llama-server") -> int | None:
    """Highest memory the model server has used since it started (VmHWM), in bytes."""
    best = None
    for st in proc.glob("[0-9]*/status"):
        try:
            text = st.read_text()
        except OSError:
            continue
        if not re.search(rf"^Name:\s+{re.escape(name[:15])}\s*$", text, re.M):
            continue
        m = re.search(r"^VmHWM:\s+(\d+) kB", text, re.M)
        if m:
            best = max(best or 0, int(m.group(1)) * 1024)
    return best


# ---------------------------------------------------------------- the run
class Lab:
    def __init__(self, provider: Provider, rec: dict[str, Any],
                 suite_path: Path | None = None, run_code: bool = False,
                 long_context: bool = True):
        self.p, self.rec, self.run_code, self.long = provider, rec, run_code, long_context
        self.s, self.fingerprint = suite(suite_path)
        self.timings: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def _ask(self, system: str, text: str, tools: list[ToolSpec] | None = None,
             max_tokens: int = 400) -> Any:
        try:
            r = self.p.complete(system, [{"role": "user", "content": text}], tools,
                                max_tokens=max_tokens)
        except (ProviderError, OSError, ValueError) as e:
            self.errors.append(f"{type(e).__name__}: {str(e)[:150]}")
            return None
        t = getattr(self.p, "last_timings", None)
        if t:
            self.timings.append(t)
        return r

    def reasoning(self) -> list[dict[str, Any]]:
        out = []
        for c in self.s["reasoning"]:
            r = self._ask("Answer exactly as asked, with nothing else.", c["ask"])
            got = _clean(r.text) if r else None
            out.append({"ask": c["ask"], "got": got, "ok": bool(got) and bool(
                re.search(c["answer"], got, re.I))})
        return out

    def tools(self) -> list[dict[str, Any]]:
        specs = {t["name"]: t for t in self.s["tools"]["specs"]}
        offered = [ToolSpec(t["name"], t["description"], t["parameters"])
                   for t in specs.values()]
        out = []
        for c in self.s["tools"]["cases"]:
            r = self._ask("Use a tool when one fits the request; otherwise just answer.",
                          c["ask"], offered)
            if r is None:
                out.append({"ask": c["ask"], "ok": False, "why": "no reply"})
                continue
            calls = r.tool_calls
            if c["tool"] is None:
                out.append({"ask": c["ask"], "ok": not calls,
                            "why": "called a tool that does not fit" if calls else ""})
                continue
            if len(calls) != 1 or calls[0].name != c["tool"]:
                out.append({"ask": c["ask"], "ok": False, "why": "wrong or no tool: "
                            + ", ".join(x.name for x in calls)})
                continue
            args = calls[0].input
            problems = check_args(specs[c["tool"]]["parameters"], args)
            problems += [f"{k} is {args.get(k)!r}" for k, pat in c["args"].items()
                         if not re.search(pat, str(args.get(k, "")))]
            out.append({"ask": c["ask"], "ok": not problems, "args": args,
                        "why": "; ".join(problems)})
        return out

    def structured(self) -> list[dict[str, Any]]:
        out = []
        for c in self.s["structured"]:
            r = self._ask("You reply with JSON only.", c["ask"])
            try:
                data = _json(r.text) if r else None
            except ValueError:
                data = None
            ok = isinstance(data, dict) and all(
                re.search(v, str(data.get(k, ""))) if isinstance(v, str) else data.get(k) == v
                for k, v in c["expect"].items())
            out.append({"ask": c["ask"], "ok": ok, "got": data})
        return out

    def coding(self) -> list[dict[str, Any]]:
        out = []
        for c in self.s["coding"]:
            r = self._ask("You write correct, plain Python.", c["ask"], max_tokens=800)
            code = (r.text if r else "") or ""
            why = safe_function(code, c["name"])
            if why:
                out.append({"name": c["name"], "ok": False, "why": why})
                continue
            ok, said = run_function(code, c["test"])
            out.append({"name": c["name"], "ok": ok, "why": said})
        return out

    def long_context(self) -> list[dict[str, Any]]:
        cfg, ctx = self.s["long_context"], int(self.rec.get("context") or 8192)
        out = []
        for n in cfg["lengths"]:
            if n + 512 > ctx:
                out.append({"tokens": n, "ok": None, "why": f"over this model's {ctx} context"})
                continue
            words = int(n * WORDS_PER_TOKEN)
            filler = [f"Note {i}: the weather on day {i} was calm and dry." for i in
                      range(words // 10)]
            filler.insert(len(filler) // 2, cfg["needle"])
            r = self._ask("Answer exactly as asked.", " ".join(filler) + "\n\n" + cfg["ask"],
                          max_tokens=20)
            got = _clean(r.text) if r else None
            t = self.timings[-1] if r and self.timings else {}
            out.append({"tokens": n, "ok": bool(got) and bool(re.search(cfg["answer"], got)),
                        "got": got, "prompt_ms": t.get("prompt_ms")})
            if r is None:
                break                         # out of memory or too slow: stop here
        return out

    def run(self, peaks_run: Callable[..., Any] | None = None,
            proc: Path = Path("/proc")) -> dict[str, Any]:
        # A server that is not up would score zero everywhere (seen 2026-10-26): refuse,
        # and nothing is saved, as with the benchmark.
        health = getattr(self.p, "health", None)
        if health is not None and not health().get("ok"):
            raise ProviderError("the model server is not answering: start it (sudo bau "
                                "models use MODEL), wait for it to load, then run the lab")
        started = dt.datetime.now(dt.UTC)
        with Peaks(peaks_run or subprocess.run) as pk:
            parts = {"reasoning": self.reasoning(), "tools": self.tools(),
                     "structured": self.structured()}
            if self.run_code:
                parts["coding"] = self.coding()
            if self.long:
                parts["long_context"] = self.long_context()
        scores = {}
        for k, rows in parts.items():
            tried = [r for r in rows if r.get("ok") is not None]
            scores[k] = round(sum(1 for r in tried if r["ok"]) / len(tried), 2) if tried \
                else None
        bar = self.s["bar"]
        short = [k for k, v in scores.items() if v is not None and v < bar.get(k, 0)]
        if len(self.errors) > bar.get("errors", 0):
            short.append("errors")
        gen = [t for t in self.timings if t.get("predicted_n")]
        first = [t["prompt_ms"] + t["predicted_ms"] / t["predicted_n"] for t in gen
                 if t.get("prompt_ms") is not None and t.get("predicted_ms")]
        speed = [t["predicted_per_second"] for t in gen if t.get("predicted_per_second")]
        return {
            "model": self.rec.get("model_id"), "at": started.isoformat(timespec="seconds"),
            "seconds": round((dt.datetime.now(dt.UTC) - started).total_seconds(), 1),
            "suite": self.fingerprint, "file_sha256": (self.rec.get("download") or {})
            .get("sha256"), "context": self.rec.get("context"), "ran_code": self.run_code,
            "scores": scores, "errors": self.errors,
            "meets_bar": not short, "short_of_bar": short,
            "time_to_first_word_ms": round(sorted(first)[len(first) // 2]) if first else None,
            "words_per_second": round(sorted(speed)[len(speed) // 2], 1) if speed else None,
            "peak_card_memory": pk.vram, "peak_server_memory": server_peak_ram(proc),
            "details": parts,
        }


# ---------------------------------------------------------------- storing and comparing
def save(result: dict[str, Any], home: Path) -> Path:
    d = home / "models" / "lab" / str(result["model"])
    d.mkdir(parents=True, exist_ok=True)
    p = d / (result["at"].replace(":", "") + ".json")
    p.write_text(json.dumps(result, indent=1, default=str))
    return p


def latest(model_id: str, home: Path) -> dict[str, Any] | None:
    files = sorted((home / "models" / "lab" / model_id).glob("*.json"))
    return json.loads(files[-1].read_text()) if files else None


def compare(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """B against A (for compression: A is the bigger file, the baseline)."""
    def same_rows(part: str) -> list[dict[str, Any]]:
        ra, rb = a["details"].get(part) or [], b["details"].get(part) or []
        return [{"case": x.get("ask") or x.get("name") or x.get("tokens"),
                 a["model"]: x.get("ok"), b["model"]: y.get("ok")}
                for x, y in zip(ra, rb, strict=False) if x.get("ok") != y.get("ok")]
    parts = sorted(set(a["scores"]) | set(b["scores"]))
    return {
        "baseline": a["model"], "candidate": b["model"],
        "same_suite": a.get("suite") == b.get("suite"),
        "scores": {k: {a["model"]: a["scores"].get(k), b["model"]: b["scores"].get(k)}
                   for k in parts},
        "speed": {m["model"]: {"words_per_second": m.get("words_per_second"),
                               "time_to_first_word_ms": m.get("time_to_first_word_ms"),
                               "peak_card_memory": m.get("peak_card_memory"),
                               "peak_server_memory": m.get("peak_server_memory")}
                  for m in (a, b)},
        "answers_that_differ": {k: same_rows(k) for k in parts if same_rows(k)},
    }


def record(model_id: str, actor: str, home: Path | None = None, audit: Any = None,
           run_code: bool = False, long_context: bool = True,
           provider: Provider | None = None) -> dict[str, Any]:
    """Run the lab on a registered model, store the result, put its summary on the record.
    Never approves (the owner's ``bau set-status``)."""
    from ..audit import AuditLog
    from ..home import bau_home
    from ..registry import CapabilityRegistry
    from .providers import build
    home = home or bau_home()
    reg = CapabilityRegistry(home / "registry" / "capabilities.yaml")
    rec = reg.data["model"].get(model_id)
    if rec is None:
        raise KeyError(f"model {model_id} not registered")
    res = Lab(provider or build(rec), rec, run_code=run_code, long_context=long_context).run()
    path = save(res, home)
    fresh = CapabilityRegistry(reg.path)       # only our result is ours to write
    if model_id in fresh.data["model"]:
        fresh.data["model"][model_id]["lab"] = {
            k: res[k] for k in ("at", "suite", "scores", "meets_bar", "short_of_bar",
                                "words_per_second", "time_to_first_word_ms",
                                "peak_card_memory", "peak_server_memory")}
        fresh.save()
    (audit or AuditLog(home / "audit" / "chain.jsonl")).append(
        "model.lab", actor, {"model": model_id, "scores": res["scores"],
                             "meets_bar": res["meets_bar"], "file": str(path)})
    return {**res, "saved": str(path)}
