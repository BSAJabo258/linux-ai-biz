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

## What BAU refuses or does on its own

- Anything about minors is never sent to the picture model.
- Every prompt is plain visual facts that start with her adult age. Things like "childlike",
  "cartoon" or "teen" are pushed away in every picture.
- `bau creator draw` makes safe-for-work pictures only. Explicit pictures for Fanvue are not
  built yet.
- The picture program is only reached on this computer (127.0.0.1).

## Still to do

- **Same face every time.** The prompt describes her the same way each time, but SDXL
  alone does not keep one exact face across pictures. A face-lock step is the next thing to
  add. Until then, pick the pictures that match her best.
- Explicit pictures for Fanvue.
- Showing the pictures themselves on the week's card.
