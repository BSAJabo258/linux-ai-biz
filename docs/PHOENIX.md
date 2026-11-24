# Phoenix / Mycelium: Phase 0 audit

The owner's specification of 2026-11-24 ("JARVIS — BAUBSA PHOENIX / MYCELIUM") asks for a
business engine that runs one loop: discover, verify, acquire, transform, sell, collect,
reconcile, allocate, reinvest, repeat. Its Part XVIII, step 41, says to begin by reading the
existing Jarvis and building on it, never a second one. This page is that reading: what BAU
already has for each part, what is missing, and the order to build the missing parts.

It describes the code as it is on 2026-11-24. Nothing here is built yet unless the table says
so. `CLAUDE.md` is the project index the spec asks for (one row per module).

## What exists, part by part

| Spec part | BAU today | State |
|---|---|---|
| Command center, voice, GUI (XVI) | Jarvis (`assistant.py`, `ui/jarvis.html`), the operations world with tabs and agent panels (`world.py`, `docs/WORLD.md`), Mission Control | have |
| Orchestration (X) | missions through the executive controller (`executive.py`, `jarvis.run_checked`), agent folders (`agentfolders.py`), the team's boss model (`team.py`), the supervisor (`supervisor.py`) | have |
| Durable time engine (IX) | systemd timers (autopilot every 30 min, Governor every 10 min, nightly updates), jobs with atomic checkpoints and reboot recovery (`jobs.py`), the Governor resumes or pauses jobs a crash left running | have (no event bus) |
| Tools and permissions (XII, XIII) | the gateway: every agent action checked for permission, budget, HOLD and network trust (`gateway.py`, `security/permissions.py`); MCP servers pinned by schema (`mcp.py`) | have |
| Approvals (XIII) | money, legal and commercial email signed by the owner's SSH key (`bau approve`); every other consequential act staged on a card | have |
| Audit (XIII) | tamper-evident hash chain (`audit.py`), evidence packages (`evidence.py`), incidents (`incidents.py`) | have |
| Knowledge (XI) | the Second Brain (`brain.py`, a graph of Markdown notes), chat library (`chats.py`), data use rights (`datagov.py`) | partial: no claim/evidence records with dates and contradictions |
| Opportunity discovery (III) | the Opportunity Miner ranks on evidence (`opportunity.py`); web research (`web.py`); Repo Scout | partial: no connectors to SAM.gov, USAspending or Grants.gov |
| Compliance (XIII) | regulations with sources and review dates (`regulations.py`, `data/regulations/`), policies, the legal review queue (`legal_queue.py`), jurisdiction (`jurisdiction.py`), sanctions screening (`sanctions.py`), tax-nexus flags (`commerce/tax.py`) | have |
| Outreach (IV.D) | the commercial email gate: CAN-SPAM classification, list source, consent, suppression, SPF/DKIM/DMARC, postal address, one-click unsubscribe (`comms/email.py`, `comms/consent.py`) | have (no sending account set up) |
| Procurement (IV) | payees and 1099 tracking, payouts prepared and executed only with signed approval (`accounting.py`) | **missing**: suppliers, donors, RFQ, quote comparison, purchase orders, receiving, three-way match |
| Materials, production, inventory (V, VI) | none | **missing** |
| Sales and commerce (VII) | subscriptions (`commerce/subscriptions.py`), Fanvue sales and fan chat | **missing** for goods: customers, quotes, orders, fulfillment, invoices |
| Treasury and ledger (VIII) | cost and revenue lines, budgets, per-mission profit and loss (`economics.py`), Fanvue earnings synced once each | partial: single-entry lines; **no double-entry journal**, no reconciliation runs, no allocation policy |
| Payment providers (VIII.17) | PayPal (`paypal.py`, 2026-11-24: invoices, checkout, capture, signed refunds and payouts, settled payments into the ledger once; `docs/PAYPAL.md`); Fanvue pays the creator directly | have PayPal; Stripe, Plaid not built |
| Metrics (XX) | usage meter (`usage.py`), money machine status (`money.py`), economics dashboard | partial |

## The stack the spec names, against BAU's rules

| Component | Decision | Why |
|---|---|---|
| n8n | **not used** | its licence is the "Sustainable Use License" ("only for your own internal business purposes", read 2026-11-24 in its LICENSE.md): fair-code, which the owner's free-open-source rule excludes |
| PostgreSQL + pgvector | not now | BAU keeps its records in atomic JSON and YAML files with an audit chain; nothing yet needs a database server on the laptop. It joins when record volume or search needs prove it (`.claude/skills/grow-bau`: measure, then add) |
| Temporal | not now | systemd timers plus checkpointed jobs already give schedules that survive restarts. Temporal joins if the procurement and sales flows need waiting timers BAU cannot keep simply |
| LangGraph | not now | the executive controller and agent folders already route work with approval gates; a second orchestrator is what the spec itself forbids |
| OpenHands | not now | `hands.py` (terminal jobs, every command on the owner's y) and the self lab (`selfmod.py`, sandboxed tests) cover the approved coding and computer tasks |
| Stripe, Plaid | owner's decision | each needs a business account the owner opens and verifies; built as adapters behind the gateway's `move.money` approval, sandbox first |

## The build order (dependency first, money first)

1. **Discovery connectors**, read only: USAspending (no key), Grants.gov, SAM.gov (a free key;
   its pages give non-federal users 10 requests a day). Each result becomes an opportunity with
   its evidence and date in the Opportunity Miner. No money, no outreach.
2. **Double-entry ledger** in exact decimals: balanced journal entries, reversing entries
   instead of edits, built on today's revenue and cost lines so nothing is lost.
3. **Procurement records**: suppliers and donors (with documented permission), RFQs, quote
   comparison by total landed cost, purchase orders, receiving and inspection, three-way match.
   A purchase order is executed only on the owner's signed approval.
4. **Inventory lots and production orders**, with actual unit cost and yield.
5. **Sales**: customers, quotes, orders, invoices; a payment-provider adapter in its sandbox.
6. **Treasury**: settlement checks, reconciliation runs, the owner's allocation policy (his
   percentages, never defaults), available reinvestment.

Each step ships as one feature with tests, the full check, and a page for the owner, as every
BAU feature does. The spec's pilot (salon hair recovery, Part XV §46) needs steps 1 to 6.

## What stays with the owner

Every payment, transfer, purchase order, contract, bid, loan and new payee is signed by the
owner (`bau approve`); every outreach email passes the commercial email gate. These are BAU's
existing rules and the spec's own Part XIII; nothing in this build loosens them.
