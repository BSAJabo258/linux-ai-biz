# BAU / BSA Jarvis: the whole system, as it stands (2026-11-18)

A review of everything put together so far: what each part does, what it is connected to, and
what is still loose. It covers `main` at `e99aec8` (after #201), including the work done from
the desktop (#198 to #201).

Companion documents from the readiness audit (same day, before #198):
[PROJECT-STATUS.md](PROJECT-STATUS.md), [FEATURE-INVENTORY.md](FEATURE-INVENTORY.md),
[DEPENDENCY-MAP.md](DEPENDENCY-MAP.md), [KNOWN-ISSUES.md](KNOWN-ISSUES.md).

## The short answer

- **Main is healthy.** `bash scripts/check.sh` on `e99aec8`: ALL PASS (1269 tests, 19 skipped;
  lint, secret scan, regulations, 44 shell scripts). Run 2026-11-18 in a fresh copy.
- **The desktop's changes are on GitHub and in main.** The opencode session's work was finished
  and merged (#198), then Jarvis's photo face (#199), Aria's face lock (#200), and the fix from
  the owner's own run of the face setup (#201).
- **Most of it joins up.** Jarvis reaches almost every part through his tools and the gateway.
  The autopilot drives the work. The world, the workstation and the money check all read the
  same real records.
- **Not everything is joined yet.** Five gaps are listed under
  [What is not connected yet](#what-is-not-connected-yet). The biggest one is outside the code:
  Fanvue is still not signed in, so the money machine has never earned anything.

## How it fits together

```
                          the owner (desktop, or the laptop through the tunnel)
                                              |
                          Jarvis's page (jarvis.html) / a terminal   
                                              |
                        Jarvis (assistant.py): picks a model, answers,
                        stages cards, never approves anything himself
                                              |
                 every tool call goes through the Universal Gateway (gateway.py)
                 and is written to the audit chain (audit.py); the Governor watches
       ___________________________|______________________________________________
      |            |              |              |             |                 |
   memory &     missions →     autopilot     the creator    God's Eye       the self lab
   Second       executive →    (every 30     feed →         (spatial.py)    (selfmod.py)
   Brain        agent folder   min, desktop) pictures →     world data,     reads, proposes,
                (researcher,      |          Fanvue queue → sky, business   tests in bubble-
                producer)         |          autopost →     checks          wrap; the owner
                   |              |          earnings                        applies
                   |       workstation shift      |
                   |       (workstation.py) → agent folder
                   |              |               |
                   +------ job records (JobStore) + ledger + queues --------+
                                              |
                 the screens that read them: Operations world, AI workstation,
                 Mission Control, System status, bau money, the briefing
```

The local model (llama.cpp on 127.0.0.1:8080) is the brain under all of it. Hosted models are
optional and only answer first when the owner has approved them and given keys.

## Part by part

Legend: **connected** = wired into the rest and covered by tests; **proven** = ran for real
(on the owner's desktop, or in the readiness audit on the real local model); **loose** = built
but not joined, or joined wrongly.

### The core

| Part | What it does | Connected to | State |
|---|---|---|---|
| Jarvis (`src/bau/assistant.py`) | The conversation: briefing, tools, cards for anything consequential | every part below, through the gateway | connected, proven (real-model check 8/8) |
| Model choice (new, #198) | The owner picks the model per conversation; local-only and offline rules still apply | `pick_model`, `src/bau/models/providers.py` | connected, unit-tested |
| Universal Gateway (`src/bau/gateway.py`) | Checks every tool call: registered, allowed, HOLD, level, network, data, budget, untrusted content | Jarvis, agents, autopilot, workstation | connected, proven |
| Audit chain (`src/bau/audit.py`) | Hash-linked record of everything; `bau audit verify` | everything | connected, proven |
| Governor (`src/bau/governor.py`) | Watchdog: HOLD, stuck work, crashed missions, findings | missions, automaton, autopost | connected, proven |
| Memory, Second Brain, chat library | Remember and recall; notes; the owner's chat exports | Jarvis, agents | connected; memory proven |
| Setup cards (`src/bau/setup_steps.py`) | Every unfinished setup step as a card with Accept | Jarvis's page; station-aware | connected, proven |

### Work: missions, agents, the workstation, the autopilot

| Part | What it does | Connected to | State |
|---|---|---|---|
| Missions (`src/bau/jarvis.py`) | Plan → readiness → executive job → agent → verify facts → result or PAUSED for the owner | executive, agent folders, portfolio, world | connected, proven (research mission ran end to end on the real model) |
| Executive (`src/bau/executive.py`) | One job per mission run in the job store | missions | connected, proven |
| Agent folders (`src/bau/agentfolders.py`) | Researcher and producer; owner approval tied to the folder's fingerprint | missions, workstation, Jarvis's `ask_agent` | connected, proven (both ran on the real model) |
| AI workstation (new, #198; `src/bau/workstation.py`, `src/bau/ui/workstation.html`) | Each approved agent folder is a worker with health from its real job log; a fixed-rule manager approves only low-risk internal work; at 0 health a successor inherits the open work | job store, agent folders, autopilot (the `workstation` job), Jarvis's page (WORKSTATION link) | connected, unit-tested; not yet run on the desktop |
| Autopilot (`src/bau/autopilot.py`) | A queue worked every 30 minutes on the desktop: scan, inspect, research, draft, learn, the workstation shift; votes and questions for anything bigger | scout, toolbox, workstation, creator feed, Fanvue autopost, automaton | connected, proven (desktop 11-10: 9 of 9 done) |
| Automaton (`src/bau/automaton.py`) | "Make money or die": posts without the review card, a budget, dies after 30 days without income | autopilot, Fanvue, governor; Jarvis's `automaton` tool (#176) | connected, never started |
| Team and supervisor | Boss, thinker, specialist; stops loops; flags facts no tool backs | agent folders | connected, unit-tested |

### The self lab (new, #198)

| Part | What it does | Connected to | State |
|---|---|---|---|
| Self lab (`src/bau/selfmod.py`, [SELF-MODIFICATION.md](../SELF-MODIFICATION.md)) | Jarvis reads his own code, proposes a change in a private copy, runs the tests in a sandbox, shows the diff. Only the owner applies it, and the safety files can never be changed | Jarvis's `self_*` tools; the audit chain; a card for test and apply | connected, unit-tested and security-reviewed; **needs bubblewrap** (see below) |

### Research and tools

| Part | What it does | Connected to | State |
|---|---|---|---|
| Web search and page reading (`src/bau/web.py`) | Private search through SearXNG on 127.0.0.1:8888; every address checked | Jarvis, the researcher | connected, proven |
| Watch a video (`src/bau/watch.py`) | Captions via yt-dlp, else the local Whisper | Jarvis | connected; yt-dlp and the voice service are installed by hand |
| Repo Scout, toolbox, catalog, open-source watch | Find, inspect and record open-source projects; never installs them | Jarvis, autopilot | connected, proven (live GitHub search) |
| MCP connectors (`src/bau/mcp.py`) | Pin and check outside tool servers | agent folders | connected; none registered yet |

### God's Eye (`src/bau/spatial.py`)

| Layer | Source | Needs a key? | State |
|---|---|---|---|
| Earthquakes | USGS | no | proven (desktop 11-10) |
| Aircraft | OpenSky | no | connected |
| Satellites | CelesTrak | no | connected |
| Wildfire (new) | NASA FIRMS | optional `FIRMS_MAP_KEY` for area queries | connected, unit-tested |
| Weather (new) | Open-Meteo | no | connected, unit-tested |
| Space weather (new) | NOAA SWPC | no | connected, unit-tested |
| Traffic (new) | TomTom | yes, `TOMTOM_API_KEY` | connected; off until the key is set |
| Ships (new) | AISStream | yes, `AISSTREAM_API_KEY` | connected; off until the key is set |
| The sky (Moon, solstices, meteor showers) | computed here | no | feeds the creator's first post of the day |
| Business checks | USGS | no | autopost only in the audience's evening; holds posts after an M7+ quake |

### The money machine

| Link | What it does | State |
|---|---|---|
| Creator profile (`src/bau/virtual_creator.py`) | Aria, a fictional adult; identity lock in every prompt | connected, proven (drafts on the real model) |
| Her face lock (new, #200; `src/bau/face.py`) | `bau creator face draw/pick/show`: the owner locks one face; safe-for-work pictures are drawn from it (IP-Adapter Plus Face) | connected, unit-tested; the owner ran its setup on the desktop (#201 fixed that run); no locked face proven yet |
| Pictures (`src/bau/media/comfy.py`) | ComfyUI on the desktop's card; age check on every picture | proven on the desktop (11-10); explicit lane (Chroma) has no face lock yet (a LoRA is the planned next step) |
| Fanvue (`src/bau/fanvue.py`) | Queue, review card, autopost, earnings into the ledger | built and tested; **not signed in** |
| `bau money` (`src/bau/money.py`) | Reads every link live, now including the face lock | connected, proven in a fresh home |
| Earnings | Fanvue's earnings into `economics/revenue.jsonl` | never received ($0) |

### Screens

| Screen | Reads from | State |
|---|---|---|
| Jarvis's page (`src/bau/ui/jarvis.html`) | Jarvis, cards, setup steps | proven |
| Jarvis's face (new, #199) | The header chip cycles PHOTO, ANIME, GLASS CORE; the photo is drawn with `bau world portraits --look avatar` and its glow follows the voice | connected; the photo needs the desktop's ComfyUI |
| Operations world | job store, autopilot queue, system status, `bau money` | proven (screenshot in the audit) |
| AI workstation (new) | job store, agent folders | connected, unit-tested |
| Mission Control, the briefing, System status | missions, ledger, governor, money | connected |

### The two computers

| Part | State |
|---|---|
| Desktop as headquarters (`sudo bau hq on`) | Jarvis runs for good; SSH from the home network, keys only |
| Laptop as station (`sudo bau station role on`, `bau station pair`) | Built and tested; the laptop is not installed yet |
| Network between them | Not proven: the tablet hotspot, or a cable with fixed addresses (`docs/LAPTOP-STATION.md`) |
| Nightly updates (`sudo bau update auto`) | Proven on the desktop (11-17); carry BAU's own program only |

## What is not connected yet

1. **Workstation and world reward unchecked work.** The job record says COMPLETED even when the
   mission's fact check failed and the mission is waiting for the owner (found in the audit,
   KNOWN-ISSUES P1-3). The new workstation reads that same record, so a worker gains +8 health
   for work nobody has checked. Fix one place, the job's final state, and the world and the
   workstation both tell the truth.
2. **Workstation shifts skip the mission fact check.** A shift runs the agent folder directly
   (`agentfolders.run`), not through `jarvis.agent_executor`. The supervisor still flags facts
   no tool backs, but the mission's rule ("every fact in the answer must appear in what the
   tools returned, else PAUSED") is not applied to shift work.
3. **The self lab cannot test on the owner's computers yet.** Its tests run only inside
   bubblewrap, and neither the stick's package list nor the installer installs it. Until then,
   on each computer: `sudo apt install bubblewrap`.
4. **The project map (CLAUDE.md) has no rows for the self lab and the AI workstation.** Every
   coding agent reads that map first, so it does not know these parts exist.
5. **Still open from the audit:**
   - Only the `research` mission type has an agent (`AGENT_FOR` in `src/bau/jarvis.py`).
   - The local voice service has no setup script or guide in the repository.
   - The open-source watch lists only llama.cpp as "running in BAU".
   - #169 (Fanvue's official connection) is unmerged.

## Licences of what joined (#198 to #201)

- **ComfyUI_IPAdapter_plus is GPL-3.0.** It is free open source and allows business use, but
  unlike the MIT and Apache projects it is copyleft: changing it and handing it to someone else
  would mean sharing the changes. BAU only runs it, unchanged, on its own computer.
- **The IP-Adapter Face models are Apache-2.0.**
- **InsightFace was left out** on purpose, because its models are for non-commercial use only.

## What the owner can do next

On the desktop, all of these only look except the first two:

```bash
sudo bau update now
sudo bau hq on
sudo apt install bubblewrap
bau selftest
bau money
bau status
```

Then sign in to Fanvue: register `http://127.0.0.1:3456/callback` in the Fanvue app, then
`bau fanvue login`. After that, `bau creator face draw` and `bau creator face pick N` lock
Aria's face.

## How this review was made

- Read every change merged since the audit (#198 to #201): code, tests and docs.
- `bash scripts/check.sh` on main `e99aec8` in a fresh copy: ALL PASS.
- Traced how the new parts connect by reading the calls between them (`workstation.py` →
  `agentfolders.run` and `JobStore`; the autopilot's `workstation` job; `selfmod.py`'s sandbox
  check).
- Not run here: anything on the owner's desktop or laptop, and none of the new parts against
  real services (the new God's Eye layers, the face lock, the workstation on real jobs).
