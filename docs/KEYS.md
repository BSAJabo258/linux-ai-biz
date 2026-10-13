# Your API keys: bring them over once, safely

BAU reads your keys from two files on the laptop:
- `/etc/bau/models.env`: Claude, Z.ai, NVIDIA, ElevenLabs, Higgsfield and other model or
  service keys;
- `/etc/bau/platforms.env`: YouTube, TikTok and other platform app keys.

Instead of typing each key, you can carry them all over from the computer that has them,
in one locked file. Your keys are **never** pasted into a chat, never put on GitHub, and
never shown on screen: BAU only ever shows their **names**.

## 1. On the computer that has your keys

It looks in your environment variables (names ending in `API_KEY`, `_TOKEN`, `_SECRET`,
`_KEY`, `_CLIENT_ID` or `_KEY_ID`) and in any `.env` files you give it. It changes nothing on
that computer.

**Windows:** put `BAU-Keys-Export.cmd` and `bau-keys-export.ps1` in the same folder (both
are in `BAU-PAYLOAD` on the stick, or download them from
<https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/installer/BAU-Keys-Export.cmd>
and <https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/installer/bau-keys-export.ps1>).

1. Double-click **`BAU-Keys-Export.cmd`**. If some keys are in `.env` files, drag those
   files onto `BAU-Keys-Export.cmd` instead.
   (If Windows says *Windows protected your PC*: **More info**, then **Run anyway**.)
2. It lists the key **names** it found. Type `y` if the list is right.
3. Choose a **passphrase** (8 or more characters) and type it twice. Remember it: without
   it the file cannot be opened, by anyone.
4. `BAU-KEYS.enc` appears next to the `.cmd` file. Copy it to a USB stick.

**Mac or Linux:** in a terminal, in the folder with `bau-keys-export.sh`:

```bash
bash bau-keys-export.sh                     # keys from your environment
bash bau-keys-export.sh ~/project/.env      # and from .env files you name
```

## 2. On the BAU laptop

Plug in the USB stick, open a terminal in its folder, and run:

```bash
sudo bau keys import BAU-KEYS.enc
```

Type your `bauadmin` password, then the passphrase you chose. It shows which key names
went where, never the values. Then:

1. **Delete `BAU-KEYS.enc`** from the USB stick.
2. Log out and in again, so Jarvis and BAU's services see the keys.
3. Check what BAU has (names only): `bau keys list`

Importing again later is safe: keys with the same name are replaced, every other line in
the files stays as it is.

## Good to know

- Only key-shaped names are accepted, so a key file can never change how the laptop runs
  (it refuses names like `PATH` or `LD_PRELOAD`).
- A wrong passphrase changes nothing; just run it again.
- New keys still need your approval where BAU asks for it. For example a model is only
  used after `bau set-status model ... APPROVED`, and YouTube or TikTok still need
  `bau youtube login` / `bau tiktok login`.
- The file is locked with AES-256 in openssl's standard format (PBKDF2-SHA256, 600,000
  rounds). If your Mac says its openssl is too old, install a new one with
  `brew install openssl` and run the script again.
