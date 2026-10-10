# BAU test drive (GitHub Codespaces)

This Codespace is for **trying and testing** BAU. GitHub's terms do not allow
hosting a production-facing application in Codespaces, so the real business runs
on the laptop installed from the two USB sticks (see `docs/INSTALL.md`; ready-made
images are on the repository's **Releases** page).

Mission Control opens automatically on port 8765 (the *Ports* tab, "Mission
Control"). Jarvis uses port 8766. Both ports are private to your GitHub account by
default - keep it that way.

**Full model for free:** follow `docs/CLOUD-TEST.md` - a free Z.ai key saved as the
Codespaces secret `ZAI_API_KEY`, then `bau models bench glm-4.7-flash-zai`, approve it,
and `bau jarvis --no-browser`. Works from a computer or an iPhone.

**Claude Code is installed:** type `claude` in the terminal and sign in with your Claude
account (it shows a link to open). It works from any computer or phone, right next to BAU.
The codespace also has an SSH server, so `gh codespace ssh` can run checks from another
computer, only through GitHub's tunnel with your login.

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
Do not put real customer data or approval keys in a Codespace. API keys only through
GitHub's Codespaces secrets (never in a file in the repository).
Free accounts get 120 core-hours a month (about 60 hours on this 2-core machine); stop the Codespace when you are done
(it also stops itself when idle).
