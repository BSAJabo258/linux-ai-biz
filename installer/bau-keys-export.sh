#!/usr/bin/env bash
# BAU keys export (Mac/Linux): run on the computer that has your API keys. It finds keys
# in your environment variables and in the .env files you name, shows their NAMES only,
# and locks them into one file with a passphrase you choose. It changes nothing here.
#   bash bau-keys-export.sh [--out FILE] [--yes] [project/.env ...]
# Then carry BAU-KEYS.enc to the BAU laptop and run: sudo bau keys import BAU-KEYS.enc
# (docs/KEYS.md). The keys never touch the disk unlocked: they go straight to openssl.
set -euo pipefail
OUT="./BAU-KEYS.enc"
YES=0
FILES=()
while (($#)); do
  case $1 in
    --out) OUT=$2; shift 2 ;;
    --yes) YES=1; shift ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) FILES+=("$1"); shift ;;
  esac
done
command -v openssl >/dev/null || { echo "openssl is needed (Mac: built in; Linux: apt install openssl)" >&2; exit 1; }
openssl enc -help 2>&1 | grep -q pbkdf2 || {
  echo "this openssl is too old (no -pbkdf2); Mac: brew install openssl, then run again" >&2; exit 1; }

# Same rule as the laptop (src/bau/keys.py): only credential-shaped names.
NAME_RE='^[A-Z][A-Z0-9_]*(API_KEY[A-Z0-9_]*|_KEY|_TOKEN|_SECRET|_CLIENT_ID|_KEY_ID)$'
wanted() { [[ $1 =~ $NAME_RE ]] && [[ $1 != BAU_* && $1 != LD_* && $1 != PYTHON* ]]; }
# Kept in memory as NAME=value lines (a later source wins); bash 3.2 (Mac) has no maps.
BODY=""
add() {
  BODY="$(printf '%s\n' "${BODY}" | grep -v "^$1=" || true)"
  BODY="${BODY:+${BODY}
}$1=$2"
}

while read -r name; do
  if wanted "${name}" && [[ -n "${!name:-}" ]]; then add "${name}" "${!name}"; fi
done < <(compgen -e)

for f in ${FILES[@]+"${FILES[@]}"}; do
  [[ -r $f ]] || { echo "cannot read ${f}" >&2; exit 1; }
  while IFS= read -r line || [[ -n $line ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line#export }"
    [[ -z $line || $line == \#* || $line != *=* ]] && continue
    name="${line%%=*}"
    value="${line#*=}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ ${#value} -ge 2 && ( $value == \"*\" || $value == \'*\' ) ]]; then
      value="${value:1:${#value}-2}"
    fi
    if wanted "${name}" && [[ -n $value ]]; then add "${name}" "${value}"; fi
  done < "$f"
done

if [[ -z ${BODY} ]]; then
  echo "No API keys found. Name the .env files that hold them: bash $0 path/to/.env" >&2
  exit 1
fi
echo "Keys found (names only):"
NAMES="$(printf '%s\n' "${BODY}" | cut -d= -f1 | sort)"
printf '%s\n' "${NAMES}" | sed 's/^/  /'
if ((YES == 0)); then
  read -r -p "Lock these $(printf '%s\n' "${NAMES}" | wc -l | tr -d ' ') keys into ${OUT}? [y/N] " ok
  [[ $ok == [yY]* ]] || { echo "Nothing written."; exit 0; }
fi

umask 077
pass=()
[[ -n ${BAU_KEYS_PASSPHRASE:-} ]] && pass=(-pass env:BAU_KEYS_PASSPHRASE)
{
  echo "# BAU-KEYS v1"
  printf '%s\n' "${BODY}" | sort
} | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -salt -out "${OUT}" ${pass[@]+"${pass[@]}"}
echo "Written: ${OUT}. Carry it to the BAU laptop and run: sudo bau keys import $(basename "${OUT}")"
echo "Remember the passphrase; delete the file once it is imported."
