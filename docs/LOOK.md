# The BAU look: your art, gently alive

Your art sits behind Jarvis and Mission Control, and on the stick's desktop and login
screen. It is "alive" in a way an 8 GB laptop can afford: still pictures with a light
animation in the page (a slow breathing glow, a golden pulse rising along the centre
line, embers drifting up; faster while Jarvis is thinking). No video wallpaper, so the
AI model keeps the memory and the battery lasts.

If your computer is set to reduce motion, the animation stops and the picture stays still.

## Choose the art

```bash
bau look                 # what is in use, and the choices
bau look set moon        # the moonlit one (the default)
bau look set light       # the white BAU one
bau look set watercolor  # the watercolour BAU one
bau look set gold        # the dark gold one
bau look set earth       # the earth and moss one
bau look set none        # no art: the plain blue sky
bau look alive off       # keep the picture, stop the animation (on to restart it)
```

## Add your own pictures

```bash
bau look add ~/Pictures/my-art.png
```

It takes JPEG or PNG pictures up to 15 MB (it checks the file really is a picture),
names it after the file (`my-art`), and uses it at once. Switch back any time with
`bau look set moon`.

Pictures made by an AI often have scrambled lettering (the orange BAU picture reads
"MOGIC", "IMEACT"); fix the words before using one with text, or pick one without.

## The desktop and the login screen (the stick)

At your first login the desktop gets the BAU art (it changes every 10 minutes between the
pictures in `/usr/share/backgrounds/bau`) and the dark theme. The login screen shows the
same art. That happens once only: after that it never changes your own choices. To pick
another picture, including your own: right-click the desktop, **Desktop Settings**.
