# My Jarvis live USB

The live USB is a whole computer system on one USB stick. Plug it into a PC, start the PC
from it, and that PC becomes your My Jarvis workstation. Nothing on the PC's own drive is
used or changed. Take the stick out and the PC is exactly as it was.

Your work (Jarvis's memory, BAU's records and keys, your files, saved Wi-Fi) is kept in
**encrypted storage on the same stick**, locked with a passphrase you choose. Without the
passphrase nobody can read it, not even with the stick in their hands.

This is the portable way to run BAU. The other way, installing BAU onto a laptop's own
drive from the two install sticks, is in `INSTALL.md`.

## What you need

- A USB stick of **at least 16 GB** (64 GB or more is better; a USB SSD is faster and
  lasts longer than a cheap flash stick).
- A 64-bit PC with **8 GB RAM** or more. No graphics card needed.
- The image file `my-jarvis-<version>-amd64.iso` and its `.sha256` file, from the
  repository's GitHub **Releases** or **Actions > build-live > Run workflow**.

## 1. Put the image on the stick

Everything already on the stick is erased.

**Windows:** install **balenaEtcher** (etcher.balena.io). Choose *Flash from file* (the
`.iso`), *Select target* (your USB stick, check the size), then *Flash!*.

Or use **Rufus** (rufus.ie): select the stick and the `.iso`, click START, and when Rufus
asks how to write it, choose **DD Image mode**. Don't use ISO mode: it leaves no free space
for your encrypted storage.

**Linux / Mac:** `sudo dd if=my-jarvis-<version>-amd64.iso of=/dev/sdX bs=4M conv=fsync status=progress`
(replace `/dev/sdX` with the stick: check with `lsblk`; a wrong letter erases that disk).

## 2. Start the PC from the stick

1. Plug the stick in and switch the PC on.
2. Open the boot menu: usually **F12**, **F11**, **F9** (HP) or **Esc** while the PC starts.
   Choose the USB stick (sometimes shown as "UEFI: <stick name>").
3. The My Jarvis menu appears. Choose **My Jarvis**.

If the PC refuses to start from USB, turn off *Secure Boot* in the firmware settings, or
choose *Utilities... > UEFI Firmware Settings* from the My Jarvis menu to get there.

## 3. First start: setup

The desktop opens and **My Jarvis Setup** starts by itself. It asks one thing at a time.

1. **Encrypted storage.** Answer `y`. It uses the free space on the stick (nothing is
   deleted), asks you to type `YES`, then asks for your passphrase twice. Choose a long
   one you will remember and write it down somewhere safe. Then it restarts.
2. **Unlock.** After the restart, the screen asks for the passphrase (*Please unlock
   disk...*). Type it and press Enter. You do this every time you start My Jarvis.
3. **Connect to the internet** (network icon, top right), then Setup continues:
   - **Local model:** answer `y` to download it (1.1 GB, checked against a fixed
     fingerprint).
   - **Measure:** Setup runs a short test on this PC and shows the speed and whether
     the model answered.
   - **Approve:** you decide. Answer `y` to let Jarvis use it.
4. **Talk to Jarvis.** Answer `y`. A private link opens in Firefox; click it, then talk
   or type.

Later, open **BAU Jarvis** from the menu to talk to Jarvis, and **Mission Control** to
see the dashboard. Setup can be run again any time; it only does what is still missing.

## The boot menu

| Entry | What it does |
|---|---|
| My Jarvis | Normal start: asks for your passphrase, opens your encrypted storage |
| limited mode | Starts without opening your storage. Nothing is saved; BAU stays off. For a quick look, or if you forgot the passphrase |
| safe graphics | Same as normal, for screens that stay black |
| recovery | Text console only, no desktop: for repairs |
| Utilities | UEFI firmware settings, checking the stick for damage |

This menu is what UEFI PCs (nearly every PC from the last ten years) show. Older BIOS-only
PCs show a simpler menu: choose the first entry for a normal start.

## Good to know

- **Wrong passphrase:** the screen asks *Retry? [Y/n]*. Press Enter to type it again, or
  `n` to start without your storage (limited mode: nothing is opened or saved).
- **Lost passphrase:** the storage cannot be opened by anyone. Rewrite the stick (step 1)
  and start again. Keep a backup of what matters (see `bau backup`).
- **Updates:** the system part of the stick is read-only, so updates come as a new
  image. Install the new image on a second stick and keep the old one until the new one
  works. Moving your encrypted storage between sticks is a later feature.
- **Security:** the firewall blocks everything coming in. BAU's dashboards only listen on
  this PC itself. The local model runs on this PC and sends nothing out.
