# Installing BAU: the Two-USB Process

Two sticks, used in this order:

| Stick | Built by | What it does |
|---|---|---|
| **USB #1: base OS** | `installer/build-usb-image.sh` | Official Debian stable installer, signature-verified, plus a "BAU install" menu entry. It installs an encrypted system with the BAU package set and a default-deny firewall. **It never chooses or erases a disk by itself.** |
| **USB #2: BAU-PAYLOAD** | `installer/make-payload.sh` | The BAU control plane, checksummed (optionally GPG-signed). It also carries the pre-wipe tools (hardware audit, backup verify, wipe gate). |

Build both on any Linux machine with `python3`, `xorriso`, `gpg`, `curl`. Stick sizes: USB #1 at least 2 GB; USB #2 at least 1 GB. A separate **backup drive** is also required (Phase 2).

> Nothing here can undo a wipe. Follow the phases in order. Every destructive step asks you to type something that proves you are looking at the right disk.

---

## Phase 0: Build the sticks (on your build machine)

```bash
git clone <this repo> && cd linux-ai-biz
python3 -m pip install -e '.[dev]'      # pytest + ruff for the build-time test run

# USB #2 first: it carries the tools you need before wiping.
installer/make-payload.sh                         # runs tests + secret scan, builds dist/BAU-PAYLOAD
installer/make-payload.sh --to /media/$USER/USB2  # or copy it straight onto a mounted stick (verified)

# USB #1
installer/build-usb-image.sh                      # downloads + verifies Debian, writes dist/bau-debian-*.iso
sudo installer/write-usb.sh dist/bau-debian-*-amd64-netinst.iso /dev/sdX
```

`write-usb.sh`:
- refuses the disk you are running from and non-USB disks;
- makes you type the stick's serial number;
- reads the stick back and compares hashes;
- writes `dist/<image>.installer-record.json`. The wipe gate needs that file. Copy it to your backup drive.

For production, sign the payload: `installer/make-payload.sh --sign <your GPG key id>`. Then on the target, run `install.sh --expect-fpr <fingerprint>`.

## Phase 1: Hardware audit (read-only, on the OLD system)

Plug in USB #2 and the backup drive.

- **Linux:** `sudo ./BAU-PAYLOAD/hw-audit.sh /media/backup/bau-baselines`
- **Windows:** run `hw-audit-windows.ps1 -Out E:\bau-baselines` in an elevated PowerShell. Then boot a Debian *live* session and run `hw-audit.sh` too, because the wipe gate needs a Linux disk baseline. **If BitLocker is on, write down the recovery key offline first.**

This writes the BAU-HARDWARE, DISK, SYSTEM, NETWORK and BACKUP baselines (spec §4). Nothing else is touched.

## Phase 2: Backup and verify

```bash
cd BAU-PAYLOAD
export PYTHONPATH=$PWD/bau-src
python3 -m bau.cli backup manifest ~/projects ~/Documents ~/Music ~/.ssh --out /media/backup/manifest.json
rsync -a ~/projects ~/Documents ~/Music ~/.ssh /media/backup/data/      # or your backup tool
python3 -m bau.cli backup verify --manifest /media/backup/manifest.json \
    --backup-root /media/backup/data --baseline-dir /media/backup/bau-baselines --encrypted
```

`verify` reads **every file back from the backup drive** and checks its hash. Pass `--encrypted` only if the backup drive really is encrypted: the manifest flags SSH keys, `.env` files and similar, and verification refuses to pass with secrets on an unencrypted drive.

Never put secret values (API keys, passwords) into documentation. Record the *names* of environment variables only (spec §1.4).

## Phase 3: Wipe gate (on the OLD system, immediately before wiping)

Write a one-page **golden recovery plan**: how you would get back to a working machine if the install fails (where the backup is, the BitLocker key, the old OS media). Then:

```bash
sudo PYTHONPATH=$PWD/bau-src python3 -m bau.cli wipe-gate --device /dev/nvme0n1 \
    --baseline-dir /media/backup/bau-baselines \
    --installer-record /media/backup/bau-debian-...iso.installer-record.json \
    --recovery-plan /media/backup/RECOVERY-PLAN.md
```

