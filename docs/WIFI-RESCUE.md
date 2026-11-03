# Wi-Fi rescue (no internet needed)

For both of your Wi-Fi cards: the desktop's MediaTek MT7921 and the laptop's Killer 1435
(Qualcomm QCA6174). The rescue works out which card it's on by itself, then tries one fix after another,
checks the Wi-Fi after each, and stops at the first one that works. It then tells you which
fix did it. It needs no internet: both cards' firmware travels with it.

## Get it

On any computer with internet, download **bau-wifi-kit.zip** from:

https://github.com/BSAJabo258/linux-ai-biz/releases/tag/bau-wifi-kit

Unzip it onto a USB stick. The kit holds:

- the rescue script;
- Debian 13's MediaTek firmware package (for the desktop);
- Debian 13's Atheros firmware package (for the laptop);
- a README.

Both firmware packages are checked against Debian's own SHA-256.

## Run it on the desktop or the laptop

Plug in the stick, open a terminal in the kit's folder and run:

```bash
sudo bash bau-wifi-rescue.sh
```

If no Wi-Fi network is saved yet, it asks once for the name and password.

To keep it on duty, so it repeats the fixes by itself whenever the Wi-Fi drops:

```bash
sudo bash bau-wifi-rescue.sh --install
```

## What it tries, in order

1. Switch the Wi-Fi radio on (it may be switched off in software).
2. Install the card's firmware from the kit, if it is missing. Only a file whose SHA-256
   matches Debian's is installed.
3. Turn the card's power saving off. This was the fix for your drop-outs in October.
4. Restart the driver.
5. Turn PCI power saving (ASPM) off for the card. Only done if your kernel's driver has that
   option: the desktop's does, the laptop's doesn't, so on the laptop this step skips itself.
6. Stop random addresses while scanning (some routers refuse them).
7. Set the US region.
8. Restart everything once more.

Everything it did goes to `/var/log/bau-wifi-rescue.log`. It never edits how the computer
starts (the boot loader).

**If nothing works**, plug in the cable once, or a supported USB Wi-Fi adapter. Then send the
log file, so the next fix can be made for your exact card.

## Tested

**What ran:**

- The real script ran against fake system commands: a pretend card whose Wi-Fi comes back
  after a given fix. It stopped at the right fix and skipped the power-saving option
  (ASPM) when the driver lacks it. It said so when the card was missing, and installed no
  firmware without the right file.
- The real script was also run against a pretend laptop card (Killer 1435): it found the
  right driver, `ath10k_pci`, and skipped the step its driver lacks.
- Both firmware packages were downloaded and checked, each SHA-256 matching Debian's:
  - MediaTek: 19,598,740 bytes, with both firmware files inside.
  - Atheros: 29,474,828 bytes, with the laptop's `board-2.bin` and `firmware-6.bin` inside.

**Not tested yet:** it has not run on your desktop or your laptop.
