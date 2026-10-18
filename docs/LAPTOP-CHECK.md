# Laptop check: can BAU go on this laptop?

Two small scripts collect everything needed to answer that question. They only **read**:
no drivers, settings, disks or BitLocker are changed. Each one writes two files:

| File | What it holds | Share it? |
|---|---|---|
| `BAU-LAPTOP-SUMMARY.txt` (Windows) / `BAU-LAPTOP-SUMMARY-LINUX.txt` (stick) | a short report with a verdict: model, memory, firmware, disks, every network/graphics device and what Linux does with it, plus the tools already installed | **Yes**: no computer name, user name, network addresses or serial numbers |
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

## 2. From the stick (proof of what Linux does)

Start the laptop from the My Jarvis stick (**limited mode** is enough: nothing is saved),
open a terminal and run:

```bash
bash /run/live/medium/BAU-PAYLOAD/bau-laptop-check.sh ~/BAU-Laptop-Check
```

With `sudo` in front it can also read the kernel's messages. Like the Windows check, it
ends with a plain verdict (`READY`, `READY, AFTER THESE STEPS` or `NOT READY`) and says why,
one line each:

- `BLOCKER:` under 8 GB of memory, a 32-bit system, or no internal disk of 64 GB or more;
- `DO FIRST:` something to do before installing: legacy BIOS instead of UEFI, missing
  firmware, a device with no driver, a disk set to RAID On (Intel RST), a blocked radio;
- `NOTE:` worth knowing, not a blocker.

It shows:

- **Memory** and **Firmware** (UEFI or legacy BIOS, Secure Boot);
- **Devices and their drivers**: each network, graphics and sound device with the driver
  Linux loaded, or `NO DRIVER LOADED`;
- **Missing firmware**: files the kernel asked for and did not find;
- **Radios**: whether Wi-Fi or Bluetooth is switched off or blocked;
- **Tools already present**: python, git, docker and the rest, one short line each, because
  a missing tool is much easier to fix before an install than during one;
- **BAU on this machine**: those tools with their versions, the listening port numbers, and
  whether any `bau-*.service` units are running. Port numbers only; the addresses stay in the
  private file.

The verdict comes first, and each `BLOCKER` / `DO FIRST` line names one reason, so the summary
can be read top to bottom. It is worked out by `installer/lib/laptop-evidence.sh`, which ships
next to the check in `BAU-PAYLOAD/lib/`; if only the script is copied somewhere else, it says
`VERDICT: unknown` rather than guessing.

A device with `NO DRIVER LOADED` or a line under **Missing firmware** is the thing to ask
about before installing. Copy `BAU-LAPTOP-SUMMARY-LINUX.txt` to another USB stick to send it.

The private `BAU-LAPTOP-FULL-LINUX.txt` adds the details the summary must not carry: the
checkout it was run from (branch, commit, working tree, last five commit names), the running
process names, the BAU service states, the listening addresses, and which secret files exist
with their permissions. Secret files are never opened, only noted as present with their mode,
and process command lines are never read or printed, because they carry tokens and keys. It also runs no repository script: it reads the checkout and nothing more. The BAU checkout is
looked for in `$BAU_DIR`, `/opt/bau`, `/srv/bau` and `~/linux-ai-biz`, and secret files in
`/etc/bau/*.env`.

## What next

When the verdict is READY (or the steps are done): back up, then follow
[LIVE-USB.md](LIVE-USB.md), "Install BAU on this laptop". The older baseline audit
(`hw-audit.sh`, `hw-audit-windows.ps1` in [INSTALL.md](INSTALL.md)) is still what the
wipe gate needs on the two-stick install.
