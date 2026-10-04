#!/usr/bin/env bash
# Phase 1: READ-ONLY hardware audit of the machine you are about to wipe (spec §4).
# Run from the BAU-PAYLOAD stick on the old system (any Linux, or a Debian live
# session). Writes the BAU-*-BASELINE.json files; changes nothing else.
#   sudo ./hw-audit.sh /media/backup-drive/bau-baselines
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:?usage: $0 OUTPUT_DIR (put it on your backup drive, not the disk being wiped)}"
SRC="${HERE}/bau-src"
[[ -d "${SRC}" ]] || SRC="${HERE}/../src"   # running from a git checkout
command -v python3 >/dev/null || { echo "python3 required" >&2; exit 1; }
if [[ ${EUID} -ne 0 ]]; then
  echo "note: without sudo, disk serials and some firmware fields may be missing" >&2
fi
PYTHONPATH="${SRC}" python3 -m bau.cli hw audit --out "${OUT}"
echo "baselines written to ${OUT}. Next: bau backup manifest / verify (docs/INSTALL.md)" >&2
