# Laptop check: can BAU go on this laptop?

Two small scripts collect everything needed to answer that question. They only **read**:
no drivers, settings, disks or BitLocker are changed. Each one writes two files:

| File | What it holds | Share it? |
|---|---|---|
| `BAU-LAPTOP-SUMMARY.txt` (Windows) / `BAU-LAPTOP-SUMMARY-LINUX.txt` (stick) | a short report with a verdict: model, memory, firmware, disks, every network/graphics device and what Linux does with it | **Yes**: no computer name, user name, network addresses or serial numbers |
| `BAU-LAPTOP-FULL.json` / `BAU-LAPTOP-FULL-LINUX.txt` | everything, including those private details | No, keep it |

## 1. On Windows (before you change anything)

No Python and nothing to install. You need two files **in the same folder** (for example
Downloads): `BAU-Laptop-Check.cmd` and `bau-laptop-check.ps1`. Both are in the
`BAU-PAYLOAD` folder on the stick, or download them:
<https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/installer/BAU-Laptop-Check.cmd>
and <https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/installer/bau-laptop-check.ps1>
(right-click the page, **Save as**, keep the name).

**The easy way: double-click `BAU-Laptop-Check.cmd`.**

1. If a blue box says *Windows protected your PC*, click **More info**, then **Run anyway**
   (Windows says this about every file from the internet).
2. Click **Yes** when it asks for administrator rights (BitLocker, Secure Boot and the TPM
   can only be read that way).
3. A black window works for about a minute, then Notepad opens the summary. Send that
   file: `BAU-LAPTOP-SUMMARY.txt`, in the `BAU-Laptop-Check` folder next to the two files.

Double-clicking `bau-laptop-check.ps1` itself only opens it in Notepad: that is normal,
use the `.cmd`. The `.md` file is this guide; open it in Notepad to read it.

**By hand, if the double-click does not work:** press Start, type **PowerShell**,
right-click **Windows PowerShell**, choose **Run as administrator**, and paste this one
line (change the folder if the file is somewhere else):

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\bau-laptop-check.ps1" -Out "$env:USERPROFILE\Downloads\BAU-Laptop-Check"
```

`ExecutionPolicy Bypass` lets this one script run this one time; it changes no setting.
If something goes wrong, take a photo of the window and send it.

### What the verdict means

| Verdict | Meaning |
|---|---|
| **READY** | Nothing stands in the way. Read the notes anyway. |
| **READY, AFTER THESE STEPS** | Do each `DO FIRST` line before installing (for example: BitLocker is on, so write down the recovery key and back up first). |
| **NOT READY** | A `BLOCKER` line says why: under 8 GB of memory, a 32-bit system, or no internal disk of 64 GB or more. |

### If it says the disk is behind Intel RST (RAID On)

Many Dell, HP and Lenovo laptops ship with the disk setting **SATA Operation: RAID On**
(Intel RST). Linux usually cannot see the disk that way, so the installer finds nothing to
install on. Switch it to **AHCI**. Switching it alone stops Windows from starting, so if
you still need Windows (for example to finish a backup), do it in this order:

1. In Windows, press Start, type **cmd**, right-click **Command Prompt**, choose **Run as
   administrator**, and type: `bcdedit /set {current} safeboot minimal`
2. Restart. At the maker's logo press the firmware key (Dell: **F2**). Find **SATA
   Operation** (Dell: System Configuration), choose **AHCI**, then Apply and Exit.
3. Windows starts in Safe Mode. Open Command Prompt as administrator again and type:
   `bcdedit /deletevalue {current} safeboot` then restart. Windows now starts normally.

If everything is backed up and Windows can go, just switch to AHCI in step 2 and start
from the stick.

The Windows check judges each device from its maker: Intel, Realtek, Qualcomm/Atheros and
MediaTek Wi-Fi work from the stick; some Broadcom Wi-Fi does not (have Ethernet or a USB
Wi-Fi adapter ready); NVIDIA graphics may need **safe graphics** in the stick's menu. It
is a good guess, not proof. The stick gives proof:

### On a desktop (graphics card, spare drive)

The same check works on a desktop. Put **`BAU-Desktop-Check.cmd`** next to
`bau-laptop-check.ps1` and double-click it (the steps are the same as above; the report
lands in a `BAU-Desktop-Check` folder). Download it from
<https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/installer/BAU-Desktop-Check.cmd>.
On top of the laptop report it says:

- **Graphics cards:** the name, the card's real memory (for example 12 GB), the driver,
  and on NVIDIA the *CUDA compute* level. A note says roughly how big a local model fits
  on the card. That is a guide only: every model is approved after `bau models bench`.
- **Which disk Windows starts from**, and **which disk has no Windows on it**. When there is
  one (for example a spare 1 TB drive), the summary says `Install BAU on: <that disk>`:
  Windows can stay on its own disk and you choose at start-up. Anything already on the
  BAU disk is erased, so copy off what you want first.
- **NVIDIA with Secure Boot on:** the NVIDIA driver must be signed with a key you enroll
  once at start-up, or Secure Boot turned off. BAU shows you the steps when it gets there.
- **No Wi-Fi card** (common on desktops): plug in an Ethernet cable before starting from
  the stick.

Send `BAU-LAPTOP-SUMMARY.txt` from the `BAU-Desktop-Check` folder. The desktop build is
designed from that report, not from guesses.

## 2. From the stick (proof of what Linux does)

Start the laptop from the My Jarvis stick (**limited mode** is enough: nothing is saved),
open a terminal and run:

```bash
bash /run/live/medium/BAU-PAYLOAD/bau-laptop-check.sh ~/BAU-Laptop-Check
```

With `sudo` in front it can also read the kernel's messages. It shows:

- **Memory** and **Firmware** (UEFI or legacy BIOS, Secure Boot);
- **Graphics card**: the driver Linux loaded and, when it can tell, the card's memory;
- **Devices and their drivers**: each network, graphics and sound device with the driver
  Linux loaded, or `NO DRIVER LOADED`;
- **Missing firmware**: files the kernel asked for and did not find;
- **Radios**: whether Wi-Fi or Bluetooth is switched off or blocked.

A device with `NO DRIVER LOADED` or a line under **Missing firmware** is the thing to ask
about before installing. Copy `BAU-LAPTOP-SUMMARY-LINUX.txt` to another USB stick to send it.

## What next

When the verdict is READY (or the steps are done): back up, then follow
[LIVE-USB.md](LIVE-USB.md), "Install BAU on this laptop". The older baseline audit
(`hw-audit.sh`, `hw-audit-windows.ps1` in [INSTALL.md](INSTALL.md)) is still what the
wipe gate needs on the two-stick install.
