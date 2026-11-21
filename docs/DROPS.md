# Weekly drops

A drop is one locked message to many fans at once. Once a week Jarvis puts two on cards:

| Drop | Who gets it | What they see |
|---|---|---|
| Subscribers | Everyone subscribed to her | One picture free (a level 1 picture you accepted, no nudity), and a level 2 picture locked behind it at your nude price |
| VIPs | Fanvue's "Spent more than $50" list | A level 3 picture you accepted, locked at your xxx price |

Each card shows the picture, the price and her message. It needs a click (no voice):

- **Accept** sends it once on Fanvue. The card then says how many fans it went to.
- **Not now** skips it. Next week's drop comes with the same or newer pictures.

## Where the pictures come from

Only pictures you already accepted for Fanvue (on their "New picture for Fanvue" cards). A
drop prefers one not posted on her feed yet. A picture sold in one drop is never used in
another.

No drop comes while any of these is true, and none of them gets its own card:

- there is no accepted picture of the right level yet (levels 2 and 3 need the explicit
  pictures set up, `docs/PICTURES.md`);
- your price for that level is not set (the "Set your Fanvue prices" card);
- Fanvue is not connected;
- BAU is on HOLD.

## Checks on every send

When you press Accept, everything is checked again:

- each picture's age check and its fingerprint (a changed file stops the drop);
- the text, against the same rules as fan chat (no claim to be human, nothing off Fanvue, no
  invented urgency, nothing about minors);
- Fanvue's $3.00 minimum;
- HOLD.

Each drop goes to Fanvue with its own retry key, so a retry can never send it twice. What
fans pay for drops comes into the money ledger with the rest of her Fanvue earnings.

## Fanvue's rules this follows

Fanvue's API (read 2026-11-21) lets a creator send one message to a smart list, with a free
preview picture and the rest locked at a price of $3.00 or more. The facts and their pages are
at the top of `src/bau/drops.py`. Behind the paywall, sheer and nude pictures are allowed for
fans who opted in; her public profile stays opaque (`docs/FANVUE.md`).
