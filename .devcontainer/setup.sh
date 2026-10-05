#!/usr/bin/env bash
# One-time Codespace setup: tools, BAU itself, a fresh BAU_HOME and a seeded Second Brain.
set -euo pipefail
sudo apt-get update -q
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q ffmpeg openssh-client xorriso
python -m pip install -q -e '.[dev,claude]'
bau init >/dev/null
bau brain import >/dev/null
echo "BAU ready: run 'bau status', 'bau brain lint', or open the Mission Control port (8765)."
