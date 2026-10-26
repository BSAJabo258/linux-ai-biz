# The BAU look: your art, gently alive

Your art sits behind Jarvis and Mission Control, and on the stick's desktop and login
screen. It is "alive" in a way an 8 GB laptop can afford: no video wallpaper, so the AI
model keeps the memory and the battery lasts.

## Two anime scenes, painted live (the default)

BAU paints two original anime-style scenes itself, so they never end and stay sharp
(better than a looping GIF, which repeats every few seconds and goes blurry):

- **Dusk:** a city at sunset: a big moon, stars that twinkle and a shooting star now and
  then, long clouds lit pink and gold from below, warm windows in the buildings, a red
  light blinking on a tower, power lines, and cherry petals drifting past. A woman stands
  on the rooftop looking at the moon, her hair and coat moving in the wind, lit pink at
  the edges by the sunset.
- **Summer:** tall summer clouds, white in the sun and blue in their own shade, the sun
  with its rays and lens flare, green hills with grass moving in the wind, power lines
  and a few petals. A woman in a white sundress and a straw hat stands on the hill,
  her long hair blowing.

Both women are grown-ups, seen from behind, the classic anime shot.

Jarvis stays in one scene for about 40 seconds, then breathes it into his glass core and
the other one unfurls out, like dusk turning into day. The petals and clouds move faster
while he thinks. The desktop and the login screen show the same two scenes as still
pictures (the desktop changes between them every 10 minutes).

If your computer is set to reduce motion, the animation stops and the picture stays still.

## Liquid: a glass mind in a living painting (Jarvis)

In Jarvis your pictures are alive like ink in water. A slow current flows through them
and rises like heat; the picture's own colours glow softly across the whole screen, and
light bleeds from its bright ink. White paper behind a picture melts away, so only the
ink floats on the dark sky.

Jarvis's core is a drop of liquid glass sitting in the painting. Like a real lens it
shows the picture behind it upside down, with rainbow edges, a rim of light in his
colour and a shine on top. Embers in the painting's own colours rise from its ink.

Every quarter of a minute Jarvis breathes the pictures: the old one spirals down into the
glass core and the next one unfurls out of it, with veins of his colour running through
the change.

It follows Jarvis:

| Jarvis is | The art |
|---|---|
| standing by | drifts slowly, cyan light |
| listening | flows faster, amber light |
| thinking | flows fastest, violet light, the glass stirs inside, a scan line passes |
| speaking | his voice ripples the glass and sends rings out from the core |

Your mouse bends the light a little where it points, and the picture and its glow
part slightly as it moves, like looking through a window.

```bash
bau look flow dusk summer gold  # only these pictures, in this order
bau look flow all               # every picture there is
bau look flow default           # back to the two anime scenes and your own pictures
bau look alive off              # one still picture instead
```

The picture you chose with `bau look set` always comes first. It costs little on the 8 GB
laptop: the laptop's graphics chip draws it at half size and at most 30 times a second,
with a few thousand embers at most,
and it stops while Jarvis's window is hidden. Without a graphics chip that can do it, or
with "reduce motion" on, you get the still picture. If the computer would draw it with
the processor instead of the graphics chip (that would run it hot), it never starts; if
it falls behind (under 12 pictures a second), it first draws smaller, then stops and
shows the still picture.

## Choose the art

```bash
bau look                 # what is in use, and the choices
bau look set dusk        # the anime city at dusk (the default)
bau look set summer      # the anime summer sky
bau look set moon        # the moonlit inkblot one
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

Fixed 2026-10-26: until then the desktop kept Xfce's own picture (the mouse). A new Xfce
desktop stores no picture setting until someone picks one, so BAU found nothing to change
and gave up. Now it writes the setting for every screen and workspace itself. Proved in a
Debian 13 Xfce desktop (xfdesktop 4.20.1): before, Xfce's default; after, the dusk scene.
It comes with a stick built after this fix; if the desktop still shows the mouse after
logging in, run `bau-look-desktop` once in a terminal.
