# AI automation: repository review

The owner's directive (2026-11-04): Phase 1 (audit BAU) and Phase 2 (research the named
repositories), before any invasive change. Nothing below was installed or run. Every fact
about an outside project was read on its own pages on 2026-11-04 (links given); anything
the pages did not say is written as **not stated**. Stars and commit counts are what the
pages showed that day.

## Phase 1: what BAU already has

Read in the code, not taken from any summary.

| Part | File | State | What matters for new tools |
|---|---|---|---|
| Universal Gateway | `src/bau/gateway.py` | working, tested | Eight checks on every call (registered, agent's tool list, HOLD, permission and approval, network trust, data boundary, blast radius, budget), audit row for allowed and denied. Verbs include `browser`; there is no `desktop` verb yet |
| Permission ladder and approvals | `src/bau/security/permissions.py` | working | READ_ONLY, LOW_RISK, REVERSIBLE, APPROVAL_REQUIRED, HIGH_IMPACT, CRITICAL. Approvals are SSH-signed by a person; the requester can never approve |
| MCP client | `src/bau/mcp.py` | working | Starts only APPROVED servers; each tool becomes its own capability `run.mcp__SERVER__TOOL`; tools default to APPROVAL_REQUIRED; the server gets a minimal environment and never BAU's keys |
| Agent loop | `src/bau/agents.py` | working | Budget checked before each step, loops stopped after `LOOP_LIMIT` (3), tool results wrapped by `untrusted()` |
| Agents as folders and skills | `src/bau/agentfolders.py` | working | Open Agent Skills format (`SKILL.md`); owner approval tied to the folder's SHA-256, so any change needs approval again |
| Sandbox | `src/bau/sandbox.py` | working | Rootless Podman: no network, read-only root, all capabilities dropped, memory/CPU/PID limits; runs only quarantined repos with a signed approval |
| Memory | `src/bau/memory.py` (MAYA Memory Lane), `src/bau/brain.py` (Second Brain) | working | Hash-linked records with status tags (EXPERIMENTAL, CURRENT, DEPRECATED, REJECTED...); memory is context, never authority |
| Repo Scout | `src/bau/scout/` | working | Search, quarantine, licence and security gates (`src/bau/security/sentinel.py` intake states) |
| Hands | `src/bau/hands.py` | working | Terminal jobs one command at a time, each on the owner's yes |
| Models | `src/bau/models/router.py`, `src/bau/models/providers.py`, `src/bau/assistant.py` (`pick_model`) | working | Hosted models first online, local llama.cpp as backup and offline |
| Executive | `src/bau/jarvis.py` | prototype | The mission walker. The Jarvis people talk to is `src/bau/assistant.py` |

The gaps BAU's own capability map (`docs/CAPABILITY-MAP.md`) already names: web
interaction, computer use, reading documents and screens, saved procedures, checking the
work. They are the same gaps the directive targets.

Corrections to the directive's assumptions:

- **Memory:** `docs/DESKTOP.md` (the owner's check report, 2026-10-23) says the desktop has
  16 GB of system memory and an RTX 3060 with 12 GB. The directive says 12 GB. Measure on
  the desktop before planning: `bau hw`.
- **The desktop session** on the stick is XFCE (`image/live-build/config/package-lists/my-jarvis.list.chroot`),
  which runs on X11. That list has no `at-spi2-core` and no browser.

## Phase 2: the repositories

### 1. Agent Desktop: https://github.com/vercel-labs/agent-desktop

- **Licence:** Apache-2.0.
- **What it is:** "Computer use for AI agents: see and operate desktop apps ... through the
  OS accessibility tree." No model inside: the calling agent (Jarvis) runs the loop.
- **Runs as:** a CLI and a C library. **MCP: yes**, `agent-desktop mcp` serves every command
  as a tool over stdio. So it fits `src/bau/mcp.py` as it is.
- **Install:** npm (Node 18+), Homebrew, or GitHub release archives with `checksums.txt`
  and build attestations. From source: Rust 1.89.0.
- **How actions work:** `snapshot` returns JSON with a ref per element
  (`@<snapshot_id>:e<n>`); `click`, `type`, `press`, `list-apps`, `list-windows`, `find`,
  `get`, `is`, `screenshot`, `launch`, `focus-window` and more. A ref from an old snapshot
  fails with `STALE_REF`; retry only when the error says `retry: safe`. Actions are
  headless by default (no pointer movement); `--headed` uses the real pointer.
- **Linux** (https://agent-browser.dev/desktop/platforms/linux, updated 2026-11-02): the
  pages name Ubuntu 24.04+ (glibc 2.35). Other distributions need an `at-spi2-core` bridge
  with fix `dc0dc33`. It needs the signed-in user's graphical session, a running AT-SPI bus
  and a window manager; over SSH or in a container it sees no apps. X11 and Wayland both
  work; pointer actions, scrolling and window control need X11. Its examples ran on Xvfb
  with openbox.
- **Unknown:** whether Debian 13's `at-spi2-core` has fix `dc0dc33` (test on the desktop);
  telemetry (not stated).
- **Activity:** 14.2k stars, 328 commits.
- **Decision: integrate** (adapter through BAU's MCP client). It is the cleanest fit:
  no second brain, structured refs instead of guessing from screenshots, and the
  snapshot-after-action loop is the verification step.

### 2. Cua: https://github.com/trycua/cua

- **Licence:** MIT for most of it. Cua Spaces and Cua Driver Bench are FSL-1.1-MIT
  (source-available; each release becomes MIT after two years); `cua-som` is AGPL-3.0;
  the optional `cua-perception` extension carries AGPL obligations.
- **What it is:** computer-use drivers, sandboxes (gVisor containers), Lume VMs (Apple
  Silicon only), small models and a benchmark.
- **Install:** `curl ... | bash` scripts, `pip install cua`. Several of its own packages are
  deprecated, one ("cuabot") with "known security issues".
- **Linux driver details:** on a page not read yet.
- **Activity:** 31.7k stars.
- **Decision: study.** It overlaps Agent Desktop. Its mixed licences and curl-pipe installers
  need care. Its sandboxes are worth a look later for the "isolated desktop on the cloud
  server" step in the capability map.

### 3. Browser Use: https://github.com/browser-use/browser-use

- **Licence:** MIT for the Python library. The hosted cloud has its own terms.
- **What it is:** a Python library for browser agents. It offers an agent loop, local
  Chrome, custom actions, structured output, and saved-run replay without model calls.
- **Python:** >= 3.11, which matches BAU. Installed with `uv add browser-use`.
- **Local models:** Ollama is named. llama.cpp and other OpenAI-compatible endpoints are
  not stated in the README.
- **Gating:** there is no per-action confirmation in the README. Its "toolsets" integration
  lets an outer tool loop (here, Jarvis) call each browser action. That is how BAU would use
  it: each action as a gateway capability, never its own agent loop.
- **MCP:** mentioned, command not stated.
- **Telemetry:** not stated in the README. Its source must be read before any run.
- **Activity:** 120k stars.
- **Decision: adapt**, after the desktop lane. It is tested side by side in the sandbox
  against Playwright's own MCP server (already the capability map's other candidate).
  Whichever passes BAU's tests with fewer moving parts wins.

### 4. LocalHarness: https://github.com/ahwurm/localharness

- **Licence:** MIT.
- **What it is:** a self-hosted agent harness for local models (llama.cpp, vLLM, Ollama,
  LM Studio), with YAML agents, MCP, SQLite memory and a single permission gate.
- **Python:** 3.12+ (Debian 13's own Python is newer, so only a separate environment would
  be needed).
- **Maturity:** "Early stage (v0.27.6, pre-1.0)". 58 stars. "No account, no telemetry."
- **The idea worth taking:** "an agent that reads untrusted content (web page or MCP result)
  is not given tools that change the machine; the check fails closed." BAU wraps untrusted
  data but does not yet take tools away after reading it.
- **Decision: study.** Borrow the "read untrusted, lose write tools" rule. Do not install:
  it would be a second agent runtime.

### 5. Hermes Agent: https://github.com/NousResearch/hermes-agent

- **Licence:** MIT.
- **What it is:** "The self-improving AI agent." Skills are created after complex tasks and
  improved in use (agentskills.io format, the same open format as BAU's agent folders). It
  has FTS5 session search, cron, and six terminal backends.
- **Install:** `curl | bash`, which brings its own Python 3.14.
- **Approvals:** the default mode is `smart`, where a second model judges risk. BAU's rule
  is that people approve. Its secrets are stripped from child processes and MCP servers,
  the same as BAU.
- **Activity:** 260k stars.
- **Decision: study.** Borrow the loop "after a successful job, write a proposed skill", but
  land it in BAU's agent folders, where the owner's SHA-256 approval already gates every
  change. Never let a model approve.

### 6. Moltis: https://github.com/moltis-org/moltis

- **Licence:** MIT.
- **What it is:** a Rust personal agent server. Commands run in containers with no network
  by default; it has a secret vault, cron, sub-agents, and Langfuse/OTLP/Prometheus
  observability.
- **Ideas worth taking:** "automatic checkpoints before skill and memory changes", and
  third-party skill "provenance pinning, drift re-trust, kill switch". BAU already re-asks
  approval when a folder's hash changes.
- **Decision: study** (a reference, not a second brain).

### 7. NanoClaw: https://github.com/nanocoai/nanoclaw

The first address given (github.com/nanoclaw/nanoclaw) was a 404. The project lives under
`nanocoai`; that page and its licence opened on 2026-11-04.

- **Licence:** MIT.
- **What it is:** "A lightweight alternative to OpenClaw that runs in containers for
  security", connecting chat apps (WhatsApp, Telegram, Slack, Discord, Gmail...) to agents.
- **Needs:** Node.js 22+ and pnpm on the host, and Docker. Its agent containers run the
  Claude Agent SDK.
- **Idea worth taking:** "agents never hold raw API keys. Outbound requests route through a
  credential gateway that injects credentials at request time and enforces per-agent
  policies and rate limits." BAU keeps keys away from agents already. This is a stronger
  version of the same rule.
- **Note:** it sends "anonymous setup diagnostics" unless `NANOCLAW_NO_DIAGNOSTICS=1` is set.
- **Decision: study** (the credential gateway pattern).

### 8. ZeroClaw: https://github.com/zeroclaw-labs/zeroclaw

- **Licence:** MIT or Apache-2.0.
- **What it is:** a Rust agent runtime with autonomy levels (ReadOnly, Supervised, Full) and
  OS sandboxes (Landlock, Bubblewrap, Docker).
- **Idea worth taking:** "tool receipts", HMAC evidence for each successful tool result. That
  is close to BAU's hash-linked audit chain.
- **Its own warning:** a "YOLO mode" exists that skips the safety gates.
- **Activity:** 33.1k stars.
- **Decision: study.**

## Also checked (the owner's second list, 2026-11-04)

The owner's rule (2026-11-04): **only the best free open source.** A licence must let the
business use it freely (MIT, Apache-2.0, BSD and the like). "Source-available" or
"fair-code" licences that limit business use are out, whatever the project calls itself.

| Repository | Licence (from its LICENSE file) | Decision and why |
|---|---|---|
| [paperclipai/paperclip](https://github.com/paperclipai/paperclip) | MIT | study: "orchestration for teams of AI agents to run a business". It would duplicate Jarvis's missions and agent roles (Node.js server + Postgres) |
| [bytedance/deer-flow](https://github.com/bytedance/deer-flow) | MIT | skip: a whole "super agent harness" (Python 3.12 + Node 22). Its own security notice says its gateway admin "is equivalent to code execution" |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | MIT | skip: an orchestration framework; BAU's agent loop already does this job |
| [letta-ai/letta](https://github.com/letta-ai/letta) | Apache-2.0 | skip: this repository is retired; its code moved to `letta-ai/letta-code`. BAU has its own memory |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | MIT | study later, for the coding layer: its own warning says its default mode gives the agent "full access to your filesystem"; Docker per conversation is optional |
| [n8n-io/n8n](https://github.com/n8n-io/n8n) | **Sustainable Use License** ("only for your own internal business purposes"), plus an enterprise licence | **out: not free open source** |
| [langgenius/dify](https://github.com/langgenius/dify) | **modified Apache 2.0** with extra conditions (no multi-tenant use without permission, keep its logo, a commercial licence in some cases) | **out: not free open source** |

Cua is kept only for its MIT parts; its FSL and AGPL parts are out under the same rule.

## Summary

| Repository | Licence | Decision |
|---|---|---|
| Agent Desktop | Apache-2.0 | **integrate** (MCP adapter) |
| Browser Use | MIT | **adapt** (actions as capabilities; tested against Playwright MCP) |
| LocalHarness | MIT | study (take the untrusted-read rule) |
| Hermes Agent | MIT | study (take the propose-a-skill loop; people approve) |
| NanoClaw | MIT | study (the credential gateway) |
| Moltis | MIT | study (checkpoints, skill provenance) |
| ZeroClaw | MIT / Apache-2.0 | study (tool receipts) |
| Cua (MIT parts only) | MIT | later |
| Paperclip, OpenHands | MIT | study later |
| DeerFlow, LangGraph, Letta | MIT / Apache-2.0 | skip (duplicate or retired) |
| n8n, Dify | not free open source | out |

None of these replace Jarvis's loop, memory, router or gateway. The plan is in
[JARVIS-AUTOMATION-ROADMAP.md](JARVIS-AUTOMATION-ROADMAP.md).
