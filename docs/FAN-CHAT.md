# Fan chat: she answers her fans on Fanvue

Your ask (2026-11-20): she talks to fans, flirts, talks dirty with adults who want it, and
sells your paid pictures. This is what Fanvue's own API is for, and Fanvue sells its own AI
chat to adult creators. Not yet tried on your real Fanvue account.

## Switch it on

1. Sign in to Fanvue once more, so Fanvue lets her read and answer chats:

   ```bash
   bau fanvue login
   ```

   `bau money` shows **fan chat (sign-in allows chat)** with a ✓ once that is done.
2. That's all. While Jarvis runs, every 3 minutes she reads new messages and writes a reply
   to each fan. The autopilot does the same every 30 minutes.
3. Each reply waits on a card in Jarvis and in the workstation's **Waiting for you**: you see
   what he wrote, her reply, and the picture she offers with its price. **Accept** sends it;
   **Not now** drops it.
4. When you like her replies, let her send them by herself:

   ```bash
   bau fanvue chat auto on      # off: back to your Accept
   ```

## What she does

- Answers in her own voice from her profile, remembers the last messages of the chat.
- Flirts, and talks dirty with a fan who wants it, inside her limits (`explicit_boundaries`).
- Offers a locked picture when it fits: only pictures you already accepted for Fanvue (level 2
  "nude" or level 3 "xxx"), at your prices from her profile. Each picture is offered to a fan
  once, and uploaded to Fanvue once.

## What she never does (every reply is checked, also with auto-send)

- Asked "are you AI?", "are you real?", "r u a bot?": she says yes, clearly, then carries on
  in character. Fanvue's rule; if the model forgets, BAU puts the yes in front.
- Never says she is a real or human woman.
- Nothing about anyone under 18 or age-play. If a fan writes something like "pretend you're
  16", she does not answer at all; you see it in `bau fanvue chat list --all`.
- No PayPal, Cash App, crypto, other apps or contact details; no meeting up.
- No made-up deadlines or "only 2 left".
- A fan who says he is broke gets kindness, never an offer.
- A fan who talks about harming himself: her reply waits for you, even with auto-send on.
- HOLD stops every reply.

## Commands

```bash
bau fanvue chat list            # replies waiting for you
bau fanvue chat list --all      # every reply: sent, dropped, refused and why
bau fanvue chat send fc_...     # send one
bau fanvue chat drop fc_...     # drop one
bau fanvue chat run             # read new messages now
bau fanvue links                # tracking links: clicks, new subscribers, money
bau fanvue links --add "Instagram bio" --platform instagram
bau fanvue welcome              # the welcome messages Fanvue sends now
bau fanvue welcome --trigger new_subscriber --text "Hi you, welcome to my private page..."
```

`bau fanvue welcome --text` shows the message and sets it only after you type `y`. Make one
tracking link per place you advertise; `bau fanvue links` then shows which place brings paying
fans.

## Facts used

Fanvue's API and rules were read 2026-11-20; the list with links is at the top of
`src/bau/fan_chat.py` and in `examples/platform-fanvue.yaml`. Fanvue's acceptable use policy
also bans "bots" and "automated scripts" without saying whether its own API is meant; Fanvue
publishes the chat API and sells AI chat itself.
