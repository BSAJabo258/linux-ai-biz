"""CLI commands for the orchestration, knowledge, media, business and operations layers."""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .audit import AuditLog
from .home import bau_home

EXIT_OK, EXIT_REVIEW, EXIT_BLOCKED, EXIT_ERROR = 0, 2, 3, 4


def _out(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _load(path: str) -> Any:
    text = Path(path).read_text()
    return json.loads(text) if path.endswith(".json") else yaml.safe_load(text)


def _human() -> str:
    if not sys.stdin.isatty():
        raise PermissionError("this action must be taken by a human at a terminal")
    return f"human:{getpass.getuser()}"


def _engine():
    from .policy import PolicyEngine
    from .regulations import Registry
    return PolicyEngine.load(Registry.load())


# ------------------------------------------------------------------ models / agents

def cmd_models(a):
    from .models.router import TaskSpec, route
    from .registry import CapabilityRegistry
    reg = CapabilityRegistry()
    if a.models_cmd == "list":
        _out([{k: m.get(k) for k in ("model_id", "provider", "deployment", "status",
                                      "trust_level", "quality", "cost_out_per_mtok")}
              for m in reg.data["model"].values()])
    elif a.models_cmd == "route":
        r = route(TaskSpec(kind=a.kind, data_classes=a.data or ["INTERNAL"],
                           needs_tools=a.tools, offline=a.offline, prefer=a.prefer,
                           min_quality=a.min_quality),
                  list(reg.data["model"].values()), reg.data["provider"])
        _out({"chosen": r.model["model_id"] if r.model else None, "reason": r.reason,
              "ranked": [m["model_id"] for m in r.candidates], "rejected": r.rejected})
        return EXIT_OK if r.model or a.kind in ("format", "validate") else EXIT_BLOCKED
    elif a.models_cmd == "bench":
        from .models.bench import benchmark
        rec = reg.data["model"].get(a.model)
        if rec is None:
            print(f"model {a.model} not registered", file=sys.stderr)
            return EXIT_ERROR
        try:
            res = benchmark(rec)
        except Exception as e:  # unreachable server, bad reply: nothing is recorded
            print(f"benchmark failed: {type(e).__name__}: {e}"[:300], file=sys.stderr)
            return EXIT_BLOCKED
        rec["benchmark"] = res
        reg.path.write_text(yaml.safe_dump(reg.data, sort_keys=True))
        AuditLog().append("model.benchmarked", f"human:{getpass.getuser()}",
                          {"model": a.model, "reply_ok": res["reply_ok"],
                           "tool_calls": res["tool_calls"]})
        _out(res)
        return EXIT_OK if res["reply_ok"] else EXIT_BLOCKED
    elif a.models_cmd == "health":
        from .models.providers import build
        out = {}
        for m in reg.data["model"].values():
            try:
                out[m["model_id"]] = build(m).health() if m.get("adapter") != "anthropic" \
                    else {"ok": None, "note": "cloud model: checked on first call"}
            except Exception as e:
                out[m["model_id"]] = {"ok": False, "error": str(e)[:200]}
        _out(out)
    return EXIT_OK


def cmd_registry_status(a):
    from .registry import CapabilityRegistry, validate
    who = _human()
    reg = CapabilityRegistry()
    rec = reg.data[a.kind].get(a.key)
    if rec is None:
        print(f"{a.kind}/{a.key} not found", file=sys.stderr)
        return EXIT_ERROR
    new = dict(rec, status=a.status, reviewed_by=who,
               reviewed_at=dt.datetime.now(dt.UTC).isoformat())
    errs = validate(a.kind, new)
    if errs:
        print("; ".join(errs), file=sys.stderr)
        return EXIT_BLOCKED
    reg.data[a.kind][a.key] = new
    reg.path.write_text(yaml.safe_dump(reg.data, sort_keys=True))
    AuditLog().append("registry.status", who, {"kind": a.kind, "key": a.key,
                                                "status": a.status})
    _out(new)
    return EXIT_OK


def cmd_agent(a):
    from . import agents
    from .registry import CapabilityRegistry
    from .runtime import TOOL_SPECS, build_gateway, provider_for
    reg = CapabilityRegistry()
    rec = reg.data["agent"].get(a.agent)
    if rec is None or rec.get("status") not in ("APPROVED", "ACTIVE"):
        print(f"agent {a.agent} missing or not approved", file=sys.stderr)
        return EXIT_BLOCKED
    provider, model = provider_for(a.model or rec["model"])
    spec = agents.AgentSpec.from_registry(rec, model, TOOL_SPECS)
    res = agents.run(spec, a.objective, provider, build_gateway(), mission_id=a.mission or "")
    _out(asdict(res))
    return EXIT_OK if res.status == "COMPLETED" else EXIT_REVIEW


# ------------------------------------------------------------------ missions

def cmd_mission(a):
    from . import blast
    from .jarvis import Jarvis
    j = Jarvis(_engine())
    if a.mission_cmd == "types":
        _out(j.types)
    elif a.mission_cmd == "plan":
        facts = _load(a.facts) if a.facts else {}
        bf = blast.Factors(**_load(a.blast)) if a.blast else None
        m = j.plan(a.objective, a.type, facts, bf)
        _out(asdict(m))
        return {"READY": EXIT_OK, "NEEDS_REVIEW": EXIT_REVIEW}.get(m.status, EXIT_BLOCKED)
    elif a.mission_cmd == "list":
        _out([{"mission_id": m.mission_id, "type": m.mission_type, "status": m.status,
               "next_action": m.next_action} for m in j.list()])
    elif a.mission_cmd == "show":
        m = j.get(a.mission_id)
        _out(asdict(m) if m else None)
    elif a.mission_cmd == "approve":
        from .security.permissions import SshApprovals, load_approval
        m = j.get(a.mission_id)
        ap = load_approval(Path(a.approval))
        signers = Path(__import__("os").environ.get("BAU_ALLOWED_SIGNERS",
                                                    "/etc/bau/allowed_signers"))
        from .cli import _content_hash
        if (m is None or ap.request_id != a.mission_id
                or ap.scope.get("bound_sha256") != _content_hash(asdict(m))
                or not SshApprovals(signers).verify(ap, "mission.run")):
            print("approval invalid for this mission", file=sys.stderr)
            return EXIT_BLOCKED
        _out(asdict(j.mark_approved(m, f"{ap.approver}@{ap.approved_at}")))
    return EXIT_OK


def cmd_legal(a):
    from .legal_queue import LegalQueue
    q = LegalQueue()
    if a.lq_cmd == "list":
        _out(q.open_items() if not a.all else q.items())
    elif a.lq_cmd == "open":
        _out(q.open(a.trigger, a.subject, a.detail))
    elif a.lq_cmd == "resolve":
        who = _human()
        _out(q.resolve(a.item_id, a.resolution, who.split(":", 1)[1]))
    return EXIT_OK


# ------------------------------------------------------------------ memory / genesis

def cmd_memory(a):
    from .memory import MemoryLane
    m = MemoryLane()
    if a.mem_cmd == "add":
        _out(asdict(m.add(a.kind, a.title, a.body, a.tag or [], a.status, "cli",
                          a.resume_phrase)))
    elif a.mem_cmd == "search":
        _out([{"score": s, "id": r.id, "title": r.title, "status": r.status}
              for s, r in m.search(a.query, a.k)])
    elif a.mem_cmd == "recent":
        _out([{"id": r.id, "ts": r.ts, "title": r.title} for r in m.recent(a.n)])
    elif a.mem_cmd == "resume":
        _out([{"id": r.id, "title": r.title, "body": r.body[:500]} for r in m.resume(a.phrase)])
    elif a.mem_cmd == "answer":
        provider = None
        if a.model:
            from .runtime import provider_for
            provider, _ = provider_for(a.model)
        _out(m.answer(a.question, provider))
    elif a.mem_cmd == "verify":
        ok, msg = m.verify()
        _out({"ok": ok, "detail": msg})
        return EXIT_OK if ok else EXIT_BLOCKED
    elif a.mem_cmd == "export":
        _out({"export": str(m.export(Path(a.out)))})
    return EXIT_OK


def cmd_genesis(a):
    from . import genesis
    from .memory import MemoryLane
    c = genesis.Corpus()
    if a.gen_cmd == "import":
        msgs = genesis.detect_and_import(Path(a.path))
        res = c.ingest(msgs)
        AuditLog().append("genesis.import", "genesis", {"source": Path(a.path).name, **res})
        _out(res)
    elif a.gen_cmd == "extract":
        msgs = c.messages()
        items = genesis.extract(msgs)
        contra = genesis.contradictions(items)
        out_dir = bau_home() / "history" / "canonical"
        sections = _system_sections()
        paths = genesis.write_canonical(items, contra, out_dir, sections)
        n_mem = genesis.to_memory(items, MemoryLane()) if a.to_memory else 0
        _out({"messages": len(msgs), "items": len(items), "contradictions": len(contra),
              "documents": [str(p) for p in paths], "memory_records": n_mem})
    return EXIT_OK


def _system_sections() -> dict[str, str]:
    """System-derived content for canonical documents that the corpus cannot supply."""
    from .registry import CapabilityRegistry
    from .regulations import Registry
    from .status import build_state
    reg = CapabilityRegistry()
    rows = ["| Model | Provider | Status | Trust |", "|---|---|---|---|"] + [
        f"| {m['model_id']} | {m['provider']} | {m['status']} | {m['trust_level']} |"
        for m in reg.data["model"].values()]
    regs = ["| Regulation | Legal status | BAU status | Next review |", "|---|---|---|---|"] + [
        f"| {r.reg_id} | {r['legal_status']} | {r['bau_status']} | {r['next_review']} |"
        for r in Registry.load()]
    build = ["| Item | Status |", "|---|---|"] + [f"| {b['item']} | {b['status']} |"
                                                   for b in build_state()]
    return {"MODEL_REGISTRY": "\n".join(rows) + "\n",
            "REGULATORY_REGISTER": "\n".join(regs) + "\n",
            "BUILD_STATE": "\n".join(build) + "\n",
            "ARCHITECTURE": "See docs/ARCHITECTURE.md in the BAU repository.\n",
            "SECURITY_MODEL": "See docs/ARCHITECTURE.md (identities, gateway, approvals).\n"}


# ------------------------------------------------------------------ media / spatial

def cmd_media(a):
    from .media import music
    if a.media_cmd == "analyze":
        _out(music.analyze(Path(a.file)))
    elif a.media_cmd == "edl":
        _out(music.edit_decision_list(music.analyze(Path(a.file)), a.scene,
                                      a.beats_per_cut))
    return EXIT_OK


def cmd_spatial(a):
    from .spatial import GodsEye, create_scene, export_scene
    ge = GodsEye()
    if a.sp_cmd == "earthquakes":
        data = ge.earthquakes(a.purpose, a.window)
    elif a.sp_cmd == "satellites":
        data = ge.satellites(a.purpose, a.group)
    else:
        data = ge.aircraft(a.purpose, tuple(a.bbox))
    if a.out:
        export_scene(create_scene([data], a.purpose), Path(a.out))
    _out({"count": data["bau"]["count"], "licence": data["bau"]["licence"],
          "out": a.out})
    return EXIT_OK


# ------------------------------------------------------------------ business

def cmd_factory(a):
    from .factories import Activation, definitions
    if a.fac_cmd == "list":
        act = Activation().active()
        _out({k: {"description": v["description"], "active": k in act,
                  "stages": [s["id"] for s in v["stages"]]} for k, v in definitions().items()})
    elif a.fac_cmd == "activate":
        who = _human()
        Activation().activate(a.name, who, a.approval_ref)
        AuditLog().append("factory.activated", who, {"factory": a.name})
        _out({"activated": a.name})
    elif a.fac_cmd == "deactivate":
        Activation().deactivate(a.name)
        _out({"deactivated": a.name})
    return EXIT_OK


def _factory_runner():
    import os

    from . import agents
    from .factories import FactoryRunner
    from .gateway import CallRequest
    from .registry import CapabilityRegistry
    from .runtime import TOOL_SPECS, build_gateway, provider_for
    from .security.permissions import SshApprovals, load_approval
    gw = build_gateway()
    signers = SshApprovals(Path(os.environ.get("BAU_ALLOWED_SIGNERS",
                                               "/etc/bau/allowed_signers")))
    gw.authority = signers
    gw.table.agent_ceiling["factory"] = "LOW_RISK"
    reg = CapabilityRegistry()

    def agent_hook(agent_id, prompt, run):
        rec = reg.data["agent"].get(agent_id)
        if rec is None or rec.get("status") not in ("APPROVED", "ACTIVE"):
            raise PermissionError(f"agent {agent_id} is not approved")
        provider, model = provider_for(rec["model"])
        prior = json.dumps(run.outputs, default=str)[-6000:]
        res = agents.run(agents.AgentSpec.from_registry(rec, model, TOOL_SPECS),
                         f"{prompt}\n\nFactory objective: {run.objective}", provider, gw,
                         context=f"Earlier stage outputs (drafts, unverified): {prior}",
                         mission_id=run.run_id)
        if res.status != "COMPLETED":
            raise RuntimeError(f"agent {agent_id} stopped: {res.status}")
        return res.final_text

    def approval_ok(capability, run, ref):
        ap = load_approval(Path(ref))
        return ap.request_id == run.run_id and signers.verify(ap, capability)

    def tool_hook(capability, run):
        ref = run.approvals.get(capability)
        ap = load_approval(Path(ref)) if ref else None
        args = (run.gate_facts.get("tool_args") or {}).get(capability, {})
        requester = ap.requester if ap else "factory"
        return gw.invoke(CallRequest(requester, capability, args, approval=ap,
                                     mission_id=run.run_id))

    return FactoryRunner(_engine(), {"agent": agent_hook, "tool": tool_hook,
                                     "approval_ok": approval_ok})


def _run_view(run) -> dict[str, Any]:
    return {"run_id": run.run_id, "factory": run.factory, "status": run.status,
            "stage_index": run.stage_index, "waiting_on": run.waiting_on,
            "completed": [h["stage"] for h in run.history]}


def cmd_factory_run(a):
    fr = _factory_runner()
    if a.fr_cmd == "start":
        run = fr.advance(fr.start(a.name, a.objective))
    else:
        run = fr.load(a.run_id)
        if a.fr_cmd == "confirm":
            fr.confirm(run, a.item, _human())
        elif a.fr_cmd == "facts":
            run.gate_facts[a.domain] = _load(a.file)
            fr._save(run)
        elif a.fr_cmd == "approval":
            run.approvals[a.capability] = str(Path(a.file).resolve())
            fr._save(run)
        if a.fr_cmd != "show":
            run = fr.advance(run)
    _out(_run_view(run))
    return {"COMPLETED": EXIT_OK, "RUNNING": EXIT_OK}.get(run.status, EXIT_REVIEW)


def cmd_opportunity(a):
    from .opportunity import Opportunity, rank
    _out(rank([Opportunity(**o) for o in _load(a.file)]))
    return EXIT_OK


def cmd_economics(a):
    from .economics import Ledger, metrics, usage_dashboard
    from .jobs import JobStore
    led = Ledger()
    if a.eco_cmd == "cost":
        _out(led.cost(a.kind, a.usd, agent=a.agent or "", mission_id=a.mission or "",
                      provider=a.provider or "", note=a.note or ""))
    elif a.eco_cmd == "sale":
        _out(led.sale(a.gross, mission_id=a.mission or "", factory=a.factory or "",
                      customer_ref=a.customer or "", new_customer=a.new_customer,
                      platform_fee=a.platform_fee, payment_fee=a.payment_fee))
    elif a.eco_cmd == "hours":
        _out(led.human_time(a.hours, mission_id=a.mission or ""))
    elif a.eco_cmd == "metrics":
        since = dt.datetime.now(dt.UTC) - dt.timedelta(days=a.days) if a.days else None
        _out(metrics(led, since, JobStore().all()))
    elif a.eco_cmd == "usage":
        _out(usage_dashboard(led))
    return EXIT_OK


def cmd_books(a):
    from .accounting import Books, prepare_payout
    b = Books()
    if a.books_cmd == "record":
        _out(b.record(**_load(a.file)))
    elif a.books_cmd == "invoice-number":
        _out({"invoice": b.next_invoice_number()})
    elif a.books_cmd == "payee":
        _out(b.add_payee(a.payee_id, a.name_ref, a.country, a.form, a.tin_on_file))
    elif a.books_cmd == "info-returns":
        _out(b.info_returns(a.year))
    elif a.books_cmd == "payout":
        _out(prepare_payout(b, a.payee_id, Decimal(a.amount), a.ownership_resolved,
                            a.sanctions))
    return EXIT_OK


def cmd_sanctions(a):
    from .sanctions import SanctionsList
    s = SanctionsList()
    if a.san_cmd == "import":
        _out({"entries": s.import_sdn_csv(Path(a.file), a.fetched_at)})
    else:
        res = s.screen(a.name, a.country, a.region)
        _out(res)
        return {"CLEAR": EXIT_OK, "REVIEW": EXIT_REVIEW}.get(res["result"], EXIT_BLOCKED)
    return EXIT_OK


def cmd_incident(a):
    from .incidents import Incidents
    inc = Incidents()
    if a.inc_cmd == "open":
        _out(inc.open(a.title, a.cls, a.severity, a.personal_data, a.jurisdiction or []))
    elif a.inc_cmd == "advance":
        _out(inc.advance(a.incident_id, a.note, f"human:{getpass.getuser()}"))
    else:
        _out(inc.open_items())
    return EXIT_OK


def cmd_legal_pages(a):
    from .datagov import DataRegistry, TrackingRegistry
    from .legal_pages import PAGES, LegalPages, render
    from .registry import CapabilityRegistry
    lp = LegalPages()
    if a.lp_cmd == "generate":
        profile = lp.profile.load()
        objs = list(DataRegistry().store.load()["objects"].values())
        provs = list(CapabilityRegistry().data["provider"].values())
        track = list(TrackingRegistry().store.load()["items"].values())
        out = []
        for page in (a.page or PAGES):
            text = render(page, profile, objs, provs, track)
            rec = lp.draft(page, text, a.jurisdiction, a.legal_basis, a.effective_date)
            out.append({"page": page, "version": rec["version"],
                        "material_change": rec["material_change"],
                        "to_fill": text.count("[[TO FILL")})
        _out(out)
    elif a.lp_cmd == "approve":
        who = _human()
        _out({k: v for k, v in lp.approve(a.page, who).items() if k != "text"})
    elif a.lp_cmd == "show":
        v = lp.latest(a.page)
        print(v["text"] if v else "no version")
    return EXIT_OK


def cmd_data(a):
    from .datagov import DataRegistry, TrackingRegistry
    d = DataRegistry()
    if a.data_cmd == "register":
        _out(d.register(_load(a.file)))
    elif a.data_cmd == "may":
        ok, why = d.may(a.data_id, a.use)
        _out({"allowed": ok, "reason": why})
        return EXIT_OK if ok else EXIT_BLOCKED
    elif a.data_cmd == "expired":
        _out(d.expired())
    elif a.data_cmd == "tracking":
        _out(TrackingRegistry().report())
    return EXIT_OK


def cmd_platform(a):
    from .platforms import PlatformRegistry
    p = PlatformRegistry()
    if a.pl_cmd == "add":
        _out(p.upsert(_load(a.file)))
    else:
        _out(p.facts(a.platform))
    return EXIT_OK


# ------------------------------------------------------------------ operations

def cmd_network(a):
    from . import network
    pol = network.TrustPolicy()
    f = network.detect()
    if a.net_cmd == "remember":
        _human()
        pol.remember(f, a.level)
    t = pol.classify(f)
    _out({"trust": str(t), "online": f.online, "vpn": f.vpn_active,
          "allowed_levels": [lvl for lvl in network.MIN_TRUST if network.allows(t, lvl)]})
    return EXIT_OK


def cmd_sandbox(a):
    from . import sandbox
    res = sandbox.run(Path(a.repo), a.cmd, a.intake_state, approved=a.approved,
                      dry_run=not a.execute)
    _out(res)
    return EXIT_OK


def cmd_a11y(a):
    from .accessibility import ACCEPTANCE, ShortcutRegistry, lint_html
    if a.a11y_cmd == "lint":
        issues = lint_html(Path(a.file).read_text())
        _out({"issues": issues, "manual_checks_still_required": ACCEPTANCE})
        return EXIT_REVIEW if issues else EXIT_OK
    reg = ShortcutRegistry()
    if a.a11y_cmd == "shortcut":
        _out(reg.add(a.command, a.key, a.danger, a.confirm))
    else:
        _out(reg.all())
    return EXIT_OK


def cmd_baseline(a):
    from . import baseline
    if a.bl_cmd == "create":
        _out(baseline.create(Path(a.out)))
    elif a.bl_cmd == "verify":
        res = baseline.verify(Path(a.manifest))
        _out(res)
        return EXIT_OK if res["clean"] else EXIT_REVIEW
    elif a.bl_cmd == "update":
        who = f"human:{getpass.getuser()}" if sys.stdin.isatty() else "process:update"
        _out(baseline.Updates().advance(a.component, a.version, a.stage, a.evidence, who))
    return EXIT_OK


def cmd_graph(a):
    from . import capgraph
    from .factories import definitions
    from .jarvis import mission_types
    from .registry import CapabilityRegistry
    g = capgraph.build(_engine(), mission_types(), definitions(), CapabilityRegistry().data)
    if a.graph_cmd == "impact":
        _out(capgraph.impact(g, a.reg_id))
    else:
        _out(g.to_dict())
    return EXIT_OK


def cmd_jarvis(a):
    from .assistant import Voice, build_assistant, load_env_file, save_config
    if a.jv_cmd == "config":
        values = {"call_me": a.call_me, "model": a.model, "elevenlabs_voice_id": a.voice_id,
                  "listen": a.listen}
        if any(v is not None for v in values.values()):
            save_config(bau_home(), **values)
        _out(yaml.safe_load((bau_home() / "config" / "jarvis.yaml").read_text())
             if (bau_home() / "config" / "jarvis.yaml").exists() else {})
        return EXIT_OK
    owner = _human()
    load_env_file()
    jv = build_assistant(owner=owner)
    if a.text:
        return _jarvis_terminal(jv)
    from .ui.jarvis_server import serve
    srv, key = serve(jv, Voice(), a.port)
    url = f"http://127.0.0.1:{a.port}/?k={key}"
    mode = f"model {jv.model.get('id')}" if jv.provider else "plain mode (no model connected)"
    print(f"Jarvis is up ({mode}). Open: {url}\nCtrl+C to stop.", file=sys.stderr)
    if not a.no_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def _jarvis_terminal(jv) -> int:
    def show(r) -> None:
        print(f"\nJarvis: {r.text}\n")
        for p in r.pending:
            print("-" * 60 + f"\n{p['summary']}\n" + "-" * 60)
            choices = {}
            for f in (p.get("form") or {}).get("fields", []):
                for i, (_, label) in enumerate(f["options"], 1):
                    print(f"  {i}. {label}")
                while (n := input(f"{f['label']} (number, no default): ").strip()) not in [
                        str(i) for i in range(1, len(f["options"]) + 1)]:
                    pass
                choices[f["name"]] = f["options"][int(n) - 1][0]
            notes = (p.get("form") or {}).get("notes")
            if notes:
                print(notes.get(choices.get("promotes"), notes["default"]))
            if p.get("preview"):
                print(f"Preview the video first: {jv.pending[p['id']].preview}")
            yes = input("Confirm? [y/N] ").strip().lower() == "y"
            out = jv.confirm(p["id"], yes, jv.owner, choices)
            print("Done." if out.get("done") else
                  "Not done." if not yes else f"That didn't go through: {out.get('result')}")
    show(jv.briefing())
    while True:
        try:
            text = input("you> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return EXIT_OK
        if text.strip().lower() in ("exit", "quit", "bye"):
            return EXIT_OK
        show(jv.ask(text))


def cmd_ui(a):
    from .ui.server import serve
    srv = serve(a.port)
    print(f"Mission Control on http://127.0.0.1:{a.port}/ (read-only; Ctrl+C to stop)",
          file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def cmd_gateway(a):
    from .runtime import build_gateway
    _out(build_gateway().catalog())
    return EXIT_OK


def _resume_agent_job(job) -> bool | None:
    """Governor executor: re-run an interrupted agent job through the gateway."""
    from . import agents
    from .jobs import JobStore
    from .registry import CapabilityRegistry
    from .runtime import TOOL_SPECS, build_gateway, provider_for
    rec = CapabilityRegistry().data["agent"].get(job.agent)
    if rec is None or rec.get("status") not in ("APPROVED", "ACTIVE"):
        return None
    provider, model = provider_for(job.model or rec["model"])
    spec = agents.AgentSpec.from_registry(rec, model, TOOL_SPECS)
    res = agents.run(spec, job.objective, provider, build_gateway(), JobStore(),
                     mission_id=job.mission_id, job=job)
    return res.status == "COMPLETED"


def cmd_governor(a):
    from .governor import Governor, hold_reason
    if a.gov_cmd == "tick":
        reviewer = None
        g = Governor()
        if g.cfg.get("reviewer_model"):
            from .runtime import provider_for
            try:
                reviewer, rec = provider_for(g.cfg["reviewer_model"])
                if rec.get("lane") == "content_only" or rec.get("trust_level") == "ABLITERATED":
                    reviewer = None
                    raise PermissionError("a content-lane / abliterated model cannot be "
                                          "the Governor's validator")
            except (KeyError, PermissionError) as e:
                print(f"validator model unavailable: {e}", file=sys.stderr)
        g.reviewer = reviewer
        rep = g.tick(executor=None if a.no_resume else _resume_agent_job)
        _out(rep)
        return EXIT_BLOCKED if rep["hold"] else EXIT_OK
    g = Governor()
    if a.gov_cmd == "status":
        _out({"hold": hold_reason(),
              "open_findings": g.open_findings(), "config": g.cfg})
    elif a.gov_cmd == "digest":
        _out(g.digest(a.hours))
    elif a.gov_cmd == "hold":
        g.hold(a.reason, by=f"human:{getpass.getuser()}")
        _out({"hold": a.reason})
    elif a.gov_cmd == "release":
        g.release(_human())
        _out({"hold": None})
    elif a.gov_cmd == "close":
        g.close(a.finding_id, _human(), a.note or "")
        _out({"closed": a.finding_id})
    return EXIT_OK


def cmd_brain(a):
    from .brain import Brain
    b = Brain()
    if a.brain_cmd == "say":
        edges = b.say(a.sentence)
        AuditLog().append("brain.edges_added", f"human:{getpass.getuser()}",
                          {"count": len(edges)})
        _out([{"source": s_, "verb": v, "target": t} for s_, v, t in edges])
    elif a.brain_cmd == "note":
        n = b.upsert(a.title, a.type, data_class=a.data_class, body=a.body)
        _out({"note": str(b.path(n.id)), "type": n.type, "data_class": n.data_class})
    elif a.brain_cmd == "import":
        _out(b.import_system())
    elif a.brain_cmd == "lint":
        issues = b.lint()
        _out(issues)
        return EXIT_REVIEW if issues else EXIT_OK
    elif a.brain_cmd == "workflows":
        _out(b.workflows())
    elif a.brain_cmd == "context":
        ctx = b.context(a.query, hops=a.hops)
        print(ctx["markdown"] or "(nothing related yet)")
        if ctx["withheld_by_data_class"]:
            print(f"\n[{ctx['withheld_by_data_class']} note(s) withheld: data class not "
                  "safe to send to a model]", file=sys.stderr)
    elif a.brain_cmd == "graph":
        if a.out:
            _out({"written": str(b.export(Path(a.out)))})
        else:
            _out(b.graph())
    return EXIT_OK


def _previewer():
    import shutil
    import subprocess
    opener = shutil.which("xdg-open")
    return (lambda v: subprocess.Popen([opener, str(v)])) if opener and \
        os.environ.get("DISPLAY") else None


def cmd_youtube(a):
    from . import youtube
    q = youtube.YouTubeQueue()
    if a.yt_cmd == "login":
        _human()
        client = youtube.YouTubeClient()
        youtube.login(client, port=a.port)
        ch = client.channel()
        AuditLog().append("youtube.connected", _human(), {})
        _out({"connected": ch["title"], "handle": ch.get("handle")})
    elif a.yt_cmd == "logout":
        youtube.TokenStore().clear()
        _out({"connected": None})
    elif a.yt_cmd == "add":
        desc = Path(a.description_file).read_text() if a.description_file else a.description
        item = q.add(Path(a.video), a.title, f"human:{getpass.getuser()}", desc or "",
                     [t for t in (a.tags or "").split(",") if t.strip()], kids=a.kids,
                     licensed=a.licensed, paid_promotion=a.paid_promotion,
                     category_id=a.category, is_aigc=False if a.not_ai else None,
                     engine=_engine())
        _out(asdict(item))
        return EXIT_OK if item.checks["ok"] else EXIT_BLOCKED
    elif a.yt_cmd == "queue":
        _out([{"item_id": i.item_id, "title": i.title, "kids": i.kids, "status": i.status,
               "ok": i.checks.get("ok"), "problems": i.checks.get("problems"),
               "warnings": i.checks.get("warnings")}
              for i in (q.items() if a.all else q.pending())])
    elif a.yt_cmd == "review":
        done = youtube.review(q, youtube.YouTubeClient(), _human(), preview=_previewer())
        _out([{"item_id": i.item_id, "status": i.status, "result": i.result} for i in done])
    elif a.yt_cmd == "status":
        client = youtube.YouTubeClient()
        out = []
        for i in q.items():
            if i.video_id:
                i.result = {**i.result, **client.status(i.video_id)}
                q.save(i)
            out.append({"item_id": i.item_id, "status": i.status, "youtube": i.result})
        _out(out)
    return EXIT_OK


def cmd_publish(a):
    from .publishing import ADAPTERS, Hub
    hub = Hub()
    if a.pub_cmd == "platforms":
        _out([{"platform": k, "label": v.label, "kids": v.allows_kids,
               "note": v.kids_note or None} for k, v in ADAPTERS.items()])
    elif a.pub_cmd == "queue":
        _out(hub.pending())
    elif a.pub_cmd == "add":
        desc = Path(a.description_file).read_text() if a.description_file else a.description
        out = hub.queue(Path(a.video), [p.strip() for p in a.to.split(",") if p.strip()],
                        f"human:{getpass.getuser()}", title=a.title, description=desc or "",
                        tags=[t for t in (a.tags or "").split(",") if t.strip()], kids=a.kids,
                        licensed=a.licensed, paid_promotion=a.paid_promotion,
                        is_aigc=False if a.not_ai else None, engine=_engine())
        _out(out)
        return EXIT_OK if all(r.get("ok", True) for r in out) else EXIT_BLOCKED
    return EXIT_OK


def cmd_tiktok(a):
    from . import tiktok
    q = tiktok.TikTokQueue()
    if a.tt_cmd == "login":
        _human()
        client = tiktok.TikTokClient()
        tiktok.login(client, port=a.port)
        info = client.creator_info()
        AuditLog().append("tiktok.connected", _human(), {})
        _out({"connected": info.get("creator_nickname"),
              "privacy_options": info.get("privacy_level_options")})
    elif a.tt_cmd == "logout":
        tiktok.TokenStore().clear()
        _out({"connected": None})
    elif a.tt_cmd == "add":
        item = q.add(Path(a.video), a.caption, f"human:{getpass.getuser()}",
                     is_aigc=False if a.not_ai else None, engine=_engine())
        _out(asdict(item))
        return EXIT_OK if item.checks["ok"] else EXIT_BLOCKED
    elif a.tt_cmd == "queue":
        _out([{"item_id": i.item_id, "video": i.video, "status": i.status,
               "ok": i.checks.get("ok"), "problems": i.checks.get("problems")}
              for i in (q.items() if a.all else q.pending())])
    elif a.tt_cmd == "review":
        done = tiktok.review(q, tiktok.TikTokClient(), _human(), draft=a.draft,
                             preview=_previewer())
        _out([{"item_id": i.item_id, "status": i.status, "result": i.result} for i in done])
    elif a.tt_cmd == "status":
        client = tiktok.TikTokClient()
        out = []
        for i in q.items():
            if i.publish_id and i.result.get("status") not in ("PUBLISH_COMPLETE", "FAILED"):
                st = client.status(i.publish_id)
                i.result = {k: st.get(k) for k in ("status", "fail_reason",
                                                   "publicaly_available_post_id")}
                if st.get("status") == "FAILED":
                    i.status = "FAILED"
                q.save(i)
            out.append({"item_id": i.item_id, "status": i.status, "tiktok": i.result})
        _out(out)
    return EXIT_OK


# ------------------------------------------------------------------ parser

def register(sub: argparse._SubParsersAction) -> None:
    s = sub.add_parser("models", help="model registry, routing, health")
    ms = s.add_subparsers(dest="models_cmd", required=True)
    ms.add_parser("list")
    ms.add_parser("health")
    x = ms.add_parser("bench", help="measure a model on this machine (required before a "
                      "local model can be approved)")
    x.add_argument("model")
    x = ms.add_parser("route")
    x.add_argument("kind")
    x.add_argument("--data", action="append")
    x.add_argument("--tools", action="store_true")
    x.add_argument("--offline", action="store_true")
    x.add_argument("--prefer", default="balanced",
                   choices=["balanced", "quality", "cost", "private"])
    x.add_argument("--min-quality", type=float, default=0.0)
    s.set_defaults(fn=cmd_models)

    s = sub.add_parser("set-status", help="human: change a registry record's status")
    s.add_argument("kind", choices=["model", "agent", "mcp", "repository", "provider"])
    s.add_argument("key")
    s.add_argument("status")
    s.set_defaults(fn=cmd_registry_status)

    s = sub.add_parser("agent", help="run an approved agent through the gateway")
    s.add_argument("agent")
    s.add_argument("objective")
    s.add_argument("--model")
    s.add_argument("--mission")
    s.set_defaults(fn=cmd_agent)

    s = sub.add_parser("mission", help="Jarvis missions")
    js = s.add_subparsers(dest="mission_cmd", required=True)
    js.add_parser("types")
    js.add_parser("list")
    x = js.add_parser("plan")
    x.add_argument("type")
    x.add_argument("objective")
    x.add_argument("--facts", help="JSON/YAML: {gate_domain: facts}")
    x.add_argument("--blast", help="JSON/YAML blast-radius factors")
    x = js.add_parser("show")
    x.add_argument("mission_id")
    x = js.add_parser("approve")
    x.add_argument("mission_id")
    x.add_argument("--approval", required=True)
    s.set_defaults(fn=cmd_mission)

    s = sub.add_parser("legal-queue", help="legal review queue (spec §120)")
    ls = s.add_subparsers(dest="lq_cmd", required=True)
    x = ls.add_parser("list")
    x.add_argument("--all", action="store_true")
    x = ls.add_parser("open")
    x.add_argument("trigger")
    x.add_argument("subject")
    x.add_argument("detail")
    x = ls.add_parser("resolve")
    x.add_argument("item_id")
    x.add_argument("resolution")
    s.set_defaults(fn=cmd_legal)

    s = sub.add_parser("memory", help="MAYA Memory Lane")
    mm = s.add_subparsers(dest="mem_cmd", required=True)
    x = mm.add_parser("add")
    x.add_argument("kind")
    x.add_argument("title")
    x.add_argument("body")
    x.add_argument("--tag", action="append")
    x.add_argument("--status", default="CURRENT")
    x.add_argument("--resume-phrase")
    x = mm.add_parser("search")
    x.add_argument("query")
    x.add_argument("-k", type=int, default=5)
    x = mm.add_parser("recent")
    x.add_argument("-n", type=int, default=10)
    x = mm.add_parser("resume")
    x.add_argument("phrase")
    x = mm.add_parser("answer")
    x.add_argument("question")
    x.add_argument("--model")
    mm.add_parser("verify")
    x = mm.add_parser("export")
    x.add_argument("out")
    s.set_defaults(fn=cmd_memory)

    s = sub.add_parser("genesis", help="Project Genesis: import and analyse AI history")
    gs = s.add_subparsers(dest="gen_cmd", required=True)
    x = gs.add_parser("import")
    x.add_argument("path", help="ChatGPT/Claude conversations.json or a folder of .md")
    x = gs.add_parser("extract")
    x.add_argument("--to-memory", action="store_true")
    s.set_defaults(fn=cmd_genesis)

    s = sub.add_parser("media", help="music analysis and beat-synced edit lists")
    md = s.add_subparsers(dest="media_cmd", required=True)
    x = md.add_parser("analyze")
    x.add_argument("file")
    x = md.add_parser("edl")
    x.add_argument("file")
    x.add_argument("--scene", action="append", required=True)
    x.add_argument("--beats-per-cut", type=int, default=4)
    s.set_defaults(fn=cmd_media)

    s = sub.add_parser("spatial", help="God's Eye public geodata")
    sp = s.add_subparsers(dest="sp_cmd", required=True)
    x = sp.add_parser("earthquakes")
    x.add_argument("--purpose", required=True)
    x.add_argument("--window", default="all_day")
    x.add_argument("--out")
    x = sp.add_parser("satellites")
    x.add_argument("--purpose", required=True)
    x.add_argument("--group", default="stations")
    x.add_argument("--out")
    x = sp.add_parser("aircraft")
    x.add_argument("--purpose", required=True)
    x.add_argument("--bbox", type=float, nargs=4, required=True,
                   metavar=("LAMIN", "LOMIN", "LAMAX", "LOMAX"))
    x.add_argument("--out")
    s.set_defaults(fn=cmd_spatial)

    s = sub.add_parser("factory", help="business factories")
    fs = s.add_subparsers(dest="fac_cmd", required=True)
    fs.add_parser("list")
    x = fs.add_parser("activate")
    x.add_argument("name")
    x.add_argument("--approval-ref", required=True)
    x = fs.add_parser("deactivate")
    x.add_argument("name")
    s.set_defaults(fn=cmd_factory)

    s = sub.add_parser("factory-run", help="start / advance a factory run")
    frs = s.add_subparsers(dest="fr_cmd", required=True)
    x = frs.add_parser("start")
    x.add_argument("name")
    x.add_argument("objective")
    for name in ("advance", "show"):
        x = frs.add_parser(name)
        x.add_argument("run_id")
    x = frs.add_parser("confirm")
    x.add_argument("run_id")
    x.add_argument("item")
    x = frs.add_parser("facts")
    x.add_argument("run_id")
    x.add_argument("domain", help="gate domain, or tool_args")
    x.add_argument("file")
    x = frs.add_parser("approval")
    x.add_argument("run_id")
    x.add_argument("capability")
    x.add_argument("file")
    s.set_defaults(fn=cmd_factory_run)

    s = sub.add_parser("opportunity", help="Opportunity Miner: rank opportunities")
    s.add_argument("file")
    s.set_defaults(fn=cmd_opportunity)

    s = sub.add_parser("economics", help="costs, revenue, metrics, usage")
    es = s.add_subparsers(dest="eco_cmd", required=True)
    x = es.add_parser("cost")
    x.add_argument("kind")
    x.add_argument("usd", type=float)
    x.add_argument("--agent")
    x.add_argument("--mission")
    x.add_argument("--provider")
    x.add_argument("--note")
    x = es.add_parser("sale")
    x.add_argument("gross", type=float)
    x.add_argument("--mission")
    x.add_argument("--factory")
    x.add_argument("--customer")
    x.add_argument("--new-customer", action="store_true")
    x.add_argument("--platform-fee", type=float, default=0.0)
    x.add_argument("--payment-fee", type=float, default=0.0)
    x = es.add_parser("hours")
    x.add_argument("hours", type=float)
    x.add_argument("--mission")
    x = es.add_parser("metrics")
    x.add_argument("--days", type=int)
    es.add_parser("usage")
    s.set_defaults(fn=cmd_economics)

    s = sub.add_parser("books", help="accounting evidence, payees, 1099s, payouts")
    bs = s.add_subparsers(dest="books_cmd", required=True)
    x = bs.add_parser("record")
    x.add_argument("file")
    bs.add_parser("invoice-number")
    x = bs.add_parser("payee")
    x.add_argument("payee_id")
    x.add_argument("--name-ref", required=True)
    x.add_argument("--country", required=True)
    x.add_argument("--form", choices=["W-9", "W-8BEN", "W-8BEN-E"])
    x.add_argument("--tin-on-file", action="store_true")
    x = bs.add_parser("info-returns")
    x.add_argument("year", type=int)
    x = bs.add_parser("payout")
    x.add_argument("payee_id")
    x.add_argument("amount")
    x.add_argument("--ownership-resolved", action="store_true")
    x.add_argument("--sanctions", default="NOT_SCREENED")
    s.set_defaults(fn=cmd_books)

    s = sub.add_parser("sanctions", help="OFAC screening")
    ss = s.add_subparsers(dest="san_cmd", required=True)
    x = ss.add_parser("import")
    x.add_argument("file")
    x.add_argument("--fetched-at", required=True)
    x = ss.add_parser("screen")
    x.add_argument("name")
    x.add_argument("--country")
    x.add_argument("--region")
    s.set_defaults(fn=cmd_sanctions)

    s = sub.add_parser("incident", help="incident management")
    ins = s.add_subparsers(dest="inc_cmd", required=True)
    x = ins.add_parser("open")
    x.add_argument("title")
    x.add_argument("--cls", required=True)
    x.add_argument("--severity", required=True)
    x.add_argument("--personal-data", action="store_true")
    x.add_argument("--jurisdiction", action="append")
    x = ins.add_parser("advance")
    x.add_argument("incident_id")
    x.add_argument("note")
    ins.add_parser("list")
    s.set_defaults(fn=cmd_incident)

    s = sub.add_parser("legal-pages", help="generate and version legal pages")
    lp = s.add_subparsers(dest="lp_cmd", required=True)
    x = lp.add_parser("generate")
    x.add_argument("--page", action="append")
    x.add_argument("--jurisdiction", default="US")
    x.add_argument("--legal-basis", default="see registry")
    x.add_argument("--effective-date", default=dt.date.today().isoformat())
    x = lp.add_parser("approve")
    x.add_argument("page")
    x = lp.add_parser("show")
    x.add_argument("page")
    s.set_defaults(fn=cmd_legal_pages)

    s = sub.add_parser("data", help="data governance and tracking")
    ds = s.add_subparsers(dest="data_cmd", required=True)
    x = ds.add_parser("register")
    x.add_argument("file")
    x = ds.add_parser("may")
    x.add_argument("data_id")
    x.add_argument("use")
    ds.add_parser("expired")
    ds.add_parser("tracking")
    s.set_defaults(fn=cmd_data)

    s = sub.add_parser("platform", help="platform policy registry")
    ps = s.add_subparsers(dest="pl_cmd", required=True)
    x = ps.add_parser("add")
    x.add_argument("file")
    x = ps.add_parser("check")
    x.add_argument("platform")
    s.set_defaults(fn=cmd_platform)

    s = sub.add_parser("network", help="network trust")
    ns = s.add_subparsers(dest="net_cmd", required=True)
    ns.add_parser("status")
    x = ns.add_parser("remember")
    x.add_argument("level", choices=["trusted", "limited"])
    s.set_defaults(fn=cmd_network)

    s = sub.add_parser("sandbox", help="run untrusted code in rootless podman")
    s.add_argument("repo")
    s.add_argument("--intake-state", required=True)
    s.add_argument("--approved", action="store_true")
    s.add_argument("--execute", action="store_true", help="default is a dry run")
    s.add_argument("cmd", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_sandbox)

    s = sub.add_parser("a11y", help="accessibility lint and keyboard shortcuts")
    acs = s.add_subparsers(dest="a11y_cmd", required=True)
    x = acs.add_parser("lint")
    x.add_argument("file")
    x = acs.add_parser("shortcut")
    x.add_argument("command")
    x.add_argument("key")
    x.add_argument("--danger", default="LOW")
    x.add_argument("--confirm", action="store_true")
    acs.add_parser("shortcuts")
    s.set_defaults(fn=cmd_a11y)

    s = sub.add_parser("baseline", help="golden baseline and controlled updates")
    bls = s.add_subparsers(dest="bl_cmd", required=True)
    x = bls.add_parser("create")
    x.add_argument("out")
    x = bls.add_parser("verify")
    x.add_argument("manifest")
    x = bls.add_parser("update")
    x.add_argument("component")
    x.add_argument("version")
    x.add_argument("stage")
    x.add_argument("--evidence", required=True)
    s.set_defaults(fn=cmd_baseline)

    s = sub.add_parser("graph", help="capability graph / regulation impact")
    gr = s.add_subparsers(dest="graph_cmd", required=True)
    gr.add_parser("show")
    x = gr.add_parser("impact")
    x.add_argument("reg_id")
    s.set_defaults(fn=cmd_graph)

    s = sub.add_parser("governor", help="watchdog that keeps BAU running while you are away")
    gv = s.add_subparsers(dest="gov_cmd", required=True)
    x = gv.add_parser("tick", help="run all checks and safe repairs once (timer runs this)")
    x.add_argument("--no-resume", action="store_true", help="re-queue jobs but do not rerun")
    gv.add_parser("status")
    x = gv.add_parser("digest", help="while-you-were-away report")
    x.add_argument("--hours", type=float, default=24)
    x = gv.add_parser("hold", help="stop everything except read-only actions")
    x.add_argument("reason")
    gv.add_parser("release", help="human: lift a hold")
    x = gv.add_parser("close", help="human: close a finding you have dealt with")
    x.add_argument("finding_id")
    x.add_argument("--note")
    s.set_defaults(fn=cmd_governor)

    s = sub.add_parser("brain", help="Second Brain: your business as linked notes")
    bs = s.add_subparsers(dest="brain_cmd", required=True)
    x = bs.add_parser("say", help='e.g. "Product team runs Slack questions which consumes '
                                  'tickets and produces answers"')
    x.add_argument("sentence")
    x = bs.add_parser("note", help="create/update a note")
    x.add_argument("title")
    x.add_argument("--type")
    x.add_argument("--data-class", choices=["PUBLIC", "INTERNAL", "CONFIDENTIAL", "PERSONAL",
                                            "SENSITIVE_PERSONAL"])
    x.add_argument("--body")
    bs.add_parser("import", help="seed from agents, models, factories, missions")
    bs.add_parser("lint", help="gaps: incomplete workflows, broken links, personal data")
    bs.add_parser("workflows")
    x = bs.add_parser("context", help="what a model would be given for a question")
    x.add_argument("query")
    x.add_argument("--hops", type=int, default=1)
    x = bs.add_parser("graph")
    x.add_argument("--out")
    s.set_defaults(fn=cmd_brain)

    s = sub.add_parser("youtube", help="review-and-upload to YouTube, made-for-kids built in")
    yt = s.add_subparsers(dest="yt_cmd", required=True)
    x = yt.add_parser("login", help="connect your YouTube channel (opens Google sign-in)")
    x.add_argument("--port", type=int, default=3456)
    yt.add_parser("logout")

    def video_args(x, many=False):
        x.add_argument("video")
        x.add_argument("--title", required=True)
        x.add_argument("--description", default="")
        x.add_argument("--description-file")
        x.add_argument("--tags", help="comma-separated")
        x.add_argument("--kids", action="store_true",
                       help="made for kids: runs the kids checks and sets the audience")
        x.add_argument("--licensed", action="store_true",
                       help="you hold a licence for any third-party characters used")
        x.add_argument("--paid-promotion", action="store_true")
        x.add_argument("--not-ai", action="store_true", help="only for human-made videos")
    x = yt.add_parser("add", help="queue a finished video for review")
    video_args(x)
    x.add_argument("--category", help="1 Film & Animation, 10 Music, 24 Entertainment, "
                   "27 Education")
    x = yt.add_parser("queue")
    x.add_argument("--all", action="store_true")
    yt.add_parser("review", help="review queued videos; your 'y' uploads")
    yt.add_parser("status", help="refresh processing status of uploaded videos")
    s.set_defaults(fn=cmd_youtube)

    s = sub.add_parser("publish", help="one video to several platforms (YouTube, TikTok...)")
    ps = s.add_subparsers(dest="pub_cmd", required=True)
    ps.add_parser("platforms", help="platforms BAU can publish to")
    ps.add_parser("queue", help="everything waiting for review, all platforms")
    x = ps.add_parser("add", help="queue one video to several platforms")
    video_args(x)
    x.add_argument("--to", required=True, help="comma-separated, e.g. youtube,tiktok")
    s.set_defaults(fn=cmd_publish)

    s = sub.add_parser("tiktok", help="review-and-post to TikTok (your click posts it)")
    tt = s.add_subparsers(dest="tt_cmd", required=True)
    x = tt.add_parser("login", help="connect your TikTok account (opens TikTok login)")
    x.add_argument("--port", type=int, default=3455)
    tt.add_parser("logout")
    x = tt.add_parser("add", help="queue a finished video for review")
    x.add_argument("video")
    x.add_argument("--caption", required=True)
    x.add_argument("--not-ai", action="store_true", help="only for human-made videos")
    x = tt.add_parser("queue")
    x.add_argument("--all", action="store_true")
    x = tt.add_parser("review", help="review queued videos; 'y' posts immediately")
    x.add_argument("--draft", action="store_true", help="send to TikTok drafts instead")
    tt.add_parser("status", help="refresh processing status of posted videos")
    s.set_defaults(fn=cmd_tiktok)

    s = sub.add_parser("gateway", help="list gateway capabilities")
    s.set_defaults(fn=cmd_gateway)

    s = sub.add_parser("jarvis", help="talk to Jarvis: spoken briefing, conversation, "
                       "actions you confirm")
    s.add_argument("--port", type=int, default=8766)
    s.add_argument("--text", action="store_true", help="talk in this terminal instead")
    s.add_argument("--no-browser", action="store_true")
    jv = s.add_subparsers(dest="jv_cmd")
    x = jv.add_parser("config", help="how Jarvis addresses you, which model, which voice")
    x.add_argument("--call-me")
    x.add_argument("--model", help="registered, approved model id (default claude-opus-5-5)")
    x.add_argument("--voice-id", help="ElevenLabs voice id")
    x.add_argument("--listen", choices=["elevenlabs", "browser"],
                   help="where push-to-talk audio is transcribed")
    s.set_defaults(fn=cmd_jarvis)

    s = sub.add_parser("ui", help="Mission Control web dashboard (localhost, read-only)")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(fn=cmd_ui)
