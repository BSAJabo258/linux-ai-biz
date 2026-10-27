# The desktop edition (designed, not built yet)

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
| 4 | Design, from the report and official pages (below) | written 2026-10-25 |
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

## The design (2026-10-25, from the report and official pages)

Every fact below was read on 2026-10-25 from the page named next to it. Nothing here has
run on the desktop yet; each step is proved by the stick build on GitHub first, then on the
desktop.

### Graphics driver

- Debian 13's own NVIDIA driver: `nvidia-driver` and `nvidia-kernel-dkms` 550.163.01, in
  non-free (packages.debian.org/trixie/nvidia-driver). NVIDIA's list for 550.163.01 has the
  RTX 3060 (download.nvidia.com/XFree86/Linux-x86_64/550.163.01/README/supportedchips.html).
- The **closed** flavour, not the open one: Debian's wiki says the open flavour of 550.163.01
  "no longer compiles" from kernel 6.12.100 on (wiki.debian.org/NvidiaGraphicsDrivers).
- Honest warning from the same wiki: the 550 branch "is no longer maintained and contains
  several security issues". It is still the newest driver Debian 13 packages. A newer
  driver straight from NVIDIA is possible later, as its own tested step.

### Secure Boot

- The driver is built **on the desktop after the install**, not on the stick. The tool that
  builds it (dkms) makes a signing key on that computer (`/var/lib/dkms/mok.key`); a key
  baked into the stick would be the same on every stick, which is unsafe.
- You enroll that key once: `sudo mokutil --import /var/lib/dkms/mok.pub`, choose a one-time
  password, restart, and in the blue screen choose **Enroll MOK**, Continue, Yes, the
  password, OK (wiki.debian.org/SecureBoot; dkms 3.2.2 README).
- Check afterwards: `mokutil --list-enrolled | grep DKMS` shows "DKMS module signing key".
- It needs the internet once (the cable port or Wi-Fi): the driver comes from Debian.

### The model engine on the graphics card

- llama.cpp built with **Vulkan**: it needs only the driver's `nvidia-vulkan-icd`, not the
  multi-gigabyte CUDA kit. Community results on an RTX 3060 (Llama-2-7B, 4-bit): Vulkan wrote
  80.6 tokens/s, CUDA 76.9 (github.com/ggml-org/llama.cpp discussions 10879 and 15013,
  different machines). CUDA (Debian's 12.4 kit, card level 8.6) stays the fallback if the
  desktop's own benchmark says Vulkan is worse.
- The port is always given (`--port 8080`): llama.cpp v0.7.0 changed its default to 9931.

### The boss model

| Choice | Model (licence) | File (4-bit) | Context |
|---|---|---|---|
| 1st | Qwen3.5-9B (Apache-2.0) | `unsloth/Qwen3.5-9B-GGUF`, Q4_K_M, 5,680,522,464 bytes | 262K (capped for 12 GB) |
| 2nd | Gemma 4 12B-it (Apache-2.0) | `unsloth/gemma-4-12b-it-GGUF`, Q4_K_M, 7,121,861,440 bytes | 256K |
| 3rd | Granite 4.2 8B (Apache-2.0) | `ibm-granite/granite-4.2-8b-GGUF`, Q4_K_M, 5,347,917,952 bytes | 128K |

Sizes and SHA-256 come from each Hugging Face file list; they are pinned when added. No
Qwen3.5 14B exists; gpt-oss-20b (12.1 GB file) leaves no room. As always, a model is
approved only after `bau models bench` on the desktop.

### The rest

- **Drive:** BAU on the 932 GB TOSHIBA, encrypted like the laptop. It is a hard disk, so a
  5.7 GB model takes longer to load than from an SSD; it stays on the card once loaded.
- **Processor:** 12 cores, so the CPU keeps plenty free for the desktop and Jarvis's page.
- **Network:** Wi-Fi (MT7921) and the 2.5 GbE port, firmware already on the stick.
- **Next design areas** (each through the `grow-bau` method): voice in and out on the card,
  more agents at once, local image work, and how the laptop and desktop share your work.

## Set up the desktop, step by step

Steps 1 to 3 use the same stick as the laptop. The desktop parts switch on only on a
computer with an NVIDIA card.

1. **Before:** copy off anything on the D drive, write down the BitLocker key for C:, and
   turn off Windows Fast Startup (the list above).
2. **Install BAU on the TOSHIBA drive** from the stick: start the computer from the stick and
   choose **Install BAU on this laptop**. Pick the TOSHIBA DT01ACA100 (932 GB), never the
   Micron NVMe (that is Windows). If the screen stays black, start again and choose **Install BAU -
   safe graphics** in the stick's menu.
3. **Start from the new drive** and log in. The internet is needed for the next step (the
   cable port or Wi-Fi).
4. **The graphics driver**, once:

   ```bash
   sudo bau-gpu-setup
   ```

   Type `y` when it asks. It installs Debian's NVIDIA driver and the newest Debian kernel.
   With Secure Boot on, it asks you for a one-time password. Restart with
   `sudo systemctl reboot`; on the blue screen choose **Enroll MOK**, Continue, Yes, the
   password, OK.
5. **Check the card:** `nvidia-smi` shows the RTX 3060.
6. **The desktop's boss model.** On the Windows side of the desktop (or any Windows
   computer), fill the 64 GB stick with `BAU-Pack-Make.cmd` (see [PACK.md](PACK.md)); it
   now also carries Qwen3.5-9B (5.7 GB). Back on BAU, with the driver from step 4 running:

   ```bash
   sudo bau pack install
   ```

   It copies and checks the models, starts the 9B on the card, measures it with a real
   benchmark, and asks you before approving it and before making it the boss. On a
   computer without NVIDIA's driver loaded (the laptop) it leaves the 9B on the stick and
   keeps the 4B. When it asks about keys, you can skip them: with step 7 no model needs one.
