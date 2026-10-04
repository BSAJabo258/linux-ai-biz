import datetime as dt
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from decimal import Decimal
from importlib import resources
from pathlib import Path

import pytest
from conftest import ON, repo_root

from bau import accessibility, baseline, capgraph, network, sandbox
from bau.accounting import Books, prepare_payout
from bau.datagov import DataRegistry, TrackingRegistry, provider_allows
from bau.economics import Ledger, metrics, usage_dashboard
from bau.factories import Activation, FactoryRunner, definitions
from bau.incidents import Incidents
from bau.jarvis import mission_types
from bau.legal_pages import LegalPages, render
from bau.legal_queue import LegalQueue
from bau.opportunity import Opportunity, assess
from bau.platforms import FileDropConnector, PlatformRegistry
from bau.sanctions import SanctionsList


# ------------------------------------------------------------------ factories
def test_factory_runs_park_on_gates_and_approvals(tmp_path, active_engine):
    calls = []
    hooks = {"agent": lambda agent, prompt, run: calls.append(agent) or f"{agent} draft",
             "tool": lambda cap, run: {"capability": cap, "status": "EXPORTED"},
             "approval_ok": lambda cap, run, ref: ref == "valid-sig"}
    runner = FactoryRunner(active_engine, hooks, home=tmp_path)
    with pytest.raises(PermissionError):
        runner.start("digital_assets", "Planner pack")
    with pytest.raises(PermissionError):
        Activation(tmp_path).activate("digital_assets", "agent:x", "ref")
    Activation(tmp_path).activate("digital_assets", "human:owner", "sig-1")
    run = runner.start("digital_assets", "Planner pack")
    run = runner.advance(run)
    assert run.status == "WAITING_CHECKLIST" and calls == ["research", "writer"]
    for item in ["asset_built", "fonts_licensed", "stock_licensed"]:
        runner.confirm(run, item, "human:owner")
    with pytest.raises(PermissionError):
        runner.confirm(run, "x", "agent:y")
    run = runner.advance(run)
    assert run.status == "WAITING_GATE" and "monetize" in run.waiting_on
    from bau.commerce.ip import RIGHTS, IPAsset, monetize_facts
    asset = IPAsset("ip1", "Pack", {"BAU": Decimal(100)}, "own", True, "assisted", ["layout"],
                    "m", True, rights={r: "not_used" for r in RIGHTS})
    run.gate_facts["monetize"] = monetize_facts(asset, "US")
    from bau.disclosure import Provenance, publish_facts
    p = Provenance("a", "image", True, False, False, True, model_id="m",
                   machine_readable_marking=True, visible_disclosure_text="AI-GENERATED IMAGE")
    run.gate_facts["publish"] = publish_facts(p, {"audience": [{"country": "US"}],
                                                  "platform_requires_ai_label": False})
    run = runner.advance(run, on=ON)
    assert run.status == "WAITING_CHECKLIST"           # accessibility checklist
    runner.confirm(run, "accessible_pdf_or_alt_text", "human:owner")
    run = runner.advance(run, on=ON)
    assert run.status == "WAITING_APPROVAL"
    run.approvals["publish.text"] = "forged"
    assert runner.advance(run, on=ON).status == "WAITING_APPROVAL"
    run.approvals["publish.text"] = "valid-sig"
    run = runner.advance(run, on=ON)
    assert run.status == "COMPLETED" and run.outputs["listing"]["status"] == "EXPORTED"
    assert runner.load(run.run_id).status == "COMPLETED"


def test_all_factory_definitions_are_consistent(engine):
    defs = definitions()
    types = mission_types()
    domains = {p.domain for p in engine.policies}
    assert set(defs) == {"faceless_media", "digital_assets", "books", "music_entertainment",
                         "automation_services", "gods_eye_media"}
    for name, f in defs.items():
        assert f["mission_type"] in types, name
        for st in f["stages"]:
            assert st["type"] in ("agent", "gate", "checklist", "approval", "tool")
            if st["type"] == "gate":
                assert st["domain"] in domains, (name, st)
    for t in types.values():
        assert set(t.get("requires", [])) <= domains


def test_opportunity_miner():
    good = assess(Opportunity("Planner templates", "Digital planners for small shops",
                              evidence=["etsy trend", "search volume"], value=4,
                              competition=2, capability_fit=5, startup_cost_usd=50,
                              months_to_revenue=1, risk=1, automation_potential=4))
    assert good["recommended_action"] in ("AUTOMATE", "CONTINUE")
    no_ev = assess(Opportunity("Something", "x", value=5, capability_fit=5))
    assert no_ev["recommended_action"] == "PAUSE"
    reg = assess(Opportunity("Supplement reviews", "health supplement affiliate site",
                             evidence=["a", "b"], value=4, capability_fit=4))
    assert reg["legal_review_required"]


