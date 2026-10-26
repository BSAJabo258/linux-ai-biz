"""The model lab: fixed questions with known answers, tool calls checked against their
schemas, JSON, long prompts, gated code runs, speed and memory, stored and compared."""

import re

import pytest

from bau.models import lab
from bau.models.providers import ModelResponse, ProviderError, ToolCall

RIGHT = {"pens": "8", "Wednesday": "Saturday", "shortest": "Bob", "17 times": "391",
         "train": "17:15", "channel": "7", "Sort": "3, 7, 19, 42", "bloops": "yes",
         "15 percent": "36", "221": "no"}
CODE = {"average": "def average(xs):\n    return sum(xs) / len(xs) if xs else 0.0\n",
        "is_palindrome": "```python\ndef is_palindrome(s):\n    t = s.replace(' ', '')"
                         ".lower()\n    return t == t[::-1]\n```"}


class Fake:
    """Answers the suite right (or wrong where told), like llama-server, with timings."""

    def __init__(self, wrong=(), bad_args=False, fail_long_over=None, evil_code=False):
        self.wrong, self.bad_args, self.fail_long_over = set(wrong), bad_args, fail_long_over
        self.evil_code, self.last_timings = evil_code, None

    def complete(self, system, messages, tools=None, max_tokens=400):
        q = messages[0]["content"]
        self.last_timings = {"prompt_ms": 50.0, "predicted_ms": 200.0, "predicted_n": 10,
                             "predicted_per_second": 50.0}
        if "secret code" in q:
            if self.fail_long_over and len(q.split()) > self.fail_long_over:
                raise ProviderError("the model server ran out of memory")
            return self._say("7419")
        if tools:
            return self._tool(q)
        if "JSON" in q:
            return self._say('Here: {"title": "Moon Song", "minutes": 12}')
        for name, code in CODE.items():
            if name in q:
                return self._say("import os\n" + code if self.evil_code else code)
        for key, ans in RIGHT.items():
            if key in q:
                return self._say("wrong" if key in self.wrong else ans)
        return self._say("?")

    def _tool(self, q):
        if "weather" in q:
            args = {"city": "Paris", "unit": "celsius" if self.bad_args else "c"}
            return ModelResponse("", [ToolCall("1", "get_weather", args)], "tool_use", "f")
        if "Add" in q:
            return ModelResponse("", [ToolCall("1", "add_numbers", {"a": 1234, "b": 5678})],
                                 "tool_use", "f")
        if "files" in q:
            return ModelResponse("", [ToolCall("1", "search_files",
                                               {"pattern": "*.mp4", "folder": "videos"})],
                                 "tool_use", "f")
        return self._say("Hello there friend")

    @staticmethod
    def _say(t):
        return ModelResponse(t, [], "end_turn", "fake", 5, 10)


REC = {"model_id": "fake-9b", "context": 16384,
       "download": {"sha256": "ab" * 32}}


def _run(provider, **kw):
    return lab.Lab(provider, REC, **kw).run(peaks_run=lambda *a, **k: (_ for _ in ()).throw(
        FileNotFoundError("nvidia-smi")))


def test_a_good_model_meets_the_bar_and_carries_its_fingerprint():
    r = _run(Fake(), run_code=True)
    assert r["scores"] == {"reasoning": 1.0, "tools": 1.0, "structured": 1.0, "coding": 1.0,
                           "long_context": 1.0}
    assert r["meets_bar"] and r["errors"] == []
    assert re.fullmatch(r"[0-9a-f]{16}", r["suite"]) and r["file_sha256"] == "ab" * 32
    assert r["words_per_second"] == 50.0 and r["time_to_first_word_ms"] == 70
    # 32K does not fit a 16K context: skipped, not failed.
    assert [x["ok"] for x in r["details"]["long_context"]] == [True, True, None, None]


def test_wrong_answers_and_bad_tool_arguments_are_caught():
    r = _run(Fake(wrong={"pens", "train", "221", "Sort"}, bad_args=True))
    assert r["scores"]["reasoning"] == 0.6 and r["scores"]["tools"] == 0.75
    weather = r["details"]["tools"][0]
    assert not weather["ok"] and "unit must be one of" in weather["why"]
    assert not r["meets_bar"] and r["short_of_bar"] == ["reasoning"]


def test_running_out_of_memory_on_a_long_prompt_is_recorded_and_stops_the_ladder():
    r = _run(Fake(fail_long_over=3000))
    ladder = r["details"]["long_context"]
    assert ladder[0]["ok"] is True and ladder[1]["ok"] is False and len(ladder) == 2
    assert r["errors"] and "out of memory" in r["errors"][0]
    assert "errors" in r["short_of_bar"]


def test_code_runs_only_when_asked_and_only_a_plain_function():
    assert "coding" not in _run(Fake())["scores"]
    r = _run(Fake(evil_code=True), run_code=True)
    assert [c["ok"] for c in r["details"]["coding"]] == [False, False]
    assert "exactly one function" in r["details"]["coding"][0]["why"]


@pytest.mark.parametrize("code", [
    "import os\ndef f(x):\n    return x",
    "def f(x):\n    return open('/etc/passwd').read()",
    "def f(x):\n    return x.__class__",
    "def f(x):\n    return x\nprint('also this')",
    "def g(x):\n    return x",
])
def test_unsafe_or_wrong_shaped_code_is_refused_before_it_runs(code):
    assert lab.safe_function(code, "f")