7. **Keep every model on this computer** (see [LOCAL-ONLY.md](LOCAL-ONLY.md)):

   ```bash
   bau privacy local-only
   bau team set --boss qwen3.5-9b --specialist qwen3.5-9b --takeover ask
   ```
8. **Measure, then try stronger models:** `bau hw`, then the steps in
   [MODEL-LAB.md](MODEL-LAB.md) (the 9B as the baseline, then Qwen3.8-27B).
9. **Try the CUDA engine** and keep it only if it is faster: [GPU.md](GPU.md).

## Tested so far (2026-10-25, not on the desktop yet)

- The stick's llama.cpp (v0.6.0, d812350) built with its Vulkan part in a clean Debian 13:
  9 minutes on 4 cores, `libggml-vulkan.so` made. On 2026-10-26 the same for build b11747
  (f711c8f), the stick's engine from now on: 7 minutes, Vulkan part made, "Vulkan0" through
  lavapipe and the right answer, and the same model-lab scores as v0.6.0 (MODEL-LAB.md).
- With no Vulkan loader it starts and lists no card. With a software Vulkan card (Mesa's
  lavapipe) it lists "Vulkan0" and answered "What is 7 times 8?" right through it.
- Through `bau-llm-start` with no NVIDIA driver loaded, it set `LLAMA_ARG_DEVICE=none` and
  answered right on the processor (15.7 tokens/s, Qwen2.5-1.5B).
- llama.cpp's own code (ggml-vulkan.cpp) uses dedicated cards first and otherwise falls
  back to built-in graphics, which is why BAU turns the card off without NVIDIA's driver.
- The driver packages resolve with apt in a clean Debian 13.7. The NVIDIA card itself, the
  driver build and Secure Boot can only be proved on the desktop.

## How it is checked

The "Check yourself" rules in `CLAUDE.md` apply: `bash scripts/check.sh` must say ALL PASS,
every report says what actually ran and what did not, and "works" is only said after it
ran on the desktop itself.
