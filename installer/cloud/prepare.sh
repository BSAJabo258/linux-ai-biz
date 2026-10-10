#!/usr/bin/env bash
# Prepare a new cloud server (DigitalOcean droplet, Debian 13) for BAU. Run once as root,
# normally by cloud-init.yaml when the droplet is created (docs/CLOUD-VM.md):
#
#   bash prepare.sh [ADMIN_NAME]        (default: bauadmin)
#
# It makes the owner's own admin login from the SSH key given to the droplet, turns off
# passwords and root login for SSH, and builds the BAU install files in the admin's home.
# The install itself (install.sh --cloud) is run by the owner over SSH: it asks for the
# approval-key passphrase and a sudo password, which only a person should choose.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "${HERE}/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "${SRC}/installer/lib/common.sh"
export BAU_LOG=/var/log/bau-prepare.log

ADMIN="${1:-bauadmin}"
[[ "${ADMIN}" =~ ^[a-z][a-z0-9_-]{1,30}$ ]] || die "admin name must be lowercase letters/digits"
require_root
# shellcheck source=/dev/null
. /etc/os-release
[[ "${ID}" == debian && "${VERSION_ID%%.*}" -ge 13 ]] || die "expected Debian 13+, found ${PRETTY_NAME}"

# ---------------------------------------------------------------- 1. the owner's login
keys=/root/.ssh/authorized_keys
grep -qE '^(ssh-|ecdsa-|sk-)' "${keys}" 2>/dev/null || \
  die "no SSH key on this server: add your key when creating the droplet (docs/CLOUD-VM.md)"
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q sudo git python3 python3-pip \
  python3-setuptools python3-venv python3-yaml
id "${ADMIN}" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash --groups sudo "${ADMIN}"
home="$(getent passwd "${ADMIN}" | cut -d: -f6)"
install -d -m 0700 -o "${ADMIN}" -g "${ADMIN}" "${home}/.ssh"
install -m 0600 -o "${ADMIN}" -g "${ADMIN}" "${keys}" "${home}/.ssh/authorized_keys"
# Until the owner chooses a sudo password (install.sh --cloud asks, then removes this).
echo "${ADMIN} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-bau-setup
chmod 0440 /etc/sudoers.d/90-bau-setup
visudo -cq || die "sudoers check failed"
log "admin login ${ADMIN} uses the droplet's SSH key"

# ---------------------------------------------------------------- 2. SSH: keys only
cat > /etc/ssh/sshd_config.d/10-bau.conf <<CONF
# BAU cloud server: the owner's key is the only way in.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers ${ADMIN}
CONF
sshd -t || { rm -f /etc/ssh/sshd_config.d/10-bau.conf; die "sshd rejected the settings"; }
systemctl reload ssh
log "SSH: key login as ${ADMIN} only; root and passwords refused"

# ---------------------------------------------------------------- 3. BAU install files
out="${home}/bau"
bash "${SRC}/installer/make-payload.sh" --skip-tests --out "${out}"
chown -R "${ADMIN}:${ADMIN}" "${out}"
cat > /etc/motd <<MOTD

  BAU is ready to install. Run once:
    sudo bash ~/bau/BAU-PAYLOAD/install.sh --cloud
  Guide: docs/CLOUD-VM.md (https://github.com/BSAJabo258/linux-ai-biz)

MOTD
log "done: log in as ${ADMIN} and run  sudo bash ~/bau/BAU-PAYLOAD/install.sh --cloud"
