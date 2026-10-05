#!/bin/sh
# First start: create the machine's audit key and BAU's state, seed the Second Brain.
set -eu
mkdir -p "$(dirname "$BAU_AUDIT_KEY")"
for key in "$BAU_AUDIT_KEY" "$BAU_UNSUB_KEY"; do
  if [ ! -s "$key" ]; then
    (umask 077; head -c 48 /dev/urandom | base64 > "$key")
  fi
done
if [ ! -f "$BAU_HOME/.container-ready" ]; then
  bau init >/dev/null
  bau brain import >/dev/null
  touch "$BAU_HOME/.container-ready"
fi
exec "$@"
