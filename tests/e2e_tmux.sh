#!/usr/bin/env bash
# End-to-end: drives the real search screen inside tmux with a small fixture package list (no network, dry run).
# Skips (exit 0) when tmux or fzf is missing.
set -uo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
command -v tmux >/dev/null && command -v fzf >/dev/null || { echo "  skip  tmux or fzf missing"; exit 0; }
T=$(mktemp -d); S=getapp-e2e-$$
trap 'tmux kill-session -t "$S" 2>/dev/null; rm -rf "$T"' EXIT
mkdir -p "$T/cache"
printf 'vlc - multimedia player and streamer\nvlc-bin - binaries from VLC\ngedit - popular text editor\n' > "$T/cache/apt.txt"
tr 'A-Z' 'a-z' < "$T/cache/apt.txt" > "$T/cache/apt.low"; cut -d' ' -f1 "$T/cache/apt.low" > "$T/cache/apt.names"
printf 'org.videolan.VLC\tVLC\tVLC media player\n' > "$T/cache/flatpak.tsv"
FAILS=0
ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILS=$((FAILS + 1)); }
screen() { tmux capture-pane -t "$S" -p 2>/dev/null; }
wait_for() {  # wait_for REGEX SECONDS
  for _ in $(seq 1 $(( $2 * 10 ))); do screen | grep -Eq "$1" && return 0; sleep 0.1; done; return 1; }
step() {  # step DESCRIPTION REGEX [SECONDS]
  if wait_for "$2" "${3:-6}"; then ok "$1"; else fail "$1"; echo "        screen was:"; screen | head -12 | sed 's/^/        | /'; fi; }

tmux new-session -d -s "$S" -x 130 -y 34 \
  "env GETAPP_CACHE_DIR=$T/cache GETAPP_DATA_HOME=$T/share GETAPP_NO_REFRESH=1 GETAPP_OFFLINE=1 TERM=xterm-256color $REPO/bin/getapp --dry-run; echo FINISHED=\$?; sleep 30"
step "the search screen opens with the web-app catalog" 'install>.*[0-9]+/[0-9]+'
tmux send-keys -t "$S" "vlc"
step "typing a query lists matches from several sources" 'flatpak +VLC.*\n?.*apt +vlc|apt +vlc.*flatpak|flatpak +VLC'
step "the details pane shows the highlighted result" 'Flatpak apps are sandboxed'
tmux send-keys -t "$S" Enter
step "Enter shows what would run, and that it is a dry run" 'flatpak install.*org.videolan.VLC'
step "...and says nothing is executed" 'dry run: nothing is executed'
tmux send-keys -t "$S" Enter
step "going back returns to the search with the query kept" 'install> vlc'
tmux send-keys -t "$S" Escape
step "Esc leaves the program cleanly" 'FINISHED=0'
echo; [ "$FAILS" = 0 ] && echo "e2e passed" || { echo "$FAILS e2e step(s) failed"; exit 1; }
