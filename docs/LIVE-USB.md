# My Jarvis live USB

The live USB is a whole computer system on one USB stick. Plug it into a PC, start the PC
from it, and that PC becomes your My Jarvis workstation. Nothing on the PC's own drive is
used or changed. Take the stick out and the PC is exactly as it was.

Your work (Jarvis's memory, BAU's records and keys, your files, saved Wi-Fi) is kept in
**encrypted storage on the same stick**, locked with a passphrase you choose. Without the
passphrase nobody can read it, not even with the stick in their hands.

The same stick can also **install BAU onto a laptop's own drive** when you're ready: pick
**Install BAU on this laptop** in the boot menu (see "Install BAU on this laptop" below).
One stick does both.

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
   - **Claude (optional):** answer `y` to let Jarvis use Claude, then paste your Anthropic
     API key (from console.anthropic.com) and press Enter. The key is not shown on screen
     and is kept only in your encrypted storage. Anthropic bills your account for every
     conversation, and what you say to Jarvis goes to Anthropic. Setup runs one short test
     conversation (a few cents) and then asks you to approve Claude: answer `y`. Answer `n`
     to skip Claude; you can run Setup again later.
   - **Local model:** answer `y` to download it (1.1 GB, checked against a fixed
     fingerprint). It also works without internet. If you approved Claude you can skip it.
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
| Install BAU on this laptop | Installs BAU onto this PC's own drive, encrypted. **Erases the drive you choose.** See below |
| limited mode | Starts without opening your storage. Nothing is saved; BAU stays off. For a quick look, or if you forgot the passphrase |
| safe graphics | Same as normal, for screens that stay black |
| recovery | Text console only, no desktop: for repairs |
| Utilities | UEFI firmware settings, checking the stick for damage |

This menu is what UEFI PCs (nearly every PC from the last ten years) show. Older BIOS-only
PCs show a simpler menu: choose the first entry for a normal start.

## Install BAU on this laptop

When you want BAU on a laptop's own drive instead of running it from the stick:

1. **Back up anything on that laptop you want to keep.** The drive you pick is erased.
   Not sure the laptop is suitable? Run the read-only check first: [LAPTOP-CHECK.md](LAPTOP-CHECK.md).
2. Start the laptop from this stick and choose **Install BAU on this laptop**.
3. The installer asks you, and only you:
   - **which drive** to install to, and to **confirm** erasing it (BAU never picks it);
   - a **passphrase** for the encrypted drive (you type it at every start; there is no way
     back in without it);
   - the **password** for the `bauadmin` account;
   - your **time zone**.

   Everything else is set the BAU way: full-disk encryption, root login off, network time.

   **Where the boot loader goes.** Near the end the installer asks **Install the GRUB boot
   loader to your primary drive?** Answer **No** unless BAU goes on the laptop's own
   drive, then pick the **same drive you installed to** (for a USB disk, the one named
   after it, e.g. SanDisk; never the stick you started from). Not sure which is which?
   Press **Alt+F2**, then Enter, type `lsblk -o NAME,SIZE,MODEL` and compare the sizes;
   **Alt+F1** brings you back.

   **"grub-install ... failed. This is a fatal error."** Nothing is lost. Press Enter,
   choose **Install the GRUB boot loader** in the menu and pick the right drive as above.
   Don't choose **Continue without boot loader**: the laptop could not start BAU. Still
   failing? **Alt+F4** shows the installer's log; a photo of the last lines tells us why.

   Other screens (console encoding, character set, font, keyboard): keep what is
   highlighted (UTF-8, "Guess optimal character set", English (US)) and press Enter.
4. It copies the same tested system you run from the stick (desktop, BAU, local-model
   runner), so nothing large is downloaded. It also copies BAU's install files to
   `/opt/bau-payload`, checking every file; a damaged copy is deleted, not used.
5. Take the stick out when it says so and restart. Type the disk passphrase, then log in
   as `bauadmin`.
6. A window **Finish installing BAU** opens by itself. No internet is needed: everything
   BAU uses is on the stick. Type your `bauadmin` password, and choose a passphrase for
   your approval key when BAU asks (remember it: it signs your approvals). It takes about
   ten minutes. (A stick built before 2026-10-13 still needs the internet here: connect
   to Wi-Fi, or use your phone, see "No Wi-Fi?" below.)
7. Log out and in again once. Jarvis is in the menu as on the stick.

   If you close the window or something goes wrong, nothing is lost: it opens again at
   the next login until BAU is installed. You can also run it yourself in a terminal:

   ```bash
   sudo bash /opt/bau-payload/install.sh
   ```

Your encrypted storage on the stick is not touched by the install: keep the stick as your
portable Jarvis and recovery stick.

## Good to know

- **No Wi-Fi? Use your phone.** Plug your phone into the laptop with its USB cable, then
  turn on **USB tethering** (Android: Settings > Network > Hotspot & tethering > USB
  tethering; iPhone: Settings > Personal Hotspot > Allow Others to Join, then trust the
  computer). Linux uses it at once, no driver needed, and the network icon shows a wired
  connection. Then run the laptop check (`docs/LAPTOP-CHECK.md`, part 2) and send the
  summary: it shows why the Wi-Fi is not working.

- **Wrong passphrase:** the screen asks *Retry? [Y/n]*. Press Enter to type it again, or
  `n` to start without your storage (limited mode: nothing is opened or saved).
- **Lost passphrase:** the storage cannot be opened by anyone. Rewrite the stick (step 1)
  and start again. Keep a backup of what matters (see `bau backup`).
- **Updates:** the system part of the stick is read-only, so updates come as a new
  image. Install the new image on a second stick and keep the old one until the new one
  works. Moving your encrypted storage between sticks is a later feature.
- **Security:** the firewall blocks everything coming in. BAU's dashboards only listen on
  this PC itself. The local model runs on this PC and sends nothing out.
