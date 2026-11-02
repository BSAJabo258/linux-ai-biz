# Wi-Fi rescue (no internet needed)

For the desktop's MediaTek MT7921 Wi-Fi card. The rescue tries one fix after another,
checks the Wi-Fi after each, and stops at the first one that works. It then tells you which
fix did it. It needs no internet: the card's firmware travels with it.

## Get it

On any computer with internet, download **bau-wifi-kit.zip** from:

https://github.com/BSAJabo258/linux-ai-biz/releases/tag/bau-wifi-kit

Unzip it onto a USB stick. The kit holds the rescue script, Debian 13's MediaTek firmware
package (checked against Debian's own SHA-256), and a README.

## Run it on the desktop

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
   option.
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
- The firmware package was downloaded and checked: 19,598,740 bytes, SHA-256 matching
  Debian's, both firmware files inside.

**Not tested yet:** it has not run on your desktop.
