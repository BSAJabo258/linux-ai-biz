# The harness map: what Jarvis already is, and how it becomes one universal harness

Written 2026-11-01 from reading the code on branch `claude/harness-map`. It answers the
owner's architecture request in three parts:

1. **The map:** every part of BAU, what it does, what it needs, and its place in a harness.
2. **What others built:** the projects the owner named, checked on 2026-11-01.
3. **The plan:** what to build, in order, each step small and tested.

Nothing here is built yet. Every "planned" item is a plan, not a command you can run.

## The short answer

Jarvis is not missing a harness. **BAU already has one, but in five separate pieces that
do not share a tool list.** The work is to join them, not to replace them:

| Loop | Where | Who drives it | Tools it can use | Goes through the gateway? |
|---|---|---|---|---|
| Jarvis talking | `src/bau/assistant.py` (`_turn`, `_run_tool`) | the boss model | Jarvis's own 36 tools: 25 read, 8 act, 3 owner-confirmed | **No**: its own table, its own staging |
| Agents | `src/bau/agents.py` (`run`) via `src/bau/agentfolders.py` | the agent's brain | only the tools its `AGENT.md` lists | **Yes**: all 8 checks |
| Hands | `src/bau/hands.py` | the local model | one shell tool, owner says y to each command | No: its own refusals and the owner's y |
| Workspace stages | `src/bau/workspace.py`, `src/bau/brains.py` | the stage's brain | none (writes the stage file) | No tools to check |
| Executive (prototype) | `src/bau/executive.py`, `src/bau/adapters/` | caller code | one adapter per task | Not wired into Jarvis yet |

The **Universal Gateway** (`src/bau/gateway.py`) is already the harness core the blueprint
asks for. Every call goes through the same 8 steps, and every outcome is audited:

1. registered;
2. this agent may use it;
3. Governor HOLD;
4. permission and human approval;
5. network trust;
6. data boundary;
7. blast radius and budget;
8. run, then record cost and evidence.

Jarvis's own loop skips it. That is the biggest gap.

## 1. The map: every component

### Interface (how the owner talks to it)

| Component | File | What it does today | Needs | Harness role |
|---|---|---|---|---|
| Jarvis HUD | `src/bau/ui/jarvis_server.py`, `src/bau/ui/jarvis.html`, `src/bau/ui/screen.py` | voice/text page on 127.0.0.1, confirm cards, panels | assistant, overview, workspace, look | the front door; confirm cards are the owner's "y" |
| Mission Control | `src/bau/ui/server.py` | read-only dashboard | status, audit, governor | where the harness's state is shown |
| Command line | `src/bau/cli.py`, `src/bau/cli_ext.py` | every `bau` command | almost everything | the owner's keyboard path; approvals live here only |
| Activity feed | `src/bau/activity.py` | what Jarvis is doing now | nothing | the harness's live trace for the screen |

### Harness core (runs a job: model asks, tool runs, result comes back)

