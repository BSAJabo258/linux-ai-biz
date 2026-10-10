# Results tracker: how your videos are doing, and whether they make money

BAU makes videos and posts them when you confirm. The results tracker reads the numbers
back afterwards:

- **views, watch time, likes, comments, shares and new subscribers** for every video BAU
  posted;
- **YouTube's estimated earnings** per video, once your channel earns from YouTube;
- **what each video cost** (the paid clips it used), so you see the **profit** per video;
- **which story formats** (count-along, question-reveal, ...) people watch most.

It only reads. It never posts, edits or deletes anything on YouTube or TikTok.

## One-time setup: log in again

The tracker needs two more permissions than posting does, so each platform asks you once
more:

```bash
bau youtube login
bau tiktok login
```

- **YouTube** asks you to allow "View YouTube Analytics reports" and "View monetary and
  non-monetary YouTube Analytics reports". The second one is what shows earnings. If you
  untick it, views still work and earnings show as "—".
- **TikTok** asks to allow reading your public videos (`video.list`).

## See it

- **On the Jarvis screen:** click the **Results** dot, then **Get the latest numbers**.
- **Ask Jarvis:** "How are our videos doing?" or "Which videos made money this month?"
- **In the terminal:**
  ```bash
  bau results refresh      # read the latest numbers (at most once an hour)
  bau results              # show them again without asking the platforms
  ```

Platforms don't count in real time. A video posted today may show no numbers until a
day or so later. BAU reads each platform at most once an hour. To read again sooner, use
`bau results refresh --force`.

## Tell BAU what each video cost

BAU knows what every paid clip cost (`bau video clips` lists them). It doesn't know which
clips went into which video until you tell it, once per video:

```bash
bau results link youtube yt_ab12 --clips clip_1a2b3c,clip_4d5e6f --episode kids-channel/ep-001
```

- `yt_ab12` is the video's id in the publish queue (shown by `bau results`).
- `--clips` lists the studio clips the video used. Profit is the earnings minus what
  those clips cost.
- `--episode` ties the video to its episode, so BAU knows its story format and can compare
  formats.

Until a video is linked, its cost and profit show as "—". The panel also shows how much
clip spending isn't linked to any video yet.

## What the numbers mean

| Word | Meaning |
|---|---|
| views | how many times the video was watched |
| watched | on YouTube, how much of the video people watched on average (more is better) |
| earned | YouTube's **estimate** of your share of the ad money. YouTube adjusts it at the end of each month; what is actually paid out goes in the ledger (`bau economics`) |
| clips | what the paid clips in this video cost |
| profit | earned minus clips; "—" until both are known |

## Things to know

- **Earnings need the YouTube Partner Program.** Until your channel is accepted, YouTube
  reports no earnings and BAU shows "—". YouTube also doesn't pay for mass-produced,
  look-alike videos, which is why the series engine warns about sameness.
- **Made-for-kids videos earn less per view.** YouTube shows no personalised ads on them.
  The tracker shows the real figure for your channel.
- **TikTok doesn't report earnings through its API.** TikTok videos show views, likes,
  comments and shares. Check earnings in the TikTok app and record payouts in the ledger.
- Estimates are not promises: BAU reports what the platforms say, nothing more.
