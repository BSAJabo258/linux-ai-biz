# Automatic updates on your desktop

Your choice (2026-11-01): **fully automatic**. Once a night your desktop installs the newest
BAU that passed every check, all by itself. If Jarvis's side doesn't come back up afterwards,
it goes back to the version before, also by itself. Jarvis tells you what happened in the
next briefing.

Before this, BAU's rule was that a person approves each update. For BAU's own program you
replaced that rule with this one. Everything else still needs you: models, keys, money,
posting and approvals.

Built 2026-11-01. The tests run on fake downloads and a fake desktop. It has **not run on
your desktop yet**.

## Where updates come from

1. You merge a change on GitHub (you say "merge").
2. GitHub runs every check on `main`. Only if they all pass, it builds BAU from that exact
   version. It puts the result on the release called **bau-update**, together with a small
   record: which version, the file name, and its SHA-256 fingerprint.
3. At night (around 3:17 to 3:47) your desktop reads that record. If it's a version it
   doesn't have yet, it downloads it.
4. The desktop checks the fingerprint. A file that doesn't match is never installed.
5. It installs the new version and checks it actually works:
   - BAU's parts load.
   - Mission Control restarts and answers on 127.0.0.1:8765.
6. If the check fails, it puts back the version that was there before:
   - after the first update, that's the last good update;
   - before that, it's the version from your stick.

A Jarvis window that is open keeps running the old version until you close and reopen it.

## Turn it on (once)

**A desktop installed from a new stick** already has everything. Turn it on in a terminal:

```bash
sudo bau update auto
```

**Your desktop today** was installed before this existed, so it needs one setup run. In a
terminal:

```bash
curl -fsSLO https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/installer/bau-update-first.sh
sudo bash bau-update-first.sh
```

The setup run does five things:

1. Fetches the newest tested version and checks its fingerprint.
2. Installs it.
3. Sets up the nightly timer.
4. Turns automatic updates on.
5. Runs the first update right away.

It ends with **Done**.

## See it, run it, stop it

```bash
bau update status      # on or off, the version installed, what happened last time
sudo bau update now    # don't wait for tonight
sudo bau update off    # stop automatic updates (sudo bau update auto turns them back on)
```

Every update is written to the audit log:

- `update.installed`: the new version is in and working.
- `update.rolled_back`: the new version failed, so the old one is back.
- `update.refused`: the download was wrong, so nothing was installed.
- `update.broken`: see below.

## If an update could not be put back

This should be rare. The next briefing starts with a warning. Then, in a terminal:

```bash
sudo bau update now
```

If that doesn't help, reinstall BAU from the copy your stick left on the desktop:

```bash
sudo bash /opt/bau-payload/install.sh
```

## What it never does

- It never updates the live stick. The stick is rebuilt instead (docs/BUILD-ISO.md).
- It never installs a version that failed a check on GitHub, and never a file whose
  fingerprint doesn't match.
- It never changes your models, keys, approvals or settings. It only replaces BAU's program
  in `/opt/bau/venv`.
- It never runs unless you turned it on.
