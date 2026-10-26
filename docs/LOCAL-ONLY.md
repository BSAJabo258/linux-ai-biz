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

From Qwen's own model cards (huggingface.co/Qwen, read 2026-10-26). These are Qwen's
numbers, not ours; BAU's own test is `bau models bench` on your computer.

| | Qwen3.5-9B | Qwen3.5-35B-A3B |
|---|---|---|
| MMLU-Pro (knowledge) | 82.5 | 85.3 |
| IFBench (following instructions) | 64.5 | 70.2 |
| BFCL-V4 (using tools) | 66.1 | 67.3 |
| TAU2-Bench (agent jobs) | 79.1 | 81.2 |
| 4-bit file (unsloth) | 5.7 GB (Q4_K_M) | 16.6 GB (UD-Q3_K_XL), 22.0 GB (Q4_K_M) |
| Licence | Apache-2.0 | Apache-2.0 |

- **Desktop (RTX 3060, 12 GB on the card, 16 GB memory):** Qwen3.5-9B is the boss. It
  fits on the card whole, so it is fast, and it is already on the stick and in the pack.
- **A stronger specialist for the desktop (planned, not tested):** Qwen3.5-35B-A3B. It
  is a "mixture of experts": only 3B of its 35B parts work on each word, so part of it can
  sit in normal memory and still be quick. Its 16.6 GB file does not fit on the card
  alone, and with 16 GB of memory it is tight. It goes in only after a real run on the
  desktop shows its speed and memory use, and you say yes.
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
