# Her social accounts

Your ask (2026-11-20): Jarvis prepares every account so it is ready to use. You do only the
human step on the platform's own page (the email or phone code). Platforms forbid accounts
made by software and close them, and her traffic would go with them.

## One account, start to finish (about 2 minutes)

```bash
bau accounts prepare reddit --email her-business-email@example.com
```

It prints, ready to paste: the sign-up page, her display name, handle ideas that fit that
platform, a strong password, her bio with the AI label, the link for that platform and a
safe-for-work profile picture (her face, age-checked). Sign up, type the code the platform
sends you, then:

```bash
bau accounts created reddit --handle THE_HANDLE_IT_GOT
```

Do the same for `x`, `instagram` and `tiktok`.

## Where each link goes (Fanvue's own advice, read 2026-11-20)

| Platform | Adult content | Link in the bio |
|---|---|---|
| Reddit | allowed | her Fanvue tracking link (`fv-1`) |
| X | allowed | her Fanvue tracking link (`fv-2`) |
| Instagram | not allowed | a link page (Linktree-style) that links to Fanvue (`fv-3`) |
| TikTok | not allowed | her Instagram |

Never put a bare Fanvue link in a caption or comment: Fanvue warns it can get the account
suspended. `bau fanvue links` shows clicks, new subscribers and money per link.

## The passwords

They are in one env file BAU reads, `/var/lib/bau/secrets/accounts.env` (your login and BAU
only), never in the repo, never on Jarvis's screen or in a log. `bau accounts password
reddit` shows one at a terminal; `bau accounts list` shows every account without passwords.

## Checked and not checked

Fanvue's guides and TikTok's AI-label rule were read on 2026-11-20. Reddit's, X's and
Instagram's own rule pages refused to load for an automatic reader that day: read their
rules once yourself before her first post there.
