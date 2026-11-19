# Platform integrations: one table, one sign-in system

Every outside platform BAU works with, its real connection state, and what is still yours to
do. One command shows it, read live, with no secrets:

```bash
bau platform status            # every platform, from this computer's own records
bau platform status --check    # also asks each signed-in platform who the account is
```

## What the statuses mean

| Status | Meaning |
|---|---|
| **LIVE-VERIFIED** | the platform itself answered just now (`--check`) and named the account |
| **CONNECTED** | signed in on this computer; the platform was not asked this time |
| **OWNER-ACTION-REQUIRED** | something only you can do first: app keys, signing in, an approval |
| **BLOCKED** | signed in, but the sign-in cannot be read or the platform refused the check; the row says why and how to fix it |
| **NOT IMPLEMENTED** | planned; BAU has no adapter for it yet |

App keys on their own never count as connected.

## Where each platform stands (2026-11-19)

| Platform | What BAU can do | Still needed | Status today |
|---|---|---|---|
| Fanvue | sign in, upload pictures, post (your Accept or autopost), bring in earnings | your app keys (`sudo bau keys set FANVUE_CLIENT_ID FANVUE_CLIENT_SECRET`), then sign in from the **Connect Fanvue** card or `bau fanvue login` | not live-verified from here; see [FANVUE.md](FANVUE.md) |
| TikTok | sign in, upload video, post (your Accept), video stats | your app keys, then `bau tiktok login`; every post stays private until TikTok audits the app (TikTok's rule, read 2026-10-05) | not live-verified |
| YouTube, Instagram, Facebook, X, Threads | nothing yet | an adapter, built only after its official API facts are checked (`.claude/skills/platform-facts/`) | not implemented |

## One sign-in system for every platform

Every platform's sign-in goes through the same pieces, so the next platform does not need its
own way of connecting:

- **One credential store** (`src/bau/credentials.py`): `BAU_HOME/secrets/<platform>.json`,
  shared by your login, Jarvis and the autopilot through the `bau` group, never anyone else.
  One lock around every refresh, so a one-use refresh token is spent once. Tokens are never
  printed or logged.
- **One way to connect from Jarvis** (`setup_steps.connect_in_jarvis`): the card runs the
  same sign-in code as the terminal and opens the platform's page; the answer comes back to
  this computer.
- **One status** (`bau platform status`): read from that store, so the terminal, Jarvis,
  `bau money` and the setup cards always agree.
- **The policy record** (`bau platform add`): each platform's rules (AI label, content,
  automation) with the date they were checked; posting is refused when it is missing or
  older than 90 days.
- **The gateway and the audit chain**: every post or upload is a tool call checked by the
  Universal Gateway and written to the audit chain; posting stays your Accept (or autopost,
  which only you switch on).

## Adding the next platform

1. Read its official API pages and record the facts with the date in the new module's
   docstring and an `examples/platform-*.yaml` policy record (the platform-facts skill).
2. Keep its sign-in in `credentials.Store("<platform>")`, and renew tokens inside
   `refresh_lock()`.
3. Give it a status row in `platforms.connections` and its capabilities in
   `platforms.CAPABILITIES`, with a `--check` call that asks the platform who the account is.
4. A posting adapter registered in `publishing.ADAPTERS`, so posting is a card you Accept.
5. Tests with fakes, never real keys, and a plant check that a missing sign-in is never
   shown as connected.

Creating accounts on a platform, accepting its terms, and phone or identity checks are always
yours. BAU can prepare the details and the checklist; it never creates an account by itself
or gets around a verification step.
