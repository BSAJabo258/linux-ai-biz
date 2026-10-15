# CLAUDE.md - BAU/BSA

BAU is a compliance-first AI business system for one owner: an encrypted Debian laptop
built from two USB sticks, a Python control plane (`src/bau`), and work layers on top
(Jarvis, agents, factories, publishing). Read `docs/HANDOFF.md` first for where things
stand and what is next.

## Layout

| Path | What |
|---|---|
| `src/bau/` | the package. `cli.py` + `cli_ext.py` = the `bau` command; `policy.py`/`regulations.py` = rule engine; `data/` = regulations, policies, factories, registry defaults |
| `src/bau/assistant.py`, `ui/jarvis_server.py`, `ui/jarvis.html` | Jarvis: briefing, conversation, tools, voice HUD |
| `src/bau/publishing.py` | publishing hub; platforms are adapters (`tiktok.py`, `youtube.py`); `kids.py` = made-for-kids rules |
| `src/bau/workspace.py`, `src/bau/brains.py`, `data/workspaces/` | ICM workspaces (`bau ws`): numbered stage folders one agent walks, owner checks each stage; kids-channel pilot. Each stage's `## Brain` says who drafts it: `small` (free local model), `strong` (Claude/Jarvis's model) or `content` (sealed content lane, never kids); the owner maps brains to models with `bau ws brains` |
| `src/bau/series.py`, `data/series_formats.yaml` | kids series engine (`bau series`): character and style sheets in `_shared/`, the same "lock" text in every clip prompt, story formats scaled to clip-sized scenes, drift check on stage 04 (`series_lock`), sameness warnings. See `docs/SERIES.md` |
| `src/bau/scout/`, `data/scout.yaml` | Repo Scout (`bau scout`): finds open-source projects for a capability, keeps claims apart from inspected and tested facts, licence/security gates; never installs or runs them. Weekly open-source watch (`bau scout watch`/`shortlist`, `scout/watch.py`, `data/scout_watch.yaml`, `bau-scout-watch.timer`): nine categories, star trends, already-have vs new, ranked test next / watch / ignore; Jarvis `open_source_watch`. See `docs/engineering/repo-intelligence.md` |
| `src/bau/studio.py`, `src/bau/media/higgsfield.py` | Video studio (`bau video`): paid Higgsfield clips under the owner's budget; priced first, owner-confirmed, downloaded with provenance, cost in the ledger. See `docs/STUDIO.md` |
| `src/bau/usage.py` | Usage meter (`bau usage`): every model call's tokens and dollars per model (free ones too), owner-set daily limits, busy replies, rate-limit headers, GitHub's wait. See `docs/USAGE.md` |
| `src/bau/results.py` | Results tracker (`bau results`): read-only views, watch time and YouTube's estimated earnings per posted video, clip cost and profit per video (`bau results link`), which story formats get watched. See `docs/RESULTS.md` |
| `src/bau/toolbox.py`, `data/toolbox.yaml` | Toolbox (`bau toolbox`): 100 researched open-source tools (connectors, grounding, evals, agents, skills, automation, memory, local models, voice, video, browsers, computer use, documents) with sources and check date; Jarvis's `toolbox` tool; `check` hands one to Repo Scout. Capability map (`data/capability_map.yaml`, `bau toolbox map`, Jarvis's `capability_map` tool): Jarvis's abilities by layer, what BAU has, gaps, how each tool would join, build order. See `docs/TOOLBOX.md`, `docs/CAPABILITY-MAP.md` |
| `src/bau/spatial.py`, `ui/screen.py` (`godseye_*`), `data/world-land.json` | God's Eye: public earthquakes / aircraft (wide named regions only, private planes unnamed) / satellites on a world map in Jarvis; 5-min cache, honours 429, every query audited with its purpose; `world_watch` tool. See `docs/GODS-EYE.md` |
| `src/bau/agentfolders.py`, `data/agents/` | Agents as folders (`bau agents`): `AGENT.md` (name, description, brain, tools, mcp, skills, max_steps + instructions) and `skills/NAME/SKILL.md` in the open Agent Skills format (only name + description load until `inspect.skill` opens one). Owner approval is tied to the folder's sha256; tools only via the gateway; community skills come in text only (`add-skill`). Jarvis: `agents`, `ask_agent`. See `docs/AGENT-FOLDERS.md` |
| `src/bau/team.py`, `src/bau/supervisor.py` | The team (`bau team`): the owner names a boss (tool-using model that runs Jarvis and the agents, e.g. local Qwen), a thinker (local uncensored model: ideas only, never tools, never kids; Jarvis `ask_thinker`) and a specialist on call (Claude). The supervisor stops loops (`agents.LOOP_LIMIT`), hands a stuck job to the specialist (`--takeover auto`, within the daily limit, or `ask`), flags facts no tool result backs, and keeps a score sheet. See `docs/TEAM.md` |
| `src/bau/governor.py` | watchdog (hold / quarantine / resume, never approves) |
| `src/bau/brain.py` | Second Brain (Markdown vault, nouns + verbs graph) |
| `src/bau/chats.py` | chat library (`bau chats`): the owner's Claude/ChatGPT exports in SQLite FTS5; Jarvis reads them per `bau chats sharing` |
| `src/bau/models/` | providers (Claude, llama.cpp, hosted OpenAI-compatible e.g. Z.ai), router, `bench.py`, `fetch.py` |
| `installer/bau-laptop-check.ps1` (+ double-click `BAU-Laptop-Check.cmd`), `installer/bau-laptop-check.sh` | Laptop check: read-only, Windows (no Python) and from the stick (drivers that really load, missing firmware); a summary safe to share with a verdict (READY / READY, AFTER THESE STEPS / NOT READY) and a private full report. See `docs/LAPTOP-CHECK.md` |
| `src/bau/keys.py`, `installer/bau-keys-export.{ps1,sh}` (+ `BAU-Keys-Export.cmd`) | Keys transfer (`bau keys import/list`): the export scripts on the owner's other computer lock API keys into `BAU-KEYS.enc` (openssl AES-256, PBKDF2-SHA256); the import routes them to `/etc/bau/models.env` / `platforms.env` (root:bau 0640). Names only, ever; only credential-shaped names accepted. See `docs/KEYS.md` |
| `installer/` | USB #1 image builder, USB #2 payload (`make-payload.sh`), `payload/install.sh` |
| `image/`, `src/bau/live.py` | My Jarvis live USB, also the full stick: `build-live.sh` (Debian Live + BAU + llama.cpp + Debian's installer in live mode), `live-build/` config (`includes.installer/preseed.cfg` = the BAU preseed for installing from the stick; `live-to-disk.sh` removes live-only startup on the installed laptop), `/BAU-PAYLOAD` on the stick, `jarvis-storage` (encrypted persistence); see `docs/MY-JARVIS.md`, `docs/LIVE-USB.md` |
| `installer/cloud/` | the owner's own cloud server (DigitalOcean, Debian 13): `cloud-init.yaml` + `prepare.sh` (admin login from the droplet key, SSH keys only), then `install.sh --cloud` (SSH the one open port, `bau-jarvis.service` on 127.0.0.1). See `docs/CLOUD-VM.md` |
| `Dockerfile`, `docker-compose.yml`, `docker/` | test drive in containers |
| `vm/` | VirtualBox rehearsal scripts (`create-vm.ps1`, `create-vm.sh`) |
| `docs/` | `INSTALL.md` (owner guide), `LIVE-USB.md`, `CLOUD-TEST.md` (free Codespaces + Z.ai), `WORKSPACES.md`, `MY-JARVIS.md` (spec + build order), `ARCHITECTURE.md`, `HANDOFF.md` |
| `.claude/skills/grow-bau/SKILL.md`, `docs/BUILD-ISO.md` | Growing BAU from any terminal: the loop any coding agent follows (ask itself, find, inspect, sandbox test, owner decides, add, rebuild) and its best-case targets; building the stick image without VS Code (GitHub button or WSL + Docker) |
| `tests/` | pytest suite |

## Commands

```bash
python3 -m pip install -e '.[dev]'        # once
python3 -m pytest -q                      # all tests (~30 s)
ruff check .                              # lint (line length 100)
bau reg validate                          # regulations + policies cross-check
bau secrets .                             # secret scan (CI runs it)
shellcheck -x installer/*.sh installer/lib/*.sh installer/payload/*.sh installer/firstboot/*.sh installer/cloud/*.sh docker/*.sh vm/*.sh image/*.sh
bash installer/make-payload.sh --skip-tests --out /tmp/pl   # build USB #2
bash image/build-live.sh --out /tmp/live                    # live USB image (Docker, ~15 GB disk)
docker compose up -d --build                                # test drive: http://localhost:8765
```

Run tests, ruff, `bau reg validate` and shellcheck before every commit. CI
(`.github/workflows/ci.yml`, `docker.yml`) runs the same on Python 3.11 and 3.13.

## Rules that must not be broken

These are the product's safety model, not style preferences:

- **Approvals are human-only.** Money, commercial email, legal and other signed approvals
  are SSH-signed by a human (`bau approve`). No agent, model, Jarvis or the Governor may
  approve, and none of them may be given a tool that does.
- **Consequential actions are confirmed by the owner.** Posting to any platform, releasing a
  HOLD, and similar actions are only *staged* by Jarvis; they run on the owner's click or
  `y`. Owner-only choices (privacy, audience, made-for-kids, commercial disclosure) never
  come from a model and never have defaults.
- **Never weaken the host.** Don't open firewall ports, disable AppArmor or encryption,
  or bind servers beyond localhost (containers bind their interface only with
  `BAU_IN_CONTAINER=1`; ports are published on 127.0.0.1). The one exception is the
  owner's cloud server (`install.sh --cloud`): SSH on 22, key login only, rate-limited.
- **Untrusted data stays data.** Tool results go to models wrapped by `agents.untrusted()`;
  Jarvis never reads `<untrusted_data>` blocks aloud.
- **Kids content** goes only to platforms with `allows_kids` (YouTube, made for kids). Never
  route child-directed videos to TikTok or other 13+ platforms.
- **Local models need a real benchmark** (`bau models bench`) before approval; never fake
  availability. Abliterated models stay in the content lane (no tools, local only).
- **No compliance claims.** BAU reports requirements, controls and evidence; it never says
  "compliant", "guaranteed" or "risk-free". Every regulation record awaits counsel review.
- **Platform facts are verified.** When adding a platform or API, check the official docs,
  record facts with the date in the module docstring and an `examples/platform-*.yaml`
  policy record, and cite regulations by `reg_id` in `data/policies/`.

## Conventions

- Before building something new, look for what others already built: `bau toolbox ask "..."`
  (and `bau scout find` for more). Prefer a vetted tool behind an adapter to writing it again.
- Match the surrounding code: stdlib first, small functions, comments only where the
  reason is not obvious. New policy rules go in `src/bau/data/policies/*.yaml` and must
  reference existing `reg_id`s (the loader refuses dangling references).
- Every behaviour change gets a test. Tests use fakes (`ScriptedProvider`, `FakeTikTok`,
  `FakeYouTube`), never real network or keys.
- The owner prefers **few commits**: one finished commit per feature on a branch, a
  draft PR, squash-merge when CI is green. Don't push half-finished work.
- Docs are written for a non-technical owner: plain words, exact commands.
- Secrets never go in the repo: keys live in `/etc/bau/*.env` on the laptop or `.env`
  (gitignored) in the test drive.
