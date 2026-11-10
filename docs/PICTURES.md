# Pictures made on your own computer

Your desktop's graphics card (RTX 3060) draws the creator's pictures. There is no picture
service, no per-picture fee, and nothing leaves the computer. BAU uses ComfyUI, a free
picture program, with the Stable Diffusion XL model.

Built 2026-11-01. It ran for real in a test computer without a graphics card: two pictures
through BAU's own code, ComfyUI and the real model (90 s at 512×512, 7 minutes at 768×768,
both on the processor). It has **not run on your desktop yet**. With the graphics card it
should be much faster, but that has not been measured.

## Set it up once (the installed desktop)

You need NVIDIA's driver first (docs/DESKTOP.md, `sudo bau-gpu-setup`), then the internet
for the first download (about 10 GB in all). In a terminal:

```bash
sudo bash /opt/bau-payload/bau-pictures-setup.sh
```

It takes a while and ends with **Local pictures are running on 127.0.0.1:8188**. It starts
by itself at every boot, and only this computer can reach it. It refuses to run on the live
stick, because there it would be gone at the next restart.

## Make pictures

```bash
bau creator init                       # once: the starter creator (docs/VIRTUAL-CREATOR.md)
bau creator draw /var/lib/bau/creators/aria.yaml "cozy autumn week" --count 7
```

The pictures land in `/var/lib/bau/artifacts/media/` as `aria-DATE-1.png`, `-2`, and so on.
Each has a `.provenance.json` next to it: AI-made, which model, the seed, and fingerprints of
the prompt and the file. Every picture is also recorded in the audit log.

**Look at every picture before you use it.** Throw away any picture that does not look
clearly adult. Fanvue's rule is that how she looks counts, not her stated age. Then list the
good ones in a week plan (docs/WEEK.md).

## Pictures for paid levels 2 and 3 (Chroma)

Your choice (2026-11-09): Chroma1-HD, a free picture model (Apache-2.0) made without a safety
filter, draws the nude and xxx unlocks for Fanvue. Set it up once, after the pictures setup
and after you have written your explicit limits (the card pops up in Jarvis by itself):

```bash
sudo bash installer/bau-explicit-setup.sh
```

It downloads three files (about 23 GB) into the picture maker and checks each against its
pinned fingerprint. If the disk is short of room, it stops and asks you to run Make room first
(docs/MAKE-ROOM.md). It uses the model card's own ComfyUI recipe, shrunk to 8-bit as it loads
so it can fit your 12 GB card; that fit is not measured yet, so the first pictures are the
test.

Every Chroma picture still gets the age check below, adds your explicit limits to what it must
never show, is always one fictional adult alone, and waits on a card in Jarvis for your Accept.

## The age check on every picture

Every picture is checked by an age model before it is kept. The model is
`dima806/fairface_age_image_detection`, pinned and checked, and it runs on this computer.

If the picture could pass for under 20 (more than 0.10 on the model's three youngest age
groups), it is moved to `/var/lib/bau/artifacts/rejected/` and never used. If the check
cannot run, the picture is not kept either. A week plan refuses any picture without a passed
check on record.

Tested 2026-11-01 on two real pictures, using BAU's own check script with the pinned model:

- the first try, which looked young, scored 0.25 and was rejected;
- the clearly adult one scored 0.05 and was kept.

Two pictures is little proof, and the age groups are wide (10-19, 20-29). So it is a second
guard, and you still look at every picture. Videos are not age-checked yet.

## What BAU refuses or does on its own

- Anything about minors is never sent to the picture model.
- Every prompt is plain visual facts that start with her adult age. Things like "childlike",
  "cartoon" or "teen" are pushed away in every picture.
- `bau creator draw` makes safe-for-work pictures only. Explicit pictures (levels 2 and 3)
  are made only by the autopilot's Fanvue feed, with Chroma, and only for Fanvue.
- The picture program is only reached on this computer (127.0.0.1).

## Still to do

- **Same face every time.** The prompt describes her the same way each time, but SDXL
  alone does not keep one exact face across pictures. A face-lock step is the next thing to
  add. Until then, pick the pictures that match her best.
- Showing the pictures themselves on the week's card.
