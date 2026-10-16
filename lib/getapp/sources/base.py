import os
import shutil
import subprocess
import time
from pathlib import Path

from .. import paths


def have(tool):
    return shutil.which(tool) is not None


def capture(argv, timeout=60):
    """stdout of a command as text, or '' if it is missing or fails."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout if done.returncode == 0 else ""


def fresh(path, max_age_seconds):
    try:
        return time.time() - Path(path).stat().st_mtime < max_age_seconds
    except OSError:
        return False


def write_atomic(path, text):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


class Source:
    name = ""
    label = ""

    def available(self):                   # can this source be searched at all?
        return True

    def search(self, tokens):              # -> [(score, Item)]
        return []

    def get(self, ident):                  # -> Item or None
        return None

    def installed_items(self):             # -> [Item]
        return []

    def install_cmds(self, item):          # -> [Cmd]
        raise NotImplementedError

    def remove_cmds(self, item):           # -> [Cmd]
        raise NotImplementedError

    def preview(self, item):               # -> str
        return item.summary

    def refresh(self):                     # rebuild any cache
        pass

    def status(self):                      # one line for `getapp doctor`
        return "ok"
