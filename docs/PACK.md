# The BAU Pack: AI models and keys for the laptop, on one USB stick

The BAU laptop can run its AI on its own, with no internet, but the AI models (about
6.5 GB) have to get onto it first. The BAU Pack carries them over on a USB stick, together
with your locked keys file if you made one (see [KEYS.md](KEYS.md)).

Two steps: fill the stick on a Windows computer that has internet, then run one command on
the laptop.

## What goes on the stick

| Model | Size | Job |
|---|---|---|
| `qwen3.5-4b` | 2.7 GB | the boss: runs Jarvis and the agents, uses tools |
| `qwen3-4b-heretic-content` | 2.5 GB | the thinker: uncensored ideas, sealed (no tools, never kids) |
| `qwen2.5-1.5b-instruct` | 1.1 GB | the backup: small and fast |

It also carries:
- **the Wi-Fi programs** (`wifi` folder, about 2 MB): `wpasupplicant` and its helpers. The
  first stick images were built without them, so a laptop installed from one cannot join
  any Wi-Fi network, even though the drivers and firmware for its Wi-Fi card are there;
- **the latest BAU** (`bau-main.zip`), so a laptop installed from an older stick gets the
  `bau pack` command.

Each model and Wi-Fi file is checked against the SHA-256 fingerprint BAU has on record when
it is downloaded, and again on the laptop. A file that does not match is deleted, never
used.

## 1. On the Windows computer: fill the stick

You need a USB stick of 16 GB or more (the 64 GB one is fine), formatted **exFAT**. Not
FAT32: it cannot hold a file over 4 GB, and the desktop's model is 5.7 GB.

1. **If the stick still holds a BAU installer image, or is FAT32, format it first.** This **erases**
   everything on it, including the installer. In File Explorer: right-click the stick,
   **Format**, File system **exFAT**, **Start**. (Keep another stick with the installer if
   you still need it.)
2. Get the two files, in the same folder: `BAU-Pack-Make.cmd` and `bau-pack-make.ps1`.
   They are in `BAU-PAYLOAD` on the installer stick, or download them from
   <https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/installer/BAU-Pack-Make.cmd>
   and <https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/installer/bau-pack-make.ps1>.
3. If you made a keys file, put `BAU-KEYS.enc` in that folder too. It is copied onto the
   stick, still locked with your passphrase.
4. Double-click **`BAU-Pack-Make.cmd`**.
   (If Windows says *Windows protected your PC*: **More info**, then **Run anyway**.)
5. It lists the USB sticks it sees. **Type the letter** of the one to fill (for example
   `E`). It never picks one for you, and never formats or erases anything.
6. Type `y` to start. The download takes a while (about 12 GB). If it stops, double-click
   again: it carries on where it stopped, and skips files that are already done.
7. When it says **The BAU Pack is ready**, eject the stick.

The stick now has a `BAU-PACK` folder with `models`, `README.txt` and (if you added it)
`BAU-KEYS.enc`.

## 2. On the laptop: Wi-Fi first (laptops installed before 18 October 2026)

If the laptop shows no Wi-Fi networks, plug in the stick, open it once in the file
manager, then open a terminal and type these four lines (none of them has the letter j):

```bash
cd /media/$USER/*/BAU-PACK/wifi
sha256sum -c SHA256SUMS
sudo apt install ./*.deb
sudo systemctl restart NetworkManager
```

The second line must say `OK` for every file; if one says `FAILED`, stop and make the pack
again. After the last line, click the network icon at the top of the screen and pick your
Wi-Fi. Once it is connected, bring BAU up to date from the stick:

```bash
sudo /opt/bau/venv/bin/pip install --no-deps --upgrade /media/$USER/*/BAU-PACK/bau-main.zip
```

## 3. On the laptop: install the pack

Nothing on the stick runs by itself when you plug it in. That is on purpose: a stick
anyone could have written to must never start anything on its own. You start it.

1. Plug in the stick (or skip the stick: see *No stick needed* below).
2. Open a terminal and type:

   ```bash
   sudo bau pack install
   ```

   It finds the pack by itself, whatever the capitals in the folder name (`BAU-PACK`,
   `BAU-pack`). If the desktop did not open the stick, it opens it itself, **read-only**,
   and Windows' own drives too. (Two packs found: add the path, for example
   `sudo bau pack install /media/bauadmin/STICK/BAU-PACK`.)
3. It checks each model again while copying it into place, then asks you **yes or no**
   before each change:
   - **Install the Wi-Fi programs?** Only if they are not installed yet (step 2 does the
     same by hand).
   - **Use qwen3.5-4b as the local model?** Yes starts it.
   - It measures the model on this laptop (does it answer, can it use a tool, how fast)
     and shows you the result. Only a model that answered properly can be approved.
   - **Approve it for Jarvis?** Yes approves it, in your name.
   - **Make it the team's boss?** Yes makes it the model that runs Jarvis and the agents
     (see [TEAM.md](TEAM.md)).
   - **Import your keys?** Only if `BAU-KEYS.enc` is on the stick. It asks for the
     passphrase you chose.
4. Last, it writes **`laptop-report.txt`** onto the stick. It describes the laptop's
   network card, its firmware and its radio switches, with addresses and Wi-Fi names
   hidden. Bring the stick back to the Windows computer and share that file to get the
   Wi-Fi sorted.

Run it again any time: models already in place are skipped, and nothing changes without
your yes.

Other commands:

```bash
bau pack check           # check every model on the stick, change nothing
sudo bau pack report     # only write laptop-report.txt onto the stick
```

## No stick needed: make the pack on Windows' own drive

If this laptop also starts Windows, make the pack on one of its drives (for example
`-Target D:\` in the Windows step). Back in Linux, `sudo bau pack install` opens that
drive **read-only** (it never writes to Windows) and installs from it. The laptop report
then goes to `/var/lib/bau/reports/laptop-report.txt`, since the drive is read-only.

If it says no pack was found: Windows may have been put to sleep instead of shut down
("Fast startup"), which keeps its drives locked. Start Windows, hold **Shift** while you
click **Shut down**, then start Linux and try again.

## The thinker

The uncensored model is copied but not started or approved: it uses most of the memory
next to the boss, so you start it only when you need it. It stays sealed: no tools, only on
this laptop, never anything for children. [WORKSPACES.md](WORKSPACES.md) ("The uncensored
model") has the commands to start, measure and approve it, then:

```bash
bau team set --thinker qwen3-4b-heretic-content
```

## If it says "qwen3.5-4b did not answer"

Qwen 3.5 "thinks out loud" before it answers, and on a laptop processor that took over
three minutes for one hello, so the check gave up. Sticks built after 21 October 2026
switch that off. On a laptop set up before, type these lines (none has the letter j):

```bash
echo LLAMA_ARG_REASONING=off | sudo tee -a /etc/bau/llm.env
sudo systemctl restart bau-llm
```

Wait a minute for the model to load, then measure it and, if it answered, approve it and
make it the boss:

```bash
sudo bau models bench qwen3.5-4b
sudo bau set-status model qwen3.5-4b APPROVED
sudo bau team set --boss qwen3.5-4b
```

`sudo systemctl status bau-llm` shows whether the model server is running and its last
messages.