The gate shows the target disk, its serial, size, backup status, installer verification, OS licence and K3 deployment mode. It then requires you to type the **disk serial number** and `WIPE /dev/nvme0n1`. The result is `BAU-WIPE-GATE.json`, valid for 60 minutes. If any check fails, nothing proceeds.

The default OS foundation is Debian, which allows commercial use. Passing `--foundation aios` without `--lab-only` is blocked: aiOS is PolyForm Noncommercial.

## Phase 4: Install the base OS (USB #1)

Boot from USB #1 and choose **BAU install** (default). You will be asked for:
- the **target disk**: check it matches the serial from Phase 3;
- the **erase confirmation**;
- the **disk-encryption passphrase**: store it offline;
- the **administrator password**;
- the **time zone**.

Everything else is preseeded: encrypted LVM, no root login, GNOME with the Orca screen reader, Podman, AppArmor, nftables, chrony, auditd and security updates. The firewall is default-deny inbound from the first boot.

## Phase 5: Install BAU (USB #2)

Log in as `bauadmin`, plug in USB #2 and the backup drive:

```bash
cd /media/bauadmin/<USB2>/BAU-PAYLOAD
sudo ./install.sh --wipe-gate-record /media/bauadmin/<backup>/bau-baselines/BAU-WIPE-GATE.json
#   add --expect-fpr <FPR> if you signed the payload; --offline if there is no network
```

`install.sh` runs these steps:
1. Verifies every file's checksum (and the signature, when signed).
2. Creates the `bau` service account (agents; **cannot** approve anything) and the `bau-approvers` group (you).
3. Generates machine keys in `/etc/bau` (audit signing, unsubscribe tokens) and **your personal approval key**. It asks you for a passphrase; that key is how you approve sends, publications and payments. Keys never leave the machine and are never logged.
4. Installs BAU into `/opt/bau/venv` and its state into `/var/lib/bau`.
5. Applies host hardening: firewall, sysctl, security-only auto-updates, authenticated time (NTS).
6. Enables `bau-recover` (every boot) and `bau-regwatch` (daily).
7. Imports the wipe-gate record into the new audit chain. Without one, the install is recorded as **UNGATED**.
8. Runs `bau selftest`.

Log out and back in (group membership), then run `bau status`.

## Phase 6: Make it real (what turns the dashboard green)

`bau status` lists every remaining item. Typical first steps:

```bash
bau reg list                                   # every rule, its status and review date
bau reg promote us-canspam --to TESTED --reviewer "Jane Counsel"   # then --to ACTIVE
bau email check-dns yourdomain.com --selector s1
bau email import-wireless-list fcc-domains.txt --fetched-at 2026-10-04
bau audit anchor                               # write the printed head hash somewhere offline

# Approving a send that needs human review (e.g. before counsel sign-off):
bau email preflight ... --evidence             # read the evidence package it writes
bau approve --capability email.send.commercial --request-id <campaign_id> \
    --requester agent:marketing --bind message.json --evidence <evidence.json> --out approval.json
# The approval covers that exact message: any edit afterwards voids it.
bau email preflight ... --approval approval.json
```

## Phase 7: Bring the work layers online

```bash
bau ui                                         # or open http://127.0.0.1:8765 (bau-ui.service)
bau set-status model claude-opus-5-5 APPROVED  # after reviewing terms; repeat for local models
bau models route reasoning --data PERSONAL     # see which model the router would use, and why
bau genesis import ~/exports/chatgpt/conversations.json
bau genesis import ~/exports/claude/conversations.json
bau genesis extract --to-memory                # drafts in /var/lib/bau/history/canonical/
bau opportunity opportunities.yaml             # rank ideas on evidence
bau factory activate digital_assets --approval-ref <your note>
bau factory-run start digital_assets "Bakery planner pack"
bau factory-run confirm <run> asset_built      # checklist items are confirmed by you
bau factory-run facts <run> monetize facts.json
bau approve --capability publish.text --request-id <run> --requester agent:writer \
    --bind /var/lib/bau/jobs/factory_runs/<run>.json --out approval.json
bau factory-run approval <run> publish.text approval.json
```

Publishing produces a reviewed export package in `/var/lib/bau/artifacts/exports/` with an upload checklist. Nothing is posted to a platform until you upload it, or until a platform API connector has been built, reviewed and approved.

The machine reports **not production-ready** until every spec §107 critical item is closed. That is by design.