# ------------------------------------------------------------------ money
def test_books_1099_and_payouts(tmp_path):
    b = Books(tmp_path)
    with pytest.raises(ValueError):
        b.record(kind="payment", amount="10")
    b.add_payee("p1", "ref:aaa", "US", "W-9", tin_on_file=False)
    b.add_payee("p2", "ref:bbb", "DE", "W-8BEN", tin_on_file=True)
    for amt, payee, kind in [("1500", "p1", "payment"), ("12", "p1", "royalty"),
                             ("2500", "p2", "payment")]:
        b.record(kind=kind, amount=amt, currency="USD", date="2026-03-01",
                 counterparty_ref=payee, description="x", evidence_ref="sha:1")
    rets = b.info_returns(2026)
    cats = {(r["payee"], r["category"]): r for r in rets}
    assert ("p1", "nonemployee_comp") not in cats          # $1,500 < $2,000 (2026)
    assert cats[("p1", "royalties")]["form"] == "1099-MISC"
    assert cats[("p2", "nonemployee_comp")]["form"].startswith("1042-S")
    po = prepare_payout(b, "p1", Decimal("100.00"), True, "CLEAR")
    assert po["status"] == "READY_FOR_APPROVAL" and po["backup_withholding"] == "24.00"
    assert prepare_payout(b, "p1", Decimal(1), False, "CLEAR")["status"] == "BLOCKED"
    assert prepare_payout(b, "p1", Decimal(1), True, "HIT")["status"] == "BLOCKED"
    assert b.next_invoice_number().endswith("00001")


def test_sanctions(tmp_path):
    csv = tmp_path / "sdn.csv"
    csv.write_text('1,"EXAMPLE TRADING CO LLC","-0- ","SDGT",-0-\n'
                   '2,"PETROV, Ivan","individual","RUSSIA-EO14024",-0-\n')
    s = SanctionsList(tmp_path)
    assert s.screen("Anyone").get("result") == "REVIEW"           # list not loaded
    s.import_sdn_csv(csv, ON.isoformat())
    assert s.screen("Example Trading Co", on=ON)["result"] == "HIT"
    assert s.screen("Ivan Petrov", on=ON)["result"] in ("HIT", "REVIEW")
    assert s.screen("Jane Smith Bakery", on=ON)["result"] == "CLEAR"
    assert s.screen("Jane", country="IR", on=ON)["result"] == "HIT"
    assert s.screen("Jane", country="SY", on=ON)["result"] == "CLEAR"   # program ended 2025
    assert s.screen("Jane Smith Bakery", on=ON + dt.timedelta(days=30))["result"] == "REVIEW"


def test_economics(tmp_path):
    led = Ledger(tmp_path)
    led.cost("model", 2.0, agent="a", provider="anthropic")
    led.cost("marketing", 10.0)
    led.sale(100.0, customer_ref="c1", new_customer=True, payment_fee=3.2)
    led.sale(50.0, customer_ref="c2", new_customer=True)
    led.human_time(2.0)
    m = metrics(led)
    assert m["revenue"] == 150 and m["profit"] == pytest.approx(150 - 12 - 3.2)
    assert m["customer_acquisition_cost"] == 5.0 and m["ai_cost_to_revenue"] == round(
        2 / 150, 4)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "providers.yaml").write_text(
        "providers:\n  anthropic:\n    balance_usd: 70\n    key_env_var: ANTHROPIC_API_KEY\n"
        "    key_rotated_at: 2026-01-01\n")
    u = usage_dashboard(led, tmp_path, now=dt.datetime(2026, 10, 4, tzinfo=dt.UTC))
    assert u["anthropic"]["rotation_due"] and u["anthropic"]["key_env_var"] == \
        "ANTHROPIC_API_KEY"


