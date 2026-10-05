#!/bin/sh
# Container test drive: create YOUR approval signing key (you choose the passphrase) and
# register it, the same thing install.sh does for the laptop's administrator.
#   docker compose run --rm ui bau-approver-setup
set -eu
key="$BAU_HOME/keys/approval_ed25519"
who="$(id -un)"
if [ ! -f "$key" ]; then
  echo "Creating your approval key - choose a passphrase you will remember."
  ssh-keygen -q -t ed25519 -C "bau-approver:$who" -f "$key"
fi
line="$who namespaces=\"bau-approval\" $(cut -d' ' -f1,2 "$key.pub")"
touch "$BAU_ALLOWED_SIGNERS"
grep -qxF "$line" "$BAU_ALLOWED_SIGNERS" || echo "$line" >> "$BAU_ALLOWED_SIGNERS"
echo "Approver registered: $who. Sign approvals with: bau approve ... --key $key"
