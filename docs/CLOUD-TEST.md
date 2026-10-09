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

Z.ai sells a monthly **GLM Coding Plan** (from about $18/month). **You don't need it: don't
buy it.** The free part is their pay-per-use **API**, where GLM-4.7-Flash costs $0.

1. Go to **z.ai**, create an account (email) and sign in.
2. Go straight to **z.ai/manage-apikey/apikey-list** (or your picture, top right >
   **API Keys**). Click **Create API Key** and copy it. It looks like a long line of
   letters and numbers. Keep it private, like a password.
3. No payment or balance is needed for GLM-4.7-Flash. If the page asks you to pay before
   it makes a key, stop: the model is no longer free there.

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

If it says **busy** or **overloaded**, Z.ai's free service is crowded. BAU already waits and
tries again for about a minute and a half; if it still gives up, run the bench again in a few
minutes. (On the first real test, 7 October 2026, it took about five minutes to get through.)
If it says **refused (HTTP 401)**, the key is wrong: check the secret.

## 5. Talk to Jarvis

In the terminal:

```bash
bau jarvis --no-browser
```

Jarvis prints a private link starting with `https://...-8766.app.github.dev/?k=`. Open it
(click it on a computer; on the phone, open the **Ports** tab and tap the globe next to
**Jarvis**, or copy the link). Tap to wake Jarvis, then talk or type. Confirmations
appear in the terminal and in the page: they're yours to make.

Around Jarvis are the parts of your business, each a dot you can click: the team on the
left (Chief of staff, Producer, Publisher, Strategist, Researcher, Compliance, Finance,
Watchdog), BAU's own systems on the right (Models, Memory, Audit), and outside connections
further out (YouTube, TikTok; Email, Drive, Calendar and CRM are not connected yet). Green
means checked and fine, amber means something waits for you, red means broken or missing,
dashed means not connected. Every colour comes from BAU's real records; nothing is green
just to look good.

Click **Producer** to walk an episode without the terminal: **Draft step 01** has the model
write it; **Read & check step 01** shows you the draft and waits for your **Confirm**. Only
your click checks a step; Jarvis can't. Approving a model stays a typed command on purpose
(the Models panel shows it, click to copy). **LOG** at the top shows the conversation.

What else is on the screen:

- **Work shows live.** While Jarvis drafts, Scout searches or a model is tested, that dot
  spins violet, its lines run fast, and its panel lists each step as it happens.
- **Panels you work in.**
  - **Producer:** **Read / edit** opens the draft in the panel and you save your changes
    there. Saving a checked step undoes its check, so you check it again. You can write the
    review step (06) there too.
  - **Scout:** type what you're looking for and press **Search**. You get one card per
    project, **Report** for the full write-up, and **Inspect safely** to download one into
    quarantine and scan it.
  - **Models:** **Test** runs the same check as `bau models bench`. Approving still happens
    in the terminal.
- **TIMELINE** lists everything that happened today, newest first: drafts, checks,
  searches, waits and confirmations. It comes from BAU's tamper-evident record, and each line
  has its record number.
- **MISSION CONTROL** opens the Mission Control data in the same screen: status, missions,
  jobs, regulations, legal queue, money, Watchdog, incidents and the Second Brain. The
  separate page on port 8765 still works.
- **On the phone** the dots stay in a ring round Jarvis. Pinch to zoom, and swipe a panel
  left or right to move to the next part.
- **WAKE WORD** is off every time you open the page. Turn it on and the page listens, in
  that tab only, for "Jarvis" followed by your question. It stops when you leave the page.
  It needs a browser with speech recognition (Chrome or Edge; Safari support varies).
- **ALERTS** asks your permission once. After that, the page shows a notification when
  something needs you while it's in the background. On an iPhone, alerts only work after you
  add the page to your Home Screen. Nothing is sent anywhere else.
- **LIGHT/DARK**, zoom (`+`, `-`, `0`), and a key for every button. Press `?` for the list.
- **VOICE · chat** (bottom left) switches between Jarvis speaking his answers and text
  only. While he speaks, **SPEAKING · TAP TO STOP** appears at the top. Tap it, or press
  `S`, to stop him.

**Mission Control** on its own is the **Ports** tab > **Mission Control** (port 8765).

## A second free model for when Z.ai is busy: NVIDIA

Z.ai's free service is often overloaded. NVIDIA runs **Nemotron 3 Super** free for testing,
and it answered in about a second when we tried it (2026-10-08). Approve both, and when
Z.ai is busy, NVIDIA answers the same question instead.

1. Get an NVIDIA key (skip this if you already have one): sign in at **build.nvidia.com**
   and open **build.nvidia.com/settings/api-keys** to create a key. Copy it.
2. Add it to your Codespaces secrets like the Z.ai key (step 2 above), named
   `NVIDIA_API_KEY`, with access to **linux-ai-biz**. Stop and start the codespace.
3. In the terminal, test it, and if it shows `"reply_ok": true`, approve it yourself:

   ```bash
   bau models bench nemotron-3-super-nim
   ```

   ```bash
   bau set-status model nemotron-3-super-nim APPROVED
   ```

4. Stop Jarvis (Ctrl+C) and start him again with `bau jarvis --no-browser`.

Z.ai answers first, and NVIDIA steps in when it's busy. When Jarvis starts, he says which
is which: `Jarvis is up (model glm-4.7-flash-zai, backup: nemotron-3-super-nim)`. On his
screen, the chip at the top shows the first choice and `+ 1 BACKUP`, and the log (**LOG**,
or press **L**) shows `via ...` under every answer, so you can see which model gave it.

To have NVIDIA answer first instead, with Z.ai as the backup, run this and restart Jarvis:

```bash
bau jarvis config --model nemotron-3-super-nim
```

**NVIDIA's rules (its API Trial terms, checked 2026-10-08):**

- **Testing only:** never for your real business.
- **No personal or confidential data:** you agree not to send any. So while the NVIDIA
  model is approved, Jarvis won't search your old chats (`docs/CHATS.md`), even as a backup.
  You can still search them yourself with `bau chats search`.
- NVIDIA doesn't keep what you send after each session, apart from security logs.

To switch it off again:

```bash
bau set-status model nemotron-3-super-nim REGISTERED
```

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
