# BAU test drive with Docker

Run the whole BAU system on your own computer (Windows, Mac or Linux) before you touch the
laptop: Mission Control, the Governor, Jarvis and an optional free local AI model.

This is a **test drive**. The laptop install from the two USB sticks is still the real
thing: it adds disk encryption, the firewall, AppArmor and the services that start at boot.

## 1. Install Docker

Install **Docker Desktop** (docker.com) on Windows or Mac, or Docker Engine on Linux. On
Windows, let it use WSL 2 when it asks.

## 2. Start BAU

Open a terminal in this repository's folder (download it from GitHub, *Code > Download
ZIP*, and unzip it) and run:

```bash
docker compose up -d --build
```

Then open **http://localhost:8765** for Mission Control. The Governor checks the system
every 10 minutes in the background.

## 3. Talk to Jarvis

```bash
docker compose run --rm --service-ports jarvis
```

It prints a private link (`http://127.0.0.1:8766/?k=...`). Open it, tap to wake Jarvis,
and talk or type. Jarvis runs in your terminal on purpose: confirmations are yours, so he
only starts for a person at a keyboard. Press Ctrl+C to stop him.

## 4. Give Jarvis a brain

Without a model, Jarvis works in basic mode (briefing and core commands). Pick one:

**Claude (best).** Create a file called `.env` in this folder:

```
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=...        # optional: the ElevenLabs voice
```

Then approve the model once:

```bash
docker compose run --rm ui bau set-status model claude-opus-5-5 APPROVED
```

**Free and private: GLM-4.7-Flash on your own computer.** This needs about **24 GB of
RAM** and an 18 GB download the first time. Nothing leaves your machine.

```bash
docker compose --profile glm up -d llm                    # downloads the model, then serves it
docker compose logs -f llm                                # wait for "server is listening"
docker compose run --rm ui bau models bench glm-4.7-flash # BAU checks it really answers
docker compose run --rm ui bau set-status model glm-4.7-flash APPROVED
```

With 16 GB of RAM, use the smaller file instead (about 14 GB): put
`BAU_LLM_HF=unsloth/GLM-4.7-Flash-GGUF:UD-Q3_K_XL` in `.env` before starting `llm`.

Jarvis uses Claude when it's approved and reachable, then GLM, then basic mode.
(GLM-5.3-Flash is a 320-billion-parameter model: even compressed it is about 93 GB,
which is beyond a laptop.)

## 5. Become the approver (optional)

Money, commercial email and legal steps need your signed approval, as on the laptop:

```bash
docker compose run --rm ui bau-approver-setup     # choose a passphrase
docker compose run --rm ui bau selftest           # everything should read "ok" or "laptop only"
```

## Useful commands

```bash
docker compose run --rm ui bau status --brief     # what Mission Control shows, as text
docker compose run --rm ui bau publish platforms  # where BAU can publish
docker compose logs -f governor                   # what the watchdog is doing
docker compose down                               # stop (your data is kept)
docker compose down -v                            # stop and delete all test data
```

Your data lives in Docker volumes (`bau-home`, `models`), not in this folder.

## Troubleshooting

- **Port already in use:** another program uses 8765 or 8766. Stop it, or change the
  left-hand port in `docker-compose.yml`.
- **"Too Many Requests" while building:** Docker Hub is rate-limiting your network. Run
  `docker compose build --build-arg BASE=mirror.gcr.io/library/debian:trixie-slim`.
- **Behind a company proxy that inspects HTTPS:**
  `docker build --secret id=extra_ca,src=/path/to/proxy-ca.pem -t bau:local .`
- **GLM is slow:** that's the CPU doing the work. A GPU, or Claude, is faster. Jarvis
  keeps GLM's long "thinking" mode off so spoken replies stay quick.
