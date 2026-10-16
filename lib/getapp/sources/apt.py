"""Debian packages. Searches a local index built from `apt-cache search .` (about 70 000 lines)."""
import os
from pathlib import Path

from .. import paths
from ..fuzzy import is_subsequence, score_item
from ..model import Item
from ..runner import Cmd
from .base import Source, capture, have, write_atomic

PKGCACHE = Path("/var/cache/apt/pkgcache.bin")


class AptSource(Source):
    name = "apt"
    label = "Debian packages"

    def __init__(self):
        self._state = None

    # ---- the index: apt.txt (as apt prints it), apt.low (lower-cased) and apt.names (package names only) -----
    def _file(self, ext):
        return paths.cache_dir() / f"apt.{ext}"

    def _stale(self):
        files = [self._file(e) for e in ("txt", "low", "names")]
        if not all(f.exists() for f in files):
            return True
        if os.environ.get("GETAPP_NO_REFRESH"):
            return False
        try:
            return PKGCACHE.stat().st_mtime > files[0].stat().st_mtime      # apt update / install happened since
        except OSError:
            return False

    def refresh(self):
        text = capture(["apt-cache", "search", "."], timeout=120)
        if text:
            low = text.lower()
            write_atomic(self._file("txt"), text)
            write_atomic(self._file("low"), low)
            write_atomic(self._file("names"), "\n".join(l.partition(" - ")[0] for l in low.splitlines()) + "\n")
        self._state = None

    def _load(self):
        """-> dict with 'names' now, and 'raw' / 'low' read on first use (they are big)."""
        if self._state is None:
            if self._stale() and have("apt-cache"):
                self.refresh()
            try:
                names = self._file("names").read_text(errors="replace").splitlines()
            except OSError:
                names = []
            self._state = {"names": names}
        return self._state

    def _lines(self, which):
        state = self._load()
        if which not in state:
            try:
                state[which] = self._file("txt" if which == "raw" else "low").read_text(errors="replace").splitlines()
            except OSError:
                state[which] = []
        return state[which]

    def available(self):
        return have("apt-get") or self._file("txt").exists()

    def installed_ids(self):
        """Names of installed packages. Cached; rebuilt only when dpkg's status file has changed."""
        cache = paths.cache_dir() / "apt.installed"
        try:
            if cache.stat().st_mtime >= Path("/var/lib/dpkg/status").stat().st_mtime:
                return set(cache.read_text().split())
        except OSError:
            pass
        out = capture(["dpkg-query", "-W", "-f", "${Package}\t${db:Status-Abbrev}\n"])
        names = {line.split("\t")[0].split(":")[0] for line in out.splitlines() if "\tii" in line}
        if names:
            write_atomic(cache, "\n".join(sorted(names)) + "\n")
        return names

    # ---- searching -------------------------------------------------------------------------------
    def search(self, tokens):
        names = self._load()["names"]
        if not names or not tokens:
            return []
        hits = [i for i, n in enumerate(names) if all(t in n for t in tokens)]          # names first: fast and relevant
        if len(hits) < 60:                                                              # too few: look in descriptions too
            seen = set(hits)
            hits += [i for i, line in enumerate(self._lines("low")) if i not in seen and all(t in line for t in tokens)]
        hits = hits[:4000]
        if not hits and len(tokens) == 1 and len(tokens[0]) >= 3:                       # typo-tolerant fallback, names only
            hits = [i for i, n in enumerate(names) if is_subsequence(tokens[0], n)][:300]
        if not hits:
            return []
        raw = self._lines("raw")
        installed = self.installed_ids()
        results = []
        for i in hits:
            name, _, summary = raw[i].partition(" - ")
            lname = name.lower()
            score = score_item(tokens, lname, lname, summary.lower())
            if score is not None:
                results.append((score, Item("apt", name, name, summary, installed=name in installed)))
        return results

    def get(self, ident):
        raw = self._lines("raw")
        prefix = ident + " - "
        for line in raw:
            if line.startswith(prefix):
                return Item("apt", ident, ident, line[len(prefix):], installed=ident in self.installed_ids())
        return None

    def installed_items(self):
        manual = capture(["apt-mark", "showmanual"]).split()
        raw = self._lines("raw")
        summaries = {}
        wanted = set(manual)
        for line in raw:
            name, _, summary = line.partition(" - ")
            if name in wanted:
                summaries[name] = summary
        return [Item("apt", n, n, summaries.get(n, ""), installed=True) for n in sorted(manual)]

    # ---- doing things ----------------------------------------------------------------------------
    def install_cmds(self, item):
        return [Cmd(["apt-get", "install", "-y", item.id], root=True)]

    def remove_cmds(self, item):
        return [Cmd(["apt-get", "remove", "-y", item.id], root=True)]

    def removal_impact(self, item):
        """Packages `apt-get remove` would take away (a simulation), so the user sees side effects first."""
        out = capture(["apt-get", "-s", "remove", item.id])
        return [line.split()[1] for line in out.splitlines() if line.startswith("Remv ")]

    def preview(self, item):
        out = capture(["apt-cache", "show", item.id])
        fields, desc, current = {}, [], None
        for line in out.splitlines():
            if not line.strip():
                break                                    # first (newest) stanza only
            if line[0] in " \t":
                if current == "Description":
                    desc.append(line.strip())
            else:
                key, _, value = line.partition(": ")
                current = key
                fields[key] = value
                if key == "Description":
                    desc = []
        lines = [f"{item.id}  {fields.get('Version', '')}", ""]
        if desc or fields.get("Description"):
            lines += [fields.get("Description", "")] + [d if d != "." else "" for d in desc] + [""]
        for key, label in (("Section", "Section"), ("Installed-Size", "Installed size (KiB)"), ("Homepage", "Homepage"),
                           ("Maintainer", "Maintainer")):
            if key in fields:
                lines.append(f"{label}: {fields[key]}")
        lines.append("")
        lines.append("Installed." if item.installed else "Installs with: sudo apt-get install " + item.id)
        return "\n".join(lines)

    def status(self):
        raw = self._load()["names"]
        return f"{len(raw)} packages indexed" if raw else "no index (run: getapp refresh)"
