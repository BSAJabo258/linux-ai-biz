# Rehearse the laptop install in a virtual machine

A virtual machine (VM) is a pretend laptop inside your computer. Here you run the real
two-stick install in it, exactly as on the laptop, without wiping anything real.

You need **VirtualBox 7** (free, virtualbox.org) on Windows, Linux or an Intel Mac, about
**70 GB free disk** and **16 GB RAM** (the VM takes 8). On an Apple-silicon Mac (M1-M4),
use the Docker test drive instead (`docker/README.md`): VirtualBox can't run this kind of VM
there.

## 1. Download the two sticks

From the repository's GitHub **Releases** page (or run *Actions > build-usb > Run
workflow* first), download into your Downloads folder:

- `bau-debian-<version>-amd64-netinst.iso` - USB #1, the operating system
- `BAU-PAYLOAD-<version>.iso` - USB #2, BAU itself, as a disc image
- `SHA256SUMS.txt` - lets the script check both files are intact

## 2. Create the VM

Windows (PowerShell, in this repository's folder):

```powershell
powershell -ExecutionPolicy Bypass -File vm\create-vm.ps1
```

Linux / Intel Mac:

```bash
bash vm/create-vm.sh
```

The script finds both images, verifies their checksums, and creates a VM called
**BAU-Test** (8 GB RAM, 4 CPUs, 60 GB disk, UEFI) with both "sticks" inserted. Options:
`-MemoryMB`, `-Cpus`, `-DiskGB`, `-Name` (Windows) or `--memory-mb`, `--cpus`, `--disk-gb`,
`--name` (Linux/Mac).

## 3. Install, exactly as on the laptop

1. Start **BAU-Test** in VirtualBox. It boots USB #1.
2. Follow the installer (INSTALL.md, Phase 4): choose the disk encryption passphrase and
   create the administrator account. The VM needs internet during this step (it has it).
3. When it restarts, unlock the disk with your passphrase and log in.
4. Open a terminal. USB #2 shows up as the **BAU-PAYLOAD** disc. Run:
   ```bash
   sudo bash /media/$USER/BAU-PAYLOAD/install.sh
   ```
   (If it isn't opened automatically: `sudo mount /dev/sr1 /mnt && sudo bash /mnt/install.sh`.)
5. Log out and back in, then check:
   ```bash
   bau selftest
   bau status
   ```
   Open Firefox in the VM at **http://localhost:8765** for Mission Control, or double-click
   **BAU Jarvis** in the app menu.

If all of that works in the VM, the real laptop will behave the same way. Afterwards the
sticks can be put away: everything lives on the (virtual) disk.

## Start over

Delete **BAU-Test** in VirtualBox (*Remove > Delete all files*) and run the script again.
