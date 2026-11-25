# BAU Watch: the whole operation on your tablet

**BAU Watch** is an Android app. It shows the business live on your tablet and lets you
answer Jarvis from it. Four views, one tap apart:

| View | What you see |
|---|---|
| **World** | the operations world: every agent walking to the room of her real job, the Inbox tab and every card waiting for you |
| **Workstation** | the AI workstation floor: each worker, her health, her tasks |
| **Tasks** | the task board: every job moving from Waiting to Working to Done (or Your review, or Stopped) as it really happens; a job that just moved glows for a moment |
| **Jarvis** | Jarvis himself: talk to him, see the briefing, answer his cards |

**Confirming from the tablet.** Jarvis's Accept / Not now cards work from the tablet:
posting, drops, clips, held work, setup steps. It is Jarvis's own page behind his own key,
the same as on the laptop.

Approvals signed with your SSH key (`bau approve`: refunds, payouts and other money moving
out) still need the laptop's terminal. Your signing key never leaves the laptop, so no app
can sign for you.

On two tablets, or a tablet and a phone, pair each one once. Each can show a different view:
the world on one, the task board on the other.

## How it is safe

The tablet reaches Jarvis through an **encrypted SSH tunnel**: the same one BAU already
allows for a station (`docs/LAPTOP-STATION.md`). The laptop lets the tablet's key do two
things only:
- **open Jarvis's screens** (the laptop's port 8766);
- **read Jarvis's address**.

It gets no shell, no other port and no files.

The app pins your laptop's key on the first connection, after you compare it. A computer
pretending to be your laptop is refused. It works on your home Wi-Fi only. Nothing on the
tablet is ever reachable from outside.

## Set it up

### 1. The laptop answers the tablet (once)

The laptop does the work while the desktop is down (`docs/COLIBRI.md`). On the laptop:

```
sudo apt install openssh-server
sudo bau hq on
```

It starts Jarvis for good as a service. It lets SSH in, by key only and from your home
network only. It also prints the laptop's address, for example `192.168.1.20`.

### 2. Install the app

1. On the tablet, open github.com/BSAJabo258/linux-ai-biz/releases/tag/bau-watch in the browser.
2. Download `bau-watch.apk`.
3. Open it. Android asks to allow installing from the browser: allow it for this once.

### 3. Pair the tablet

1. Open **BAU Watch**. It makes its own key and shows a line starting
   `sudo bau hq allow "ecdsa-sha2-nistp256 …"`. Press **Copy the line**, send it to
   yourself, and type it in the laptop's terminal.
2. In the app, type the laptop's address and your login name on the laptop. Press
   **Check the laptop**.
3. The app shows the laptop's key, starting `SHA256:`. On the laptop, type:
   ```
   sudo ssh-keygen -lf /etc/ssh/ssh_host_ecdsa_key.pub
   ```
   Press **It matches** only if every character is the same.

It opens on the World view. The buttons at the bottom switch views. The screen stays on, and
if the Wi-Fi drops or the laptop restarts, it reconnects by itself within 15 seconds.

## Good to know

- **Updates:** a new build of the app replaces the release. This build is signed with a
  one-time build key, so to update, uninstall the old app first and pair again (step 3).
- **Another laptop, or a new install:** press **Pair again** in the app.
- **Take a tablet's access away:** on the laptop, remove its line (it ends in
  `bau-watch-…`) from `~/.ssh/authorized_keys`. `sudo bau hq off` closes SSH for everyone.
- The task board alone also works in any browser on the laptop: Jarvis's address with
  `/watch` in place of `/` (for example `http://127.0.0.1:8766/watch?k=…`).
- The app's code is in `android/`. Its tunnel is tested against a real SSH server with BAU's
  own key line (`android/tunnel`). The app is built by `.github/workflows/android.yml`.
