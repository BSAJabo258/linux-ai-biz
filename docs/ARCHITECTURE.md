# Architecture: How the Spec Maps to This Code

## Principle

BAU owns the control plane; everything else is a replaceable capability (spec §0, §111-112). This repository is the **trust plane + compliance control plane + installer**: the part everything else must pass through. Models, agents, media engines and factories plug in later as adapters behind it.

```
           objective / job
                 |
      +----------v-----------+      facts      +------------------+
      | domain fact extractor | --------------> |  policy compiler |  <- policies/*.yaml
      | email sms subscription|                 |  (one decision   |  <- regulations/*.yaml
      | publish chatbot ip    |                 |   path)          |     (legal_status x bau_status,
      +-----------------------+                 +--------+---------+      dates, sources)
                                                         | Decision (8 states)
                        +--------------------------------+-------------------+
                        |                                |                   |
                 PASS -> proceed       PASS_WITH_REVIEW -> signed human approval    else -> stop
                        |                                |
                        +----------> evidence package + hash-chained, HMAC-signed audit log
```

## The decision model (`decision.py`, `policy.py`)

**States:**
- PASS
- NOT_APPLICABLE
- PASS_WITH_REVIEW
- INCOMPLETE_FACTS
- UNKNOWN
- EXPIRED
- CONFLICT
- BLOCKED

When findings are combined, the worst state wins. An empty evaluation is UNKNOWN, never PASS.

**Three-valued logic:** a missing fact is `None`, which can only produce INCOMPLETE_FACTS, never a pass.

**Date-awareness:** each regulation computes `in_force | future | unknown_date | not_law | dead` for the decision date:
- vacated/repealed rules are not enforced;
- proposed rules are not law;
- enacted rules with an unknown operative date are enforced as a precaution.

**Asymmetry:**
- a failing requirement blocks whatever the review status of its regulation;
- a passing one gives a clean PASS only when every cited regulation is ACTIVE (human-signed);
- a regulation past `next_review` turns a pass into EXPIRED.

**Jurisdiction:**
- ISO 3166 codes (`CA` = Canada, `US-CA` = California).
- An unknown location expands to the strictest union of every rule set.
- Each domain declares its `coverage`. A jurisdiction outside it is UNKNOWN, or PASS_WITH_REVIEW if only partly covered.

**Conflict:** policies may `set` a value (e.g. `consent_model`). Differing values resolve to the strictest when an ordering is declared; otherwise the result is CONFLICT (spec §117).

**Compile-time safety:** an unknown operator, unknown on_fail state, duplicate ID or **reference to a nonexistent regulation** refuses to load.

## Spec section → implementation

