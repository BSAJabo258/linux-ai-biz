import datetime as dt
import json

import pytest
import yaml
from conftest import ON

from bau import network
from bau.audit import AuditLog
from bau.economics import Budgets, Ledger
from bau.gateway import CallRequest, Gateway, GatewayDenied, Handler
from bau.governor import Governor, hold_reason, parse_verdict
from bau.jarvis import Jarvis
from bau.jobs import JobStore
from bau.models.providers import ScriptedProvider
from bau.security.permissions import CapabilityTable


def gov(home, **kw):
    kw.setdefault("systemctl", "")
    kw.setdefault("online", True)
    return Governor(home, audit=AuditLog(home / "audit" / "chain.jsonl", key=b""), **kw)


def test_hold_blocks_everything_but_read_only(tmp_path):
    g = gov(tmp_path)
    gw = Gateway(table=CapabilityTable(), audit=AuditLog(tmp_path / "a.jsonl", key=b""),
                 ledger=Ledger(tmp_path), budgets=Budgets(),
                 trust=lambda: network.Trust.TRUSTED, hold=lambda: hold_reason(tmp_path))
    gw.register("memory.search", Handler(lambda query: [query], "READ_ONLY"))
    gw.register("artifact.write_draft", Handler(lambda: "ok", "LOW_RISK"))
    g.hold("test")
    assert gw.invoke(CallRequest("agent:x", "memory.search", {"query": "q"})) == ["q"]
    with pytest.raises(GatewayDenied) as e:
        gw.invoke(CallRequest("agent:x", "artifact.write_draft"))
    assert e.value.step == "governor_hold"
    with pytest.raises(PermissionError):
        g.release("agent:x")                      # the AI side cannot lift a hold
    g.release("human:owner")
    assert gw.invoke(CallRequest("agent:x", "artifact.write_draft")) == "ok"


def test_hold_stops_jarvis(tmp_path, active_engine):
    from test_commerce_disclosure import GOOD_OFFER

    from bau.commerce.subscriptions import offer_facts
    j = Jarvis(active_engine, home=tmp_path)
    m = j.plan("Launch", "launch_subscription",
               {"subscription": offer_facts(GOOD_OFFER, "US", "CA", ON)}, on=ON)
    assert m.status == "READY"
    gov(tmp_path).hold("spend")
    with pytest.raises(PermissionError, match="HOLD"):
        j.run(m, lambda mm: {"status": "COMPLETED"})


def test_tick_repairs_stuck_jobs_and_resumes_once_per_limit(tmp_path):
    store = JobStore(tmp_path)
    job = store.create("m1", "write a draft", "agent:writer", ["agent_loop"])
    job.status = "RUNNING"
    store.checkpoint(job)
    raw = json.loads((store.dir / f"{job.job_id}.json").read_text())
    raw["updated_at"] = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)).isoformat()
    (store.dir / f"{job.job_id}.json").write_text(json.dumps(raw))
    calls = []

    def fail(j):
        calls.append(j.job_id)
        return False

    g = gov(tmp_path)
    rep = g.tick(executor=fail)
    assert store.load(job.job_id).status == "INTERRUPTED"
    assert any(f["remedy"] == "marked INTERRUPTED for resume" for f in rep["new"])
    for _ in range(4):
        g.tick(executor=fail)
    assert len(calls) == 3                        # max_auto_resumes, then the owner decides
    assert any("auto-resume stopped" in f["detail"] for f in g.digest()["needs_you"])
    # A live job (fresh checkpoint) is never touched, and network waits are re-queued.
    live = store.create("m3", "live", "agent:writer", ["s"], status="RUNNING")
    waiting = store.create("m4", "net", "agent:writer", ["s"], status="WAITING_FOR_NETWORK",
                           needs_network=True)
    g.tick(executor=lambda j: None)
    assert store.load(live.job_id).status == "RUNNING"
    assert store.load(waiting.job_id).status == "INTERRUPTED"
    # Unknown job types are left alone, not counted as failures.
    other = store.create("m2", "x", "factory:y", ["s"], status="INTERRUPTED")
    g.tick(executor=lambda j: None if j.job_id == other.job_id else False)
    assert other.job_id not in g._state()["resumes"]


