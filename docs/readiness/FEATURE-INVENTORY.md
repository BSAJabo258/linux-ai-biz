# Feature inventory (2026-11-18)

Every major feature, its status, and the evidence behind the status. The status comes from
what ran, never from what a document says.

| Status | Meaning |
|---|---|
| **WORKING** | a real functional run succeeded (a real model, a real service or the owner's machine) |
| **PARTIALLY WORKING** | some paths ran for real, important ones are missing or wrong |
| **IMPLEMENTED-UNTESTED** | code exists and its unit tests pass with fakes, but it never ran for real |
| **MISSING** | not implemented |
| **BROKEN** | tried and failing |
| **BLOCKED** | needs something outside the code: a key, an account, a person's action, hardware |

Where the evidence comes from:

- **here**: this audit, 2026-11-18, in a cloud machine (4 CPU cores, 15 GB memory, no graphics
  card). Main at `1d82c70`. The real model was `qwen3.5-4b` (the pinned file, its SHA-256
  checked) on llama.cpp build b11747, the stick's own commit and settings (`--jinja`,
  `--ctx-size 8192`, reasoning off, 3 threads). Web search was SearXNG at the pinned commit,
  set up the way `installer/bau-search-setup.sh` does it. Every run used a fresh, empty home.
- **desktop 11-10**: the audit of the owner's desktop in `docs/automaton/CURRENT_STATE.md`.
- **owner**: output the owner pasted from the desktop (2026-11-16 to 11-18).
- **CI**: `bash scripts/check.sh` (1198 tests on main plus #176; lint, secrets, regulations,
  shellcheck) on Python 3.11 and 3.13.

Approvals stayed human-only throughout. Where a run needed the owner's approval (the model, an
agent), it was given in the throwaway home the way the unit tests give it
(`approve(..., "human:...")`). The human-at-a-terminal guard was never bypassed.

## Jarvis and the core

| Feature | Status | Evidence | Where |
|---|---|---|---|
| Jarvis conversation on a local model | **WORKING** | here: `.claude/skills/real-model-check/run.py qwen3.5-4b` passed **8/8** (status, remember, recall, usage, creator batch, workspaces, posting never direct, audit chain). Answers took 7.7 to 241.9 s on 3 cores | `src/bau/assistant.py` |
| Jarvis on the screen (web page → model → tool → answer) | **WORKING** | here: the real page, the real model; "What missions do I have?" called the `missions` tool and answered right about the PAUSED mission. 137.9 s on CPU; 0 page errors | `src/bau/ui/jarvis_server.py`, `src/bau/ui/jarvis.html` |
| Model routing (`pick_model`): hosted first online, local backup, local only offline or at $0 | **WORKING** (local path) | here: every turn answered by `qwen3.5-4b`. Desktop 11-10: every turn. The hosted path was not run here (no keys) | `src/bau/assistant.py` |
| Rich router (`bau models route`) | **IMPLEMENTED-UNTESTED** live | not on the live path; unit tests only | `src/bau/models/router.py` |
| Model benchmark before approval | **WORKING** | here: `bau models bench qwen3.5-4b`: reply ok, tool calls ok, 2.1 words/s. Desktop 11-10: 11 models benchmarked | `src/bau/models/bench.py` |
| Universal Gateway (every tool call checked) | **WORKING** | here: every agent and Jarvis tool call went through it and onto the audit chain. Desktop 11-10: 4 live refusals on an untrusted network | `src/bau/gateway.py` |
| Audit chain (hash-linked, verifiable) | **WORKING** | here: `bau audit verify` ok (8, 23, 32 records); `bau recover` ok | `src/bau/audit.py` |
| Governor (watchdog: HOLD, stuck work, findings) | **WORKING** | here: `bau governor tick` raised the PAUSED mission as an ACTION. Desktop 11-10: 1139 ticks | `src/bau/governor.py` |
| Memory (remember / recall) | **WORKING** | here: real-model check "recall finds 7pm" | `src/bau/memory.py` |
| Second Brain | **IMPLEMENTED-UNTESTED** live | the producer agent's `memory.brain` lookup ran (empty vault); no real vault content tried | `src/bau/brain.py` |
| Chat library (Claude/ChatGPT exports) | **IMPLEMENTED-UNTESTED** live | unit tests only | `src/bau/chats.py` |
| Usage meter (tokens and dollars per model) | **WORKING** | here: "How much have the models cost today?" → $0.00, 4 local calls, no invented limit | `src/bau/usage.py` |
| Setup cards (pop-ups with Accept) | **WORKING** | here: 2 cards appeared in the page (updates, autopilot). Owner: cards seen on the desktop | `src/bau/setup_steps.py` |
| Restart and recovery (`bau recover`, data survives a restart) | **WORKING** | here: a new process read back the mission, its job and the audit chain | `src/bau/cli_ext.py` |
| Release checklist (`bau status`) | **WORKING** | here: says RED, `production_ready: false`, with 25 red items (see KNOWN-ISSUES) | `src/bau/data/build_state.yaml` |