# ------------------------------------------------------------------ governance
def test_data_governance(tmp_path):
    d = DataRegistry(tmp_path / "o.yaml")
    with pytest.raises(ValueError):
        d.register({"data_id": "x"})
    d.register({"data_id": "leads", "source": "signup form", "owner": "BAU",
                "category": "contact", "sensitivity": "PERSONAL", "purpose": "newsletter",
                "lawful_basis": "consent", "retention_days": 1, "location": "local",
                "uses_allowed": ["store", "process"], "collected_at": "2026-01-01"})
    assert d.may("leads", "process")[0]
    assert not d.may("leads", "train")[0]
    assert not d.may("unknown", "view")[0]
    assert [r["data_id"] for r in d.expired(ON)] == ["leads"]
    cloud = {"status": "APPROVED", "data_retained": "none", "training_on_customer_data": False,
             "jurisdiction": "US", "dpa_signed": True}
    assert provider_allows(cloud, ["PERSONAL"])[0]
    assert not provider_allows(cloud, ["AUTHENTICATION"])[0]
    assert not provider_allows(dict(cloud, dpa_signed=False), ["PERSONAL"])[0]
    assert not provider_allows(dict(cloud, status="REGISTERED"), ["PUBLIC"])[0]
    t = TrackingRegistry(tmp_path / "t.yaml")
    t.add("pixel", "pixel", ["ip"], "ads", "adco", 90, False, False)
    assert t.report()["problems"] == ["pixel"]


def test_incidents_and_legal_queue(tmp_path, monkeypatch):
    inc = Incidents(tmp_path)
    i = inc.open("Laptop stolen", "SECURITY", "critical", personal_data=True,
                 jurisdictions=["EU", "US"])
    assert any("72" in c["to"] or "Art. 33" in c["to"] for c in i["clocks"])
    i = inc.advance(i["id"], "remote wipe", "human:o")
    i = inc.advance(i["id"], "class", "human:o")
    i = inc.advance(i["id"], "evidence", "human:o")
    assert i["stage"] == "PRESERVE_EVIDENCE" and i["evidence_anchor"]["head"]
    assert inc.open_items()
    q = LegalQueue(tmp_path)
    item = q.open("digital_replica", "voice of artist X", "license terms unclear")
    assert q.open("digital_replica", "voice of artist X", "again")["id"] == item["id"]
    with pytest.raises(PermissionError):
        q.resolve(item["id"], "ok", "agent:legal", require_tty=False)
    q.resolve(item["id"], "license signed 2026-10-01", "counsel", require_tty=False)
    assert not q.open_items()


def test_legal_pages_versioning(tmp_path):
    lp = LegalPages(tmp_path)
    profile = {"legal_name": "BAU Media LLC", "contact_email": "hi@bau.example",
               "postal_address": "100 Main St, Detroit MI", "dsr_url": "https://bau.example/p"}
    objs = [{"category": "contact", "purpose": "newsletter", "retention_days": 365}]
    text = render("privacy_policy", profile, objs, [{"provider_id": "esp",
                                                     "jurisdiction": "US"}], [])
    assert "BAU Media LLC" in text and "[[TO FILL" not in text
    v1 = lp.draft("privacy_policy", text, "US", "CCPA", "2026-10-04")
    assert v1["status"] == "DRAFT" and "DRAFT" in v1["text"]
    lp.approve("privacy_policy", "counsel", require_tty=False)
    v2 = lp.draft("privacy_policy", text.replace("newsletter", "newsletter and sharing with "
                                                 "partners"), "US", "CCPA", "2026-11-04")
    assert v2["version"] == 2 and v2["material_change"] and v2["user_notification_required"]
    blank = lp.draft("refund_policy", render("refund_policy", {}, [], [], []), "US", "x", "x")
    assert blank
    with pytest.raises(ValueError):
        lp.approve("refund_policy", "counsel", require_tty=False)   # [[TO FILL]] left


def test_platforms(tmp_path):
    reg = PlatformRegistry(tmp_path)
    assert not reg.facts("youtube")["platform_policy_current"]
    rec = {f: "x" for f in ["policy_version", "ai_content_policy", "copyright_policy",
                            "music_policy", "advertising_policy", "commercial_content_policy",
                            "api_policy", "automation_policy", "account_limits",
                            "appeal_process", "source_url"]}
    reg.upsert(dict(rec, platform="youtube", requires_ai_label=True,
                    last_verified=ON.isoformat()))
    f = reg.facts("youtube", ON)
    assert f["platform_policy_current"] and f["platform_requires_ai_label"]
    art = tmp_path / "v.mp4"
    art.write_bytes(b"x")
    res = FileDropConnector(tmp_path / "out").publish(art, {"title": "t"})
    assert res["status"] == "EXPORTED_FOR_MANUAL_UPLOAD"
    assert (Path(res["path"]) / "UPLOAD_CHECKLIST.txt").exists()