| Spec | Implementation |
|---|---|
| §1.2, §99 untrusted content / prompt injection | `agents.py` (`untrusted()` wrapping, injection flagging, constitution), memory and Genesis prompts |
| §1.4 secrets | `security/secrets_scan.py`, CI secret scan, keys generated on-machine; sandbox and MCP refuse secrets in config |
| §1.5, §96-97 evidence + audit | `audit.py` (hash chain, HMAC, PII refusal, anchor), `evidence.py` |
| §3, §90, §104-105 OS, golden baseline, updates | `installer/` (Debian, LUKS, preseed, hardening), `baseline.py` (freeze, verify drift, TEST→CANARY→VALIDATE→PROMOTE) |
| §4 hardware gate | `hardware.py`, `installer/hw-audit.sh`, `hw-audit-windows.ps1` |
| §4.1 backup | `backup.py` (manifest + read-back verify) |
| §5 wipe gate | `wipe_gate.py`, `write-usb.sh` record, `install.sh` import |
| §6 K3 | registered as OFFLOAD in `data/registry_defaults.yaml`; reached through `models/providers.LocalHTTPProvider` |
| §7-8, §113, §122, §125 Jarvis + missions | `jarvis.py`, `data/missions.yaml` (compliance dependencies per mission type) |
| Governor (owner-away oversight) | `governor.py`, `bau-governor.timer`, `bau governor ...` (see below) |
| Second Brain (memory you own, model-agnostic) | `brain.py`, `bau brain ...`, Mission Control *Second Brain* view, agent tool `memory.brain`: one Markdown note per noun in `BAU_HOME/brain/` (Obsidian-compatible), typed verb edges, sentences compiled to workflows, system import, gap lint, data-class-filtered context for any model |
| TikTok review-and-post (§80) | `tiktok.py`, `bau tiktok ...`: OAuth (PKCE) login, queue with pre-checks (claims, provenance, publish gate, platform record), interactive review that shows what TikTok's Content Sharing Guidelines require; the owner's 'y' uploads (chunked) and posts via the Content Posting API, or sends to drafts. Only a human at a terminal can post; tokens in `BAU_HOME/secrets/tiktok.json` (0600) |
| §9-12, §74-75, §114-118 compliance engine | `regulations.py`, `policy.py`, `decision.py`, `jurisdiction.py` |
| §13-16, §77, §80-81 AI disclosure + likeness | `disclosure.py`, `policies/ai_disclosure.yaml`, media gateway provenance |
| §17-18, §26, §82-83, §101 data governance | `datagov.py` (data objects, use rights, provider boundary, tracking registry) |
| §19-20 data rights | `privacy/dsr.py` (deadlines, per-store deletion outcomes) |
| §21 consent | `comms/consent.py` |
| §22-23, §79 subscriptions + cancellation | `commerce/subscriptions.py`, `policies/commerce.yaml` |
| §24-25 claims | `claims.py` |
| §33, §120 high-impact actions, legal review queue | `data/missions.yaml` (`high_impact`, `legal_review`), `legal_queue.py` |
| §34 NIST AI RMF | registry record `nist-ai-rmf`; GOVERN = policies/approvals, MAP = mission planning, MEASURE = evidence/metrics, MANAGE = incidents/revocation |
| §35 incidents | `incidents.py` (stage order, notification clocks, evidence anchoring) |
| §36-37, §111 Sentinel | `security/sentinel.py` (static only, canonical state machine) |
| §38-41 Project Genesis | `genesis.py` (ChatGPT/Claude/Markdown importers, dedupe, extraction, status tags, contradictions, 22 canonical drafts) |
| §42 MAYA Memory Lane | `memory.py` (hash-linked Markdown records, BM25 search, resume phrases, deterministic export) |
| §43, §94 capability graph + legal-change impact | `capgraph.py` (`bau graph impact <reg_id>`) |
| §44-47 models, router, trust, Heretic | `registry.py`, `models/providers.py` (Claude via official SDK with refusal fallbacks; llama.cpp/Ollama; scripted), `models/router.py`, `models/heretic.py` |
| Content lane (owner decision, amends §46-47) | an ABLITERATED local model may be approved with `lane: content_only` + `use_for` (creative_writing, script, lyrics, comedy, ad_copy, image_prompt, storyboard). The router uses it only for those jobs, never with tools or data beyond PUBLIC/INTERNAL, and prefers it there; agents refuse to give it tools; every use is audited (`model.content_lane`); it can never be the Governor's validator. Example: `examples/content-lane-model.yaml` |
| §48, §102 agents + budgets | `agents.py`, `economics.Budgets` |
| §49, §55, §73 permissions / revocation / money | `security/permissions.py` (SSH-signed human approvals, `bau approve`), `accounting.prepare_payout` |
| §50 Universal Gateway | `gateway.py` (one ordered check path, audit on allow and deny) |
| §51 MCP router | `mcp.py` (stdio JSON-RPC client; each approved tool becomes its own gated capability) |
| §52-53 network + endpoint trust | `network.py` |
| §54 blast radius | `blast.py` (escalates approval requirements in the gateway) |
| §56-58 media + music video | `media/gateway.py` (FFmpeg + HTTP adapters, provenance sidecars, C2PA when available), `media/music.py` (beat grid, sections, drops, edit decision list) |
| §59 God's Eye | `spatial.py` (USGS, OpenSky, CelesTrak; person-targeting refused) |
| §60-65 business factories | `factories.py`, `data/factories.yaml` (six factories, inactive by default), `bau factory-run` |
| §61 Opportunity Miner | `opportunity.py` |
| §66-67 IP + royalties | `commerce/ip.py` |
| §68-72 tax, accounting evidence, 1099s | `commerce/tax.py`, `accounting.py` |
| OFAC (gap G-06) | `sanctions.py` |
| §76, §78 legal pages + terms versioning | `legal_pages.py` (drafts from live data, material-change detection, counsel approval) |
| §80 platform policies | `platforms.py` (policy registry, file-drop connector) |
| §84-85 economics + usage dashboard | `economics.py` |
| §86-89 jobs, checkpoints, recovery, offline | `jobs.py`, `bau recover` (audit + memory + registries), WAITING_FOR_NETWORK in gateway |
| §92-93 regulation watcher | `regulations.watch`, `bau-regwatch.timer`, `bau reg promote` |
| §95 Mission Control | `ui/` (localhost, read-only, keyboard-first, command palette), `status.py` |
| §100 sandbox | `sandbox.py` (rootless podman, no network, read-only, caps dropped) |
| §28-30 accessibility | `accessibility.py` (WCAG lint, shortcut registry); CLI and Mission Control are keyboard-only |
| Outbound comms (gap G-01) | `comms/email.py`, `comms/sms.py`, `comms/dns_auth.py` |

