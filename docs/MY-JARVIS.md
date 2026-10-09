# My Jarvis OS: spec to code, and the build order

The *My Jarvis OS* specification (BAUBSA internal engineering spec) describes a
bootable AI operating environment.

The decision was to grow it out of BAU, in this repository, rather than start over. Most
of the spec's safety model already exists here. The parts it adds are built phase by
phase, each as one finished, tested pull request.

## The 369 architecture in this repository

| Spec | Here | Status |
|---|---|---|
| 3 · Jarvis (question, reason, plan, act) | `assistant.py`, `jarvis.py` (missions), `ui/jarvis_server.py` | Conversation, tools, owner-confirmed actions, missions with compliance gates |
| 6 · God's Eye (observe, verify, audit) | `governor.py` (watch, hold, quarantine; never approves), `audit.py` (hash-chained, HMAC-signed) | Health checks and findings; wider monitoring and event records are Phase 8 |
| 9 · Learning Engine | Not built | Phase 11 (Self-Lab) |
| Protected core (§9) | Human-only SSH-signed approvals, registry validation, `baseline.py` (TEST, CANARY, VALIDATE, PROMOTE), hardening | Enforced: no agent, model or the Governor can approve |
| No false success (§69) | Decision engine (missing facts are never a pass), `bau models bench` (no fake availability), Jarvis stages actions and the owner confirms | Enforced and tested |
| Memory (§17-19) | Second Brain (`brain.py`), Jarvis memory lane, history | MCP Memory Service and the memory firewall are Phase 5 |
| Model router (§22-24, 48) | `models/router.py`, registry with benchmark-before-approval, Claude, then GLM, then Qwen-1.5B, then basic | LiteLLM gateway is Phase 6, the AMD worker Phase 12 |
| MCP (§33) | `mcp.py` registry records (permissions, network, credentials, sandbox) | Live MCP servers are Phase 7 |
| Secrets (§62) | Keys created on the machine, never in Git or the image; `bau secrets` scan in CI | Enforced |

## Boot model

Both ways of running are supported:

