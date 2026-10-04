#!/usr/bin/env bash
# BAU control-plane installer. Runs on the new Debian system from USB #2.
#
#   sudo ./install.sh [--wipe-gate-record FILE] [--expect-fpr GPG_FPR] [--offline]
#
# Idempotent: safe to re-run for upgrades; existing keys, state and the audit
# chain are never overwritten.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG=/var/log/bau-install.log
log()  { printf '[bau-install] %s\n' "$*" | tee -a "${LOG}" >&2; }
die()  { printf '[bau-install] ERROR: %s\n' "$*" | tee -a "${LOG}" >&2; exit 1; }

GATE=""
EXPECT_FPR=""
OFFLINE=0
ALLOW_OS=0
while (($#)); do
  case $1 in
    --wipe-gate-record) GATE=$2; shift 2 ;;
    --expect-fpr) EXPECT_FPR=$2; shift 2 ;;
    --offline) OFFLINE=1; shift ;;
    --allow-other-os) ALLOW_OS=1; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) die "unknown argument $1" ;;
  esac
done

[[ ${EUID} -eq 0 ]] || die "run with sudo"
ADMIN="${SUDO_USER:-}"
[[ -n "${ADMIN}" && "${ADMIN}" != root ]] || die "run via sudo from the administrator account"
touch "${LOG}" && chmod 0600 "${LOG}"

# ---------------------------------------------------------------- 1. verify payload
log "verifying payload checksums"
(cd "${HERE}" && sha256sum --quiet --strict -c SHA256SUMS) || die "payload corrupted or modified"
if [[ -f "${HERE}/SHA256SUMS.asc" ]]; then
  if [[ -n "${EXPECT_FPR}" ]]; then
    st="$(gpg --batch --status-fd 1 --verify "${HERE}/SHA256SUMS.asc" "${HERE}/SHA256SUMS" 2>/dev/null || true)"
    grep -q "VALIDSIG.* ${EXPECT_FPR}\$" <<<"${st}" || die "payload signature not by ${EXPECT_FPR}"
    log "payload signature verified (${EXPECT_FPR})"
  else
    log "WARNING: payload is signed but --expect-fpr not given; signature not checked"
  fi
fi

# ---------------------------------------------------------------- 2. platform
# shellcheck source=/dev/null
. /etc/os-release
if [[ "${ID}" != debian || "${VERSION_ID%%.*}" -lt 13 ]] && ((ALLOW_OS == 0)); then
  die "expected Debian 13+, found ${PRETTY_NAME} (use --allow-other-os at your own risk)"
fi
pkgs=(python3 python3-venv python3-yaml nftables podman uidmap apparmor apparmor-utils chrony
      auditd unattended-upgrades dnsutils openssh-client ffmpeg)