### What "complete" means here

Every layer in spec §2 has working, tested code. What cannot be finished from a repository is
listed in `bau status`:
- counsel sign-off on regulations;
- your domain's DNS records and the FCC wireless list;
- a CPA's tax rules;
- approving models and agents;
- the real storefront;
- the on-hardware boot and restore drill;
- the first real revenue mission.

Third-party projects named in the spec (aiOS, open-context, Open-Generative-AI, God's Eye UI, Heretic, MAYA repos) plug in through the adapters above only after Sentinel review.

## Second Brain

The model is not the memory. `BAU_HOME/brain/` holds one Markdown note per *noun* - team,
role, workflow, artifact, tool, agent, model, capability, governance, factory, mission type -
with YAML frontmatter (`type`, `data_class`, `status`, `relations`) and `[[wikilinks]]`, so the
folder opens in Obsidian with the same graph view. *Verbs* are typed edges: runs, consumes,
produces, uses, owns, governs, requires, feeds, approves, monitors, blocks, publishes, sells,
serves.

* `bau brain say "Product team runs Slack questions which consumes tickets and produces
  answers"` compiles the sentence into nodes and edges (a verb after "which/that" applies to the
  previous object; after "and" to the current subject; objects split on commas and "and").
* `bau brain import` mirrors agents, models, tools, factories, mission types and their
  compliance gates into the brain; the owner's own notes are never overwritten.
* `bau brain lint` lists what is not yet automatable: workflows without an owner, inputs or
  outputs; broken links; untyped notes; e-mail addresses or phone numbers in notes not marked
  PERSONAL.
* Any model gets the same context (`memory.brain` agent tool, `bau brain context`, and the
  `brain` step of every Jarvis plan): the matching notes plus their neighbours, as plain
  Markdown, **only PUBLIC/INTERNAL notes** unless the caller explicitly allows more.

## Jarvis, the conversational front door (`assistant.py`, `ui/jarvis_server.py`)

`jarvis.py` plans missions; `assistant.py` is the presence on top: a briefing built from live
facts, a natural conversation with memory (`BAU_HOME/jarvis/history.jsonl`), and tools.

| Tool kind | Examples | Rule |
|---|---|---|
| read | status, night report, missions, TikTok queue, deadlines, money, brain lookup/gaps | runs freely |
| act | brain add, remember, plan mission, hold everything | low-risk, runs when asked, audited `jarvis.tool` |
| confirm | post to TikTok, release a hold | **staged only** (`jarvis.staged`); runs when the owner presses Confirm (`jarvis.confirmed`, actor `human:<login>`) |

* Tool results reach the model wrapped as untrusted data; only arguments declared in a
  tool's schema get through, so a model (or injected text) cannot pre-fill owner-only
  choices. TikTok privacy and commercial disclosure come only from the confirmation card,
  with no default, next to the video preview - as TikTok's sharing rules require.
* Signed approvals are never tools. Jarvis explains them and gives the `bau approve` command.
* The HUD server runs as the owner (`bau jarvis` needs a TTY), binds 127.0.0.1:8766, and
  requires a per-launch key (in the link it opens; sent as `X-Jarvis-Key`), a local Host,
  a same-origin `Origin`, and size-limited bodies. Mission Control stays read-only.
* Voice: ElevenLabs text-to-speech (cached by text) and speech-to-text when a key is
  configured; otherwise the browser's speech. Plain mode (no model) keeps the briefing and
  core commands working offline.

## Publishing hub and kids content (`publishing.py`, `youtube.py`, `kids.py`)

Every platform is an adapter in `publishing.ADAPTERS` with the same four abilities: list
what is waiting, build the confirm card (summary, owner-only choices, preview), post after
a human confirms, and say whether it accepts child-directed content. Jarvis (`publish_queue`,
`post_video`), the CLI (`bau publish`) and the queues all go through the hub. Adding
Instagram or Facebook means one adapter plus its policy record in the platform registry.

| Platform | Adapter | Owner chooses at confirm | Kids |
|---|---|---|---|
| TikTok | `tiktok.py` (Content Posting API) | privacy, commercial disclosure | never (13+) |
| YouTube | `youtube.py` (Data API v3, resumable upload) | audience (made for kids or not), privacy, full-watch confirmation for kids | yes, made for kids |

Kids rules live in the `publish` policy domain (`data/policies/kids_content.yaml`) and only
apply when a video is child-directed. `kids.scan` turns the title, description and tags into
facts: personal-info requests, links, engagement bait, purchase pressure, unsuitable themes,
sensational titles, third-party characters, and near-duplicate episodes. The rules cite
`us-coppa`, `industry-youtube-made-for-kids`, `us-ftc-act-s5`, `us-ftc-endorsement-guides`,
`us-lanham-act` and `industry-youtube-inauthentic-content` (near-copies are a review
warning, not a block). Uploads set `selfDeclaredMadeForKids` and `containsSyntheticMedia`;
paid promotion uploads go up private, because the API cannot tick the box.

## Two tiers: operator and Governor

BAU is run by two AIs with different jobs:

* **Operator** (Jarvis + agents) plans missions and does the work, always through the
  Universal Gateway.
* **Governor** (`governor.py`) watches the operator in the owner's place. Every 10 minutes
  (`bau-governor.timer` -> `bau governor tick`) it checks, in order: audit-chain integrity,
  stuck/interrupted jobs, failed or paused missions, agents hitting the gateway or tripping
  injection detection, 24h spend, red Mission Control items, disk space, and service health.
  If `config/governor.yaml` names an approved `reviewer_model`, a validator model also reads
  every finished mission's result, ideally a different model from the operator.

What the Governor fixes on its own is limited to moves that make the system safer or restore
it: mark a stuck job INTERRUPTED and resume it from its checkpoint (at most
`max_auto_resumes` times), re-queue jobs when the network returns, QUARANTINE an agent, or
put BAU on **HOLD** (the gateway then runs only READ_ONLY capabilities and Jarvis starts
nothing). Everything else becomes a finding for the owner (`bau governor digest`,
or the **Governor** view in Mission Control; a HOLD also shows as a BLACK status row).

The Governor has **no approval rights**. Approvals stay human-signed (SSH key), and only a
human can release a hold, restore a quarantined agent (`bau set-status`) or close a finding.
That asymmetry (it can stop things but never authorise them) is what makes it safe to run
unattended.

| Setting (`config/governor.yaml`) | Default |
|---|---|
| `stale_job_minutes` | 30 |
| `max_auto_resumes` | 3 |
| `denials_per_hour` (quarantine threshold) | 5 |
| `daily_spend_hold_usd` | 50 |
| `min_free_disk_pct` | 10 |
| `services` | `bau-ui.service`, `bau-regwatch.timer` |
| `reviewer_model` | none |

## Runtime layout

| Path | Owner / mode | Contents |
|---|---|---|
| `/opt/bau/venv` | root | the installed package |
| `/var/lib/bau` (`BAU_HOME`) | `bau:bau` 2770 | regulations, policies, audit, evidence, consent, suppression, dsr, jobs, reports... (spec §91 `.bau/` layout) |
| `/etc/bau/audit.key`, `unsubscribe.key` | `root:bau` 0640 | machine-generated |
| `bau-ui.service` | runs as `bau`, localhost only | Mission Control on http://127.0.0.1:8765 |
| `bau jarvis` | runs as the owner, localhost only | Jarvis HUD on http://127.0.0.1:8766 (private per-launch link) |
| `bau-governor.timer` | runs as `bau`, every 10 min | Governor tick; state in `BAU_HOME/governor/` |
| `/etc/bau/models.env` (optional) | `root:bau` 0640 | API keys for the Governor's resume runs, validator model and Jarvis (incl. `ELEVENLABS_API_KEY`) |
| `/etc/bau/allowed_signers` | `root:bau` 0644 | public keys of the humans who may approve; only root can add one |
| `~bauadmin/.ssh/bau_approval_ed25519` | the admin, passphrase-protected | the admin's personal approval signing key |

## Identities

| Account | Can | Cannot |
|---|---|---|
| `bauadmin` (human, in `bau` + `bau-approvers`) | run everything; sign approvals with a personal key (`bau approve`); promote regulations (interactive TTY only) | approve a request it made itself |
| `bau` (service; agents run here) | read/write state, sign audit records, **verify** approvals | create an approval: it holds no signing key, and only root edits `allowed_signers` |