def test_the_locked_down_run_stops_runaway_code():
    # Code reaching here has passed safe_function (no open, imports or dunders); the
    # limits catch what is left: endless loops and memory bombs.
    assert lab.run_function("def f():\n    while True:\n        pass", "f()")[0] is False
    assert lab.run_function("def f():\n    return bytearray(1 << 30)", "f()")[0] is False
    assert lab.run_function("def f():\n    return 1", "assert f() == 1") == (True, "tests pass")


def test_schema_checks():
    spec = {"type": "object", "properties": {"a": {"type": "number"}},
            "required": ["a"], "additionalProperties": False}
    assert lab.check_args(spec, {"a": 1}) == []
    assert lab.check_args(spec, {}) == ["missing a"]
    assert lab.check_args(spec, {"a": "1", "z": 2}) == ["a should be number",
                                                        "unknown argument z"]
    assert lab.check_args(spec, {"a": True}) == ["a should be number"]


def test_peak_server_memory_is_read_from_proc(tmp_path):
    for pid, name, kb in (("10", "llama-server", 6_000_000), ("11", "bash", 9_000_000)):
        (tmp_path / pid).mkdir()
        (tmp_path / pid / "status").write_text(f"Name:\t{name}\nVmHWM:\t{kb} kB\n")
    assert lab.server_peak_ram(tmp_path) == 6_000_000 * 1024


def test_card_peak_is_sampled():
    import subprocess
    used = iter(["410\n", "9800\n"] + ["9000\n"] * 50)
    fake = lambda *a, **k: subprocess.CompletedProcess(a, 0, next(used), "")  # noqa: E731
    with lab.Peaks(fake) as p:
        p._sample()
    assert p.vram == 9800 << 20


def test_compare_shows_what_compression_cost():
    big, small = _run(Fake()), _run(Fake(wrong={"221"}, bad_args=True))
    big["model"], small["model"] = "q4", "q2"
    c = lab.compare(big, small)
    assert c["same_suite"] and c["scores"]["reasoning"] == {"q4": 1.0, "q2": 0.9}
    assert [d["case"] for d in c["answers_that_differ"]["reasoning"]] == [
        "Is 221 a prime number? Answer yes or no."]


def test_record_stores_the_result_and_never_approves(tmp_path):
    from bau.audit import AuditLog
    from bau.registry import CapabilityRegistry
    from bau.runtime import seed_registry
    seed_registry(tmp_path)
    res = lab.record("qwen3.5-9b", "human:owner", home=tmp_path,
                     audit=AuditLog(tmp_path / "a.jsonl"), long_context=False,
                     provider=Fake())
    rec = CapabilityRegistry(tmp_path / "registry" / "capabilities.yaml").data["model"][
        "qwen3.5-9b"]
    assert rec["lab"]["meets_bar"] is True and rec["status"] == "REGISTERED"
    assert lab.latest("qwen3.5-9b", tmp_path)["scores"] == res["scores"]


def _models_args(cmd, model):
    import argparse
    return argparse.Namespace(models_cmd=cmd, model=model)


def test_use_needs_root_and_a_downloaded_local_model(tmp_path, monkeypatch, capsys):
    from bau import cli_ext
    from bau.runtime import seed_registry
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    seed_registry(tmp_path)
    assert cli_ext.cmd_models(_models_args("use", "claude-opus-5-5")) != 0
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    with pytest.raises(SystemExit, match="sudo"):
        cli_ext.cmd_models(_models_args("use", "qwen3.8-27b-q2"))
    monkeypatch.setattr("os.geteuid", lambda: 0)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    started = []
    monkeypatch.setattr("bau.pack._start", lambda *a: started.append(a) or True)
    assert cli_ext.cmd_models(_models_args("use", "qwen3.8-27b-q2")) != 0
    assert "not downloaded yet" in capsys.readouterr().err and not started
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "Qwen3.8-27B-UD-Q2_K_XL.gguf").write_bytes(b"x")
    assert cli_ext.cmd_models(_models_args("use", "qwen3.8-27b-q2")) == 0
    assert started and started[0][0] == "qwen3.8-27b-q2"


def test_the_candidates_are_pinned_and_not_approved():
    import yaml

    from bau.home import shipped_data
    reg = yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text())["model"]
    for mid, size in (("qwen3.8-27b-q2", 9_828_981_664), ("qwen3.8-27b-iq3", 10_934_860_704)):
        rec = reg[mid]
        assert rec["status"] == "REGISTERED" and rec["license"] == "Apache-2.0"
        assert rec["download"]["size"] == size and len(rec["download"]["sha256"]) == 64
        assert rec["chat_template_kwargs"] == {"enable_thinking": False}


def test_a_server_that_is_not_up_is_refused_and_nothing_is_saved(tmp_path):
    from bau.runtime import seed_registry
    seed_registry(tmp_path)

    class Down(Fake):
        def health(self):
            return {"ok": False, "error": "Connection refused"}
    with pytest.raises(ProviderError, match="not answering"):
        lab.record("qwen3.5-9b", "human:owner", home=tmp_path, provider=Down())
    assert lab.latest("qwen3.5-9b", tmp_path) is None
