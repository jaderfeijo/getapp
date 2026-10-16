import argparse
import os
import shutil
import signal
import subprocess
import sys

from . import __version__
from .actions import perform
from .runner import Cmd, run
from .search import format_line, resolve, search
from .sources import all_sources, by_name


def cmd_search(args):
    query = " ".join(args.query)
    try:
        items = search(query)
    except Exception:
        items = []
    color = not args.plain
    for item in items:
        print(format_line(item, color=color))
    return 0


def cmd_preview(args):
    item = resolve(args.key)
    if item is None:
        print("No details.")
        return 0
    print(by_name()[item.source].preview(item))
    return 0


def cmd_installed(args):
    for src in all_sources():
        for item in src.installed_items():
            print(format_line(item, color=not args.plain))
    return 0


def cmd_doctor(args):
    print(f"getapp {__version__}")
    print(f"python  {sys.version.split()[0]}")
    fzf = shutil.which("fzf")
    version = subprocess.run([fzf, "--version"], capture_output=True, text=True).stdout.split()[0] if fzf else "MISSING (sudo apt install fzf)"
    print(f"fzf     {version}")
    print(f"sudo    {'yes' if shutil.which('sudo') or os.geteuid() == 0 else 'MISSING (installs need root)'}")
    for src in all_sources():
        ok = "ok " if src.available() else "-- "
        print(f"{ok} {src.name:<8} {src.label}: {src.status()}")
    return 0


def cmd_refresh(args):
    for src in all_sources():
        print(f"refreshing {src.name} ...")
        src.refresh()
    print("done")
    return 0


def cmd_setup(args):
    tools = {
        "flatpak": [Cmd(["apt-get", "install", "-y", "flatpak"], root=True),
                    Cmd(["flatpak", "remote-add", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"], root=True)],
        "snap": [Cmd(["apt-get", "install", "-y", "snapd"], root=True)],
        "chromium": [Cmd(["apt-get", "install", "-y", "chromium"], root=True)],
    }
    return run(tools[args.what], dry_run=args.dry_run)


def cmd_install(args):
    code = 0
    for key in args.keys:
        code |= perform(key, "install", dry_run=args.dry_run, yes=args.yes)
    return code


def cmd_remove(args):
    if not args.keys:
        from .tui import remove_screen
        return remove_screen(dry_run=args.dry_run)
    code = 0
    for key in args.keys:
        code |= perform(key, "remove", dry_run=args.dry_run, yes=args.yes)
    return code


def cmd_tui(args):
    from .tui import install_screen
    return install_screen(" ".join(args.query), dry_run=args.dry_run)


def build_parser():
    p = argparse.ArgumentParser(prog="getapp", description="One fuzzy search to install apps from apt, Flatpak, Snap and the web.")
    p.add_argument("--version", action="version", version=f"getapp {__version__}")
    p.add_argument("--dry-run", action="store_true", default=bool(os.environ.get("GETAPP_DRY_RUN")),
                   help="show what would be run, run nothing")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("search", help="print the ranked results for a query (used by the search screen)")
    s.add_argument("--plain", action="store_true", help="no colours")
    s.add_argument("query", nargs="*")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("preview", help="details for one result, e.g. apt:vlc")
    s.add_argument("key")
    s.set_defaults(func=cmd_preview)

    s = sub.add_parser("installed", help="list what getapp can remove")
    s.add_argument("--plain", action="store_true")
    s.set_defaults(func=cmd_installed)

    s = sub.add_parser("install", help="install by key without the search screen, e.g. getapp install flatpak:com.slack.Slack")
    s.add_argument("--yes", "-y", action="store_true")
    s.add_argument("keys", nargs="+")
    s.set_defaults(func=cmd_install)

    s = sub.add_parser("remove", help="remove by key, or with no key open the remove screen")
    s.add_argument("--yes", "-y", action="store_true")
    s.add_argument("keys", nargs="*")
    s.set_defaults(func=cmd_remove)

    sub.add_parser("doctor", help="what works on this machine").set_defaults(func=cmd_doctor)
    sub.add_parser("refresh", help="rebuild the package lists").set_defaults(func=cmd_refresh)

    s = sub.add_parser("setup", help="install the tools a source needs")
    s.add_argument("what", choices=["flatpak", "snap", "chromium"])
    s.set_defaults(func=cmd_setup)

    s = sub.add_parser("tui", help="the search screen (the default)")
    s.add_argument("query", nargs="*")
    s.set_defaults(func=cmd_tui)
    return p


def main(argv=None):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)          # `getapp search x | head` should end quietly
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    commands = {"search", "preview", "installed", "install", "remove", "doctor", "refresh", "setup", "tui"}
    flags = {"--dry-run", "--version", "-h", "--help"}
    # `getapp vlc` / `getapp` start the search screen; subcommands are only recognised as the first non-flag word
    first = next((a for a in argv if a not in flags), None)
    if first is None or first not in commands:
        argv = [a for a in argv if a in flags] + ["tui"] + [a for a in argv if a not in flags]
    args = parser.parse_args(argv)
    return args.func(args)
