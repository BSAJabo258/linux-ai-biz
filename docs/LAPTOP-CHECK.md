# Laptop check: can BAU go on this laptop?

Two small scripts collect everything needed to answer that question. They only **read**:
no drivers, settings, disks or BitLocker are changed. Each one writes two files:

| File | What it holds | Share it? |
|---|---|---|
| `BAU-LAPTOP-SUMMARY.txt` (Windows) / `BAU-LAPTOP-SUMMARY-LINUX.txt` (stick) | a short report with a verdict: model, memory, firmware, disks, every network/graphics device and what Linux does with it | **Yes**: no computer name, user name, network addresses or serial numbers |
| `BAU-LAPTOP-FULL.json` / `BAU-LAPTOP-FULL-LINUX.txt` | everything, including those private details | No, keep it |

## 1. On Windows (before you change anything)

No Python and nothing to install. Get `bau-laptop-check.ps1` from the `BAU-PAYLOAD` folder
on the stick, or download it:
<https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/installer/bau-laptop-check.ps1>

1. Put the file in your **Downloads** folder.
2. Press Start, type **PowerShell**, right-click **Windows PowerShell** and choose
   **Run as administrator** (BitLocker, Secure Boot and the TPM can only be read that way).
3. Type these two lines:

   ```powershell
   cd $HOME\Downloads
   powershell -ExecutionPolicy Bypass -File .\bau-laptop-check.ps1
   ```

   `ExecutionPolicy Bypass` lets this one script run this one time; it changes no setting.
4. After about a minute it shows the report and saves it in `Downloads\BAU-Laptop-Check`.
   Send `BAU-LAPTOP-SUMMARY.txt`.

### What the verdict means

| Verdict | Meaning |
|---|---|
| **READY** | Nothing stands in the way. Read the notes anyway. |
| **READY, AFTER THESE STEPS** | Do each `DO FIRST` line before installing (for example: BitLocker is on, so write down the recovery key and back up first). |
| **NOT READY** | A `BLOCKER` line says why: under 8 GB of memory, a 32-bit system, or no internal disk of 64 GB or more. |

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

With `sudo` in front it can also read the kernel's messages. It shows:

- **Memory** and **Firmware** (UEFI or legacy BIOS, Secure Boot);
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