def test_tick_quarantines_misbehaving_agent(tmp_path):
    reg = tmp_path / "registry" / "capabilities.yaml"
    reg.parent.mkdir(parents=True)
    rec = {"agent_id": "agent:x", "version": "1", "purpose": "p", "model": "m",
           "permissions": [], "budget_usd_per_day": 1, "network_scope": "none",
           "tools": [], "approval_policy": "human", "risk_level": "LOW", "status": "ACTIVE"}
    reg.write_text(yaml.safe_dump({"agent": {"agent:x": rec}}))
    audit = AuditLog(tmp_path / "audit" / "chain.jsonl", key=b"")
    for _ in range(5):
        audit.append("gateway.denied", "agent:x", {"capability": "publish.video",
                                                   "step": "permission", "reason": "no"})
    rep = gov(tmp_path).tick()
    assert yaml.safe_load(reg.read_text())["agent"]["agent:x"]["status"] == "QUARANTINED"
    assert any(f["check"] == "agents" for f in rep["new"])


def test_tick_spend_and_audit_tamper_put_bau_on_hold(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "governor.yaml").write_text("daily_spend_hold_usd: 1.0\n")
    Ledger(tmp_path).cost("api", 2.5, agent="agent:x")
    g = gov(tmp_path)
    rep = g.tick()
    assert rep["hold"] and "spend" in rep["hold"]
    assert len(g.tick()["new"]) == 0              # same problem is not re-reported
    g.release("human:owner")
    (tmp_path / "config" / "governor.yaml").write_text("daily_spend_hold_usd: 100\n")
    chain = tmp_path / "audit" / "chain.jsonl"
    lines = chain.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["actor"] = "someone-else"
    lines[0] = json.dumps(rec)
    chain.write_text("\n".join(lines) + "\n")
    rep = gov(tmp_path).tick()
    assert rep["hold"] == "audit chain failed verification"


def test_validator_model_reviews_finished_missions(tmp_path, active_engine):
    from test_commerce_disclosure import GOOD_OFFER

    from bau.commerce.subscriptions import offer_facts
    j = Jarvis(active_engine, home=tmp_path)
    for _ in range(2):
        m = j.plan("Launch", "launch_subscription",
                   {"subscription": offer_facts(GOOD_OFFER, "US", "CA", ON)}, on=ON)
        j.run(m, lambda mm: {"status": "COMPLETED", "summary": "fully compliant!"})
    prov = ScriptedProvider(['{"verdict": "OK", "reason": "fine"}',
                             '{"verdict": "CONCERN", "reason": "claims compliance"}'])
    g = gov(tmp_path, reviewer=prov)
    rep = g.tick()
    concerns = [f for f in rep["new"] if f["check"] == "validator"]
    assert len(concerns) == 1 and "claims compliance" in concerns[0]["detail"]
    assert "<untrusted_data" in prov.calls[0]["messages"][0]["content"]
    g.tick()
    assert len(prov.calls) == 2                   # each mission is reviewed once


def test_parse_verdict_fails_closed():
    assert parse_verdict('{"verdict": "OK", "reason": "x"}') == ("OK", "x")
    assert parse_verdict("looks fine to me")[0] == "CONCERN"
    assert parse_verdict('{"verdict": "APPROVE"}')[0] == "CONCERN"


def test_findings_close_requires_human(tmp_path):
    g = gov(tmp_path)
    g.hold("x")
    with pytest.raises(PermissionError):
        g.close("fnd_1", "agent:x")
    g.close("fnd_1", "human:owner", "dealt with")
