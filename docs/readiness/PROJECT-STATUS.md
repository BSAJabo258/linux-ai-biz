# Project status (2026-11-18)

The readiness audit of BAU / BSA Jarvis: what is built, what really works, what is missing,
and how close it is to use as a product and a business. Companion documents:
[FEATURE-INVENTORY.md](FEATURE-INVENTORY.md) (every feature, with its evidence),
[DEPENDENCY-MAP.md](DEPENDENCY-MAP.md) (what each part needs) and
[KNOWN-ISSUES.md](KNOWN-ISSUES.md) (P0 to P3).

## The answer first

**The platform works. The business has not started.**

- **Jarvis works on a real local model.** On 2026-11-18, on 3 processor cores with the pinned
  `qwen3.5-4b`:
  - The project's own real-model check passed 8/8.
  - A question typed in the web page reached the model, used the right tool and came back
    right.
  - The producer agent wrote a real draft for review.
  - A research mission ran from plan to web search to a sourced report. The checker caught one
    claim no source backed and stopped the mission for the owner instead of calling it done.
  - Every step went through the gateway and onto a verifiable audit chain, and all of it
    survived a restart.
- **The money has not started.** 0 pictures drawn for the business, 0 posts, $0 received.
  Fanvue is not connected (the sign-in was refused twice). The one link that blocks every
  dollar is the owner's to clear.
- **BAU's own release checklist says not production ready.** 22 critical items are not done,
  most of them checks only the owner, counsel or a CPA can close.

### How far along, by tested function

Of the 55 features in the inventory:

| Status | Features | Share |
|---|---|---|
| WORKING (a real run) | 30 | 55% |
| PARTIALLY WORKING | 6 | 11% |
| IMPLEMENTED-UNTESTED (unit tests only) | 10 | 18% |
| BLOCKED (keys, accounts, hardware, the owner) | 7 | 13% |
| BROKEN or MISSING | 2 | 4% |

As a whole:

- **The core platform** (Jarvis, gateway, audit, memory, agents, research, the screen,
  updates) **is about 85% there**: it runs; the main gaps are missions for more than one job
  type, and records that tell the truth about unverified work.
- **The revenue pipeline** (creator → pictures → Fanvue → earnings) **is about 40% there**:
  everything is built and unit-tested, but the chain has never run once end to end, and its
  first link outside BAU (the Fanvue sign-in) is not connected.
- **Selling to outside customers** (Prompt 5): not assessed yet. The RED checklist decides what
  may be claimed.

These percentages are judgments drawn from the inventory, not measurements.

## 1. Where the project stands

| What | State |
|---|---|
| Repository | github.com/BSAJabo258/linux-ai-biz, main `1d82c70` (after merging #191 to #196 on 2026-11-18) |
| Size | 123 Python modules, about 27,800 lines; 89 test files, 1193 tests passing and 17 skipped; 79 top-level `bau` commands and 301 subcommands |
| Checks | `bash scripts/check.sh` ALL PASS on main; CI green on Python 3.11 and 3.13 |
| Help screens | all 301 `bau ... --help` screens open without an error (checked 2026-11-18) |
| Open work | #169 (Fanvue's official connection: unmerged, conflicts) |
| Old branches | about 290 on GitHub, most from merged work |
| Desktop | headquarters; BAU `9ae6e0f` installed 11-17, update pending (KNOWN-ISSUES P0) |
| Laptop | station; not installed yet |
| Stick | release `live-v0.1.0-9ae6e0f`, built and booted in a virtual machine |

## 2. Work already done (found, not redone)

Earlier audits and plans this one built on, and what came of their recommendations:

| Earlier finding (where) | Implemented? | Evidence |
|---|---|---|
| The executive controller existed but nothing called it (`docs/automaton/CAPABILITY_MATRIX.md`, 11-10) | **yes** | every mission run now goes through it (Phase 1, 11-11); the soy-wax mission ran through it |
| No `bau mission run` (same, 11-10) | **yes** | `bau mission run` exists and ran (via its function) |
| Jarvis could not reach the automaton (same) | **yes** | #176, merged 2026-11-18 after three review rounds |
| An agent could start without what its job needs (agent readiness, 11-15) | **yes** | `bau agents ready` named the gaps, then passed |
| No retry or resume for failed work (same, 11-10) | **no** | `bau recover` marks interrupted jobs; nothing resumes them |
| No benchmark history, real-model check run by hand (same) | **no** | still by hand; this audit's run is recorded here |
| Ten specialist agents (spec) | **no** | 2 agent folders (producer, researcher) |
| Laptop as a station (11-15) | **yes in code** | #179 to #196; not yet on hardware |
| Is the money machine running (11-18) | **yes** | `bau money` |

## 3. Commands to fill in what this audit could not see

No computer was connected to this session, so the machines' own facts (graphics card, disk,
services, versions) are not re-read here. All of these only look; they change nothing.

On the desktop:

```bash
bau update status
bau selftest
bau hw
bau money
bau status
bau agents list
bau hq status
```

On the laptop, after its install:

```bash
bau update status
bau selftest
bau hw
bau station status
```

## 4. What to do next (the shortest safe path)

1. **Owner, desktop:** `sudo bau update now`, then `sudo bau hq on` (rewrites the service with
   the restart limit), then the commands in section 3. Paste the output.
2. **Owner, Fanvue:** register `http://127.0.0.1:3456/callback` in the Fanvue app, then
   `bau fanvue login`.
3. **Code (Prompt 2):**
   - Make the job record and the world tell the truth about unverified work.
   - Add an agent for the first sellable mission type.
   - Add the voice setup script.
4. **Owner and counsel:** the RED checklist (`bau status`).

## How this audit was run

- Environment: a cloud machine (4 cores, 15 GB, no graphics card, Python 3.13.18, Node
  22.23.4, Claude Code; OpenCode not installed).
- The real model: llama.cpp built at the stick's pinned commit, and the pinned `qwen3.5-4b`
  file with its SHA-256 checked, run with the stick's own `bau-llm` settings. The web: SearXNG
  at its pinned commit.
- Fresh empty homes for every run. Owner approvals were given only inside those throwaway homes,
  the way the unit tests give them. The human-at-a-terminal guard was never bypassed, and
  nothing was approved, posted or sent anywhere real.
- Screenshots of the running page were taken in headless Chromium. They are kept with the run,
  not in the repository.
