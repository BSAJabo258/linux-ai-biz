# Pictures made on your own computer

Your desktop's graphics card (RTX 3060) draws the creator's pictures. There is no picture
service, no per-picture fee, and nothing leaves the computer. BAU uses ComfyUI, a free
picture program, with the Stable Diffusion XL model.

Built 2026-11-01. It ran for real in a test computer without a graphics card: two pictures
through BAU's own code, ComfyUI and the real model (90 s at 512×512, 7 minutes at 768×768,
both on the processor). It has **not run on your desktop yet**. With the graphics card it
should be much faster, but that has not been measured.

## How long BAU waits for a picture (fixed 2026-11-20)

ComfyUI draws one picture at a time; the others wait in its line. BAU now waits like this:

- **While a picture waits in line:** up to an hour. After that BAU takes it out of the line
  and says so.
- **While it is being drawn:** up to 15 minutes for a safe-for-work picture, 45 for a Chroma
  (levels 2 and 3) picture. On your desktop Chroma took 9 to 33 minutes a picture. After
  that BAU stops that picture.
- **Whenever BAU gives up** (or you press Ctrl-C), it takes its own picture back, and never
  anyone else's.

Before this, BAU gave up after 15 minutes counted from sending, so every Chroma picture and
every picture that waited in line was given up, but ComfyUI still drew it for nobody, and the
next run sent another. On 2026-11-20 the line held 15 of them. Pictures already in the line
from before the fix still run; this fix only stops new ones from piling up.

To see the line: `curl -s http://127.0.0.1:8188/queue`.

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

## Her face lock: the same woman in every picture (2026-11-18)

Your choice: one locked face for your creator. Set it up once, after the pictures setup:

```bash
sudo bash installer/bau-face-setup.sh   # the face nodes and two face models, about 3.4 GB
bau creator face draw                   # 4 candidate faces (--count up to 8)
bau creator face pick 2                 # you lock the one you like (here number 2)
bau creator face show                   # is it locked, and what is next
```

The candidates land in `creators/faces/candidates` (never where Fanvue posts come from), each
age-checked like every picture. Only you lock a face, at your terminal. From then on every
level 0 and 1 picture is drawn from that face with IP-Adapter Plus Face (h94/IP-Adapter,
Apache-2.0; the ComfyUI_IPAdapter_plus nodes, GPL-3.0, run inside ComfyUI). No InsightFace:
its face models are for non-commercial use only. Each picture's record says which face it used.
If the locked file is changed, BAU stops using it until you pick again. `bau money` shows the
face lock as one of its links.

Not tested on your card yet: the face nodes were checked in their code, not run here. The first
`bau creator face draw` and the first feed picture after it are the test.

## Her face on levels 2 and 3: her LoRA (2026-11-18)

Chroma has no face lock like the one above, so her face there is a LoRA: a small add-on file
trained on pictures of her. Do it once, after her face is locked and Chroma is set up:

```bash
bau creator face dataset                        # 20 clothed pictures of her, from her face
                                                # look at them: delete any that are not her
                                                # (the .png and its .txt)
sudo bash installer/bau-lora-train.sh aria      # installs the trainer once, then trains
bau creator face use-lora                       # you lock the result
```

The dataset is drawn in `creators/faces/dataset/<id>` with a caption for each picture naming
her trigger word (`bau` + her id, for Aria `bauaria`); it is never posted. The training uses
kohya-ss/sd-scripts (Apache-2.0, pinned commit) with its own advice for a 12 GB card, about
1,000 steps, a few hours. While it trains, the chat model and the picture maker are stopped
(this computer's memory cannot hold all three) and started again at the end, also if it fails.
The first run also downloads about 8 GB: the trainer's Python and PyTorch, and a plain text
encoder (the picture maker's own is in a format the trainer cannot read).

The LoRA learns her face from clothed pictures only. What a level 2 or 3 picture shows still
comes from that level's prompt and your explicit limits, and every picture still gets the age
check and your Accept. Each picture's record names the LoRA it used. If the LoRA file is
changed, BAU stops using it until you lock it again.

Not tested yet: the trainer has not run on this computer. sd-scripts is tested on Python
3.10 to 3.12 and this computer has 3.13, so the first run is the test.

## Clips for levels 2 and 3 (Wan 2.2, 2026-11-21)

Short clips of her alone, made on this desktop from one of her kept explicit pictures, so her
face stays hers. The model is Wan 2.2 TI2V-5B (free licence, Apache-2.0), run inside the same
ComfyUI as the pictures, with ComfyUI's own workflow.

Set it up once (about 18 GB, checked file by file):

```bash
sudo bash installer/bau-video-setup.sh
```

Or press Accept on the **Set up short clips** card in Jarvis; it comes after the Chroma card.
Then the **Set your clip price** card asks what a fan pays to unlock one clip (filled in from
Fanvue's advice, $14.99; nothing posts until you Accept). At a terminal it is
`bau creator prices PROFILE --subscription .. --nude .. --xxx .. --clip ..`.

What happens:

- At most one of the day's posts is a clip: feet (level 2) or her alone, touching herself or
  with a toy (level 3), from `clips:` in `src/bau/data/creator_prompts.yaml`.
- **Every frame is age-checked:** all of them (73 in a 3-second clip), each through the same
  age model as the pictures. One frame that could pass for under 20, a frame missing, or a
  check that cannot run, and the clip is not kept (it stays in `artifacts/rejected`).
- **Her alone, within Fanvue's rules.** Fanvue's own pages (read 2026-11-21) ban bodily fluids
  and need ID and signed consent for anyone else shown. So a clip prompt that names another
  person, fluids (finishing on her, creampies, squirting) or anything Fanvue bans is refused
  and never sent. Those wait for Fanvue's written answer.
- Your limits are added to what every clip must never show.
- It goes on a card like a picture, and the card plays the clip. While the automaton runs it
  posts by itself, as pictures do (your choice).

Not measured yet: how long a clip takes on the RTX 3060 and the largest size that fits. It
starts at 704x1280, 3 seconds; the first real clip sets these.

## Still to do

- Showing the pictures themselves on the week's card.
