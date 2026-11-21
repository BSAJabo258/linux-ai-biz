# The watch

Every 10 minutes the Governor (BAU's watchdog, `bau-governor.timer`) checks the computer the
way an uptime monitor checks a website. Anything that breaks pops up in Jarvis as a card
with its fix.

## What it watches

| What | When it pops up |
|---|---|
| The money machine, link by link (the same links as `bau money`): her profile, the boss model, the picture maker, her face lock, the Fanvue keys and sign-in, fan chat's permissions, prices, the autopilot, autopost, HOLD | A link that **was working and stopped**. A link you never set up has its own setup card instead, so you are not told twice |
| Services: Jarvis, the picture maker, the local model, the autopilot timer, Mission Control, the rules watch | One that **failed** (`journalctl -u NAME` says why). One not installed on this computer is left alone |
| Disk | Less than 10% free |

The card says what broke, what was found and the exact fix, for example
`sudo systemctl start bau-pictures.service`.

- **Accept:** you've seen it. It pops up again only if it gets fixed and then breaks again.
- **Not now:** it comes back later.

The Governor's other findings (jobs, missions, spending, rule reviews, the install
checklist) stay in its night report, so the cards are only for breakdowns.

On the laptop station the money links are not watched: the work runs on the desktop.
