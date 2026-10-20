#!/usr/bin/env bash
# Every check, one command, the same as CI: lint, secret scan, regulations, tests, and
# ShellCheck on every shell script in the repo (found, not listed by hand, so none is
# missed). One line per check; the output is shown only for a check that failed.
#   bash scripts/check.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
failed=0

step() {
  local name="$1" out
  shift
  if out="$("$@" 2>&1)"; then
    printf 'PASS  %-12s %s\n' "${name}" "$(tail -n 1 <<< "${out}" | grep -E 'passed|scripts' || true)"
  else
    printf 'FAIL  %s\n' "${name}"
    tail -n 40 <<< "${out}"
    failed=1
  fi
}

# shellcheck disable=SC2329  # called through step below
shell_scripts() {
  local files
  files="$({ git ls-files --cached --others --exclude-standard '*.sh'; git grep --untracked -lE '^#!.*\b(ba)?sh\b' -- ':!*.sh' ':!*.md'; } | sort -u)"
  xargs shellcheck -x <<< "${files}" && echo "$(wc -l <<< "${files}") scripts"
}

step lint ruff check .
step secrets bau secrets .
step regulations bau reg validate
step shellcheck shell_scripts
step tests python3 -m pytest -q
if [[ "${failed}" -eq 0 ]]; then echo "ALL PASS"; else echo "SOMETHING FAILED: fix it before committing"; fi
exit "${failed}"
