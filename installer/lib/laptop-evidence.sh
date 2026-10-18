#!/usr/bin/env bash
# Evidence for bau-laptop-check.sh: the verdict, the "what BAU would find in place" lines
# that are safe to share, and the private details that belong only in the full report.
# Sourced by the check, never run on its own. Read only: nothing here writes files.
#
# Three rules live here because they are easy to lose in an edit:
#   - secret files are only stat-ed (name and mode), never opened;
#   - process command lines are never read, only process names;
#   - no repository script is run: a checkout is read with git plumbing only.

_ev_mem_mb() { awk '/MemTotal/ {print int($2 / 1024); exit}' /proc/meminfo 2>/dev/null; }

_ev_gb() { awk -v mb="$1" 'BEGIN {printf "%.1f", mb / 1024}'; }

# Largest internal disk in whole GB; 0 when lsblk is missing or says nothing useful.
# Key=value pairs, because a plain column list shifts when a field (MODEL, TRAN) is empty.
_ev_disk_gb() {
  lsblk -d -n -P -o TYPE,TRAN,SIZE 2>/dev/null | awk '
    {
      t = tr = s = ""
      for (i = 1; i <= NF; i++) {
        split($i, kv, "="); gsub(/"/, "", kv[2])
        if (kv[1] == "TYPE") t = kv[2]
        else if (kv[1] == "TRAN") tr = kv[2]
        else if (kv[1] == "SIZE") s = kv[2]
      }
      if (t != "disk" || tr == "usb") next
      g = 0
      if (s ~ /T$/) { sub(/T$/, "", s); g = s * 1024 }
      else if (s ~ /G$/) { sub(/G$/, "", s); g = s }
      else { sub(/[MG]$/, "", s); g = s / 1024 }
      if (g > best) best = g
    }
    END { printf "%d", best + 0 }'
}

_ev_tool_line() {
  local name=$1 version
  if ! have "${name}"; then printf '  %s: not installed\n' "${name}"; return; fi
  case "${name}" in
    python3) version="$(python3 -V 2>&1)" ;;
    git) version="$(git --version 2>&1)" ;;
    docker) version="$(docker --version 2>&1)" ;;
    node) version="$(node --version 2>&1)" ;;
    uv) version="$(uv --version 2>&1)" ;;
    *) version="present" ;;
  esac
  printf '  %s: %s\n' "${name}" "${version%%$'\n'*}"
}

# Port numbers only: the summary must not say which address answers them.
_ev_ports() {
  if have ss; then
    ss -H -lntu 2>/dev/null | awk '{n = split($5, a, ":"); if (a[n] ~ /^[0-9]+$/) print a[n]}' | sort -n -u
  elif have netstat; then
    netstat -lntu 2>/dev/null | awk 'NR > 2 {n = split($4, a, ":"); if (a[n] ~ /^[0-9]+$/) print a[n]}' | sort -n -u
  fi
}

_ev_services() {
  if ! have systemctl; then echo "  (no systemd here)"; return; fi
  local listed
  listed="$(systemctl list-units --type=service --all --no-legend 'bau-*.service' 2>/dev/null || true)"
  if [[ -z "${listed}" ]]; then echo "  no bau-*.service units on this machine"; return; fi
  awk '{printf "  %s %s\n", $1, $3}' <<< "${listed}"
}

