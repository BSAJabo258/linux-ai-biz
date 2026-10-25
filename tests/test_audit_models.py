"""Holes found by the code audit of 2026-10-25 (models, money, data), each written as a
failing test first."""

import io
import json

import pytest
import yaml

from bau.models.providers import (
    FallbackProvider,
    LocalHTTPProvider,
    OpenAICompatProvider,
    ProviderError,
    ScriptedProvider,
)


class Resp(io.BytesIO):
    headers: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(payload):
    return lambda req, timeout=0: Resp(json.dumps(payload).encode())


BAD_ARGS = {"choices": [{"message": {"content": "", "tool_calls": [
    {"id": "c1", "function": {"name": "web_search", "arguments": '{"query": "x", '}}]}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3}}


# ------------------------------------------------------------------ malformed model replies
def test_a_broken_tool_call_lets_the_backup_model_answer():
    first = OpenAICompatProvider("https://a.example", "m1", "k", "/v1/chat/completions",
                                 opener=opener_for(BAD_ARGS))
    backup = ScriptedProvider(["backup answered"])
    out = FallbackProvider([first, backup], ["m1", "m2"]).complete(
        "s", [{"role": "user", "content": "q"}])
    assert out.text == "backup answered"


@pytest.mark.parametrize("payload", [
    {"choices": [{"message": {"tool_calls": [
        {"id": "c", "function": {"name": "t", "arguments": "[1,2]"}}]}}]},   # not an object
    {"error": {"message": "context too long"}}])                                 # no choices
def test_a_malformed_reply_is_a_provider_error_not_a_crash(payload):
    with pytest.raises(ProviderError):
        LocalHTTPProvider(opener=opener_for(payload)).complete(
            "s", [{"role": "user", "content": "q"}])


# ------------------------------------------------------------------ routing
def test_a_model_whose_last_benchmark_failed_is_not_routed(tmp_path):
    from bau.runtime import provider_for, seed_registry
    seed_registry(tmp_path)
    path = tmp_path / "registry" / "capabilities.yaml"
    d = yaml.safe_load(path.read_text())
    d["model"]["qwen3.5-4b"].update(status="APPROVED",
                                    benchmark={"reply_ok": False, "tool_calls": False})
    path.write_text(yaml.safe_dump(d))
    with pytest.raises(Exception, match="benchmark"):
        provider_for("qwen3.5-4b", tmp_path)


# ------------------------------------------------------------------ a cut-off line
def test_a_cut_off_log_line_does_not_stop_metered_calls(tmp_path):
    from bau.audit import AuditLog
    from bau.usage import Metered, Usage
    u = Usage(tmp_path, AuditLog(tmp_path / "a.jsonl", key=b""))
    u.set_limits(100000, None, by="human:owner")
    u.record("m", "p", 10, 5)
    with u.log.path.open("a") as fh:
        fh.write('{"ts": "2026-10-25T10:0')                 # power cut mid-append
    m = Metered(ScriptedProvider(["hi"]), u, lambda mid: {}, "m")
    assert m.complete("s", [{"role": "user", "content": "x"}]).text == "hi"
    u.record("m", "p", 1, 1)                                  # next line starts fresh
    assert len(list(u.log)) == 3


def test_a_cut_off_audit_tail_does_not_stop_the_chain(tmp_path):
    from bau.audit import AuditLog
    a = AuditLog(tmp_path / "chain.jsonl", key=b"k")
    a.append("x", "human:owner", {})
    with a.path.open("a") as fh:
        fh.write('{"seq": 1, "ha')
    rec = a.append("y", "human:owner", {})
    assert rec["seq"] == 1
    ok, why = a.verify()
    assert ok and "cut off" in why
    # Deleting a real record is still caught.
    lines = a.path.read_text().splitlines()
    a.path.write_text("\n".join(lines[1:]) + "\n")
    assert not a.verify()[0]


# ------------------------------------------------------------------ money reports
def test_the_1099_report_flags_a_payee_with_no_form_instead_of_crashing(tmp_path):
    from bau.accounting import Books
    b = Books(tmp_path)
    b.add_payee("ref:p1", "ref:x", "US", None, False)
    b.record(kind="payment", amount="2500", currency="USD", date="2026-03-01",
             counterparty_ref="ref:p1", description="work", evidence_ref="ev1")
    rows = b.info_returns(2026)
    assert rows and rows[0]["missing_tax_form"] is True


def test_one_clip_posted_to_two_platforms_is_paid_for_once(tmp_path):
    from bau.audit import AuditLog
    from bau.economics import Ledger
    from bau.results import Results
    Ledger(tmp_path).cost("api", 3.0, agent="studio", job_id="clip_aaa")
    r = Results(tmp_path, AuditLog(tmp_path / "a.jsonl", key=b""))
    r.videos = lambda: [
        {"platform": "youtube", "item_id": "y1", "video_id": "V1", "title": "t",
         "posted_at": "", "made_for_kids": False},
        {"platform": "tiktok", "item_id": "t1", "video_id": "T1", "title": "t",
         "posted_at": "", "made_for_kids": False}]
    for p, i in (("youtube", "y1"), ("tiktok", "t1")):
        r.links.append({"platform": p, "item_id": i, "clips": ["clip_aaa"], "episode": ""})
    assert r.report()["totals"]["cost_usd"] == 3.0


def test_a_download_killed_just_before_the_rename_finishes_next_time(tmp_path):
    import hashlib
    import urllib.error

    from bau.models.fetch import fetch
    data = b"x" * 1000
    (tmp_path / "m.gguf.part").write_bytes(data)

    def opener(req, timeout=0):                    # servers answer 416 for bytes=1000-
        raise urllib.error.HTTPError(req.full_url, 416, "Range Not Satisfiable", {},
                                     io.BytesIO(b""))
    rec = {"model_id": "m", "download": {"url": "https://h/m.gguf", "file": "m.gguf",
           "size": 1000, "sha256": hashlib.sha256(data).hexdigest()}}
    assert fetch(rec, tmp_path, opener=opener).read_bytes() == data


# ------------------------------------------------------------------ the registry
def test_a_benchmark_never_undoes_a_revoke_made_while_it_ran(tmp_path, monkeypatch):
    from bau.audit import AuditLog
    from bau.models import bench as B
    from bau.runtime import seed_registry
    seed_registry(tmp_path)
    path = tmp_path / "registry" / "capabilities.yaml"
    d = yaml.safe_load(path.read_text())
    d["model"]["qwen3.5-4b"].update(status="APPROVED",
                                    benchmark={"reply_ok": True, "tool_calls": True})
    path.write_text(yaml.safe_dump(d))

    def slow_bench(rec, provider=None):            # the owner revokes it meanwhile
        d2 = yaml.safe_load(path.read_text())
        d2["model"]["qwen3.5-4b"]["status"] = "REVOKED"
        path.write_text(yaml.safe_dump(d2))
        return {"reply_ok": True, "tool_calls": True}
    monkeypatch.setattr(B, "benchmark", slow_bench)
    monkeypatch.setattr("bau.assistant.load_env_file", lambda *a, **k: None)
    B.record("qwen3.5-4b", "human:owner", tmp_path, AuditLog(tmp_path / "a.jsonl", key=b""))
    rec = yaml.safe_load(path.read_text())["model"]["qwen3.5-4b"]
    assert rec["status"] == "REVOKED" and rec["benchmark"]["reply_ok"] is True
