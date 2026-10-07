#!/usr/bin/env bash
# Runs as root on Debian 13 (normally inside the build container): builds llama.cpp from
# its pinned source, then the live image with live-build. Called by build-live.sh.
set -euo pipefail

WORK=$1
VERSION=${VERSION:?}
# llama.cpp v0.6.0 (checked 2026-10-07: tag v0.6.0 -> this commit on github.com/ggml-org).
LLAMA_TAG=v0.6.0
LLAMA_COMMIT=d81235049384534c167caea52b85a694f6103d14

export DEBIAN_FRONTEND=noninteractive
if [[ -f ${WORK}/extra-ca.crt ]]; then          # build machine's proxy only, not the image
  apt-get update -q && apt-get install -y -q ca-certificates >/dev/null
  cp "${WORK}/extra-ca.crt" /usr/local/share/ca-certificates/build-extra-ca.crt
  update-ca-certificates >/dev/null
fi
apt-get update -q
apt-get install -y -q live-build cmake build-essential git libssl-dev ca-certificates \
  python3 >/dev/null

# ---------------------------------------------------------------- llama.cpp
llama="${WORK}/llama-${LLAMA_COMMIT}"
if [[ ! -x ${llama}/llama-server ]]; then
  src="${WORK}/llama-src"
  rm -rf "${src}"
  git clone --quiet --depth 1 --branch "${LLAMA_TAG}" https://github.com/ggml-org/llama.cpp \
    "${src}"
  [[ $(git -C "${src}" rev-parse HEAD) == "${LLAMA_COMMIT}" ]] \
    || { echo "llama.cpp ${LLAMA_TAG} is not commit ${LLAMA_COMMIT}: refusing" >&2; exit 1; }
  # Portable: one CPU backend per instruction-set level, picked at run time on the owner's PC.
  cmake -S "${src}" -B "${src}/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON \
    -DGGML_NATIVE=OFF -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON \
    -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON >/dev/null
  cmake --build "${src}/build" --target llama-server -j "$(nproc)" >/dev/null
  rm -rf "${llama}"
  mkdir -p "${llama}"
  cp -a "${src}"/build/bin/llama-server "${src}"/build/bin/*.so* "${llama}/"
  cp "${src}/LICENSE" "${llama}/LICENSE"
  rm -rf "${src}"
fi
LD_LIBRARY_PATH="${llama}" "${llama}/llama-server" --version
install -d "${WORK}/lb/config/includes.chroot/opt/llama.cpp"
cp -a "${llama}/." "${WORK}/lb/config/includes.chroot/opt/llama.cpp/"
printf '%s %s\n' "${LLAMA_TAG}" "${LLAMA_COMMIT}" \
  > "${WORK}/lb/config/includes.chroot/opt/llama.cpp/VERSION"

# ---------------------------------------------------------------- live image
cd "${WORK}/lb"
lb clean >/dev/null 2>&1 || true          # keeps the package cache between builds
lb config
# Keep live-build's GRUB files, with the My Jarvis menu in place of its default one.
mkdir -p config/bootloaders
cp -a /usr/share/live/build/bootloaders/grub-pc config/bootloaders/grub-pc
cp grub.cfg config/bootloaders/grub-pc/grub.cfg
lb build 2>&1 | tee "${WORK}/lb-build.log" | grep -E '^P: |^E: |error' || true
iso="$(find . -maxdepth 1 -name '*.hybrid.iso' | head -1)"
[[ -n ${iso} ]] || { echo "live-build produced no ISO; see lb-build.log" >&2; exit 1; }

mkdir -p "${WORK}/out"
name="my-jarvis-${VERSION}-amd64.iso"
mv -f "${iso}" "${WORK}/out/${name}"
python3 - "${WORK}" "${name}" "${LLAMA_TAG}" "${LLAMA_COMMIT}" <<'EOF'
import json, sys, pathlib, datetime
work, name, tag, commit = sys.argv[1:]
lb = pathlib.Path(work, "lb")
rel = dict(l.split("=", 1) for l in
           (lb / "config/includes.chroot/etc/my-jarvis-release").read_text().split())
pkgs = (lb / "chroot.packages.live").read_text().split("\n") if (lb / "chroot.packages.live").exists() else []
kernel = [p.split()[0] + " " + p.split()[1] for p in pkgs if p.startswith("linux-image-")]
json.dump({"image": name, "version": rel["MYJARVIS_OS_VERSION"],
           "git_commit": rel["GIT_COMMIT"], "git_dirty": rel["GIT_DIRTY"] == "true",
           "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "debian": "13 (trixie)", "kernel": kernel, "llama_cpp": f"{tag} {commit}",
           "packages": [p for p in pkgs if p]},
          open(pathlib.Path(work, "out", "manifest.json"), "w"), indent=1)
EOF
echo "image: ${WORK}/out/${name}"
