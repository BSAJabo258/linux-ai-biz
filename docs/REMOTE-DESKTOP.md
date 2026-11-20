# Remote desktop: your iPhone on the home Wi-Fi

Your choice (2026-11-20): see and use the desktop from your iPhone, at home only. Not yet
switched on on your desktop; nothing listens until you do.

## Switch it on (once, at the desktop)

```bash
sudo bau remote-desktop on
```

It installs Debian 13's own remote desktop server (xrdp, free, Apache-2.0) and prints the
address to type on the iPhone. It:
- lets it in through the firewall **only from your home network** (like the laptop's SSH),
  at most 15 new connections a minute;
- takes **encrypted connections only** (TLS);
- lets **only your login** in (never root), with your normal computer password.

## On the iPhone

1. App Store: **Windows App** by Microsoft (free).
2. **+**, Add PC, type the address `sudo bau remote-desktop on` printed (for example
   `192.168.1.20`).
3. Connect. The first time it asks about the desktop's certificate: accept it (it is your
   own desktop's). Log in with your desktop login name and password.

You get your own XFCE desktop session; open Jarvis there in the browser (`bau jarvis url`
prints his address). It works only on your home Wi-Fi, not on mobile data.

## Check or switch off

```bash
bau remote-desktop status         # on or off, and the address
sudo bau remote-desktop off       # stops it and closes its port again
```

Reinstalling BAU keeps your choice (the installer reads `/etc/bau/remote-desktop`).
