# Rehearse the laptop install in a virtual machine

A virtual machine (VM) is a pretend laptop inside your computer. Here you run the real
two-stick install in it, exactly as on the laptop, without wiping anything real.

You need **VirtualBox 7** (free, virtualbox.org) on Windows, Linux or an Intel Mac, about
**70 GB free disk** and at least **8 GB RAM** (the VM takes half your RAM, up to 8 GB, so your
computer keeps enough for itself). On an Apple-silicon Mac (M1-M4),
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

Or in VS Code: *Terminal > Run Task... > BAU: create or fix the test VM*.

The script finds both images, verifies their checksums, and creates a VM called
**BAU-Test** (half your RAM up to 8 GB, half your CPU cores up to 4, 60 GB disk, UEFI)
with both "sticks" inserted. It boots from its own disk first, so the installer stick only
runs while that disk is empty. Options:
`-MemoryMB`, `-Cpus`, `-DiskGB`, `-Name` (Windows) or `--memory-mb`, `--cpus`, `--disk-gb`,
`--name` (Linux/Mac).

**Already made the VM?** Run the same command (or the same VS Code task). It sees that
**BAU-Test** exists and fixes it instead: safe memory and CPUs for this computer, disk first.
If the VM is running it asks before powering it off. Its disk and everything you installed
are kept.

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

## If it seems frozen

- **Black screen after boot:** it's waiting for the disk passphrase behind the logo. Click
  the VM window, type the passphrase, press Enter (Esc shows the prompt).
- **Very slow, green turtle icon in the VM's status bar (Windows):** Hyper-V is in the way.
  Turn off Windows Security > Device security > Core isolation > **Memory integrity**,
  restart the PC, try again.
- **Whole PC freezes:** the VM has too much memory. Restart the PC if you have to, then run
  the create-vm command (or VS Code task) again: it resizes BAU-Test to fit your PC.
- **Mouse or keyboard stuck in the VM:** press the **right Ctrl** key to release them.
- **Grey or black screen after login:** Settings > Display > Graphics Controller
  **VBoxSVGA** and tick **Enable 3D Acceleration**.
- **Stuck at "Retrieving" / "Installing software":** the installer downloads packages;
  20-40 minutes is normal. Check the PC is online.

To stop a stuck VM without restarting the PC: close its window > **Power off the machine**
(or end **VirtualBoxVM** in Task Manager).

## Start over

Delete **BAU-Test** in VirtualBox (*Remove > Delete all files*) and run the script again.
