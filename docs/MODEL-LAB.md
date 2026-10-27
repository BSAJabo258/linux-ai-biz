# The model lab: measure first, then choose

**Owner's rule, 2026-10-26:** find out what the computer can really do, test the strongest
models that fit, and let the numbers choose. Never assume the graphics card's memory, and
keep it apart from the computer's own memory.

## 1. Measure the computer

```bash
bau hw                      # memory, graphics card and its memory, processor, disk, engine
bau hw --full               # every detail
bau hw fit --size 9828981664   # would a model file of this many bytes run here?
```

It only reads. The card's memory comes from NVIDIA's own `nvidia-smi`; until NVIDIA's
driver runs (`sudo bau-gpu-setup`) it says "unknown" instead of guessing. `fit` answers
**card** (fast), **card+memory** (works, slower), **memory** (processor only, slow),
**no**, or **unknown**. It is an estimate: the file plus about 1 GB for the model engine
and an 8K-word context. The lab below measures the real thing.

`bau models fetch` uses the same check: it refuses when the disk is too small and tells
you the estimate before a download of many GB starts.

## 2. Test a model

The model must be running first. To run a downloaded candidate (this does not approve
it, and does not make it the boss):

```bash
bau models fetch qwen3.8-27b-q2
sudo bau models use qwen3.8-27b-q2
bau models lab qwen3.8-27b-q2              # add --run-code for the coding part
```

The lab asks every model the same things (`src/bau/data/model_lab.yaml`):

| Part | What it checks |
|---|---|
| Reasoning | 10 questions with known answers (sums, days, order, logic) |
| Tools | 3 tool calls checked against their rules (right tool, every required value, right kind of value, allowed values only, nothing extra), and one request where no tool fits |
| JSON | a reply that must be valid JSON with the right values |
| Coding (`--run-code`) | 2 small Python fixes, checked by running their tests |
| Long prompts | a hidden fact in prompts of about 2,000, 8,000, 16,000 and 32,000 tokens (only those the model's context allows); stops at the first that runs out of memory |
| Speed | time to the first word and words per second, from llama-server's own measurements |
| Memory | the model server's peak memory, and the card's peak memory while the lab ran |

It ends with **meets the bar** or what it fell short on (the bar is at the top of the
suite file). Every result is saved in `BAU_HOME/models/lab/MODEL/` with the suite's
fingerprint and the model file's SHA-256, and its summary goes on the model's record.

**Safety:** the lab only grades replies, never follows them. Code a model writes runs
only with `--run-code`, and only if it is a single plain function (no imports, no files,
no hidden names); it runs in a separate Python with no settings, nothing it can write,
5 seconds and 512 MB at most.

## 3. Compare

```bash
bau models compare qwen3.5-9b qwen3.8-27b-q2      # the first is the baseline
```

Add `--repeat 3` to run the lab three times (middle value and range) and `--tag NAME` to
keep a setup apart, e.g. the same model on the CUDA engine (`--tag cuda`, compared as
`qwen3.5-9b@cuda`; see [GPU.md](GPU.md)). The lab also records the card's highest
temperature and power draw and how busy it was.

It shows each part's score for both, their speed and memory, and every question one got
right and the other wrong. This is also how you see what compression costs: run the lab
on the 2-bit and the 3-bit file of the same model and compare them.

## 4. You decide

Nothing changes on its own. When a candidate meets the bar and beats the boss in your
own numbers:

```bash
bau set-status model qwen3.8-27b-q2 APPROVED
bau team set --boss qwen3.8-27b-q2
```

To go back: `sudo bau models use qwen3.5-9b` and `bau team set --boss qwen3.5-9b`.

## On the desktop, in this order

1. `bau hw`, after `sudo bau-gpu-setup`: note the card's memory and how much the screen
   already uses.
2. `bau models lab qwen3.5-9b --run-code`: the baseline.
3. Qwen3.8-27B, 2-bit (9.8 GB, the likeliest to fit on the card), then 3-bit (10.9 GB, the
   estimate says it may spill into memory next to the screen): fetch, use, lab, compare.
4. Mellum2.1 (`mellum2.1-12b`, 8.1 GB, for coding): fetch, use, `lab --run-code`, compare
   with the 9B. It thinks before it answers, so expect it to be slower per answer.

## Tested so far (2026-10-26)

- 25 tests (`tests/test_machine.py`, `tests/test_model_lab.py`) with fake computers and a
  fake model: the RTX 3060 report read right, "unknown" without the driver, fit answers,
  wrong answers and bad tool values caught, out of memory on a long prompt recorded,
  unsafe code refused before it runs, endless loops and memory bombs stopped, a model
  server that is not up refused with nothing saved.
- `bau hw` run for real on the cloud test machine (no graphics card: it said so).
- The whole lab, for real, against the stick's own llama-server (v0.6.0, d812350) on the
  cloud machine's processor (3 threads, no graphics card):

  | | Qwen3.5-4B (Q4_K_M) | Qwen2.5-1.5B (Q4_K_M) |
  |---|---|---|
  | Reasoning | 9 of 10 (said Tuesday for "Wednesday + 10 days") | 8 of 10 |
  | Tools | 4 of 4 | 4 of 4 |
  | JSON | right | wrong (wrapped it in an extra "object") |
  | Coding (`--run-code`) | 2 of 2 | 2 of 2 |
  | Long prompts | 2,000 and 8,000 right (16,000 and 32,000 over its 16K setting) | 2,000 right |
  | Time to first word | 1.3 s | 0.3 s |
  | Words per second | 5.4 | 15.2 |
  | Server's peak memory | 9.2 GB (this run had llama-server's default 8 GB prompt cache, not the stick's 1 GB) | 2.4 GB (1 GB cache, as on the stick) |
  | Whole lab | 6 minutes | 39 seconds |
  | Lab says | meets the bar | short of the bar: JSON |

  The first try at the 1.5B ran while its server was still loading and scored zero on
  everything; the lab now refuses that and saves nothing (proved on the next run).
- The stick's engine moved from llama.cpp v0.6.0 to build b11747 (f711c8f, 2026-10-20)
  after the same lab on both, Qwen3.5-4B, the stick's settings, 3 threads:

  | | v0.6.0 | b11747 |
  |---|---|---|
  | Scores | reasoning 0.9, tools 1.0, JSON 1.0, coding 1.0, long 1.0 | the same, the same wrong answer |
  | Time to first word | 1.29 s | 1.29 s |
  | Words per second | 5.4 | 5.2 |
  | Whole lab | 6 min 5 s | 5 min 57 s |

  On b11747 a page from another website gets no CORS answer and `/slots` answers 501, as
  before; with lavapipe it lists "Vulkan0" and answers right through it.
- Not yet run on the desktop or the laptop, and no card was there to measure card memory.
