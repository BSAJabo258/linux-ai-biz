# The desktop edition (planned, not built yet)

**Owner's decision, 2026-10-20:** the desktop gets **its own design**, not a copy of the
laptop: its own model (bigger, on the graphics card), its own set of tools, its own
workflows and its own look. What stays the same are the rules in `CLAUDE.md` (approvals
are human-only, posting waits for your click, kids content only to YouTube made-for-kids,
nothing listens beyond the computer itself, no compliance claims).

What we know so far, from the owner:

- a desktop PC with a graphics card with 12 GB of memory (to be confirmed by the check);
- a 1 TB drive already in it, for BAU to run from;
- started and installed from **one USB stick**, the same way as the laptop;
- Windows may be wiped if it has to be; the owner can restore those files later.

## The order (the same method as the laptop)

| Step | What | Status |
|---|---|---|
| 1 | The desktop check: `installer/BAU-Desktop-Check.cmd` (see [LAPTOP-CHECK.md](LAPTOP-CHECK.md)) | built |
| 2 | The owner runs it and sends `BAU-LAPTOP-SUMMARY.txt` | waiting on the owner |
| 3 | Optional proof from Linux: the stick's `bau-laptop-check.sh` shows which graphics driver really loads | waiting on the owner |
| 4 | Design, from the report only (below) | not started |
| 5 | Build the desktop stick, test it in CI, then on the desktop | not started |

## What the report decides

Nothing here is chosen from memory. Each answer comes from the check report, or from an
official page with its link and date written next to the code.

| Question | Decided by |
|---|---|
| Which graphics driver goes on the stick | the card's maker and model in the report |
| How the local AI uses the card (llama.cpp's GPU build) | the maker, the driver and, on NVIDIA, the CUDA compute level |
| Which model is the boss, and how big | the card's memory, then a real `bau models bench` on the desktop |
| Whether a driver-signing step is needed at start-up | Secure Boot on or off |
| Where BAU is installed | the `Install BAU on:` line (the disk without Windows) |
| Wi-Fi or cable | whether a Wi-Fi card is found |

## Design areas (to fill in after the report)

These are questions, not promises. Each candidate goes through the `grow-bau` method (find,
inspect, test in a sandbox, the owner decides) before it is added.

- **The model team:** a stronger boss on the graphics card; whether a second local model
  (thinker or helper) fits next to it; when Claude is still called.
- **Tools:** what a desktop with a graphics card can do that the laptop could not, for
  example speech in and out on the machine, more agents working at once, and local image
  work. Each one is measured, not assumed.
- **Workflows:** which jobs run on the desktop by themselves (scheduled, with every
  consequential step still waiting for your click).
- **The look:** its own design for a big screen.
- **Laptop and desktop together:** whether the laptop keeps its own edition and how the two
  share your work.

## How it is checked

The "Check yourself" rules in `CLAUDE.md` apply: `bash scripts/check.sh` must say ALL PASS,
every report says what actually ran and what did not, and "works" is only said after it
ran on the desktop itself.