# ------------------------------------------------------------------ operations
def test_network_trust(tmp_path):
    pol = network.TrustPolicy(tmp_path / "n.yaml")
    cafe = network.NetworkFacts(online=True, wifi_ssid="Coffee", gateway_mac="aa:bb")
    assert pol.classify(cafe) == network.Trust.UNTRUSTED
    assert not network.allows(network.Trust.UNTRUSTED, "APPROVAL_REQUIRED")
    assert network.allows(network.Trust.UNTRUSTED, "READ_ONLY")
    pol.remember(cafe, "trusted")
    assert pol.classify(cafe) == network.Trust.TRUSTED
    assert "Coffee" not in (tmp_path / "n.yaml").read_text()   # stored as a hash
    assert pol.classify(network.NetworkFacts(online=False)) == network.Trust.OFFLINE
    ep = network.EndpointRegistry(tmp_path / "e.yaml")
    with pytest.raises(ValueError):
        ep.add("bank", "bank.example", pins=["aa"])
    import hashlib
    der = b"certificate-bytes"
    fp = hashlib.sha256(der).hexdigest()
    ep.add("bank", "bank.example", pins=[fp], backup_pins=["bb"])
    assert ep.verify("bank", fetch_cert=lambda d: der)["ok"]
    assert not ep.verify("bank", fetch_cert=lambda d: b"mitm")["ok"]


