# The whole business on the laptop, with Colibri

The desktop is down, so the laptop takes over: Jarvis, the agents, the autopilot, clips,
PayPal and Fanvue's money all run there. Its model runs on **Colibri**
(github.com/JustVugg/colibri, Apache-2.0). Colibri keeps only part of a big model in memory
and reads the rest from the disk when it needs it. That lets the laptop's 8 GB run
**Qwen3-Coder-30B-A3B**, a much stronger model than the stick's small one, with tool calls.

Facts read on Colibri's own pages and code on 2026-11-24 (release v2.2.0).

## What to expect

- **It is slow.** Colibri's own figures are from an 8-core desktop with a fast disk: about
  5 words a second, and "a request whose tool block makes the prompt about 500 tokens takes
  around two minutes from a cold cache". Jarvis's requests are longer, and the XPS 13 has 4
  cores and runs from the USB disk. Expect minutes per answer at first. It speeds up as the
  experts it uses most stay in memory.
- **It uses most of the memory**: about 6.5 GB. Close what you do not need.
- **No pictures.** The laptop has no graphics card, so her new Fanvue pictures wait for the
  desktop. Posts already queued, fan chat, clips, PayPal and the books keep working.
- **Measured, not guessed.** Step 3 measures it on your laptop. If it is too slow, step 6
  goes back to the stick's small model.

## Set it up

### 1. The laptop does the work

```
sudo bau station role off
```

The laptop was set up as the station, which leaves the work to the desktop. This turns its
autopilot back on.

### 2. Install Colibri and the model (once, about 20 GB)

The script is in the BAU payload on a laptop installed from the newest stick. On this laptop,
download it from GitHub first:

```
git clone --depth 1 https://github.com/BSAJabo258/linux-ai-biz ~/bau-src
sudo bash ~/bau-src/installer/bau-colibri-setup.sh
```

It checks that the laptop has 8 GB of memory and 22 GB of free disk, then builds Colibri at
the exact tested version. It downloads the model's 57 files and checks every one against its
fingerprint: a file that does not match is deleted and the script stops. If the download is
cut off, run the same line again and it carries on.

Last, it starts the model as a service on this computer only (127.0.0.1:8000, no network).
The stick's small model is stopped, because both do not fit in 8 GB.

### 3. Measure it, then make it Jarvis's model

```
sudo bau models bench qwen3-coder-30b-colibri
```

If the bench says it answered and used a tool, approve it and make it the boss:

```
sudo bau set-status model qwen3-coder-30b-colibri APPROVED
sudo bau team set --boss qwen3-coder-30b-colibri
```

### 4. The business's keys

The keys were on the desktop. Bring them over with the `BAU-KEYS.enc` file from your other
computer (`docs/KEYS.md`):

```
sudo bau keys import /media/YOUR-STICK/BAU-KEYS.enc
```

Or type them in one by one with `sudo bau keys set NAME`. Then sign in to Fanvue and
YouTube on the laptop, and check PayPal:

```
bau fanvue login
bau youtube login
bau paypal check
```

### 5. Start Jarvis and check the money machine

```
bau jarvis
bau money
```

`bau money` lists every link from the creator to the money, with the fix for any that is not
working.

### 6. Undo

```
sudo systemctl disable --now bau-colibri
sudo systemctl enable --now bau-llm
sudo bau station role on
```

This goes back to the stick's small model and to the laptop as the desktop's station.

## Good to know

- `sudo systemctl status bau-colibri` shows whether the model is running and its last
  messages.
- **Short of memory?** Lower `COLI_CAP` in `/etc/bau/colibri.env` from 32 to 16, then run
  `sudo systemctl restart bau-colibri`. It uses less memory and answers slower.
- **Checked before it joined BAU.** Its code was scanned in quarantine. The 12 "secrets" the
  scan flagged are test placeholders and AWS's published example key. The "cookie" and
  "startup file" patterns are a web-page cleaner and test sentences. It was built and tested
  in a sandbox with no network. Its server answers on 127.0.0.1 only and refuses any other
  address without a key.
- Pinned versions: Colibri commit `e479104` (v2.2.0), the model at commit `d839110` of
  huggingface.co/Justvugg/Qwen3-Coder-30B-A3B-colibri-int4. The fingerprints are in
  `installer/colibri/`.
