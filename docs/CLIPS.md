# Campaign clips (GTA 6 and other streams)

Jarvis finds the newest streams, cuts their best moments into vertical clips and puts each one
on a card. You press Accept, it goes up on YouTube Shorts, and you submit its link to the
campaign. Every fact below was read on the official pages on 2026-11-24.

## Where the money comes from

**Clipping campaigns.** A streamer or brand puts up a budget on Content Rewards (Whop's clipping
site) and pays clippers for every 1,000 views their clips get. On 2026-11-24 the GTA 6
campaigns paid $0.50 to $1.50 per 1,000 views, with a cap per clip. On November 20 the 12
campaigns with GTA 6 in their name had 2,083 approved clips and about 71.9 million views
(Content Rewards' own count).

Plain numbers: a clip with 100,000 views earns $50 to $150 at those rates. A clip with 1,000
views earns about $1. Budgets are first come, first served, and run out.

**Why not your own GTA channel.** Rockstar's own policy (updated 2025-01-10) allows fans'
gameplay videos for non-commercial use only: "'Non-commercial' means that you don't make money
through the game footage you post." YouTube also keeps plain gameplay clip channels out of ad
money (its "reused content" rule). Campaigns are different: the streamer pays you, from his own
budget, to clip his own streams.

**Every campaign's brief sets the rules, and they are strict:**
- only the streamer's official streams and replays;
- the caption and hashtags he names on every clip;
- sometimes his overlay picture;
- "Stolen clips, reuploads, fabricated context, fake reactions, and misleading titles are
  prohibited";
- only TikTok, Instagram Reels and YouTube Shorts.

**You submit each clip yourself.** A clip is paid only if you paste its link into the campaign
**within 30 minutes of posting**, from an account you connected there. Content Rewards shows
no way for software to do that. So Jarvis never posts by himself: a clip posted while you sleep
would earn nothing.

## What Jarvis does by himself

Every autopilot run (every 30 minutes), for each campaign you added:
1. looks at the newest videos on the brief's own channels (links only);
2. downloads only the **sound** of a new stream and finds its loudest moments (a shout, a crash,
   the chat going wild), skipping the first two minutes;
3. downloads **only those minutes** of video (a laptop's disk stays small);
4. cuts each into a vertical 1080x1920 clip: the stream at full width over a blurred copy of
   itself, the brief's overlay on top;
5. writes the brief's caption and hashtags, and says it is paid ("#ad" in the title, "Paid clip
   for the ... campaign" first in the description);
6. puts it on a card, up to your number a day for that campaign.

He checks the video's channel against the brief before cutting anything: footage from anyone
else is refused.

**On the card** you see the clip. You pick who sees it on YouTube (public, unlisted or private,
no default) and answer "made for kids" (GTA 6 is rated M, so the only answer is no).
- **Accept:** it goes up on YouTube Shorts and the campaign's page opens. Submit the link there
  within 30 minutes.
- **Not now:** the clip is dropped and its file deleted.

HOLD stops all of it. Every check runs again when you press Accept.

## Set it up

### 1. The laptop does the work (the desktop is down)

The laptop is set up as the station, which leaves the work to the desktop. While the desktop is
down, make the laptop do the work:

```
sudo bau station role off
sudo apt install yt-dlp
```

The first line turns the laptop's autopilot back on. The second installs the video downloader.
If Twitch or YouTube downloads fail, Debian's copy may be too old: install the newest release
from github.com/yt-dlp/yt-dlp into /usr/local/bin instead.

The laptop has no graphics card for her Fanvue pictures, so those wait for the desktop. Cutting
clips needs only the processor.

### 2. Your YouTube channel (once)

1. On console.cloud.google.com, make a project and switch on **YouTube Data API v3**.
2. **OAuth consent screen:** External; add the scope `.../auth/youtube.upload`; then press
   **Publish app** so it is **In production**. Left in "Testing", Google ends the sign-in every
   7 days. Google will show a "not verified" warning when you sign in: that is your own app,
   continue.
3. **Credentials → Create OAuth client → Desktop app.** Copy its client ID and secret.
4. On the laptop:
   ```
   sudo bau keys set YOUTUBE_CLIENT_ID YOUTUBE_CLIENT_SECRET
   bau youtube login
   ```
   Google opens in the laptop's browser: sign in with the channel's account and press Allow.
   `bau youtube status` says whether it is connected.

### 3. Content Rewards (once)

On contentrewards.com: sign up, **connect your YouTube channel** (clips can only be submitted
from a connected account), and join a GTA 6 campaign. Read its brief: it names the streamer's
channels, the caption, the hashtags and any overlay.

### 4. Tell Jarvis about the campaign

Copy the brief into one command. For example, for a Twitch streamer:

```
bau clips campaign "Kai Cenat GTA 6" \
  --url https://contentrewards.com/c/campaigns/THE-CAMPAIGN \
  --source https://www.twitch.tv/kaicenat \
  --caption "Watch Kai Cenat live on Twitch" \
  --hashtag GTA6 --hashtag KaiCenat \
  --rate 1.00 --seconds 40 --per-day 3
```

If the brief gives an overlay picture, put it in `BAU_HOME/clips/overlays/` and add
`--overlay its-file-name.png`.

Then either wait for the autopilot, or clip one stream now:

```
bau clips make kai-cenat-gta-6 https://www.twitch.tv/videos/THE-VIDEO --count 2
bau clips run       # what the autopilot does, right now
bau clips list      # every clip and its state
```

## Good to know

- **Music claims:** GTA's in-game radio is licensed music. A clip with the radio playing can get
  a YouTube music claim. That takes ad money or blocks it in some countries, but campaign pay
  comes from the campaign.
- **Never** clip leaked or pre-release footage, cheats, glitches or exploits: Rockstar takes those
  down.
- TikTok is not used yet: BAU's TikTok app is not audited, so its posts would be private.
- Platform facts and their pages: `examples/platform-youtube.yaml`, and the top of
  `src/bau/clips.py` and `src/bau/youtube.py`.
