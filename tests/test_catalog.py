"""Phase 2 of the universal automation upgrade: one tool catalog joined from the toolbox, Repo
Scout, the open-source watch and the registry, each record in one of twelve states set only by
evidence; and the MCP connector manager: health check with a time limit, the owner's pinned
tool list, refusal when a server's tools change, revoke."""

import json
import sys
from pathlib import Path

import pytest
import yaml

from bau import mcp
from bau.catalog import STATES, Catalog

SERVER = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"
REC = {"mcp_id": "fake", "version": "1", "source": "https://github.com/acme/fake-mcp",
       "license": "MIT", "tools": ["echo"], "permissions": ["read"], "network": False,
       "data_access": "none", "credentials": [], "risk": "low", "sandbox": "process",
       "status": "APPROVED", "command": [sys.executable, str(SERVER)],
       "read_only_tools": ["echo"]}


def cand(repo, **extra):
    c = {"id": repo.lower(), "full_name": repo, "url": f"https://github.com/{repo}",
         "origin": "search", "claimed": {"description": "a browser agent"},
         "license": {"declared": "MIT", "source": "GitHub metadata"},
         "security": {"status": "not reviewed"}, "validation": {"status": "not tested"}}
    c.update(extra)
    return c


def home_with(tmp_path, cands=(), mcp_recs=(), health=None):
    (tmp_path / "scout").mkdir()
    (tmp_path / "scout" / "candidates.json").write_text(
        json.dumps({c["id"]: c for c in cands}))
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "capabilities.yaml").write_text(
        yaml.safe_dump({"mcp": {r["mcp_id"]: r for r in mcp_recs}}))
    if health:
        (tmp_path / "mcp").mkdir()
        (tmp_path / "mcp" / "health.json").write_text(json.dumps(health))
    return Catalog(tmp_path)


INSPECTED = {"commit": "abc123", "at": "2026-11-11T00:00:00", "verdict": "ELIGIBLE_FOR_SANDBOX",
             "surfaces": {"mcp_server": True}}


def test_states_come_only_from_evidence(tmp_path):
    cat = home_with(tmp_path, cands=[
        cand("a/claims-only"),
        cand("b/inspected", inspected=dict(INSPECTED, verdict="QUARANTINE_FOR_REVIEW"),
             license={"declared": "MIT", "detected": "Apache-2.0", "status": "HUMAN_REVIEW"}),
        cand("c/licence-ok", inspected=dict(INSPECTED, verdict="QUARANTINE_FOR_REVIEW"),
             license={"detected": "MIT", "status": "COMMERCIAL_OK"}),
        cand("d/reviewed", inspected=INSPECTED,
             license={"detected": "MIT", "status": "COMMERCIAL_OK"}),
        cand("e/tested", inspected=INSPECTED, validation={"status": "passed"},
             license={"detected": "MIT", "status": "COMMERCIAL_OK"}),
        # A permissive licence claimed by GitHub but no download: still only discovered.
        cand("f/claims-mit", license={"declared": "MIT", "detected": "MIT",
                                      "status": "COMMERCIAL_OK"})])
    got = {r["id"]: r["state"] for r in cat.records()}
    assert got["a/claims-only"] == "DISCOVERED"
    assert got["b/inspected"] == "INSPECTED"
    assert got["c/licence-ok"] == "LICENSE_VERIFIED"
    assert got["d/reviewed"] == "SECURITY_REVIEWED"
    assert got["e/tested"] == "TESTED"
    assert got["f/claims-mit"] == "DISCOVERED"
    d = cat.show("d/reviewed")
    assert d["commit"] == "abc123" and d["runtime"].startswith("MCP server")
    # Nothing BAU recorded makes a tool installed or connected.
    assert not {"INSTALLED", "CONNECTED"} & set(got.values())
    assert len(STATES) == 12


def test_toolbox_watch_and_registry_join_one_record(tmp_path):
    rec = dict(REC, status="ACTIVE")
    cat = home_with(tmp_path, cands=[cand("acme/fake-mcp", inspected=INSPECTED,
                                          license={"detected": "MIT",
                                                   "status": "COMMERCIAL_OK"})],
                    mcp_recs=[rec, dict(REC, mcp_id="gone", source="local", status="REVOKED")],
                    health={"fake": {"at": "2026-11-11T01:00:00", "ok": True,
                                     "tools": ["echo"], "changed": False, "error": None}})
    r = cat.show("acme/fake-mcp")
    assert r["state"] == "ENABLED" and r["approval_status"] == "ACTIVE"
    assert r["health_check"]["ok"] is True and r["last_verified"] == "2026-11-11"
    assert any("registry" in p for p in r["provenance"])
    assert cat.show("gone")["state"] == "REVOKED"
    # The shipped toolbox is in it (claims), and llama.cpp runs in BAU.
    assert cat.show("ggml-org/llama.cpp")["state"] == "ENABLED"
    browser = cat.find("browser")
    assert browser and all(x["state"] for x in browser)
    assert cat.summary()["counts"]["ENABLED"] >= 2
    with pytest.raises(ValueError):
        cat.find(state="WORKS")