# Every reason that decides the verdict, in the same words the doc uses.
evidence_verdict() {
  local blockers=() steps=() mem_mb arch disk_gb nodrv fw blocked raid
  mem_mb="$(_ev_mem_mb)"
  if [[ -n "${mem_mb}" ]] && (( mem_mb < 7680 )); then
    blockers+=("only $(_ev_gb "${mem_mb}") GB of memory; BAU needs 8 GB or more")
  fi
  arch="$(uname -m 2>/dev/null)"
  case "${arch}" in
    i?86 | armv6* | armv7*) blockers+=("32-bit system (${arch}); BAU needs a 64-bit one") ;;
    "") ;;
  esac
  disk_gb="$(_ev_disk_gb)"
  if [[ -n "${disk_gb}" ]] && (( disk_gb > 0 && disk_gb < 64 )); then
    blockers+=("no internal disk of 64 GB or more (largest internal: ${disk_gb} GB)")
  fi

  [[ -d /sys/firmware/efi ]] || steps+=("this laptop started in legacy BIOS mode; install in UEFI mode instead")
  nodrv="$(devices 2>/dev/null | grep -c 'NO DRIVER LOADED' || true)"
  if [[ -n "${nodrv}" ]] && (( nodrv > 0 )); then
    steps+=("${nodrv} device(s) with NO DRIVER LOADED; check them before installing")
  fi
  fw="$(missing_firmware 2>/dev/null)"
  if [[ -n "${fw}" && "${fw}" != *"none reported"* && "${fw}" != *"could not read"* ]]; then
    steps+=("missing firmware; see Missing firmware above")
  fi
  blocked="$(rfkill list 2>/dev/null | grep -c 'blocked: yes' || true)"
  if [[ -n "${blocked}" ]] && (( blocked > 0 )); then
    steps+=("${blocked} radio(s) blocked; Wi-Fi or Bluetooth will not work until unblocked")
  fi
  raid="$(lspci -nnk 2>/dev/null | grep -ci 'raid bus controller' || true)"
  if [[ -n "${raid}" ]] && (( raid > 0 )); then
    steps+=("disk controller reports RAID (often Intel RST); Linux may not see the disk - switch to AHCI first")
  fi
  if ! have lsblk; then steps+=("lsblk is missing, so disk and RAID checks were skipped"); fi

  if ((${#blockers[@]})); then echo "VERDICT: NOT READY"
  elif ((${#steps[@]})); then echo "VERDICT: READY, AFTER THESE STEPS"
  else echo "VERDICT: READY"; fi
  echo
  local line
  for line in "${blockers[@]+"${blockers[@]}"}"; do echo "  BLOCKER: ${line}"; done
  for line in "${steps[@]+"${steps[@]}"}"; do echo "  DO FIRST: ${line}"; done
  echo "  NOTE: a good guess, not proof - the device list below is what Linux actually did."
}

# Safe to share: tool versions and port numbers, no paths and no addresses.
evidence_summary() {
  echo "BAU on this machine:"
  local tool
  for tool in python3 git docker node uv curl; do _ev_tool_line "${tool}"; done
  local ports
  ports="$(_ev_ports)"
  if [[ -n "${ports}" ]]; then
    printf '  listening ports: %s\n' "$(tr '\n' ' ' <<< "${ports}" | sed 's/ $//')"
  else
    echo "  listening ports: none"
  fi
  echo "  Jarvis services:"
  _ev_services
  echo
}

_ev_checkouts() {
  local c
  for c in "${BAU_DIR:-}" /opt/bau /srv/bau "${HOME:-/root}/linux-ai-biz" "${PWD}"; do
    [[ -n "${c}" && -d "${c}/.git" ]] && printf '%s\n' "${c}"
  done | sort -u
}

# Private: paths, addresses and secret file names. Still never a secret's contents.
evidence_full() {
  echo "### BAU checkout"
  local found=0 dir branch commit dirty
  while IFS= read -r dir; do
    [[ -n "${dir}" ]] || continue
    found=1
    branch="$(git -C "${dir}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    commit="$(git -C "${dir}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    dirty="$(git -C "${dir}" status --porcelain 2>/dev/null | wc -l)"
    echo "  ${dir}: ${branch} ${commit}, ${dirty} changed file(s)"
    git -C "${dir}" log -5 --format='    %h %s' 2>/dev/null || true
  done < <(_ev_checkouts)
  (( found )) || echo "  (no BAU checkout found here)"
  echo

  echo "### bau services"
  _ev_services
  echo

  echo "### listening addresses"
  if have ss; then ss -lntu 2>/dev/null || true; else echo "  (ss not available)"; fi
  echo

  echo "### secret files (name and mode only; contents never read)"
  local f mode any=0 etc="${BAU_ETC:-/etc/bau}"
  for f in "${etc}"/*.env; do
    [[ -e "${f}" ]] || continue
    any=1
    mode="$(stat -c '%a' "${f}" 2>/dev/null || echo unknown)"
    printf '  %s %s\n' "${mode}" "${f}"
    [[ "${mode}" == "600" ]] || echo "    ^ readable by others; chmod 600 recommended"
  done
  (( any )) || echo "  (no ${etc}/*.env)"
  echo

  echo "### process names (command lines are never read: they carry tokens)"
  ps -eo comm= 2>/dev/null | sort | uniq -c | sort -rn | head -n 20 | awk '{printf "  %s %s\n", $1, $2}'
  echo
}
