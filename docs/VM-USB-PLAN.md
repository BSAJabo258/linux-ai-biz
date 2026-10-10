# VM rehearsal and two USB install plan

This runbook prepares and rehearses the **full Debian install-to-disk path** using two
separate images. USB #1 installs encrypted Debian. USB #2 installs BAU, Jarvis, and the
optional Claude SDK. It is different from the one-stick live system described in
[`LIVE-USB.md`](LIVE-USB.md).

## Readiness gates

Complete these gates in order. Stop and repair any failure before moving on.

### Gate 1: repository checks

From the repository root, with Python 3.11 or 3.13 and the development requirements installed:

```bash
python3 -m pip install -e '.[dev]'
ruff check src tests linktranscript_studio
bau secrets .
bau reg validate
python3 -m pytest -q
shellcheck -x installer/*.sh installer/lib/*.sh installer/payload/*.sh \
  installer/firstboot/*.sh docker/*.sh vm/*.sh image/*.sh \
  image/live-build/auto/config image/live-build/config/hooks/live/*.chroot \
  image/live-build/config/includes.chroot/usr/local/sbin/bau-live-init \
  image/live-build/config/includes.chroot/usr/local/bin/jarvis-setup
```

The GitHub Actions workflow is the reference list of CI checks. The payload builder also
runs its test suite and secret scan unless `--skip-tests` is passed. Only use that option
after Gate 1 succeeds.

### Gate 2: build both install images

Use a Linux build machine with `xorriso`, `gpg`, `curl`, Python, and internet access. The
Debian image builder downloads the current stable installer and verifies Debian's signature
and checksum before remastering it.

```bash
installer/make-payload.sh --with-claude --out dist
installer/build-usb-image.sh --out dist
version="$(PYTHONPATH=src python3 -c 'import bau; print(bau.__version__)')"
xorriso -as mkisofs -quiet -V BAU-PAYLOAD -J -R \
  -o "dist/BAU-PAYLOAD-${version}.iso" dist/BAU-PAYLOAD
cd dist
sha256sum bau-debian-*.iso BAU-PAYLOAD-*.tar.gz BAU-PAYLOAD-*.iso > SHA256SUMS.txt
sha256sum --check SHA256SUMS.txt
```

`--with-claude` places the Anthropic SDK wheels on USB #2 for offline installation. It does
not include an API key. Keep `dist/` and the matching `SHA256SUMS.txt` together for the VM.
The equivalent GitHub Actions workflow builds these files and publishes them as a release.

### Gate 3: create the isolated VM

Install VirtualBox 7 on a machine with hardware virtualization enabled, at least 8 GB RAM,
and about 70 GB free disk. Put both ISO files and `SHA256SUMS.txt` in one directory, then:

```bash
bash vm/create-vm.sh --usb1 dist/bau-debian-<version>-amd64-netinst.iso \
  --payload dist/BAU-PAYLOAD-<version>.iso
```

On Windows, use `powershell -ExecutionPolicy Bypass -File vm\create-vm.ps1` from the
repository folder after putting the images beside the script or in Downloads. The scripts
check the image hashes when `SHA256SUMS.txt` is beside them and attach both images to a
60 GB virtual disk. Start the VM and select **BAU install**.

The VM's virtual disk is the install target. Confirm the displayed virtual disk before
accepting the Debian erase prompt. The physical host disks are not part of the VM.

#### Cloud VM option

GitHub Codespaces is useful for editing this repo and launching its image workflow, but its
machine-type documentation does not promise a CPU vendor or nested virtualization. Do not
assume an AMD Codespace can run this VM.

For an AMD cloud host, Azure `Dasv5` is a candidate: Microsoft lists AMD EPYC processors and
nested virtualization support for the series. The documented AMD nested path is Hyper-V on
Windows Server 2022 or later (or Windows 11), with the Azure VM security type set to Standard.
This repo's `vm/create-vm.*` scripts require VirtualBox; Microsoft says other hypervisors
nested inside Hyper-V are unsupported. On Azure, use Hyper-V to create the 60 GB Debian test
guest and attach both downloaded ISOs. Verify the chosen SKU's feature table and regional
availability first. Compute and storage are billable.

#### Make the images downloadable

The `dist/` files are ignored build outputs and are not committed to Git. After the updated
repo commit is pushed, run **GitHub → Actions → build-usb → Run workflow**. The workflow reruns
the checks and publishes a release with the two ISO images, payload tar, and
`SHA256SUMS.txt`. Download the Debian ISO, payload ISO, and manifest onto the VM host. A
workflow rebuild can use a newer Debian point release, so verify downloaded files against
that release's manifest instead of relying on hashes in an older handoff.

### Gate 4: install USB #2 in the VM

Finish Debian setup, unlock the virtual disk, log in as `bauadmin`, and install the payload
from the attached second image. For the VM rehearsal, omit `--wipe-gate-record`; the
installer will explicitly mark the test machine `UNGATED` in its audit chain. That is
expected for this disposable VM and is not a production install procedure.

```bash
sudo mount /dev/sr1 /mnt
sudo bash /mnt/install.sh
```

If the desktop mounted the image, run its `install.sh` from the mounted `BAU-PAYLOAD`
directory instead. Confirm that `bau selftest` completes, `bau status` works, Mission Control
opens at `http://localhost:8765`, and the audit chain records `install.ungated` followed by
`install.completed`.

### Gate 5: enable and verify Claude for Jarvis

On the installed VM, configure the Claude key locally. Never put it in the repository, the
image, a transcript, or this plan:

```bash
sudo install -m 0640 -o root -g bau /dev/null /etc/bau/models.env
sudoedit /etc/bau/models.env   # add ANTHROPIC_API_KEY=<your key>
```

Then follow the owner-controlled model approval flow in [`INSTALL.md`](INSTALL.md): review
the model terms, approve `claude-opus-5-5`, and start Jarvis in text mode for a smoke check.
If Claude is unavailable, Jarvis should report the configured fallback or plain mode rather
than claiming the Claude check passed.

## Rehearsal acceptance checklist

- [ ] Both ISO images match the adjacent checksum manifest.
- [ ] USB #1 boots in UEFI and installs Debian to the VM's encrypted virtual disk.
- [ ] USB #2 checks its manifest and installs the BAU wheel and bundled Anthropic SDK.
- [ ] `bau selftest`, `bau status`, the UI, and the audit-chain checks complete.
- [ ] Claude works only after the owner configures a key and explicitly approves the model.
- [ ] Any failure is fixed, then the relevant CI checks and the full test suite pass again.
- [ ] Record the image names, hashes, VM result, and any unresolved issue before preparing
  physical sticks.

## Physical USBs are a separate final operation

After the VM checklist passes, follow [`INSTALL.md`](INSTALL.md) phases 0–5 on the real
computer. USB #1 is written with `installer/write-usb.sh`; that operation erases the
selected drive. Identify the device and its serial before running it. USB #2 can be copied
to a mounted stick with `installer/make-payload.sh --to <mounted-USB2>` or by unpacking the
payload archive. Keep the encrypted backup and wipe-gate procedure in the install runbook;
the VM's `UNGATED` record must never be reused for the real installation.