def test_revoked_wins_over_any_evidence(tmp_path):
    cat = home_with(tmp_path, cands=[cand("acme/fake-mcp", inspected=INSPECTED,
                                          validation={"status": "passed"},
                                          license={"detected": "MIT",
                                                   "status": "COMMERCIAL_OK"})],
                    mcp_recs=[dict(REC, status="REVOKED")])
    assert cat.show("acme/fake-mcp")["state"] == "REVOKED"
    assert STATES[-2:] == ("DISABLED", "REVOKED")    # the furthest state wins: these two last


def test_health_check_pin_and_changed_tools_refused(tmp_path):
    from bau.audit import AuditLog
    from bau.gateway import Gateway
    audit = AuditLog(tmp_path / "a.jsonl", key=b"")
    with pytest.raises(PermissionError):
        mcp.check(dict(REC, status="REGISTERED"), tmp_path)    # untested code: not started
    res = mcp.check(REC, tmp_path, audit=audit)
    assert res["ok"] and res["tools"] == ["delete_all", "echo", "unreviewed"]
    assert not res["changed"] and "bau mcp pin fake" in res["next"]
    assert mcp.health(tmp_path)["fake"]["schema_sha256"] == res["schema_sha256"]
    assert '"mcp.checked"' in (tmp_path / "a.jsonl").read_text()
    pinned = mcp.pin(REC, tmp_path, "human:owner")
    assert pinned["schema_sha256"] == res["schema_sha256"]
    # Same server: it attaches. A server whose tools changed: refused, nothing registered.
    client, specs = mcp.attach(Gateway(audit=audit), pinned)
    client.close()
    assert list(specs) == ["run.mcp__fake__echo"]
    changed = dict(pinned, env={"FAKE_MCP_EXTRA": "1"})
    g = Gateway(audit=audit)
    with pytest.raises(PermissionError, match="tools changed"):
        mcp.attach(g, changed)
    assert not any(c.startswith("run.mcp__") for c in g.table.levels)
    res = mcp.check(changed, tmp_path)
    assert res["ok"] and res["changed"] and "send_mail" in res["tools"]
    assert "will not start it" in res["next"]


def test_health_check_stops_a_server_that_does_not_answer(tmp_path):
    res = mcp.check(dict(REC, env={"FAKE_MCP_HANG": "1"}), tmp_path, timeout=1.5)
    assert not res["ok"] and "no answer within 1.5 s" in res["error"]
    with pytest.raises(ValueError, match="no good check"):
        mcp.pin(REC, tmp_path, "human:owner")


def test_cli_and_jarvis(tmp_path, monkeypatch, capsys):
    from bau.assistant import TOOL_NODE, Assistant
    from bau.audit import AuditLog
    from bau.cli import main
    home_with(tmp_path, mcp_recs=[REC])
    monkeypatch.setenv("BAU_HOME", str(tmp_path))
    assert main(["mcp", "list"]) == 0
    assert '"pinned": false' in capsys.readouterr().out
    assert main(["mcp", "check", "fake"]) == 0
    assert main(["mcp", "check", "nope"]) != 0
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert main(["mcp", "pin", "fake"]) != 0         # the owner's decision, at a terminal
    reg = yaml.safe_load((tmp_path / "registry" / "capabilities.yaml").read_text())
    assert "schema_sha256" not in reg["mcp"]["fake"]
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert main(["mcp", "pin", "fake"]) == 0
    reg = yaml.safe_load((tmp_path / "registry" / "capabilities.yaml").read_text())
    assert reg["mcp"]["fake"]["schema_sha256"]
    assert main(["mcp", "revoke", "fake"]) == 0
    reg = yaml.safe_load((tmp_path / "registry" / "capabilities.yaml").read_text())
    assert reg["mcp"]["fake"]["status"] == "REVOKED"
    assert main(["catalog", "--state", "REVOKED"]) == 0
    assert "acme/fake-mcp" in capsys.readouterr().out
    assert main(["catalog"]) == 0
    a = Assistant(tmp_path, None, {}, "human:owner", AuditLog(tmp_path / "j.jsonl", key=b""))
    assert a.tools["tool_catalog"].kind == "read" and TOOL_NODE["tool_catalog"] == "scout"
    out, err = a._run_tool("tool_catalog", {"query": "fake"})
    assert not err and out["tools"][0]["state"] == "REVOKED"
    out, err = a._run_tool("tool_catalog", {"id": "acme/fake-mcp"})
    assert not err and out["approval_status"] == "REVOKED"
    out, err = a._run_tool("tool_catalog", {})
    assert not err and "counts" in out
