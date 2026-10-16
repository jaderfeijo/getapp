"""Install / remove one item: show what will run, ask, run."""
import os
import sys

from .runner import run
from .search import resolve
from .sources import by_name


def _ask(prompt, yes):
    if yes or os.environ.get("GETAPP_YES"):
        return True
    try:
        answer = input(f"{prompt} [Y/n] ").strip().lower()
    except EOFError:
        return False
    return answer in ("", "y", "yes")


def perform(key, action, dry_run=False, yes=False, out=None):
    """action is 'install' or 'remove'. Returns 0 on success."""
    out = out or sys.stdout
    item = resolve(key)
    if item is None:
        print(f"I do not know '{key}'.", file=out)
        return 1
    source = by_name()[item.source]
    if action == "install":
        if item.installed:
            print(f"{item.name} is already installed ({item.source}).", file=out)
            return 0
        cmds = source.install_cmds(item)
        title = f"Install {item.name} from {source.label}"
    else:
        cmds = source.remove_cmds(item)
        title = f"Remove {item.name} ({source.label})"
    print(f"\n\033[1m{title}\033[0m" if out.isatty() else f"\n{title}", file=out)
    print("This will run:", file=out)
    for cmd in cmds:
        print("   " + cmd.shown(), file=out)
    if action == "remove" and item.source == "apt":
        impact = [p for p in source.removal_impact(item) if p != item.id]
        if impact:
            print(f"\nNote: apt would also remove {len(impact)} other package(s): {', '.join(impact[:12])}"
                  + (" ..." if len(impact) > 12 else ""), file=out)
    if dry_run:
        print("(dry run: nothing is executed)", file=out)
        return 0
    if not _ask("Go ahead?", yes):
        print("Cancelled.", file=out)
        return 1
    code = run(cmds, out=out)
    print(("Done." if code == 0 else "That did not work."), file=out)
    return code