## Agents, missions and the workforce

| Feature | Status | Evidence | Where |
|---|---|---|---|
| Agent folders (AGENT.md, skills, approval tied to the folder's sha256) | **WORKING** | here: the producer and researcher loaded, were approved in the harness home, and ran | `src/bau/agentfolders.py` |
| Agent readiness check (`bau agents ready`) | **WORKING** | here: named the exact gaps (approval, search service, model), then passed all 6 checks once they were met | `src/bau/agentfolders.py` |
| Producer agent (drafts copy for review) | **WORKING** | here: real model, real task: read its 2 skills, saved `artifacts/drafts/autumn-ember-candle-blurb.md` marked for review, invented no price or claim, flagged what it was unsure of | `src/bau/data/agents/producer/AGENT.md` |
| Researcher agent | **WORKING** | here: real model, real SearXNG: found 2 US soy-wax suppliers with links to their own pages and a source on every line | `src/bau/data/agents/researcher/AGENT.md` |
| Mission run: plan → readiness → executive job → agent → verify → result | **PARTIALLY WORKING** | here: a `research` mission ran end to end in 461 s; the checker caught one unbacked phrase and left the mission **PAUSED for the owner**, as designed. But only 1 of the 10 mission types has an agent (`AGENT_FOR = {"research": "researcher"}`): the other 9 answer "no agent carries out ... missions yet" | `src/bau/jarvis.py`, `src/bau/executive.py` |
| Job records (what ran, which model, which tools) | **BROKEN** (partly) | here: the job said `COMPLETED`, `model: null`, `tools: []` while its mission was PAUSED (verification failed) and the agent had used the model and `search.web` | `src/bau/jobs.py`, `src/bau/jarvis.py` |
| Mission portfolio (priority, budget, goal, money) | **WORKING** (read) | here: `bau mission portfolio` showed the mission with $0 from the ledger | `src/bau/jarvis.py` |
| Supervisor and team (boss, thinker, specialist; loop stop; handover) | **IMPLEMENTED-UNTESTED** live | unit tests only; desktop 11-10: 0 agent runs | `src/bau/team.py`, `src/bau/supervisor.py` |
| Autopilot (a queue Jarvis works every 30 min) | **WORKING** (on the desktop) | desktop 11-10: 9 tasks queued, 9 done. Not run here (needs the timer) | `src/bau/autopilot.py` |
| Automaton ("make money or die") | **IMPLEMENTED-UNTESTED** live | unit tests; never started on the desktop. Jarvis's read tool for it is #176, merged 2026-11-18 | `src/bau/automaton.py` |
| Hands (terminal jobs, the owner's y each command) | **IMPLEMENTED-UNTESTED** live | unit tests only | `src/bau/hands.py` |
| Workspaces (`bau ws`) | **PARTIALLY WORKING** | here: listed for real, but the model then wrongly said it "cannot create workspaces yet" (`bau ws` does), after 187 s | `src/bau/workspace.py` |

## Research and tools

| Feature | Status | Evidence | Where |
|---|---|---|---|
| Web search (SearXNG on 127.0.0.1:8888) | **WORKING** | here: 51 results for a real query; the researcher used it | `src/bau/web.py`, `installer/bau-search-setup.sh` |
| Read a page (address checked, redirects checked) | **WORKING** | here: the researcher read the suppliers' pages; a broken result address (`http:///go/...`) was refused | `src/bau/web.py` |
| Repo Scout (`bau scout find`) | **WORKING** | here: a live GitHub search returned 24 projects with scores and licence gates | `src/bau/scout/` |
| Toolbox (103 researched tools, `bau toolbox ask`) | **WORKING** | here: answered "local speech to text" with sourced entries | `src/bau/toolbox.py`, `src/bau/data/toolbox.yaml` |
| Tool catalog (`bau catalog`) | **WORKING** (read) | here: listed tools with evidence-based states | `src/bau/catalog.py` |
| MCP connectors (pin, check, revoke) | **IMPLEMENTED-UNTESTED** live | here: `bau mcp list` → none registered | `src/bau/mcp.py` |
| Rootless sandbox for untrusted code | **BLOCKED** here | needs podman (not in this machine); unit tests pass; the stick carries podman | `src/bau/sandbox.py` |
| Watch a video (captions, else local Whisper) | **PARTIALLY WORKING** | the caption path needs yt-dlp, which is not installed by BAU; the Whisper path needs `bau-voice` (see the next row) | `src/bau/watch.py` |
| Local voice (Kokoro speaks, Whisper listens, 127.0.0.1:8767) | **PARTIALLY WORKING** | desktop 11-10: a sentence spoken and heard back word for word. But nothing in the repository installs it and the voice guide the code names (VOICE.md) does not exist: a reinstall loses it | `src/bau/assistant.py` (`Voice`) |
| God's Eye (quakes, aircraft, satellites, sky) | **WORKING** | desktop 11-10: live USGS read | `src/bau/spatial.py` |

## The money machine (creator → Fanvue → earnings)

| Feature | Status | Evidence | Where |
|---|---|---|---|
| Money check (`bau money`, 9 links read live) | **WORKING** | here: fresh home 2 of 9 ready, first gap named with its fix. Not yet run on the desktop | `src/bau/money.py` |
| Creator profile and sfw drafts | **WORKING** | here: `bau creator init` and Jarvis's creator batch drafted 7 sfw posts on the real model | `src/bau/virtual_creator.py` |
| Pictures (ComfyUI, SDXL / Chroma, age check) | **WORKING** (on the desktop) | desktop 11-10: ComfyUI on the RTX 3060, Chroma installed and checked. Pictures drawn for the business: **0**. Not possible here (no graphics card) | `src/bau/media/comfy.py` |
| Fanvue sign-in | **BLOCKED** | the app's redirect address was refused on the desktop twice (#169 notes); the owner must register `http://127.0.0.1:3456/callback` and run `bau fanvue login`. Not connected | `src/bau/fanvue.py` |
| Fanvue posting and autopost | **IMPLEMENTED-UNTESTED** live | unit tests; posts made: **0** | `src/bau/fanvue.py`, `src/bau/creator_feed.py` |
| Earnings into the ledger | **IMPLEMENTED-UNTESTED** live | unit tests; money received: **$0** | `src/bau/economics.py` |
| TikTok / week of posts (Ayrshare) | **BLOCKED** | needs the owner's TikTok app keys | `src/bau/tiktok.py`, `src/bau/week.py` |
| Instagram | **MISSING** | planned | |
| Paid video (Higgsfield) | **BLOCKED** | needs a key and budget | `src/bau/studio.py` |

## Screen and world

| Feature | Status | Evidence | Where |
|---|---|---|---|
| Operations world (rooms, characters, real jobs) | **PARTIALLY WORKING** | here: screenshot with the real agents and status panel, 0 page errors. But it put the researcher in **Delivered** while its mission was waiting for the owner (it reads the job record, see above) | `src/bau/world.py`, `src/bau/ui/jarvis.html` |
| Character art (adult women from the owner's picture, 7 looks) | **WORKING** | rendered in the screenshot; rebuilt by `tests/test_world_art.py` in CI | `scripts/world_sprites.py` |
| Portraits (`bau world portraits`) | **BLOCKED** here | needs ComfyUI; stops at once with a plain line when it is off | `src/bau/world.py` |

## Two computers, install and updates

| Feature | Status | Evidence | Where |
|---|---|---|---|
| Desktop as headquarters (`sudo bau hq on`) | **PARTIALLY WORKING** | owner 11-17: HQ on, the service was stuck restarting until the port fix (#181, #189). Not re-checked on the desktop since | `src/bau/station.py`, `src/bau/cli_ext.py` |
| Laptop station (tunnel, Jarvis HQ launcher, station role) | **IMPLEMENTED-UNTESTED** on hardware | proven on a real sshd in a container (tunnel to Jarvis only, no shell); the laptop is not installed yet | `src/bau/station.py`, `docs/LAPTOP-STATION.md` |
| Network between the two (tablet hotspot or cable) | **BLOCKED** | not proven; the cable recipe is written | `docs/LAPTOP-STATION.md` |
| Nightly updates (wheel, checked, rolls back) | **WORKING** | owner 11-17: `sudo bau update now` installed `9ae6e0f`; the release now holds main `dba8907` | `src/bau/update.py` |
| The stick (live system and installer) | **WORKING** (built, booted) | release `live-v0.1.0-9ae6e0f` built; it booted to the desktop and the installer ran in QEMU (the virtual machine died near the end) | `image/build-live.sh` |
| Install onto the laptop's WD disk | **BLOCKED** | waits on the owner | `docs/LIVE-USB.md` |

## Counts

| Status | Features |
|---|---|
| WORKING | 30 |
| PARTIALLY WORKING | 6 |
| IMPLEMENTED-UNTESTED | 10 |
| BROKEN (partly) | 1 |
| BLOCKED | 7 |
| MISSING | 1 |
| **Total** | **55** |

Counted from the tables above by a script, not by hand. WORKING includes features proven only
in parts (marked "(local path)", "(read)", "(on the desktop)").
