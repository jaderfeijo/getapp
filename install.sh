#!/usr/bin/env bash
# getapp installer for Debian and derivatives (Ubuntu, Mint, Pop!_OS, ...). Run ./install.sh --help for the options.
# Default: installs for your user into ~/.local (no root needed except for the apt packages it depends on).
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PREFIX="${PREFIX:-$HOME/.local}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DRY=0 UNINSTALL=0 DESKTOP=1 DEPS=1 WITH_FLATPAK=0 WITH_SNAP=0 WITH_CHROMIUM=0 SYSTEM=0

usage() {
  cat <<USAGE
getapp: one fuzzy search to install apps from apt, Flatpak, Snap and web apps.

Usage: ./install.sh [options]
  --system             install for all users into /usr/local (uses sudo)
  --prefix DIR         install into DIR instead of ~/.local
  --with-flatpak       also install Flatpak and add the Flathub store
  --with-snap          also install snapd (the Snap Store can be searched without it)
  --with-chromium      also install Chromium, which web apps use
  --no-desktop-entry   do not add getapp to your app launcher
  --no-deps            do not apt-install anything (you must have python3 and fzf)
  --uninstall          remove getapp
  --dry-run            show what would be done, change nothing
  -h, --help           this help
USAGE
}
while [ $# -gt 0 ]; do
  case "$1" in
    --system) SYSTEM=1 ;;
    --prefix) PREFIX="${2:?--prefix needs a directory}"; shift ;;
    --with-flatpak) WITH_FLATPAK=1 ;;
    --with-snap) WITH_SNAP=1 ;;
    --with-chromium) WITH_CHROMIUM=1 ;;
    --no-desktop-entry) DESKTOP=0 ;;
    --no-deps) DEPS=0 ;;
    --uninstall) UNINSTALL=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
if [ "$SYSTEM" = 1 ]; then PREFIX=/usr/local; DESKTOP_DIR=/usr/local/share/applications; fi

say() { printf '%s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
SUDO=""; [ "$(id -u)" != 0 ] && have sudo && SUDO="sudo"
# commands that write under the prefix need root only for --system
PSUDO=""; [ "$SYSTEM" = 1 ] && PSUDO="$SUDO"
run() { if [ "$DRY" = 1 ]; then say "[dry-run] $*"; else "$@"; fi; }

LIBDIR="$PREFIX/lib/getapp-py"
BIN="$PREFIX/bin/getapp"
ENTRY="$DESKTOP_DIR/getapp.desktop"

if [ "$UNINSTALL" = 1 ]; then
  run $PSUDO rm -rf "$LIBDIR"
  run $PSUDO rm -f "$BIN" "$ENTRY"
  say "getapp removed. (Apps you installed with it stay installed; its caches are in ~/.cache/getapp.)"
  exit 0
fi

# --- Debian check and dependencies ------------------------------------------------------------------
have apt-get || { say "This installer is for Debian and Debian-based systems (it needs apt-get)."; exit 1; }
if [ "$DEPS" = 1 ]; then
  pkgs=()
  have python3 || pkgs+=(python3)
  have fzf || pkgs+=(fzf)
  [ "$WITH_FLATPAK" = 1 ] && ! have flatpak && pkgs+=(flatpak)
  [ "$WITH_SNAP" = 1 ] && ! have snap && pkgs+=(snapd)
  [ "$WITH_CHROMIUM" = 1 ] && ! have chromium && pkgs+=(chromium)
  if [ "${#pkgs[@]}" -gt 0 ]; then
    say "Installing: ${pkgs[*]}"
    run $SUDO apt-get install -y "${pkgs[@]}"
  fi
  if [ "$WITH_FLATPAK" = 1 ]; then
    run $SUDO flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
  fi
else
  have python3 && have fzf || { say "Missing python3 and/or fzf (sudo apt install python3 fzf), or drop --no-deps."; exit 1; }
fi

# --- install ----------------------------------------------------------------------------------------
say "Installing getapp into $PREFIX ..."
if [ "$DRY" = 1 ]; then
  say "[dry-run] copy lib/getapp (python package + data/webapps.tsv) to $LIBDIR/getapp"
  say "[dry-run] install bin/getapp to $BIN"
  [ "$DESKTOP" = 1 ] && say "[dry-run] write the launcher entry $ENTRY"
  exit 0
fi
$PSUDO rm -rf "$LIBDIR/getapp"
$PSUDO install -d "$LIBDIR" "$PREFIX/bin"
$PSUDO cp -r "$HERE/lib/getapp" "$LIBDIR/getapp"
$PSUDO install -d "$LIBDIR/getapp/data"
$PSUDO install -m 644 "$HERE/data/webapps.tsv" "$LIBDIR/getapp/data/webapps.tsv"
$PSUDO find "$LIBDIR" -name __pycache__ -type d -prune -exec rm -rf {} +
$PSUDO install -m 755 "$HERE/bin/getapp" "$BIN"

if [ "$DESKTOP" = 1 ]; then
  $PSUDO install -d "$DESKTOP_DIR"
  tmp=$(mktemp)
  cat > "$tmp" <<ENTRY
[Desktop Entry]
Version=1.0
Type=Application
Name=getapp
GenericName=App installer
Comment=Search and install apps from apt, Flatpak, Snap and the web in one place
Exec=$BIN
Icon=system-software-install
Terminal=true
Categories=System;Settings;PackageManager;
Keywords=install;app;apt;flatpak;snap;web;package;software;
ENTRY
  $PSUDO install -m 644 "$tmp" "$ENTRY"; rm -f "$tmp"
fi

say ""
say "Installed: $BIN"
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) say "Note: $PREFIX/bin is not on your PATH; add it, or run $BIN" ;; esac
say "Try:   getapp doctor     (what works on this machine)"
say "       getapp            (the search screen)"
say "       getapp --dry-run  (the same, but nothing is ever installed)"
[ "$DESKTOP" = 1 ] && say "It is also in your app launcher as \"getapp\"."
exit 0
