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
  To build it yourself, step by step: [BUILD-ISO.md](BUILD-ISO.md).

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

## Installing programs while running from the stick

Running from the stick, the system's "disk" is a slice of the laptop's **memory**: about
half of it (3.7 GB on an 8 GB laptop). Only your files and settings are kept on the
encrypted storage. So, on the live stick:

- **programs you install are gone at the next restart;**
- **big installs fill memory.** When that slice is full, nothing more installs (apt says
  *"You don't have enough free space in /var/cache/apt/archives/"*), and the laptop is
  short of memory for Jarvis and the desktop. Linux may then stop a program. The stick
  tells Linux to stop the local model first (it restarts by itself), so your terminal and
  the desktop are spared where possible.

The laptop check shows how full it is (`system space (in memory, live stick)`).

**To install programs that stay, put BAU on a disk:** open **Install BAU to a disk**
from the applications menu (System). It lists the disks, marks the stick BAU started
from (never pick that one), and on your `y` restarts to the start menu.

`bau pack install` refuses to copy the models into this memory: start My Jarvis normally
and unlock your encrypted storage first, or install BAU to a disk.

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

   **"Use entire disk" is right.** BAU encrypts the whole drive it installs to, and the
   Debian installer can only do that on a whole drive, so "use the largest continuous free
   space" does not work here. "Entire disk" means **only the drive you pick**: the other
   drives (Windows, the stick you started from) are not touched. That drive is also your
   storage: the system takes about 15 GB, the rest holds your files, BAU's data and the
   AI models (about 6.5 GB). A 128 GB SanDisk is plenty. Pick it by its **name and size**
   in the list; never the one that holds Windows, never the stick you started from.

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

   **"Debootstrap Error: Failed to determine the codename for the release."** A stick built
   before 2026-10-14 needs the internet at this step (newer sticks don't). Nothing is lost:
   plug your phone in with a USB cable and turn on **USB tethering** (Settings > Network >
   Hotspot & tethering). Press Enter on the error, then in the installer's menu choose
   **Configure the network** (it finds the phone by itself), then **Choose a mirror of the
   Debian archive** (keep deb.debian.org), then **Install the system** again.

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

## Your laptop: Dell XPS 13 9380

From your laptop check (October 2026):

| Part | On BAU |
|---|---|
| Wi-Fi (Killer 1435 / Qualcomm QCA6174) | works: firmware and the Wi-Fi login program are on the stick |
| Bluetooth (Qualcomm QCA61x4A) | works: pair speakers and controllers with the Bluetooth icon at the top |
| Sound (speakers, headphones, Jarvis's voice) | works: volume in the sound icon, or `pavucontrol` |
| Screen (Intel UHD 620), brightness keys | work |
| Webcam | works (standard USB camera driver) |
| Fingerprint reader (Goodix 27c6:5385) | not supported by Linux's fingerprint software as far as we know: use your password |
| Heat | Intel's thermal service (`thermald`) keeps the CPU from overheating and throttling |
| Internal SSD (Intel 512 GB) | **hidden from Linux** while the firmware's storage mode is "RAID On" |

**The internal SSD.** Dell ships this laptop with the storage mode set to "RAID On", and
in that mode Linux cannot see the internal drive at all, which is why the installer only
offers the USB stick. To ever install BAU on the internal drive next to Windows, the mode
must be "AHCI" (F2 at start > System Configuration > SATA Operation). **Do not switch it
straight away**: Windows set up in RAID mode may then not start. Windows must be prepared
first (start it once in Safe Mode, switch to AHCI, start Windows again). This is your
choice; running BAU from the SanDisk does not need it.

## If the desktop dies after a few minutes

On the owner's Dell XPS 13 9380 the taskbar disappeared a few minutes after unlocking and
then nothing worked. The stick now starts with three settings against the two known
causes on that laptop:

| Setting | What it stops |
|---|---|
| `i915.enable_psr=0` | the screen's power saving, which freezes parts of the picture on this laptop |
| `usbcore.autosuspend=-1` | USB power saving that can put the stick to sleep |
| `pcie_port_pm=off` | power saving on the USB-C / Thunderbolt ports, which can make a stick behind them drop out |

They cost a little battery. A stick installed with the BAU installer gets them too.

**Big copies no longer freeze the desktop.** With 8 GB of memory, Linux normally gathers
over a gigabyte of data before writing it out (a model download, the BAU Pack). It then
writes all of it to the stick in one go. On a slow stick that takes minutes, and every
program that needs to read from the stick waits, so the desktop seems dead. The stick now
writes in small steps (at most 48 MB waiting), on the live stick as well as on a stick
BAU is installed on. To try this on a stick made before the change, type once after
unlocking:

```bash
sudo sysctl vm.dirty_background_bytes=16777216 vm.dirty_bytes=50331648
```

**Plug the stick into the port on the right side.** The two ports on the left are
Thunderbolt; the right one is plain USB-C and is the steadiest place for the stick.

**If it still happens: press Ctrl+Alt+F9.** That is the health console. It keeps working
even when the rest of the system has stopped, and shows:

- why Wi-Fi is off (no driver, switched off, or the card's firmware complaining);
- every 30 seconds: free memory, heat, how much is waiting to be written, and whether
  the stick is still there;
- **STICK GONE**, **DISK BUSY**, **MEMORY ALMOST FULL** or **HOT** in capitals when one of
  those is the cause;
- the kernel's warnings as they happen.

Take a photo of that screen and send it: it says which of the causes it is.
**Ctrl+Alt+F7** goes back to the desktop.

BAU already installed on a stick before this change? Add the settings once:

```bash
sudo sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="/&i915.enable_psr=0 usbcore.autosuspend=-1 pcie_port_pm=off /' /etc/default/grub
sudo update-grub
```

## Good to know

- **BAU installed onto a USB stick:** it works, but ordinary sticks are not made for an
  operating system's constant writes. A stick that overheats or drops out makes Linux
  switch it to read-only: programs fail and the screen goes black. The stick image
  therefore eases the load by itself when it finds it is running from a USB stick (fewer
  writes, swap in memory instead of on the stick). For daily use, the laptop's own drive
  (next to Windows) or a USB **SSD** (built for constant writes) are much more reliable.
  To check whether the stick dropped out, run `sudo dmesg -T | grep -iE "i/o error|read-only|usb.*reset"`
  after it happens: any lines mean the stick.
- **Sticks open by themselves** when plugged in (they show in the file manager), exFAT and
  Windows (NTFS) drives included.

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
