# BAU on your own cloud server (DigitalOcean)

A codespace can be deleted, and everything in it goes with it. Your own cloud server keeps
BAU, Jarvis, his memory and your files running day and night, until you delete it. This
guide sets one up on **DigitalOcean** with **Debian 13**, about 30 minutes in all.

How it stays safe:
- **One way in.** The only way into the server is SSH with *your* key: no passwords, no
  root login.
- **Nothing on the open internet.** Jarvis and Mission Control can't be reached from the
  internet at all. You open them through a private tunnel from your own computer.
- **Everything else stays closed.** BAU's firewall blocks every other connection. This is
  the one exception to BAU's "no open ports" rule: a cloud server has no other way in. It
  is recorded in the server's audit record (`install.cloud`).

## What it costs

Prices from DigitalOcean's pricing page on 2026-10-10 (check the create screen; they
change):

| Size (Basic, Regular) | Monthly | Good for |
|---|---|---|
| 4 GB, 2 CPUs | $24 | BAU and Jarvis with hosted models (Z.ai, Claude) - tight |
| **8 GB, 4 CPUs** | **$48** | **Recommended: BAU, Jarvis, video tools, room to spare** |
| 16 GB, 8 CPUs | $96 | also a small local model (slow without a GPU) |

**Backups** cost 20% more for weekly or 30% for daily (weekly on the 8 GB size: $9.60 a
month). Turn them on: they are what saves you if something breaks. You pay by the hour
until you **destroy** the server; switching it off does not stop the bill.

## 1. Make your SSH key (once, on your Windows PC)

Open **PowerShell** and run:

```powershell
ssh-keygen -t ed25519 -C "my-bau-server"
```

Press Enter to accept the place it saves to, then choose a passphrase you will remember.
Then show the public half, which is safe to share:

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub
```

Copy the whole line it prints (it starts with `ssh-ed25519`). Never share the file
without `.pub` - that is your private key.

## 2. Create the server

1. Sign up at **digitalocean.com** and add a payment method.
2. Click **Create > Droplets**.
3. **Region:** the one closest to you.
4. **Image:** **Debian**, version **13**.
5. **Size:** **Basic**, **Regular**, **8 GB / 4 CPUs** (or your choice from the table).
6. **Authentication:** **SSH Key** > **Add SSH Key**, paste the line from step 1, name it.
7. **Backups:** turn on (weekly is fine).
8. Open **Additional Options**, turn on **Startup scripts** ("User data"), and paste
   the whole of this file from the repository:
   [`installer/cloud/cloud-init.yaml`](../installer/cloud/cloud-init.yaml)
9. **Hostname:** `bau`. Click **Create Droplet** and copy its **IP address** when it
   appears.

Give it about 5 minutes. The startup script downloads BAU, creates your login
`bauadmin`, locks SSH to your key, and prepares the install.

## 3. Install BAU (one command)

In PowerShell (put your server's IP in place of `YOUR_SERVER_IP`):

```powershell
ssh bauadmin@YOUR_SERVER_IP
```

Type `yes` the first time. You should see "BAU is ready to install". Then run:

```bash
sudo bash ~/bau/BAU-PAYLOAD/install.sh --cloud
```

It asks for three things - choose them yourself and keep them safe:
1. a **passphrase for your approval key** (twice). This key signs money, legal and email
   approvals, and only you have it;
2. a **sudo password** for `bauadmin` (twice), needed for upgrades later.

When it says `done`, log out (`exit`) and log back in, then check:

```bash
bau status
```

**If `ssh bauadmin@...` is refused after 10 minutes**, the startup script didn't run (on
DigitalOcean it is only promised for Ubuntu and CentOS images). Log in once as root and
start it by hand:

```bash
ssh root@YOUR_SERVER_IP
apt-get update && apt-get install -y git
git clone --depth 1 https://github.com/BSAJabo258/linux-ai-biz /opt/bau-src
bash /opt/bau-src/installer/cloud/prepare.sh bauadmin
exit
```

Then continue with `ssh bauadmin@YOUR_SERVER_IP` above. After this, root login is off.

## 4. Give Jarvis his model keys

Keys go in one file on the server that only you and BAU can read:

```bash
sudo install -m 0640 -o root -g bau /dev/null /etc/bau/models.env
sudo nano /etc/bau/models.env
```

Add the lines you use, for example:

```
ZAI_API_KEY=your-zai-key
HIGGSFIELD_API_KEY_ID=your-id
HIGGSFIELD_API_KEY_SECRET=your-secret
```

Save with Ctrl+O, Enter, Ctrl+X. Then approve and test the model as before
(`docs/CLOUD-TEST.md`), and restart Jarvis so he picks up the keys:

```bash
bau models bench glm-4.7-flash-zai
sudo systemctl restart bau-jarvis
```

## 5. Open Jarvis (every time)

Jarvis runs on the server all the time. To open him, make the private tunnel from your
PC and keep that PowerShell window open:

```powershell
ssh -L 8766:127.0.0.1:8766 -L 8765:127.0.0.1:8765 bauadmin@YOUR_SERVER_IP
```

In that window, get his address (it holds your private key, so don't share it):

```bash
bau jarvis url
```

Open the `http://127.0.0.1:8766/?k=...` address it shows in your browser. Mission Control
is at `http://127.0.0.1:8765`. Closing the window closes the tunnel; Jarvis keeps running
on the server.

**From your iPhone:** an SSH app that can forward ports (for example Termius) does the
same tunnel; then open the same address in Safari.

## 6. Bring your data from a codespace

If your old codespace still exists (check **github.com/codespaces**), open its terminal
and pack Jarvis's memory and the transcript files:

```bash
tar czf ~/bau-move.tgz -C /workspaces .bau-home -C /workspaces/linux-ai-biz linktranscript_studio
```

Download `bau-move.tgz` (right-click it in the file list > Download), then copy it to the
server from PowerShell with `scp bau-move.tgz bauadmin@YOUR_SERVER_IP:` and ask Claude to
help you merge it in. Don't delete the codespace until the copy is safely on the server.

## Backups and upgrades

- **Backups:** DigitalOcean's backups (step 2) copy the whole server. You can also take a
  **Snapshot** before big changes (Droplet > Snapshots).
- **Upgrades:** Debian security updates install themselves. To upgrade BAU:
  ```bash
  cd /opt/bau-src && sudo git pull
  sudo bash installer/make-payload.sh --skip-tests --out ~/bau
  sudo bash ~/bau/BAU-PAYLOAD/install.sh
  ```
  The server remembers it is a cloud install, so SSH stays open.

## What this does not do

- **Disk encryption:** BAU does not encrypt the server's disk the way it encrypts the
  laptop's. Your keys and data live on DigitalOcean's hardware, so keep personal data you
  don't need off the server.
- **Running a big local AI model:** that needs a GPU server, which costs far more. Jarvis
  thinks with hosted models (Z.ai, Claude) here.
