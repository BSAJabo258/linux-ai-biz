# A week of posts with one click

You approve the creator's week once. Ayrshare then posts each one on its day, on Instagram
and TikTok, with the platform's AI label on every post. Jarvis can only put the week on
your screen; it posts nothing until you confirm.

Built 2026-11-01. Tested with a fake Ayrshare only: not yet run against your real account.

## What you need once

1. **An Ayrshare account** with Instagram and TikTok linked in its dashboard. Videos need
   a paid Ayrshare plan.
2. **Its API key on the laptop.** Put `AYRSHARE_API_KEY` into your keys file on your
   other computer ([KEYS.md](KEYS.md)), then on the laptop, from the stick's folder:

   ```bash
   sudo bau keys import BAU-KEYS.enc
   ```

   It goes to `/etc/bau/platforms.env` with the other platform keys. It never reaches a
   model or a log.

## Every week

1. Put the finished pictures and videos in `/var/lib/bau/artifacts/media/` (30 MB each at
   most).
2. Write the week's plan in `/var/lib/bau/weeks/`, for example `nov-week-1.yaml`:

   ```yaml
   posts:
     - when: 2026-11-03T19:00:00-05:00     # Michigan time; always give the -05:00
       platform: instagram                 # instagram or tiktok
       tier: sfw
       caption: "Cozy latte by the window. #AI virtual creator"
       media: mon.jpg
     - when: 2026-11-04T19:00:00-05:00
       platform: tiktok
       tier: sfw
       caption: "Autumn walk, AI-generated."
       media: tue.mp4
   ```

3. Tell Jarvis: "Schedule the week nov-week-1."
4. One card shows every post. Pick who can see the TikTok posts, read them, confirm.

## What BAU refuses (with the reason)

- Anything but sfw on Instagram and TikTok. Fanvue is not on Ayrshare; its own
  connection is planned.
- A caption that refers to minors.
- A caption without an AI disclosure (`#AI`, "AI-generated", "virtual creator").
- A time in the past, or one without a time zone.
- Media outside the media folder.
- A week that changed after you saw the card: Jarvis shows it again.
- Sending the same week twice.

Each week leaves `weeks/NAME.sent.json` (what Ayrshare answered) and a `week.scheduled`
line in the audit record.
