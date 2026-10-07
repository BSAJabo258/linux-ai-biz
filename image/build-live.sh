#!/usr/bin/env bash
# Build the My Jarvis live USB image (Debian 13 live system with BAU, llama.cpp and the
# encrypted-storage setup), reproducibly from this repository.
#
#   bash image/build-live.sh [--out DIR] [--skip-tests] [--extra-ca FILE.pem]
#
# Output: DIR/my-jarvis-<version>-amd64.iso (write it to a USB stick, see docs/LIVE-USB.md),
#         its .sha256 and a .manifest.json (git commit, Debian, llama.cpp, BAU, packages).
# Needs Docker (the build runs as root in a privileged Debian 13 container), about 15 GB
# of free disk and an internet connection. On Debian 13 itself, as root: --native.
# --extra-ca: trust a company proxy's certificate during the build (never put in the image).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
# shellcheck source=../installer/lib/common.sh
source "${ROOT}/installer/lib/common.sh"

OUT="${ROOT}/dist"
SKIP_TESTS=0
NATIVE=0
EXTRA_CA=""
BASE="${BASE:-debian:trixie}"
while (($#)); do
  case $1 in
    --out) OUT=$2; shift 2 ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    --native) NATIVE=1; shift ;;
    --extra-ca) EXTRA_CA=$2; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) die "unknown argument $1" ;;
  esac
done

mkdir -p "${OUT}"
OUT="$(cd "${OUT}" && pwd)"
WORK="${OUT}/live-work"
mkdir -p "${WORK}"

# 1. BAU wheel (tests and secret scan run first unless --skip-tests).
args=(--out "${WORK}/payload")
((SKIP_TESTS)) && args+=(--skip-tests)
bash "${ROOT}/installer/make-payload.sh" "${args[@]}"

# 2. Stage the live-build configuration with BAU's payload inside it.
# Fresh configuration every time; live-build's package cache is kept between builds.
[[ -d ${WORK}/lb/cache ]] && mv "${WORK}/lb/cache" "${WORK}/lb-cache"
rm -rf "${WORK}/lb"
mkdir -p "${WORK}/lb"
[[ -d ${WORK}/lb-cache ]] && mv "${WORK}/lb-cache" "${WORK}/lb/cache"
cp -a "${HERE}/live-build/." "${WORK}/lb/"
inc="${WORK}/lb/config/includes.chroot"
install -d "${inc}/opt/bau/wheels" "${inc}/opt/bau/payload" "${inc}/opt/bau/docs"
cp "${WORK}"/payload/BAU-PAYLOAD/wheels/bau-*.whl "${inc}/opt/bau/wheels/"
cp -a "${ROOT}/installer/payload/systemd" "${ROOT}/installer/payload/hardening" \
  "${inc}/opt/bau/payload/"
cp "${ROOT}"/docs/*.md "${inc}/opt/bau/docs/"
version="$(cat "${HERE}/VERSION")"
commit="$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"
dirty="$(git -C "${ROOT}" status --porcelain 2>/dev/null | grep -q . && echo true || echo false)"
printf 'MYJARVIS_OS_VERSION=%s\nGIT_COMMIT=%s\nGIT_DIRTY=%s\n' "${version}" "${commit}" \
  "${dirty}" > "${inc}/etc/my-jarvis-release"
cp "${HERE}/inside.sh" "${WORK}/inside.sh"
rm -f "${WORK}/extra-ca.crt"
if [[ -n ${EXTRA_CA} ]]; then
  cp "${EXTRA_CA}" "${WORK}/extra-ca.crt"
fi

# 3. Build (llama.cpp from pinned source, then the image).
if ((NATIVE)); then
  [[ ${EUID} -eq 0 ]] || die "--native needs root"
  VERSION="${version}" bash "${WORK}/inside.sh" "${WORK}"
else
  need docker
  # shellcheck disable=SC2086  # DOCKER_ARGS: extra options, e.g. --network host
  docker run --rm --privileged ${DOCKER_ARGS:-} -v "${WORK}:/work" -e VERSION="${version}" \
    -e http_proxy -e https_proxy -e no_proxy "${BASE}" bash /work/inside.sh /work
fi

iso="my-jarvis-${version}-amd64.iso"
mv -f "${WORK}/out/${iso}" "${OUT}/${iso}"
mv -f "${WORK}/out/manifest.json" "${OUT}/${iso%.iso}.manifest.json"
(cd "${OUT}" && sha256sum "${iso}" > "${iso}.sha256")
log "built ${OUT}/${iso} ($(du -h "${OUT}/${iso}" | cut -f1))"
log "write it to a USB stick: docs/LIVE-USB.md"
