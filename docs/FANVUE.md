# Fanvue: posting Aria's pictures and counting her money

Built 2026-11-03 from Fanvue's own developer pages (api.fanvue.com/docs, read the same day).
Tested against a fake Fanvue only. It has **not run against your real Fanvue account yet**.

## What it does

1. Jarvis (or you) queues one of Aria's pictures with its caption. The picture must be one
   BAU drew on your desktop (`bau creator draw`) and that passed the age check. BAU adds the
   AI label to every caption, because Fanvue's rules and BAU's both require it. A caption that
   refers to minors is refused.
2. Jarvis puts the post on your screen as a card: the picture, the caption and the level.
3. You pick **who sees it** (subscribers only, or followers and subscribers). Nothing is
   picked for you. Press **Accept**.
4. Only then does BAU upload the picture to Fanvue and post it. Each post goes up once.
5. When you ask Jarvis about money, he first brings in what Fanvue earned (at most once an
   hour). Every sale is counted once. Refunds and chargebacks are taken off. Fanvue's cut is
   kept apart, so you can see what you keep.

Levels 0 (free teaser) and 1 (subscribers, no nudity) for now. Levels 2 and 3 come once BAU
can draw their pictures.

## Let Jarvis post on his own (your switch)

Your choice (2026-11-03): once Fanvue is connected, a card asks **"Let Jarvis post to Fanvue on
his own"**. You pick who sees the posts and how many a day (1 to 10). Nothing is picked for
you. After that, every 30 minutes the autopilot posts the oldest queued post, until your
number for the day is reached. No click per post.

Every check still runs on every post: the age check, the AI label, no minors, a picture that
changed. If one fails, autopost stops for the rest of the day; `bau fanvue queue --all` shows
which post and why. HOLD stops it at once.

```bash
bau fanvue autopost off                                            # back to Accept per post
bau fanvue autopost on --audience subscribers --per-day 3          # or set it in a terminal
```

## Set it up once

Fanvue gives out no API keys. Every app signs in through Fanvue's own Allow page. So:

1. On Fanvue, open the **Developer Area** and create an app. On its **Authentication** tab, add
   this redirect address exactly:

   ```
   http://127.0.0.1:3456/callback
   ```

   Turn on these scopes: `read:self`, `read:media`, `write:media`, `write:creator`,
   `write:post`, `read:insights`.

   Not known yet: Fanvue's pages do not say whether they accept a `127.0.0.1` address. If
   the Authentication tab refuses it, tell me what it says.
2. Put the app's Client ID and Client Secret into your keys file on your other computer as
   `FANVUE_CLIENT_ID` and `FANVUE_CLIENT_SECRET`, then bring them in with
   `bau keys import` (docs/KEYS.md). Never paste them into a chat.
3. Jarvis then shows a **Connect Fanvue** card. Press Accept: a terminal opens, then Fanvue
   opens in the browser. Sign in and press **Allow**. Or, in a terminal:

   ```bash
   bau fanvue login
   ```

## By hand

```bash
bau fanvue add NAME.png --caption "Evening in" --level 1    # queue a picture
bau fanvue queue                                            # what is waiting
bau fanvue sync                                             # bring in the earnings now
bau fanvue logout                                           # forget the Fanvue login
```

Posting itself is always the card in Jarvis and your Accept.

## What it never does

- It never posts without your Accept, and never twice.
- It never picks the audience for you.
- It never posts while BAU is on HOLD, or a picture that changed after it was queued.
- It never posts a picture that has no age check or no provenance record.
- It keeps the Fanvue login in `BAU_HOME/secrets/fanvue.json`, readable only by you.

## Fanvue facts used (read 2026-11-03 on api.fanvue.com/docs)

- Sign-in: OAuth with PKCE. There are no API keys. Login tokens are short-lived and renew
  themselves, and each renewal replaces the old one.
- A post's text can be up to 5000 characters. The audience is `subscribers` or
  `followers-and-subscribers`. Paid posts are priced in cents, $3.00 at least.
- Pictures upload in parts, and Fanvue processes them before a post can use them.
- Earnings are reported in US cents, with refunds and chargebacks as negative rows.
- The limit is 200 requests a minute. BAU waits and tries again when Fanvue says "too many".
- The API has no field for an AI label. Fanvue's help pages (read 2026-11-01) require AI
  content to be disclosed in the bio, a caption or a watermark, so BAU puts it in every
  caption.
