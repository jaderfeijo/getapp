"""Runs the commands behind an install or a removal, printing each one first. Supports a dry run."""
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Cmd:
    argv: Optional[list] = None       # an external command ...
    root: bool = False                # ... that needs root (run through sudo unless we already are root)
    call: Optional[Callable] = None   # ... or a Python step (returns True on success)
    label: str = ""                   # what a Python step is shown as

    def shown(self):
        if self.call is not None:
            return self.label or "(internal step)"
        argv = self.full_argv()
        return " ".join(_quote(a) for a in argv)

    def full_argv(self):
        if self.root and os.geteuid() != 0:
            return ["sudo"] + list(self.argv)
        return list(self.argv)


def _quote(arg):
    import shlex
    return shlex.quote(arg)


def _style(text, code, stream):
    return f"\033[{code}m{text}\033[0m" if stream.isatty() else text


def run(cmds, dry_run=False, out=None):
    """Run the commands in order, stop at the first failure. Returns 0 on success."""
    out = out or sys.stdout
    for cmd in cmds:
        print(_style("$ ", "1;36", out) + cmd.shown(), file=out, flush=True)
        if dry_run:
            continue
        if cmd.call is not None:
            if not cmd.call():
                print(_style("that step failed", "31", out), file=out)
                return 1
            continue
        code = subprocess.call(cmd.full_argv())
        if code != 0:
            print(_style(f"failed (exit status {code})", "31", out), file=out)
            return code
    return 0
