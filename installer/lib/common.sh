#!/usr/bin/env bash
# Shared helpers for BAU installer scripts. Source, do not execute.

# Set BAU_LOG=/path to also append messages to a log file.
_emit() {
  printf '%s\n' "$*" >&2
  if [[ -n "${BAU_LOG:-}" ]]; then printf '%s\n' "$*" >> "${BAU_LOG}"; fi
}
log()  { _emit "[bau] $*"; }
warn() { _emit "[bau] WARNING: $*"; }
die()  { _emit "[bau] ERROR: $*"; exit 1; }

need() {
  local missing=()
  for c in "$@"; do command -v "$c" >/dev/null 2>&1 || missing+=("$c"); done
  if ((${#missing[@]})); then
    die "missing required tools: ${missing[*]}"
  fi
}

require_root() {
  [[ ${EUID} -eq 0 ]] || die "run as root (sudo $0 ...)"
}

# confirm_typed PROMPT EXPECTED - a human must type EXPECTED exactly.
confirm_typed() {
  local prompt=$1 expected=$2 reply
  [[ -t 0 ]] || die "confirmation must be typed at an interactive terminal"
  read -r -p "${prompt}: " reply
  [[ "${reply}" == "${expected}" ]] || die "confirmation did not match; nothing was changed"
}
