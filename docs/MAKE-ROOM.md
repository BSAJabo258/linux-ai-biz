# Make room for Jarvis

The problem (your desktop, 2026-11-08): the installer split the disk into a small system part
(`/`) and a big `/home` part. BAU's big files all go into the system part:

- the local models (`/var/lib/bau/models`);
- the picture maker (`/usr/local/comfyui`);
- the CUDA engine (`/opt/llama.cpp-cuda`).

So `/` fills up and installs stop, while `/home` stays nearly empty.

## Fix it without reformatting

When `/` is more than 85% full, Jarvis shows a **Make room for Jarvis** card. Press Accept and
type your password in the terminal that opens. Or, in a terminal:

```bash
sudo bash installer/bau-make-room.sh
```

It does five things:

1. Stops Jarvis's model, picture and screen services for a moment.
2. Copies each big folder into `/home/bau-data` and checks that the copy matches.
3. Links each folder back to where BAU expects it (a line in `/etc/fstab`), so nothing else
   changes.
4. Removes the old copy, which frees the space on `/`.
5. Starts the services again and shows the free space before and after.

Your keys, BAU's data and the audit log stay where they are; only the three big folders move.
It is safe to run again, because it skips what it already moved.

**A second drive instead:** first format it **with encryption** (in Disks: Format, then choose
encrypted), mount it, then run:

```bash
sudo bash installer/bau-make-room.sh /path/to/a/folder/on/that/drive
```

It refuses a drive that is not encrypted, and a folder on `/` (moving there frees nothing).

**To put everything back:**

```bash
sudo bash installer/bau-make-room.sh --undo
```

It brings each folder back only if `/` has the room for it.

## New installs

The stick's installer now uses Debian's "atomic" recipe ("all files in one partition", from
https://www.debian.org/releases/trixie/example-preseed.txt, read 2026-11-08), still with full-disk
encryption. A new install has one big part, so this cannot happen again. That change is on the
stick only after the stick is rebuilt (docs/BUILD-ISO.md).

Tested 2026-11-08 against fake disk commands (`tests/test_make_room.py`). It has **not run on
your desktop yet**.
