# BAU test drive (GitHub Codespaces)

This Codespace is for **trying and testing** BAU. GitHub's terms do not allow
hosting a production-facing application in Codespaces, so the real business runs
on the laptop installed from the two USB sticks (see `docs/INSTALL.md`; ready-made
images are on the repository's **Releases** page).

Mission Control opens automatically on port 8765 (the *Ports* tab, "Mission
Control"). The port is private to your GitHub account by default - keep it that way.

Try:

```bash
bau status                         # what is still needed before production
bau brain say "Content team runs TikTok publishing which consumes scripts, music and produces videos"
bau brain lint                     # what is not automatable yet
bau mission types
bau governor tick --no-resume
bau gateway                        # every capability an agent can ask for
```

State lives in `/workspaces/.bau-home` (outside the repository, never committed).
Do not put real customer data, API keys or approval keys in a Codespace.
Free accounts get 120 core-hours a month; stop the Codespace when you are done
(it also stops itself when idle).
