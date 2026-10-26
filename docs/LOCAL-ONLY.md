# Local only: every model stays on this computer

**Owner's decision, 2026-10-26:** no cloud models. Claude, OpenAI-style hosted models (Z.ai,
NVIDIA) keep what is sent to them, and your workflows are your business. BAU's thinking
runs on the models on your own computer.

## Turn it on (once, on the installed computer)

```bash
bau privacy local-only
bau privacy                 # shows your choice
```

Only you can set it, typed at the terminal; no model, agent or Jarvis can change it. To
allow approved cloud models again: `bau privacy cloud`.

## What it does

Every model in BAU is started in one place, and with local only on, that place refuses:

- Claude (any version) and every hosted model that needs an API key (Z.ai, NVIDIA);
- any model server on another computer, even one whose record says "local". Only
  addresses on this computer count (127.0.0.1, ::1, localhost).

So Jarvis skips them when he picks his model, the team refuses a cloud specialist
(`bau team set`), the specialist and the double-check say "not double-checked" instead
of sending anything out, and `bau models bench` refuses them too. You don't need any API
keys for models; leave them out of `BAU-KEYS.enc`.

What still uses the internet, only when you ask for it: web research (`web_search`,
`read_page`) reads public pages, and posting to YouTube sends the video you confirmed.
Neither hands your files or conversations to a model.

## The best local models for your computers

Read 2026-10-26 from the Hugging Face pages named below. Scores are each maker's own
numbers (not ours, and not always measured the same way); BAU's own test is
`bau models bench` on your computer. Sizes are the real file sizes.

| Model (licence) | Kind | 4-bit-or-smaller files | Maker's scores |
|---|---|---|---|
| Qwen3.5-9B (Apache-2.0), today's boss | 9B | Q4_K_M 5.7 GB | IFBench 64.5, BFCL-V4 66.1, GPQA 81.7 |
| Qwen3.8-27B (Apache-2.0), August 2026 | 27B | UD-Q2_K_XL 9.8 GB, UD-IQ3_XXS 10.9 GB, UD-IQ3_S 12.0 GB, Q4_0 16.1 GB | IFBench 79.5, GPQA 89.2, LiveCodeBench v6 90.3, Terminal Bench 2.1 73.0 |
| Qwen3.5-35B-A3B (Apache-2.0) | 35B, 3B working per word | UD-Q3_K_XL 16.6 GB | IFBench 70.2, BFCL-V4 67.3 |
| Mellum2.1-12B-A2.5B Thinking (Apache-2.0), JetBrains, coding | 12B, 2.5B per word | Q4_K_M 8.1 GB | JetBrains's own table: LiveCodeBench 82.0 vs the 9B's 75.4, but SWE-bench Verified 47.0 vs the 9B's 50.0 |

Pages: `Qwen/Qwen3.5-9B`, `unsloth/Qwen3.5-9B-GGUF`, `Qwen/Qwen3.8-27B`,
`unsloth/Qwen3.8-27B-GGUF`, `Qwen/Qwen3.5-35B-A3B`, `unsloth/Qwen3.5-35B-A3B-GGUF`,
`JetBrains/Mellum2.1-12B-A2.5B-Thinking(-GGUF)`.

- **Desktop today:** Qwen3.5-9B is the boss. It fits on the card whole, it is on the stick
  and in the pack.
- **First to test on the desktop (registered, not tested):** Qwen3.8-27B in its 9.8 GB
  and 10.9 GB files (`qwen3.8-27b-q2`, `qwen3.8-27b-iq3`; steps in
  [MODEL-LAB.md](MODEL-LAB.md)). It uses the same design as Qwen3.5 (`qwen3_5` in its config), so the
  stick's llama.cpp should load it, but only a run proves that. Whether it fits next to the
  desktop's own screen on the card, how fast it is, and how much 2- and 3-bit compression
  costs in right answers are exactly what the desktop test must measure.
- **Also registered for the desktop test:** Mellum2.1 (`mellum2.1-12b`, 8.1 GB), for
  coding. The stick's llama.cpp is now build b11747, which has the Mellum fixes of 15-16
  October (JetBrains names b11747 for its speed-up "MTP" files).
- **Later:** Qwen3.5-35B-A3B (part of it in normal memory).
- **Not for this computer:** Qwen3.8-Flash-Next (125B; and its own "qwen-community"
  licence, not Apache).
- **Laptop (8 GB, no graphics card):** Qwen3.5-4B stays the boss.

With local only, set the team like this (all on your computer):

```bash
bau team set --boss qwen3.5-9b --specialist qwen3.5-9b --takeover ask
```

## Tested so far (2026-10-26)

- Tests (`tests/test_localonly.py`): with local only on, Claude and Z.ai records are
  refused, a "local" record pointing at another computer is refused, the 9B on 127.0.0.1
  still starts, Jarvis picks the local model over an approved Z.ai one, the team refuses
  Claude as the specialist, and the command refuses anyone not at a terminal. Removing the
  check makes four of these tests fail.
- Not yet run on your desktop.
