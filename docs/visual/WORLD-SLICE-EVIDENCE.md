# The world's first slice: evidence (2026-11-20)

One real research task, watched from start to finish in the operations world, on the real
local model and the real private search service. This page records what ran, what the
screen showed at each step, and what went wrong on the way. The product is described in
[BAUBSA-WORLD-PRODUCT-SPEC.md](BAUBSA-WORLD-PRODUCT-SPEC.md).

## What ran

- A fresh, empty BAU home on a cloud test computer (3 processor cores, no graphics card),
  not the owner's desktop.
- The model: `qwen3.5-4b` (Q4_K_M) on llama.cpp build b11747, the stick's own build,
  on 127.0.0.1:8080.
- Private search: SearXNG on 127.0.0.1:8888.
- Jarvis's page in a real browser (headless Chromium), polling `/api/world` every 5 seconds
  as it does for the owner.
- The researcher agent folder, approved in the test home (the same harness approval the
  tests use).
- The task, given to Jarvis as a mission: "Find two US suppliers that sell wholesale soy wax
  for candle makers, with a link to each supplier's own page."
- Screenshots of the page before the mission, while it worked, and after; each with the
  researcher's record card open.

Nothing was faked. The world read only the job and mission records the real run wrote.

## Run 3: the whole life, delivered (627 seconds)

| Step | What the records said | What the screen showed |
|---|---|---|
| Before | no job | the researcher in the Headquarters lounge, "idle", "Job: none yet" |
| Recorded, dispatched | job `job_52cef4fccef0`, RUNNING | she walked to the Research library; her task under Current tasks; "Recorded: done, Dispatched: done, Working: now" |
| Working | tools through the gateway: `inspect.skill`, `memory.brain`, `memory.search`, `search.web` | at her desk in the Research library, "working" |
| Result | COMPLETED | "Result: done" with the four tools named |
| Checked (manager) | `verification: VERIFIED` (every link in her answer was in what search returned) | "Checked: done" |
| Your review | nothing with an outside effect, check passed | "Your review: not needed" |
| Delivered | mission COMPLETED, next "delivered and checked" | she walked to **Delivered**; header "1 delivered today"; "Delivered: done" |

Her answer named CandleScience and Fillmore Container, each with a link to its own pages,
and listed the search results each fact came from. No page errors in the browser.

## Run 2: a bad answer, caught and sent to you (481 seconds)

The same task, with the model started with llama.cpp's default four parallel slots. The
researcher was dispatched and worked as in run 3, but the model wrote about 1,000 words of
garbled text and called no tool. The manager's check found no fact backed by a tool
(`verification: FAILED`), the mission paused, and the world put her in **Waiting for you**
with "Checked: stopped", "Your review: waiting", "Delivered: waiting". The world showed the
failure exactly as it happened; nothing bad was delivered.

## Run 1: too slow, stopped (failed)

Jarvis's page started his own briefing on the same model while the mission ran, two
answers shared three cores, and the agent's model call timed out. The job FAILED and the
world put her in **Stopped**. Runs 2 and 3 wait until the model is idle before starting the
mission.

## Found on the way

- **Garbled answers with parallel slots (a lead, not proven).** Run 2 used the default
  slots; the server log shows the answer reused another slot's cached prompt (4 new prompt
  tokens) before the text went wrong. Run 3 started the server with one slot
  (`-np 1 --cache-reuse 0`) and answered well. One run each way is not proof. The stick's
  `bau-llm-start` keeps the default slots, so this is worth testing on the desktop before
  changing it.
- **Speed.** About 2 words a second on this test computer's 3 cores; the desktop's card
  should be much faster, not measured yet.
- **The record card scrolls.** The task's steps are at the bottom of the card; on a small
  window you scroll to see them.

## The checks

- `tests/test_world_lifecycle.py`: six tests for every step above (assigned, working,
  checked and delivered, failed check, failed job, the world's own answer). Removing the
  "assigned" rule from `world.py` makes two of them fail (tried once, then put back).
- `bash scripts/check.sh`: ALL PASS before the commit.

## Not tested yet

- On the owner's desktop and through the laptop station.
- With a workstation shift (the same path, `jarvis.run_checked`; covered by tests only).
