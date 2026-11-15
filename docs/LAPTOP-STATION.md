# The laptop as Jarvis's operations station

Built 2026-11-15. You asked for this: Jarvis on the desktop, the AI workstation on the laptop,
controlled by Jarvis, with the laptop not carrying a second Jarvis. Tested here on a real SSH
server with BAU's own settings; not yet on your two computers.

## How it works

- **The desktop is headquarters.** Jarvis, the models, the autopilot and every agent run
  there. Jarvis runs for good as a service and still answers only on the desktop itself
  (127.0.0.1).
- **The laptop is the station.** It shows Jarvis and his operations world (the WORLD view)
  through one encrypted SSH tunnel to the desktop. It runs no Jarvis of its own and needs no
  models, so it keeps its space and memory free.
- **What the laptop's key can do on the desktop: two things only.** Carry the tunnel to
  Jarvis, and print Jarvis's address. It cannot open a shell, run a command, reach any
  other port, or open a connection back into the desktop. All of this was tried and refused
  on a real SSH server.
- **The desktop cannot reach into the laptop.** The laptop accepts no incoming connections,
  so nothing can be pushed to it.
- **If the home network drops,** the tunnel comes back by itself within seconds. Jarvis's
  work goes on on the desktop meanwhile.

The one thing this opens: the desktop accepts SSH, by key only, from home-network addresses
only (10.x, 172.16-31.x, 192.168.x and local IPv6), a few new connections a minute at most.
This is the second exception to BAU's "nothing comes in" rule, after your cloud server. It
is on only after you run `sudo bau hq on` yourself. `sudo bau hq off` closes it again.

## Set it up

### 1. On the desktop, once

```bash
sudo apt install openssh-server      # only if bau hq on asks for it
sudo bau hq on
```

It prints the next line for the laptop, with your desktop's address in it.

From now on, open Jarvis on the desktop itself with:

```bash
xdg-open "$(bau jarvis url | tail -1 | sed 's/^[[:space:]]*//')"
```

### 2. On the laptop

Install it from the stick as usual (encrypted Debian with BAU). Skip the model pack: the
laptop does not need the models. Then:

```bash
bau station pair YOURNAME@DESKTOP-ADDRESS     # e.g. owner@192.168.1.20
```

It makes the laptop's own key, starts the tunnel, puts **Jarvis HQ** in the menu, and prints
one line to run on the desktop.

### 3. On the desktop, the line it printed

```bash
sudo bau hq allow 'ssh-ed25519 AAAA... bau-station'
```

### 4. On the laptop

```bash
sudo systemctl disable --now bau-autopilot.timer bau-scout-watch.timer   # his work runs on the desktop
bau station open                                                           # or Jarvis HQ in the menu
```

Jarvis opens in the browser, straight on his world.

## Day to day

```bash
bau station status          # laptop: is the tunnel up
bau hq status               # desktop: on or off, which stations are allowed
bau station unpair          # laptop: stop the tunnel and forget the desktop
sudo bau hq off             # desktop: close SSH again
```

## Not built yet

- The laptop running agent work of its own for the desktop (a worker). Today it shows Jarvis
  and his world, and you work through him.
- Finding the desktop by name: give its address. `sudo bau hq on` prints it.
