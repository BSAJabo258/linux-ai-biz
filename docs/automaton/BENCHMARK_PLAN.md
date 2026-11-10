# AUTOMATON AI: benchmark plan (2026-11-10)

What to measure, how, and what may be claimed. No claim of superiority over any other system
is made anywhere until it has been measured the same way on the same tasks.

## Today's measurements

| Measure | Tool | Result on the desktop (`qwen3.5-9b`) |
|---|---|---|
| Everyday tasks done by actually doing them | `.claude/skills/real-model-check/run.py` | 7/8 before this change, 8/8 twice after |
| Seconds per answer | same | 0.8 to 5.0 s |
| Model quality, tool calls, JSON, speed, memory | `bau models lab` | per model, stored with the suite fingerprint |
| Unit and regression tests | `bash scripts/check.sh` | 1053 passed |

## The suite to build (roadmap gap 2)

| Metric | How it is measured |
|---|---|
| Mission completion rate | fixed missions with a known end state on disk; pass only when that state exists |
| Multi-step reliability | the same mission 5 times; pass rate and spread |
| Tool execution success | audit rows: called, refused, failed, succeeded |
| Planning accuracy | plans compared with a reference step list per mission type |
| Error recovery | planted failures (tool error, model timeout, interruption); recovered or not |
| Verification accuracy | planted false claims ("saved" with nothing saved); caught or not |
| Memory retrieval | facts saved in one session, asked in a fresh one |
| Agent coordination | missions needing two agents; duplicate or circular work counted |
| Latency and resources | seconds per step, tokens, dollars (usage meter), peak memory |
| Human interventions | owner clicks and answers per mission |
| Local model performance | the same suite on each approved local model |

## Rules

- Every run is stored (JSON, with the commit, model, machine and date) so results form a
  history; a drop between runs is reported, not averaged away.
- A comparison with another system names the system, its version, the tasks, the machine and
  the date, and uses the same graders. Until then, nothing is called better or faster.
- Fakes are allowed in unit tests only; a benchmark result always comes from a real model.