def test_sandbox_command(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(PermissionError):
        sandbox.run(repo, ["pytest"], "SENTINEL_SCANNED", approved=True, dry_run=True)
    with pytest.raises(PermissionError):
        sandbox.run(repo, ["pytest"], "QUARANTINED", approved=False, dry_run=True)
    out = sandbox.run(repo, ["pytest"], "QUARANTINED", approved=True, dry_run=True)
    cmd = out["command"]
    for flag in ["--network=none", "--read-only", "--cap-drop=ALL",
                 "--security-opt=no-new-privileges"]:
        assert flag in cmd
    assert any(c.endswith(":/src:ro,Z") for c in cmd)
    with pytest.raises(PermissionError):
        sandbox.command(repo, ["x"], sandbox.SandboxProfile(env={"API_KEY": "x"}), tmp_path)


def test_accessibility(tmp_path):
    page = (resources.files("bau.ui") / "page.html").read_text()
    assert accessibility.lint_html(page) == []
    bad = '<html><body><img src=x><div onclick="go()">Go</div><input id=a><button></button>' \
          '<h1>x</h1><h3>y</h3></body></html>'
    rules = {i["rule"] for i in accessibility.lint_html(bad)}
    assert {"1.1.1", "2.1.1", "3.3.2", "4.1.2", "1.3.1", "3.1.1", "2.4.1"} <= rules
    reg = accessibility.ShortcutRegistry(tmp_path / "s.yaml")
    reg.add("mission.plan", "ctrl+shift+p")
    with pytest.raises(ValueError):
        reg.add("other", "ctrl+shift+p")
    with pytest.raises(ValueError):
        reg.add("pay", "ctrl+shift+m", danger_level="CRITICAL")
    with pytest.raises(ValueError):
        reg.add("x", "ctrl+c")


def test_golden_baseline_and_updates(tmp_path):
    home = tmp_path / "home"
    (home / "regulations").mkdir(parents=True)
    (home / "regulations" / "r.yaml").write_text("a: 1")
    (home / "config").mkdir()
    (home / "config" / "audit.key").write_text("SECRET")
    res = baseline.create(tmp_path / "golden", home=home)
    assert baseline.verify(Path(res["manifest"]), home=home)["clean"]
    import tarfile
    with tarfile.open(res["bundle"]) as t:
        assert not any("key" in n for n in t.getnames())
    (home / "regulations" / "r.yaml").write_text("a: 2")
    drift = baseline.verify(Path(res["manifest"]), home=home)
    assert not drift["clean"] and "state:regulations/r.yaml" in drift["changed"]
    up = baseline.Updates(home)
    with pytest.raises(ValueError):
        up.advance("bau", "0.2", "PROMOTE", "ev", "human:o")
    for st in ["TEST", "CANARY", "VALIDATE"]:
        up.advance("bau", "0.2", st, "ev", "process:ci")
    with pytest.raises(PermissionError):
        up.advance("bau", "0.2", "PROMOTE", "ev", "process:ci")
    up.advance("bau", "0.2", "PROMOTE", "ev", "human:o")
    assert up.state("bau") == "PROMOTE"


def test_capability_graph_impact(engine):
    import yaml

    from bau.home import shipped_data
    seed = yaml.safe_load((shipped_data() / "registry_defaults.yaml").read_text())
    g = capgraph.build(engine, mission_types(), definitions(), seed)
    imp = capgraph.impact(g, "us-canspam")
    assert "email" in imp["domain"] and "send_email_campaign" in imp["mission"]
    imp = capgraph.impact(g, "us-ftc-reviews-rule")
    assert "publish" in imp["domain"] and "faceless_media" in imp["factory"]


def test_mission_control_server(isolated_home):
    from bau.ui.server import serve
    srv = serve(0, isolated_home)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        html = urllib.request.urlopen(base + "/").read().decode()
        assert "Mission Control" in html
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/status")
        assert e.value.code == 403
        req = urllib.request.Request(base + "/api/status", headers={"X-BAU": "1"})
        data = json.loads(urllib.request.urlopen(req).read())
        assert data["production_ready"] is False
        for ep in ["regulations", "jobs", "missions", "legal-queue", "economics", "incidents"]:
            r = urllib.request.Request(f"{base}/api/{ep}", headers={"X-BAU": "1"})
            assert urllib.request.urlopen(r).status == 200
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(base + "/api/status", data=b"x",
                                                          method="POST"))
        assert e.value.code == 405
        bad_host = urllib.request.Request(base + "/", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(bad_host)
        assert e.value.code == 421
    finally:
        srv.shutdown()


def test_runtime_gateway_and_cli(isolated_home, tmp_path):
    env = {"BAU_HOME": str(isolated_home), "PYTHONPATH": str(repo_root() / "src"),
           "BAU_AUDIT_KEY": str(tmp_path / "none"), "PATH": "/usr/bin:/bin"}

    def bau(*args):
        return subprocess.run([sys.executable, "-m", "bau.cli", *args], capture_output=True,
                              text=True, env=env)
    assert bau("init").returncode == 0
    cat = json.loads(bau("gateway").stdout)
    assert {c["capability"] for c in cat} >= {"memory.search", "artifact.write_draft"}
    models = json.loads(bau("models", "list").stdout)
    assert {m["model_id"] for m in models} >= {"claude-opus-5-5", "k3"}
    r = bau("models", "route", "reasoning")
    assert r.returncode == 3 and "status REGISTERED" in r.stdout   # nothing approved yet
    assert bau("set-status", "model", "claude-opus-5-5", "APPROVED").returncode == 3  # no tty
    r = bau("mission", "plan", "launch_subscription", "Launch planner subscription")
    assert json.loads(r.stdout)["status"] == "BLOCKED"
    assert bau("memory", "add", "decision", "Base OS", "Debian").returncode == 0
    assert "Base OS" in bau("memory", "search", "debian").stdout
    assert bau("memory", "verify").returncode == 0
    r = bau("graph", "impact", "us-canspam")
    assert "send_email_campaign" in r.stdout
    assert bau("factory", "list").returncode == 0
    assert bau("audit", "verify").returncode == 0


def test_factory_run_cli_with_agents(isolated_home, tmp_path):
    import yaml
    env = {"BAU_HOME": str(isolated_home), "PYTHONPATH": str(repo_root() / "src"),
           "BAU_AUDIT_KEY": str(tmp_path / "none"), "PATH": "/usr/bin:/bin"}

    def bau(*args):
        return subprocess.run([sys.executable, "-m", "bau.cli", *args], capture_output=True,
                              text=True, env=env)
    assert bau("init").returncode == 0
    reg_path = isolated_home / "registry" / "capabilities.yaml"
    reg = yaml.safe_load(reg_path.read_text())
    reg["model"]["scripted-test"] = {
        "model_id": "scripted-test", "name": "scripted", "version": "1", "provider": "local",
        "source": "test", "license": "test", "commercial_use": True, "deployment": "local",
        "adapter": "scripted", "script": ["Draft: planner pack for bakeries."],
        "trust_level": "VERIFIED", "privacy": "local", "status": "APPROVED",
        "benchmark": {"ok": True}}
    for a in reg["agent"].values():
        a["model"] = "scripted-test"
    reg_path.write_text(yaml.safe_dump(reg))
    r = bau("factory-run", "start", "digital_assets", "Bakery planner pack")
    assert r.returncode == 3 and "not activated" in r.stderr
    (isolated_home / "config" / "factory_activation.yaml").write_text(
        "active:\n  digital_assets: {by: 'human:test', approval: sig}\n")
    r = bau("factory-run", "start", "digital_assets", "Bakery planner pack")
    view = json.loads(r.stdout)
    assert view["status"] == "WAITING_CHECKLIST" and view["completed"] == ["market", "design"]
    run = json.loads((isolated_home / "jobs" / "factory_runs" /
                      f"{view['run_id']}.json").read_text())
    assert run["outputs"]["design"].startswith("Draft:")
    chain = [json.loads(line)["event"] for line in
             (isolated_home / "audit" / "chain.jsonl").read_text().splitlines()]
    assert "factory.started" in chain and "factory.advanced" in chain
