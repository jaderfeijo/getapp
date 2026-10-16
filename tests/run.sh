#!/usr/bin/env bash
# All the tests: unit tests, the installer in a throwaway prefix, the real screen in tmux, and a privacy scan.
# Nothing here installs software or touches your configuration.
set -uo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
FAILS=0
ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILS=$((FAILS + 1)); }
check() { if eval "$2"; then ok "$1"; else fail "$1"; fi; }

echo "unit tests"
if python3 -m unittest discover -s "$REPO/tests" > "$(mktemp)" 2>&1; then
  n=$(python3 -m unittest discover -s "$REPO/tests" 2>&1 | grep -oE '^Ran [0-9]+' | cut -d' ' -f2); ok "$n unit tests"
else python3 -m unittest discover -s "$REPO/tests" 2>&1 | tail -25; fail "unit tests"; fi

echo "installer"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
check "install.sh parses" 'bash -n "$REPO/install.sh"'
"$REPO/install.sh" --dry-run --prefix "$T/p" --no-deps --no-desktop-entry >/dev/null 2>&1
check "--dry-run installs nothing" '[ ! -e "$T/p" ]'
XDG_DATA_HOME="$T/share" "$REPO/install.sh" --prefix "$T/p" --no-deps > "$T/install.out" 2>&1
check "installs the program and its data" '[ -x "$T/p/bin/getapp" ] && [ -f "$T/p/lib/getapp-py/getapp/data/webapps.tsv" ]'
check "adds a launcher entry" 'grep -q "^Exec=$T/p/bin/getapp" "$T/share/applications/getapp.desktop"'
check "the installed copy runs on its own" 'GETAPP_CACHE_DIR="$T/cache" GETAPP_NO_REFRESH=1 GETAPP_OFFLINE=1 "$T/p/bin/getapp" doctor | grep "^getapp " >/dev/null'
check "the installed copy finds the web catalog" 'GETAPP_CACHE_DIR="$T/cache" GETAPP_NO_REFRESH=1 GETAPP_OFFLINE=1 "$T/p/bin/getapp" search --plain github | grep "^web:github" >/dev/null'
XDG_DATA_HOME="$T/share" "$REPO/install.sh" --prefix "$T/p" --no-deps --uninstall >/dev/null 2>&1
check "--uninstall removes everything" '[ -z "$(find "$T/p" "$T/share" -type f 2>/dev/null)" ]'

echo "the real screen (tmux)"
"$REPO/tests/e2e_tmux.sh" 2>&1 | sed 's/^/  /' | grep -E 'ok |FAIL|skip|passed|failed' || fail "end-to-end"
[ "${PIPESTATUS[0]}" = 0 ] || FAILS=$((FAILS + 1))

echo "privacy: nothing about the machine that runs these tests is in the repository"
cd "$REPO"; files=$(git ls-files 2>/dev/null || find . -type f -not -path './.git/*')
scan() { hits=$(echo "$files" | xargs grep -nIE -e "$2" 2>/dev/null | grep -v '^tests/' || true)
  if [ -z "$hits" ]; then ok "$1"; else fail "$1"; echo "$hits" | head -5 | sed 's/^/        /'; fi; }
scan "no absolute home directories" '(/home/[a-z_][a-z0-9_-]*|/Users/[A-Za-z0-9_-]+)'
scan "no e-mail addresses"          '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
scan "no tokens or private keys"    '(ghp_|gho_|github_pat_|BEGIN [A-Z ]*PRIVATE KEY)'
[ -z "${PRIVACY_TERMS:-}" ] || scan 'none of $PRIVACY_TERMS' "$PRIVACY_TERMS"
echo; if [ "$FAILS" = 0 ]; then echo "all tests passed"; else echo "$FAILS group(s) failed"; exit 1; fi