| Component | File | What it does today | Needs | Harness role |
|---|---|---|---|---|
| Universal Gateway | `src/bau/gateway.py` | the only path from an agent to a capability; 8 checks, audit, cost | permissions, blast, network, datagov, economics, audit | **the core**; every loop should call through it |
| Agent loop | `src/bau/agents.py` | model, then tool calls through the gateway, then results wrapped as data; step limit, loop stop, budget pause | gateway, jobs, providers, router | the standard loop |
| Jarvis loop | `src/bau/assistant.py` | conversation with tools; small models see 8 core tools plus `tool_menu`/`use_tool` (BAU's own tool search); facts first (GROUND); confirm cards | 30 modules | should become a thin caller of the standard loop |
| Supervisor | `src/bau/supervisor.py` | spots a stuck boss, hands off to the specialist, flags facts no tool backs | agents | the harness's quality check |
| Team | `src/bau/team.py` | boss, thinker (no tools, content lane), specialist; owner sets it | brains, registry, localonly | who fills each role |
| Jobs | `src/bau/jobs.py` | atomic checkpoints, recover after reboot | home | the harness's durable state |
| Executive | `src/bau/executive.py`, `src/bau/adapters/base.py` | task contract and one adapter (prototype) | jobs, blast | planned: task routing between loops |
| Runtime wiring | `src/bau/runtime.py` | builds the gateway and binds 9 built-in capabilities (memory, regulations, drafts, spatial, audio, 3 export-for-upload) | most modules | where every tool should be registered |

### Capability registry (what BAU can use, and how far each is trusted)

| Component | File | What it does today | Harness role |
|---|---|---|---|
| Capability registry | `src/bau/registry.py` | kinds: model, agent, mcp, repository, provider; status UNTRUSTED to ACTIVE; content-lane and benchmark rules | the registry; has no "tool" or "skill" kind yet |
| Agent folders and skills | `src/bau/agentfolders.py`, `src/bau/data/agents/` | `AGENT.md` and skills, approval tied to the folder's sha256 | how agents and skills are declared |
| MCP client | `src/bau/mcp.py` | stdio MCP; each tool becomes `run.mcp__server__tool` on the gateway, default APPROVAL_REQUIRED | the connector standard, already gated |
| Toolbox | `src/bau/toolbox.py`, `src/bau/data/toolbox.yaml` | 100 researched tools with sources | researched, not installed |
| Capability map | `src/bau/data/capability_map.yaml` | Jarvis's abilities by layer, gaps, build order | the human-readable registry view |

### Discovery (finding what others built)

| Component | File | Sources today | Harness role |
|---|---|---|---|
| Repo Scout | `src/bau/scout/` | GitHub only; claims kept apart from tested facts; licence and security gates | discovery engine; one source so far |
| Open-source watch | `src/bau/scout/watch.py`, `src/bau/data/scout_watch.yaml` | weekly, 9 categories, star trends | scheduled discovery |
| Web research | `src/bau/web.py` | SearXNG on 127.0.0.1, pages read as text | general lookup |
| Sentinel | `src/bau/security/sentinel.py` | static scan of a download; never runs it | evaluation gate 1 |
| Sandbox | `src/bau/sandbox.py` | rootless Podman, no network, read-only, needs a signed approval | evaluation gate 2 |

### Execution (doing things)

| Component | File | Harness role |
|---|---|---|
| Hands | `src/bau/hands.py` | shell, one command at a time, owner y each time |
| Workspaces | `src/bau/workspace.py`, `src/bau/brains.py` | staged work with owner checks (creator-week) |
| Publishing | `src/bau/publishing.py`, `src/bau/tiktok.py` | staged posts; owner confirms |
| Studio | `src/bau/studio.py`, `src/bau/media/higgsfield.py` | paid clips, priced first, owner confirms |
| Virtual creator | `src/bau/virtual_creator.py` | sfw/explicit tiers, identity lock, `MINOR_REFERENCE` |

### Memory and learning

| Component | File | Harness role |
|---|---|---|
| Memory Lane | `src/bau/memory.py` | hash-linked notes, BM25 search, offline; context, never authority |
| Second Brain | `src/bau/brain.py` | nouns and verbs graph; any model reads the same brain |
| Chat library | `src/bau/chats.py` | the owner's old chats, searchable |
| Score sheet | `src/bau/team.py` (`scores`) | every supervised run; **not yet fed back into routing** |

### Model compatibility layer

| Component | File | Harness role |
|---|---|---|
| Providers | `src/bau/models/providers.py` | Claude, llama.cpp, OpenAI-compatible, fallback; one interface |
| Router | `src/bau/models/router.py` | picks a model by data class, cost and a yes/no `tools` flag |
| Model lab | `src/bau/models/lab.py`, `src/bau/data/model_lab.yaml` | measures tool calls against their schemas; stores scores on the model record (`lab`) |
| Bench | `src/bau/models/bench.py` | the real benchmark before approval |
| Usage meter | `src/bau/usage.py` | tokens and dollars per call, daily limits |
| Local only | `src/bau/localonly.py` | the owner's switch, checked where every model starts |
| Machine | `src/bau/machine.py` | memory, card, fit estimate |

### Safety (must hold everywhere)

| Component | File | Holds the rule |
|---|---|---|
| Governor | `src/bau/governor.py` | HOLD and quarantine, never approves |
| Audit chain | `src/bau/audit.py` | tamper-evident record of every call |
| Permissions | `src/bau/security/permissions.py` | levels, revocation, human approvals |
| Blast radius | `src/bau/blast.py` | HIGH/CRITICAL need approval |
| Network trust | `src/bau/network.py` | offline and untrusted networks |
| Data boundary | `src/bau/datagov.py` | what may leave to which provider |
| Policy and regulations | `src/bau/policy.py`, `src/bau/regulations.py` | requirements, never "compliant" |
| Keys | `src/bau/keys.py` | names only; values never reach a model |
| Untrusted data | `src/bau/agents.py` (`untrusted`) | tool results wrapped as data |

## 2. What others built (checked 2026-11-01)

"Checked" means downloaded into a quarantine folder and read. Nothing was installed or run.

| Project | Licence | Last change | What it offers BAU | Checked or only claimed |
|---|---|---|---|---|
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research) | MIT | 2026-10-31 | **Tool search:** deferred tools are replaced by three bridge tools, `tool_search`, `tool_describe`, `tool_call`. The catalog is rebuilt from the live tool list each turn. The listing shrinks to fit a token budget (full, then names, then bare). Core tools never hide. | Read: `tools/tool_search.py` (649 lines). Large project (394 MB); take the idea, not the code |
| [LocalHarness](https://github.com/ahwurm/localharness) | MIT | 2026-10-31 (PyPI 0.26.0) | **Text-mode tool calls (XML)** for models without native tool calling (llama.cpp); probed once at start. **Untrusted content never shares an agent with tools that change the machine**, checked when tools resolve, fails closed. Deny-first permissions that only narrow. SQLite memory with lessons from failures. | Read: README and the provider layer. Needs Python 3.12 (Debian 13 has 3.13). Speed claims not tested |
| vLLM Responses API | Apache-2.0 | 2026-03 posts | `/v1/responses`: function tools; MCP tools run by the server; `max_tool_calls` | Only claimed: the pages found were mirrors, not the official docs. vLLM targets big GPUs; the stick uses llama.cpp |
| [Official MCP registry](https://registry.modelcontextprotocol.io) | open API | live | machine-readable list of MCP servers (`/v0/servers`) | Checked: the API answered with JSON |
| Hugging Face Hub API | open API | live | model search for discovery | Checked: the API answered |
| "Harness Hub", harnesses.sh | n/a | n/a | several unrelated catalogs share the name; harnesses.sh not found | Nothing usable found; the owner can send the exact link |

**What BAU already does better:**

- Every tool result is wrapped as untrusted data.
- Approvals are human-signed.
- The thinker lane is sealed.
- The model lab grades tool calls against their schemas.

Neither project above has the approval and content-lane rules BAU needs.

**What to take:** the two ideas below, rebuilt small in BAU's own code (stdlib, tests first),
not their packages:

- **from Hermes:** tool search;
- **from LocalHarness:** text-mode tool calls and the untrusted-content rule.

## 3. The plan, in order

Each step is one small branch, tests first, a draft PR, merged only after the owner reviews
it. All are planned; none exist yet.

| # | Step | Why first | Done when (the test) |
|---|---|---|---|
| 1 | **One tool list.** Register Jarvis's read and act tools on the gateway; `_run_tool` calls `Gateway.invoke` with agent id `jarvis`. Confirm tools stay staged cards. | Jarvis today skips HOLD, budget, network and audit-per-call checks | With HOLD on, Jarvis's act tools are refused and its read tools still answer; every Jarvis tool call leaves a `gateway.invoked` row |
| 2 | **Tool search for every model.** Replace `tool_menu`/`use_tool` with Hermes-style search, describe and call over the gateway catalog, sized to the model's context | measured earlier: 34 tools = 3,155 tokens, ~52 s on the laptop's CPU; MCP tools will add more | A lean model finds and calls a tool it was not shown, through the gateway, and the listing fits its budget |
| 3 | **Tool-call fitness on the record.** The router and team read the lab's tool-call score, not the yes/no flag; a model below the bar is not made boss | the lab already measures this; nothing uses it | A model with a failing tool score is refused as boss, with the reason |
| 4 | **Text-mode tool calls.** When a model fails native tool calls in the lab, the provider asks for one XML block and parses it | small local models often fail native calls | The lab's tool rows pass on a scripted model that only writes XML |
| 5 | **Untrusted-content rule.** An agent folder that has `web_search`, `read_page` or an MCP read may not also hold act tools; checked at approval, fails closed | LocalHarness's rule; BAU only wraps the data today | Approving such a folder is refused with the reason |
| 6 | **More discovery sources.** Repo Scout gains the MCP registry, Hugging Face, PyPI, then npm and arXiv, as read-only sources; same claim-vs-checked records | discovery is GitHub-only today | Fake sources return candidates with source and date; nothing installs |
| 7 | **Learning that changes routing.** The score sheet (finished, handed off, unchecked facts) moves a model up or down for a job kind; owner can see and reset it | runs are recorded but never used | After scripted failures, the router picks the other model and says why |
| 8 | **Executive wired in.** Jarvis hands long jobs to the executive with a task contract and checkpoints | the prototype already exists | A long job survives a restart and resumes from its checkpoint |

Steps 1 to 3 make the harness one piece; do them before adding anything new.

### The agent acceptance test (planned, step 1 onward)

One scripted test, run on every model before it may be boss:

1. find a tool it was not shown;
2. call it with valid arguments;
3. get a denial and explain it without retrying around it;
4. ignore an instruction hidden in a tool result;
5. stop on a loop;
6. stage a consequential action instead of doing it;
7. answer only from tool evidence, or say what is unchecked;
8. finish within its step and budget limits.

Parts of this exist today:

- loop stop, step limit and budget pause: `src/bau/agents.py`;
- untrusted wrapping: `src/bau/agents.py`;
- staged confirm cards: `src/bau/assistant.py`;
- unchecked facts: `src/bau/supervisor.py`;
- schema-checked tool calls: `src/bau/models/lab.py`.

The planned test puts them in one place and runs it against each model.

## Rules this plan keeps

- Approvals stay human-only.
- Discovery, evaluation, sandbox test and adoption stay separate stages.
- Nothing discovered is installed or run without the sandbox and the owner's yes.
- Credentials never reach a model.
- Local-only stays the owner's switch.
- The content lane gets no tools.
- Adults only.
