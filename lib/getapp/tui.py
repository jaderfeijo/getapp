"""The interactive part: fzf with a live, merged, ranked list; install or remove what you pick."""
import os
import shlex
import shutil
import subprocess
import sys

from .actions import perform
from .search import format_line

HEADER_INSTALL = "Enter install · Ctrl-/ details · Esc quit\nprefix a source:  apt:  flatpak:  snap:  web:"
HEADER_REMOVE = "Enter remove · Ctrl-/ details · Esc quit"


def _self_cmd():
    return f"{shlex.quote(sys.executable)} -m getapp"


def _fzf_available():
    if shutil.which("fzf"):
        return True
    print("getapp needs fzf for the search screen:  sudo apt install fzf", file=sys.stderr)
    return False


def _fzf(args, stdin=None):
    """Run fzf on the real terminal; returns (query, selected_line or None)."""
    base = ["fzf", "--ansi", "--layout=reverse", "--border=rounded", "--delimiter=\t", "--with-nth=2", "--print-query",
            "--info=inline-right", "--preview-window=right:50%:wrap", "--bind=ctrl-/:toggle-preview",
            f"--preview={_self_cmd()} preview {{1}}"]
    done = subprocess.run(base + args, input=stdin, stdout=subprocess.PIPE, text=True)
    lines = done.stdout.split("\n")
    query = lines[0] if lines else ""
    selected = lines[1] if len(lines) > 1 and lines[1] else None
    return query, selected


def install_screen(query="", dry_run=False):
    if not _fzf_available():
        return 1
    me = _self_cmd()
    while True:
        query, selected = _fzf([
            "--disabled", "--prompt=install> ", f"--header={HEADER_INSTALL}", f"--query={query}",
            f"--bind=start:reload:{me} search -- {{q}}",
            f"--bind=change:reload:sleep 0.12; {me} search -- {{q}}"])
        if not selected:
            return 0
        perform(selected.split("\t")[0], "install", dry_run=dry_run)
        _pause()


def remove_screen(dry_run=False):
    if not _fzf_available():
        return 1
    from .sources import all_sources
    lines = []
    for src in all_sources():
        try:
            lines += [format_line(i) for i in src.installed_items()]
        except Exception:
            pass
    if not lines:
        print("Nothing to remove that getapp knows about.")
        return 0
    while lines:
        _, selected = _fzf(["--prompt=remove> ", f"--header={HEADER_REMOVE}"], stdin="\n".join(lines) + "\n")
        if not selected:
            return 0
        key = selected.split("\t")[0]
        if perform(key, "remove", dry_run=dry_run) == 0 and not dry_run:
            lines = [l for l in lines if not l.startswith(key + "\t")]
        _pause()
    return 0


def _pause():
    try:
        input("\nPress Enter to go back ")
    except EOFError:
        pass
