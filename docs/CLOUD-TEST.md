# Test drive in the cloud, free, from your computer or iPhone

Your own PC doesn't need to be powerful for this. Two free services do the heavy lifting:

- **GitHub Codespaces** is a computer in the cloud that runs BAU: Mission Control, the
  Governor and Jarvis. A free GitHub account includes about 60 hours a month on the
  default 2-core machine. It switches itself off when idle.
- **Z.ai** runs the full **GLM-4.7-Flash** model for free (checked 2026-10-07, listed
  as "Free" on docs.z.ai). Jarvis sends his questions to it over the internet.

Everything opens in a web browser, so it works the same on Windows, a Mac or Safari on
an iPhone.

**Privacy.** With Z.ai, what you say to Jarvis and his status summaries go to Z.ai's
servers (a company in Singapore). Their API terms say this content is processed and not
stored; they don't say either way whether it's used for training. That's fine for
testing. Don't put real customer data, passwords or approval keys into a test drive.

## 1. Get your free Z.ai key (once)

1. Go to **z.ai**, create an account and sign in.
2. Open **API Keys** (in your account menu), create a key and copy it. It looks like a
   long line of letters and numbers. Keep it private, like a password.

## 2. Give the key to your Codespace (once)

The key goes into GitHub's secret store, never into the repository:

1. On github.com: your picture (top right) > **Settings** > **Codespaces** >
   **Secrets** > **New secret**.
2. Name: `ZAI_API_KEY`. Value: paste the key. Repository access: choose
   **linux-ai-biz**. Click **Add secret**.

## 3. Start the cloud computer

1. Open the repository on github.com, click the green **Code** button > **Codespaces** >
   **Create codespace on main** (or open the one you already have).
2. Wait for it to finish setting up (a few minutes the first time). Mission Control
   opens by itself in a new tab.

On an **iPhone**: open github.com in Safari and sign in. If you use Microsoft Authenticator
for GitHub's two-step sign-in, approve it there. Then go to the repository > **Code** >
**Codespaces** and open your codespace. Turn the phone sideways for more room.

## 4. Switch on the full model (once per codespace)

In the codespace's **Terminal** (bottom panel; menu > Terminal > New Terminal), type:

```bash
bau models bench glm-4.7-flash-zai
```

BAU checks that the model really answers and can use a tool. If it shows
`"reply_ok": true`, approve it yourself:

```bash
bau set-status model glm-4.7-flash-zai APPROVED
```

## 5. Talk to Jarvis

In the terminal:

```bash
bau jarvis --no-browser
```

Jarvis prints a private link starting with `https://...-8766.app.github.dev/?k=`. Open it
(click it on a computer; on the phone, open the **Ports** tab and tap the globe next to
**Jarvis**, or copy the link). Tap to wake Jarvis, then talk or type. Confirmations
appear in the terminal and in the page: they're yours to make.

**Mission Control** is the **Ports** tab > **Mission Control** (port 8765).

## Who can open these links

Both ports are **private**: GitHub only opens them for you, signed in to your account. In
the Ports tab, leave their visibility on *Private*. Don't change it to *Public*. Jarvis's
link also carries a one-time key, and Jarvis only answers his own page.

## When you're done

Click your codespace's name (bottom left) > **Stop Current Codespace**, or just close it:
it stops by itself after 30 minutes idle. Stopped codespaces don't use your free hours.
Your BAU state stays in the codespace until you delete it.

## The same model elsewhere

The free Z.ai model works anywhere BAU runs, if the key is there:

- **Docker test drive:** add `ZAI_API_KEY=...` to the `.env` file next to
  `docker-compose.yml`.
- **Laptop or live USB:** `sudo sh -c 'echo ZAI_API_KEY=... >> /etc/bau/models.env'`.

Then bench and approve it as in step 4. Jarvis uses it when Claude isn't approved, and
before the small local model.
