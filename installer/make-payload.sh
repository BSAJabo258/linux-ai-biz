#!/usr/bin/env bash
# USB #2 - build the BAU-PAYLOAD bundle that installs the control plane.
#
# Output: dist/BAU-PAYLOAD/ (copy the folder onto any USB stick) and
#         dist/BAU-PAYLOAD-<version>.tar.gz
# Contents are pinned by SHA256SUMS; with --sign KEYID the sums are also
# GPG-signed, and install.sh --expect-fpr verifies that signature.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
# shellcheck source=lib/common.sh
source "${HERE}/lib/common.sh"

OUT_DIR="${ROOT}/dist"
SIGN_KEY=""
TO=""
SKIP_TESTS=0
while (($#)); do
  case $1 in
    --out) OUT_DIR=$2; shift 2 ;;
    --sign) SIGN_KEY=$2; shift 2 ;;
    --to) TO=$2; shift 2 ;;          # mounted USB stick to copy onto
    --skip-tests) SKIP_TESTS=1; shift ;;
    -h|--help) echo "usage: $0 [--out DIR] [--sign GPG_KEYID] [--to /media/usb] [--skip-tests]"; exit 0 ;;
    *) die "unknown argument $1" ;;
  esac
done
need python3 sha256sum tar

cd "${ROOT}"
if ((SKIP_TESTS == 0)); then
  log "running test suite (a payload is never built from failing code)"
  python3 -m pytest -q tests || die "tests failed"
fi
log "scanning for secrets"
PYTHONPATH="${ROOT}/src" python3 -m bau.cli secrets "${ROOT}/src" >/dev/null \
  || die "secret scanner found something in src/ - fix before building"

version="$(PYTHONPATH="${ROOT}/src" python3 -c 'import bau; print(bau.__version__)')"
P="${OUT_DIR}/BAU-PAYLOAD"
rm -rf "${P}"
mkdir -p "${P}/wheels"

log "building wheel ${version}"
# Offline build first; some distro setuptools/wheel combinations break it, so fall
# back to pip's isolated build (fetches setuptools from PyPI).
if ! python3 -m pip wheel --quiet --no-deps --no-build-isolation -w "${P}/wheels" "${ROOT}" \
     >/dev/null 2>&1; then
  warn "offline wheel build failed; retrying with build isolation"
  python3 -m pip wheel --quiet --no-deps -w "${P}/wheels" "${ROOT}" || die "wheel build failed"
fi

cp "${HERE}/payload/install.sh" "${P}/install.sh"
cp -r "${HERE}/payload/systemd" "${HERE}/payload/hardening" "${P}/"
cp "${HERE}/hw-audit.sh" "${HERE}/hw-audit-windows.ps1" "${P}/"
cp -r "${ROOT}/src" "${P}/bau-src"         # lets hw-audit/backup/wipe-gate run before install
find "${P}/bau-src" -name '__pycache__' -prune -exec rm -rf {} +
cp -r "${ROOT}/docs" "${P}/docs"
cp "${ROOT}/LICENSE" "${P}/"
chmod 0755 "${P}/install.sh" "${P}/hw-audit.sh"

commit="$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"
dirty="$(git -C "${ROOT}" status --porcelain 2>/dev/null | head -c1 | wc -c)"
cat > "${P}/MANIFEST.json" <<EOF
{"name": "BAU-PAYLOAD", "version": "${version}", "git_commit": "${commit}",
 "git_dirty": $([[ "${dirty}" -gt 0 ]] && echo true || echo false),
 "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)", "target": "Debian 13+ amd64"}
EOF

sums_tmp="$(mktemp)"
(cd "${P}" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "${sums_tmp}"
mv "${sums_tmp}" "${P}/SHA256SUMS"
chmod 0644 "${P}/SHA256SUMS"
if [[ -n "${SIGN_KEY}" ]]; then
  need gpg
  gpg --batch --yes --local-user "${SIGN_KEY}" --armor --detach-sign -o "${P}/SHA256SUMS.asc" \
    "${P}/SHA256SUMS"
  log "signed SHA256SUMS with ${SIGN_KEY}"
else
  warn "payload not signed; install.sh will verify checksums only (use --sign for production)"
fi

tar -C "${OUT_DIR}" -czf "${OUT_DIR}/BAU-PAYLOAD-${version}.tar.gz" BAU-PAYLOAD
log "payload: ${P}"
if [[ -n "${TO}" ]]; then
  [[ -d "${TO}" ]] || die "--to ${TO} is not a mounted directory"
  rm -rf "${TO}/BAU-PAYLOAD"
  cp -r "${P}" "${TO}/"
  sync
  (cd "${TO}/BAU-PAYLOAD" && sha256sum --quiet -c SHA256SUMS) || die "copy on USB failed verification"
  log "copied and verified on ${TO}/BAU-PAYLOAD"
fi
