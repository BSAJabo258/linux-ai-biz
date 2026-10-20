# Windows scripts and their Debian versions

You run Debian now, so here is every Windows script in BAU and what to use on Debian
instead. Checked 2026-10-20 against the repository itself. The Windows files are kept:
they are still the right tool on a Windows computer.

| Windows file | What it does | On Debian use | Status |
|---|---|---|---|
| `installer/BAU-Laptop-Check.cmd` + `bau-laptop-check.ps1` | read-only check before installing | `installer/bau-laptop-check.sh` | ready, and shows more: the drivers Linux really loads, missing firmware, sound and Bluetooth |
| `installer/BAU-Desktop-Check.cmd` | the same check, for the desktop | `installer/bau-laptop-check.sh` (it has a graphics card section) | ready |
| `installer/BAU-Keys-Export.cmd` + `bau-keys-export.ps1` | locks your API keys into `BAU-KEYS.enc` | `installer/bau-keys-export.sh` | ready |
| `installer/hw-audit-windows.ps1` | the older hardware audit for the wipe gate | `installer/hw-audit.sh` | ready |
| `vm/create-vm.ps1` | makes the VirtualBox test machine | `vm/create-vm.sh` | ready |
| `installer/BAU-Pack-Make.cmd` + `bau-pack-make.ps1` | fills a BAU Pack stick with the local models and your keys file | none yet | planned, not built. On Debian, copy the model files by hand; `bau pack check` then checks them against their pinned hashes |

PowerShell 7 can be installed on Debian, but it would not help: these scripts read
Windows-only things (the registry, BitLocker, Windows disks), which do not exist on Linux.

**"Unable to locate package powershell"** is normal: Debian does not carry PowerShell, so
`apt install powershell` finds nothing until Microsoft's package source is added
(Microsoft's page "Install PowerShell 7 on Debian" lists Debian 13 as supported). On the
live stick it would also go into memory and be gone at restart (see
[LIVE-USB.md](LIVE-USB.md), "Installing programs while running from the stick").

**`.ps1` files on a stick do not run on Linux.** Use the Linux file next to it in the
table above. A stick with a `BAU-PACK` folder (made on Windows by `BAU-Pack-Make.cmd`)
needs no PowerShell at all: plug it in and run `sudo bau pack install` (see
[PACK.md](PACK.md)).

## Sound and Bluetooth

The laptop check on Debian now has **Sound**, **Bluetooth** and **Sound and Bluetooth
packages** sections. Run it from the stick (it only reads):

```bash
sudo bash /run/live/medium/BAU-PAYLOAD/bau-laptop-check.sh ~/BAU-Laptop-Check
```

What we found (2026-10-20): the stick is built without Debian's "recommended" extras, and
three packages your laptop needs only come that way, so they were never on the stick:

| Package | What it does |
|---|---|
| `alsa-ucm-conf` | sound routing for laptop sound chips like the XPS's; Debian: "absolutely necessary to make some sound hardware work" |
| `alsa-topology-conf` | the matching topology files for the same chips |
| `libspa-0.2-bluetooth` | lets PipeWire play sound through Bluetooth headphones and speakers |

The next stick build carries all three. Until then, if the check says they are missing,
it prints the exact command (it needs the internet):

```bash
sudo apt install alsa-ucm-conf alsa-topology-conf libspa-0.2-bluetooth
```

Then log out and back in, and run the check again. On the live stick this lasts until you
restart, because the system part starts fresh each time (only your files and settings are
kept). On a laptop where BAU is installed to the disk, it stays.

If sound still does not work after that, send the **Sound** section of the summary: its
`kernel:` lines name the next thing to fix.