- **Live USB (new, MVP #1):** `image/` builds a Debian 13 live system. You boot from the
  USB every time. Private state lives in a LUKS2 container on the same USB, opened at
  boot. Only `/home`, `/etc/bau`, `/var/lib/bau` and saved Wi-Fi persist; the rest of the
  system is read-only and resets on reboot. Owner guide: `LIVE-USB.md`.
- **Install to disk (existing):** USB #1 installs encrypted Debian on a laptop, and
  USB #2 installs BAU. The sticks are then put away. Owner guide: `INSTALL.md`.

### Live USB design

| Spec | Implementation |
|---|---|
| §4 Debian, no custom kernel | live-build, Debian 13 trixie, stock kernel (`image/live-build/auto/config`) |
| §5 USB layout | Hybrid ISO (EFI + live system), then the encrypted partition in the remaining space |
| §6-7 Controlled, encrypted persistence | `persistence-encryption=lukslabel`: live-boot opens only a LUKS2 container labelled `persistence` and never uses plain storage. `persistence.conf` lists exactly what persists. `jarvis-storage setup` creates it and never deletes a partition. |
| §7 No unprotected substitute | `bau-live-init`: without unlocked encrypted storage it is LIMITED mode, where no keys are created and BAU services stay off |
| §53 Boot menu | My Jarvis, limited mode, safe graphics, recovery, UEFI firmware settings, integrity check |
| §23 Lightweight local model | Qwen2.5-1.5B-Instruct Q4_K_M, about 1.1 GB, Apache-2.0. Downloaded to the encrypted storage and pinned by SHA-256 (`bau models fetch`). Served by llama.cpp v0.6.0, which is built from pinned source with per-CPU backends. It must pass `bau models bench`, then the owner approves it. |
| §55-56 Image versioning and pipeline | `image/VERSION` and `image/build-live.sh` → ISO, `.sha256` and `.manifest.json` (git commit, kernel, llama.cpp, package list); `.github/workflows/build-live.yml` |
| §57 Boot test | QEMU/OVMF test of the real image: boot, create storage, unlock, Jarvis answers, reboot, memory still there |

## MVP #1 (this phase)

```
BOOT USB → UNLOCK (passphrase) → DESKTOP → NETWORK → JARVIS SETUP
→ LOCAL MODEL (fetched, verified, benchmarked, owner-approved)
→ ASK A QUESTION → ANSWER → REMEMBER → REBOOT → MEMORY STILL THERE
```

## Architecture principle: structure before frameworks (ICM)

Since 2026-10-07 the plan follows **Interpretable Context Methodology**: folder structure as
agent architecture. Sources: Van Clief & McDermott, arXiv:2603.16021, MIT licence, and
github.com/RinDig/icm-architect. The paper is a design proposal; we treat it as design
discipline, not measured performance.

The idea is that, for sequential, human-checked, repeatable work, one agent walking
well-made folders does what a multi-agent framework would:

- numbered stage folders carry the order;
- each stage's `CONTEXT.md` names exactly which files it reads;
- outputs are plain files the owner edits before the next stage reads them.

Most of BAU's business is that kind of work: episodes, books, client deliverables.

How this changes the plan:

- **Factories become ICM workspaces first** (`bau ws`, `src/bau/workspace.py`). The
  pilot is the kids channel (`data/workspaces/kids-channel/`). The owner's check on each
  stage is recorded with a SHA-256 of the output, so editing afterwards voids it. Kids
  rules run on the stages that list them, and every draft and check is in the audit chain.
- **Small and free models become useful.** A stage loads about 2k-8k tokens, so a step
  fits Qwen-1.5B's 8k context or a free hosted model. A stage that would overflow the
  model is refused, never silently cut.
- **Several spec "engines" are structures, not new software.** Missions become a record
  library. The question graph and evidence become a knowledge bundle with typed
  frontmatter. Skills become workspaces and templates.
- **Frameworks only where ICM honestly loses:** real-time loops (God's Eye watching
  live), many users at once (the public product), and the system branching on its own
  mid-run. Hermes, OpenHands and LiteLLM come in for those cases, not by default.

What ICM doesn't replace in BAU: the signed approvals, the tamper-evident audit chain,
the locked core (no agent edits `_shared/`, policies or regulations), and `untrusted()`
wrapping of anything from outside.

## Build order from here (spec §87)

Each phase is one pull request with tests, and is boot-tested where it touches the image.

| Phase | Content | Notes |
|---|---|---|
| 0-3 | Repository, base image, encrypted persistence, system tools | **Done in MVP #1** (main stays protected by PR + CI) |
| 4 | **ICM workspaces** (structure before frameworks): `bau ws`, kids-channel pilot; then the other factories (faceless media, books, digital assets) as workspaces | **Pilot done 2026-10-07.** Next: run real episodes with the free Z.ai model, then convert the next factory |
| 4b | Hermes as executive, behind an adapter (`upstream/` pinned by commit, licence recorded) | Only for what workspaces can't do (live loops, concurrency). Verify Hermes' repo and licence first |
| 5 | MCP Memory Service, provenance fields, memory firewall (trust score, then validation, then persist) | Extends the Second Brain; nothing auto-trusted |
| 6 | LiteLLM gateway in front of the existing router | Router stays replaceable; routing decisions logged |
| 7 | MCP servers with explicit capability profiles (default DENY) | Uses the existing `mcp` registry kind |
| 8 | God's Eye: wider observation, event records (§21), "green means verified" | Grows from the Governor |
| 9 | OpenHands engineering worker in a sandbox; PRs only, never push to main | GitHub-hosted or ephemeral runners, never this laptop as a public runner |
| 10 | Question graph and evidence as a knowledge-bundle workspace; Capability Registry; Repo Scout | **Repo Scout started 2026-10-09** (`bau scout`, `docs/engineering/repo-intelligence.md`): discovery, evidence, licence/security gates, quarantine + Sentinel inspection. Next: sandbox validation reports, licence review record, adapter interface, first integration. Discovery ≠ installation |
| 11 | Self-Lab: trajectories, regression database, challenge generator, promotion gates | |
| 12 | AMD Developer Cloud worker (ROCm + vLLM, one model, one benchmark), create-run-destroy discipline | Read credit terms from the AMD dashboard, never hard-code them |
| 13 | Model training (LoRA/QLoRA, DPO …) | Only with enough trajectories and benchmarks |
| 14 | Public product, separated from internal Jarvis | Customer data is never training data without consent |

Rules carried over from the spec into CLAUDE.md's rules: never weaken the host; approvals
are human-only; no false success; local models need a real benchmark; secrets are never
in Git or the image; every behaviour change gets a test.
