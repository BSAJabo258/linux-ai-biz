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

Close any Jarvis window you had open first (Ctrl+C in it): only one Jarvis can use his
address. `sudo bau hq status` must then say `"jarvis_service": "active"`. If it says
`activating` or `failed` (it gives up after 5 tries when his address is taken), run
`sudo systemctl restart bau-jarvis.service`.

From now on the **BAU Jarvis** menu entry opens the Jarvis that runs for good. Or open him
on the desktop itself with:

```bash
xdg-open "$(bau jarvis url | tail -1 | sed 's/^[[:space:]]*//')"
```

### 2. On the laptop (the Dell XPS 13), once

**Install.** Start the laptop from the stick and pick the install. When it asks which disk,
pick the **WD disk of about 1 TB** (the external USB one), not the laptop's own disk, and
put the boot loader on the WD disk too. Skip the model pack: the laptop does not need the
models. From then on the laptop starts BAU from the WD disk: plug it in, press **F12** at
the Dell logo and pick the WD disk.

**Then, at a terminal on the laptop, in this order:**

```bash
sudo bau update auto                           # keep BAU up to date by itself, every night
sudo bau station role on                       # this laptop is the station
bau station pair bauadmin@DESKTOP-ADDRESS      # e.g. bauadmin@192.168.1.20
```

`sudo bau station role on` tells everything on the laptop that the desktop does the work:
the autopilot and the open-source watch stop here (so the desktop's GitHub scans are not done
twice), the menu's Jarvis opens the desktop's Jarvis instead of starting one here, no
pictures are drawn and nothing is posted to Fanvue from the laptop, the setup pop-ups for
desktop jobs (search, autopilot, pictures, Fanvue) do not show, and `bau money` says the
money machine runs on the desktop. `sudo bau station role off` undoes it.

`bau station pair` makes the laptop's own key, starts the tunnel, puts **Jarvis HQ** in the
menu, and prints one line to run on the desktop. The account is `bauadmin` on both computers.

### 3. On the desktop, the line it printed

```bash
sudo bau hq allow 'ssh-ed25519 AAAA... bau-station'
```

### 4. On the laptop

Use only the **Jarvis HQ** menu entry (or `bau station open`). Jarvis opens in the browser,
straight on his world.

### The network between the two

Your desktop gets its internet from the tablet over a USB cable, and the laptop uses the
tablet's Wi-Fi hotspot. Whether the tablet lets the two computers reach each other is **not
proven**: many phones and tablets keep their hotspot's devices apart. Test it from the laptop:

```bash
bau station status                    # "tunnel": "active" means it works
ssh bauadmin@DESKTOP-ADDRESS
```

For the `ssh` line: `Permission denied (publickey)` is good news (the desktop answered; it
only takes the station's key). `Connection timed out` or `No route to host` means the two
cannot reach each other through the tablet.

If it does not work, join the two with a network cable (the XPS 13 has no network socket, so
it needs a USB-C Ethernet adapter) and give each a fixed address. First find each
computer's wired device name with `nmcli device` (it starts with `en`, e.g. `enp3s0`), and
put it in place of IFACE.

On the desktop:

```bash
sudo nmcli con add type ethernet con-name bau-link ifname IFACE ipv4.method manual ipv4.addresses 192.168.77.1/24 ipv4.never-default yes
```

On the laptop:

```bash
sudo nmcli con add type ethernet con-name bau-link ifname IFACE ipv4.method manual ipv4.addresses 192.168.77.2/24 ipv4.never-default yes
bau station pair bauadmin@192.168.77.1
```

Both keep their internet from the tablet (`ipv4.never-default yes`: the cable carries only
the tunnel). The desktop's headquarters firewall already allows 192.168.x addresses.

## Day to day

```bash
bau station status          # laptop: is the tunnel up
bau hq status               # desktop: on or off, which stations are allowed
bau station unpair          # laptop: stop the tunnel and forget the desktop
sudo bau station role off   # laptop: not the station any more (its timers on again)
sudo bau hq off             # desktop: close SSH again
```

## Not built yet

- The laptop running agent work of its own for the desktop (a worker). Today it shows Jarvis
  and his world, and you work through him.
- Finding the desktop by name: give its address. `sudo bau hq on` prints it.
