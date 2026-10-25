# The desktop edition (planned, not built yet)

**Owner's decision, 2026-10-20:** the desktop gets **its own design**, not a copy of the
laptop: its own model (bigger, on the graphics card), its own set of tools, its own
workflows and its own look. What stays the same are the rules in `CLAUDE.md` (approvals
are human-only, posting waits for your click, kids content only to YouTube made-for-kids,
nothing listens beyond the computer itself, no compliance claims).

**Owner's decision, 2026-10-23:** BAU goes on the desktop's second drive (Windows calls it
D:) and Windows stays on its own drive (C:). At start-up you choose which one runs. It is
installed from the 128 GB stick. The laptop waits until a second 1 TB drive is bought.

## What the desktop check found (2026-10-23)

From the owner's `BAU-LAPTOP-SUMMARY.txt` (verdict: READY, AFTER THESE STEPS):

| Part | Found |
|---|---|
| Computer | ASUS ROG Strix G15CF, Windows 11 Home |
| Processor | Intel Core i7-12700F, 12 cores, 20 threads |
| Memory | 16 GB |
| Graphics | NVIDIA GeForce RTX 3060, 12 GB, CUDA compute 8.6 (Windows driver 576.57) |
| Windows drive | Micron 3400 NVMe SSD, 477 GB (BitLocker on) |
| BAU's drive | TOSHIBA DT01ACA100, 932 GB hard disk on SATA, no Windows on it |
| Network | MediaTek MT7921 Wi-Fi 6 and Bluetooth, Realtek 2.5 GbE cable port |
| Start-up | UEFI, Secure Boot on, TPM 2.0 |

The card was listed twice; that was the check counting an old Windows driver entry (fixed:
a card is now listed at most as many times as it is plugged in).

Before installing:

1. **Copy off anything on the TOSHIBA drive (D:)**: installing erases it.
2. **Write down the BitLocker recovery key for C:** (aka.ms/myrecoverykey). Windows may ask
   for it once after a new start-up menu is added.
3. **Turn off Windows Fast Startup** (Control Panel > Power Options > Choose what the power
   buttons do), so Windows really shuts down and leaves the disks alone.
4. Secure Boot is on: the NVIDIA driver must then be signed with a key you enroll once at
   start-up, or Secure Boot turned off. The desktop stick will show the steps.

BAU's drive is a hard disk, not an SSD: everything works, but loading a large model from
it takes longer than from an SSD (to be measured on the desktop).

## The order (the same method as the laptop)

| Step | What | Status |
|---|---|---|
| 1 | The desktop check: `installer/BAU-Desktop-Check.cmd` (see [LAPTOP-CHECK.md](LAPTOP-CHECK.md)) | built |
| 2 | The owner runs it and sends `BAU-LAPTOP-SUMMARY.txt` | done 2026-10-23 (above) |
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
