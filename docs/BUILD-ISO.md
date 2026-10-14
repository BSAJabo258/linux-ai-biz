# Build the stick image yourself (no VS Code needed)

The stick image (`my-jarvis-<version>-amd64.iso`) holds everything: the live system,
the installer, BAU, llama.cpp and every package BAU needs, so a laptop installs with no
internet. Every change merged into `main` reaches the stick only after a new build.
There are two ways to build it. Neither needs VS Code.

## Way 1: one click on GitHub (easiest, any browser)

1. Open https://github.com/BSAJabo258/linux-ai-biz and sign in.
   On a phone: open the browser menu and tick **Desktop site** first.
2. Click **Actions**, then **build-live** on the left.
3. Click **Run workflow**, keep **Branch: main**, click the green **Run workflow**.
4. Wait about 40 minutes. A green tick means it is done.
5. Click **Releases** (right side of the repository's main page). The newest
   `live-v...` release has the `.iso` and a `.sha256` file. Download both.
6. Check the download on Windows, in PowerShell:

   ```powershell
   Get-FileHash "$HOME\Downloads\my-jarvis-0.1.0-amd64.iso" -Algorithm SHA256
   ```

   The long number must match the one in the `.sha256` file and on the release page.
   If it doesn't, download again.
7. Write it to the stick with balenaEtcher (or Rufus in **DD Image mode**), as in
   [LIVE-USB.md](LIVE-USB.md).

## Way 2: on your Windows computer (no GitHub needed to build)

Slower (about an hour) and needs about 15 GB of free disk. The build runs inside
Linux on Windows (WSL) with Docker.

1. **Linux on Windows.** Open PowerShell **as administrator** and type:

   ```powershell
   wsl --install -d Debian
   ```

   Restart when asked. Debian opens and asks for a new Linux user name and password
   (only for this Linux; write them down).
2. **Docker.** Install **Docker Desktop** from docker.com. In Docker Desktop:
   **Settings > Resources > WSL integration**, switch on **Debian**, **Apply & restart**.
3. **The build.** Open **Debian** from the Start menu and type, one line at a time:

   ```bash
   sudo apt update && sudo apt install -y git python3-venv python3-pip
   git clone https://github.com/BSAJabo258/linux-ai-biz.git
   cd linux-ai-biz
   python3 -m venv .venv && . .venv/bin/activate
   python3 -m pip install -e '.[dev]'
   bash image/build-live.sh --out ~/dist
   ```

   It runs BAU's tests first, then builds. Near the end, a line
   `[bau] built /home/<you>/dist/my-jarvis-...-amd64.iso` means it worked.
4. **Find the image.** In File Explorer, type `\\wsl$\Debian\home\` in the address bar,
   open your Linux user name, then `dist`. Check it with `Get-FileHash` as in Way 1.

Next time, only the last steps are needed:

```bash
cd linux-ai-biz && git pull && . .venv/bin/activate && bash image/build-live.sh --out ~/dist
```

## Make BAU stronger from any terminal

An instruction file in the repository tells any AI coding agent how to grow BAU safely:
question itself first, find proven open-source projects, inspect and test them in a
sandbox, show you the evidence, and add a project only after **you** say yes, then get the
stick rebuilt. It is `.claude/skills/grow-bau/SKILL.md`.

- **Claude Code** (Windows Terminal, the Debian window above, or claude.ai/code):

  ```bash
  cd linux-ai-biz
  claude
  ```

  then type `/grow-bau`, and say what you want, for example
  `/grow-bau cut what I spend on tokens`.
- **Any other agent** (Codex, Gemini CLI, Aider): start it in the `linux-ai-biz` folder
  and paste:

  ```text
  Read .claude/skills/grow-bau/SKILL.md and CLAUDE.md, then follow the skill step by
  step for this job: <what you want>. Stop and ask me at step 5.
  ```

Useful commands on their own:

- `bau scout shortlist`: what this week's open-source watch found worth testing.
- `bau toolbox ask "what you need"`: the researched tools for a job.
- `bau toolbox map`: what Jarvis can do today, and the gaps.