missing=()
for p in "${pkgs[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
if ((${#missing[@]})); then
  ((OFFLINE == 0)) || die "missing packages and --offline given: ${missing[*]}"
  log "installing missing packages: ${missing[*]}"
  apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${missing[@]}"
fi

# ---------------------------------------------------------------- 3. identities
getent group bau >/dev/null || groupadd --system bau
getent group bau-approvers >/dev/null || groupadd --system bau-approvers
id bau >/dev/null 2>&1 || useradd --system --gid bau --home-dir /var/lib/bau \
  --shell /usr/sbin/nologin --comment "BAU agents (no approval rights)" bau
# The human administrator may approve; the agent account never can.
usermod -aG bau,bau-approvers "${ADMIN}"
if id -nG bau | tr ' ' '\n' | grep -qx bau-approvers; then
  die "service account 'bau' must not be in bau-approvers"
fi

# ---------------------------------------------------------------- 4. directories + keys
install -d -m 2770 -o bau -g bau /var/lib/bau
install -d -m 0750 -o root -g bau /etc/bau
install -d -m 0755 /opt/bau
umask 077
mk_key() {  # mk_key FILE GROUP - generated on this machine, never shipped, never logged
  [[ -s "$1" ]] && return 0
  head -c 48 /dev/urandom | base64 > "$1"
  chown "root:$2" "$1"
  chmod 0640 "$1"
  log "created $1"
}
mk_key /etc/bau/audit.key bau
mk_key /etc/bau/unsubscribe.key bau
umask 022
# Per-human approval key: the admin signs approvals with their own passphrase-
# protected key; the agent account can verify (allowed_signers) but never sign.
akey="$(getent passwd "${ADMIN}" | cut -d: -f6)/.ssh/bau_approval_ed25519"
if [[ ! -f "${akey}" ]]; then
  log "creating ${ADMIN}'s approval signing key - choose a passphrase"
  runuser -u "${ADMIN}" -- mkdir -p -m 0700 "$(dirname "${akey}")"
  runuser -u "${ADMIN}" -- ssh-keygen -q -t ed25519 -C "bau-approver:${ADMIN}" -f "${akey}"
fi
line="${ADMIN} namespaces=\"bau-approval\" $(cut -d' ' -f1,2 "${akey}.pub")"
touch /etc/bau/allowed_signers
grep -qxF "${line}" /etc/bau/allowed_signers || echo "${line}" >> /etc/bau/allowed_signers
chown root:bau /etc/bau/allowed_signers
chmod 0644 /etc/bau/allowed_signers

# ---------------------------------------------------------------- 5. application
wheels=("${HERE}"/wheels/bau-*.whl)
wheel="${wheels[-1]}"
[[ -f "${wheel}" ]] || die "no wheel in payload"
[[ -x /opt/bau/venv/bin/python ]] || python3 -m venv --system-site-packages /opt/bau/venv
/opt/bau/venv/bin/pip install --quiet --no-index --no-deps --force-reinstall "${wheel}"
# Optional: Claude SDK, bundled by `make-payload.sh --with-claude` for offline install.
if compgen -G "${HERE}/wheels/anthropic-*.whl" >/dev/null; then
  /opt/bau/venv/bin/pip install --quiet --no-index --find-links "${HERE}/wheels" anthropic
  log "Claude SDK installed (cloud models still need approval: bau set-status model ...)"
fi
ln -sf /opt/bau/venv/bin/bau /usr/local/bin/bau
cat > /etc/profile.d/bau.sh <<'EOF'
export BAU_HOME=/var/lib/bau
export BAU_AUDIT_KEY=/etc/bau/audit.key
export BAU_ALLOWED_SIGNERS=/etc/bau/allowed_signers
EOF
export BAU_HOME=/var/lib/bau BAU_AUDIT_KEY=/etc/bau/audit.key
runuser -u bau -- env BAU_HOME=/var/lib/bau BAU_AUDIT_KEY=/etc/bau/audit.key \
  /usr/local/bin/bau init >/dev/null
log "BAU $(/usr/local/bin/bau --version) installed"

# ---------------------------------------------------------------- 6. host hardening
install -m 0644 "${HERE}/hardening/nftables.conf" /etc/nftables.conf
systemctl enable --now nftables >/dev/null
nft -c -f /etc/nftables.conf || die "firewall rules invalid"
install -m 0644 "${HERE}/hardening/99-bau-sysctl.conf" /etc/sysctl.d/99-bau.conf
sysctl --quiet --system >/dev/null || true
install -m 0644 "${HERE}/hardening/20auto-upgrades" /etc/apt/apt.conf.d/20auto-upgrades
install -m 0644 "${HERE}/hardening/52unattended-upgrades-bau" \
  /etc/apt/apt.conf.d/52unattended-upgrades-bau
install -d /etc/chrony/conf.d
install -m 0644 "${HERE}/hardening/bau-nts.conf" /etc/chrony/conf.d/bau-nts.conf
systemctl restart chrony || true
systemctl enable --now auditd >/dev/null 2>&1 || true
aa-enabled -q 2>/dev/null || log "WARNING: AppArmor is not enabled"

# ---------------------------------------------------------------- 7. services
install -m 0644 "${HERE}"/systemd/*.service "${HERE}"/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable bau-recover.service bau-regwatch.timer bau-governor.timer bau-ui.service >/dev/null
systemctl start bau-regwatch.timer bau-governor.timer bau-ui.service

# ---------------------------------------------------------------- 8. wipe-gate evidence
audit() { runuser -u bau -- env BAU_HOME=/var/lib/bau BAU_AUDIT_KEY=/etc/bau/audit.key \
  /opt/bau/venv/bin/python -c "import sys,json; from bau.audit import AuditLog; \
AuditLog().append(sys.argv[1], 'installer', json.loads(sys.argv[2]))" "$1" "$2"; }
if [[ -n "${GATE}" ]]; then
  [[ -f "${GATE}" ]] || die "wipe-gate record not found: ${GATE}"
  install -m 0640 -o bau -g bau "${GATE}" /var/lib/bau/reports/BAU-WIPE-GATE.json
  h="$(sha256sum "${GATE}" | cut -d' ' -f1)"
  audit install.gated "{\"wipe_gate_record_sha256\": \"${h}\"}"
  log "wipe-gate record imported"
else
  audit install.ungated '{"note": "no wipe-gate record supplied"}'
  log "WARNING: no wipe-gate record - install is marked UNGATED in the audit chain"
fi
audit install.completed "{\"payload\": $(cat "${HERE}/MANIFEST.json")}"

sed -i '/BAU base OS installed/,/This notice is removed by install.sh./d' /etc/motd || true

# ---------------------------------------------------------------- 9. self-test
log "self-test:"
runuser -u bau -- env BAU_HOME=/var/lib/bau BAU_AUDIT_KEY=/etc/bau/audit.key \
  /usr/local/bin/bau selftest | tee -a "${LOG}" || true
log "done. Log out and back in (group membership), then run: bau status"
