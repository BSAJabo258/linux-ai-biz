"""Usage meter: every model call counted (free ones too), tokens and dollars per model,
daily limits only the owner sets, busy replies and rate-limit signals, GitHub's wait.
Written before the code it tests."""

import io
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from bau.assistant import Assistant, Voice
from bau.audit import AuditLog
from bau.economics import Ledger
from bau.models.providers import (
    FallbackProvider,
    LocalHTTPProvider,
    ProviderError,
    ScriptedProvider,
)
from bau.usage import Usage

FREE = {"id": "free-model", "provider": "zai", "cost_in_per_mtok": 0, "cost_out_per_mtok": 0}


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    return tmp_path


def make(home, provider, model=FREE):
    return Assistant(home, provider, model, "human:owner",
                     AuditLog(home / "audit" / "chain.jsonl", key=b""))


def test_every_model_call_is_counted_even_free_ones(home):
    a = make(home, ScriptedProvider(["hello", "again"]))
    a.ask("hi")
    a.ask("hi again")
    s = Usage(home).summary()
    assert s["today"]["calls"] == 2 and s["today"]["tokens"] == 30
    assert s["today"]["usd"] == 0 and s["week"]["calls"] == 2
    m = s["by_model"][0]
    assert (m["model"], m["provider"], m["tokens_in"], m["tokens_out"]) == (
        "free-model", "zai", 20, 10)


def test_paid_calls_reach_the_ledger_exactly_once(home):
    paid = {"id": "paid", "provider": "anthropic", "cost_in_per_mtok": 1_000_000,
            "cost_out_per_mtok": 0}
    make(home, ScriptedProvider(["hello"]), paid).ask("hi")
    assert Ledger(home).spent(agent="jarvis") == pytest.approx(10.0)
    assert Usage(home).summary()["today"]["usd"] == pytest.approx(10.0)


class Busy:
    model = "first"

    def complete(self, *a, **kw):
        raise ProviderError("https://api.z.ai is busy (HTTP 429): overloaded")


def test_backups_show_which_model_answered_and_which_was_busy(home):
    chain = FallbackProvider([Busy(), ScriptedProvider(["hi"])], ["first", "second"])
    make(home, chain, {**FREE, "id": "first", "fallbacks": ["second"]}).ask("hello")
    by = {m["model"]: m for m in Usage(home).summary()["by_model"]}
    assert by["second"]["calls"] == 1 and by["second"]["errors"] == 0
    assert by["first"]["errors"] == 1 and "429" in by["first"]["last_error"]
    assert by["first"]["busy"] == 1


def test_daily_limits_are_the_owners_and_stop_jarvis_politely(home):
    u = Usage(home)
    with pytest.raises(PermissionError):
        u.set_limits(daily_tokens=20, daily_usd=None, by="agent:jarvis")
    u.set_limits(daily_tokens=20, daily_usd=None, by="human:owner")
    prov = ScriptedProvider(["one", "two", "three"])
    a = make(home, prov)
    a.ask("first")                                          # 15 tokens: 75 %
    assert Usage(home).summary()["warnings"] == []
    a.ask("second")                                         # 30 tokens: over
    s = Usage(home).summary()
    assert any("limit" in w for w in s["warnings"])
    calls = len(prov.calls)
    r = a.ask("third")
    assert len(prov.calls) == calls                         # the model was not called
    assert "limit" in r.text and "bau usage limits" in r.text
    events = [x["event"] for x in AuditLog(home / "audit" / "chain.jsonl").records()]
    assert "usage.limits_set" in events


def test_limits_warn_before_they_are_reached(home):
    Usage(home).set_limits(daily_tokens=None, daily_usd=1.0, by="human:owner")
    Usage(home).record("m", "p", 10, 5, usd=0.85)
    assert any("85%" in w for w in Usage(home).summary()["warnings"])


def test_rate_limit_headers_from_hosted_models_are_kept(home):
    class R(io.BytesIO):
        headers = {"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "20s",
                   "Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    body = {"model": "glm", "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
    p = LocalHTTPProvider(opener=lambda req, timeout: R(json.dumps(body).encode()))
    make(home, p, {**FREE, "id": "glm"}).ask("hello")
    s = Usage(home).summary()
    m = s["by_model"][0]
    assert m["limits"] == {"x-ratelimit-remaining-requests": "0",
                           "x-ratelimit-reset-requests": "20s"}
    assert any("glm" in w and "no requests left" in w for w in s["warnings"])


def test_github_wait_from_repo_scout_shows_in_the_meter(home):
    (home / "scout").mkdir()
    until = time.time() + 600
    (home / "scout" / "github-rate.json").write_text(json.dumps(
        {"search": {"blocked_until": until, "remaining": "0"}, "core": {"remaining": "41"}}))
    s = Usage(home).summary()
    assert s["github"]["search"]["remaining"] == "0" and s["github"]["search"]["waiting_until"]
    assert s["github"]["core"]["remaining"] == "41" and not s["github"]["core"]["waiting_until"]
    assert any("GitHub" in w for w in s["warnings"])


def test_old_calls_leave_today_but_stay_in_the_week(home):
    import datetime as dt
    u = Usage(home)
    u.record("m", "p", 100, 0, when=dt.datetime.now(dt.UTC) - dt.timedelta(days=2))
    u.record("m", "p", 1, 0)
    s = u.summary()
    assert s["today"]["tokens"] == 1 and s["week"]["tokens"] == 101


# ------------------------------------------------------------------ on screen and terminal

def test_usage_tool_node_endpoint_and_cli(home, capsys):
    from bau.cli import main
    from bau.overview import overview
    from bau.ui.jarvis_server import serve
    a = make(home, ScriptedProvider(["hi"]))
    a.ask("hello")
    assert "usage_today" in a.tools and a.tools["usage_today"].kind == "read"
    node = {n["id"]: n for n in overview(a)["nodes"]}["usage"]
    assert "15 tokens" in node["summary"]
    srv, _ = serve(a, Voice(home), 0, key="k123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/usage"
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(urllib.request.Request(url, headers={"X-Jarvis-Key": "no"}))
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"X-Jarvis-Key": "k123"})) as r:
            assert json.loads(r.read())["today"]["calls"] == 1
    finally:
        srv.shutdown()
    assert main(["usage"]) == 0
    assert json.loads(capsys.readouterr().out)["today"]["tokens"] == 15


def test_cli_limits_need_a_person_at_the_terminal(monkeypatch):
    from bau.cli import main
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["usage", "limits", "--daily-tokens", "100000"]) == 3


def test_page_has_a_usage_panel():
    from importlib import resources
    page = (resources.files("bau.ui") / "jarvis.html").read_text()
    assert 'n.id === "usage"' in page and "function renderUsage" in page
