"""Flatpak apps from Flathub. Searches a local list refreshed once a day."""
import gzip
import os
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import paths
from ..fuzzy import score_item
from ..model import Item
from ..runner import Cmd
from .base import Source, capture, fresh, have, write_atomic

REMOTE = "flathub"
MAX_AGE = 24 * 3600


class FlatpakSource(Source):
    name = "flatpak"
    label = "Flatpak (Flathub)"

    def __init__(self):
        self._rows = None

    def _file(self):
        return paths.cache_dir() / "flatpak.tsv"

    def available(self):
        return have("flatpak")

    @staticmethod
    def _appstream_files():
        roots = [Path("/var/lib/flatpak/appstream"), Path.home() / ".local/share/flatpak/appstream"]
        return [f for root in roots for f in sorted(root.glob(f"{REMOTE}/*/active/appstream.xml.gz"))]

    @staticmethod
    def parse_appstream(fileobj):
        """(app id, name, summary) for every desktop application in a Flathub AppStream file."""
        rows = []
        for _, el in ET.iterparse(fileobj, events=("end",)):
            if el.tag == "component":
                if el.get("type") in ("desktop-application", "desktop"):
                    name = summary = None
                    for child in el:
                        if child.tag == "name" and not child.attrib:        # attribute-free = the default language
                            name = child.text
                        elif child.tag == "summary" and not child.attrib:
                            summary = child.text
                    app_id = (el.findtext("id") or "").strip()
                    if app_id:
                        rows.append((app_id, (name or app_id).strip(), " ".join((summary or "").split())))
                el.clear()
        return rows

    def refresh(self):
        """Flathub's AppStream file has names and summaries (`flatpak remote-ls` has no descriptions)."""
        if not self.available():
            return
        rows = []
        for f in self._appstream_files():
            try:
                with gzip.open(f) as fh:
                    rows = self.parse_appstream(fh)
                break
            except (OSError, ET.ParseError):
                continue
        if not rows:                                              # no AppStream data yet: names only
            out = capture(["flatpak", "remote-ls", "--app", "--columns=application,name", REMOTE], timeout=120)
            rows = [tuple(line.split("\t")[:2]) + ("",) for line in out.splitlines() if "\t" in line]
        if rows:
            write_atomic(self._file(), "\n".join("\t".join(r) for r in rows) + "\n")
        self._rows = None

    def _load(self):
        if self._rows is None:
            if self.available() and not os.environ.get("GETAPP_NO_REFRESH") and not fresh(self._file(), MAX_AGE):
                self.refresh()
            rows = []
            try:
                text = self._file().read_text(errors="replace")
            except OSError:
                text = ""
            for line in text.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0]:
                    rows.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
            self._rows = rows
        return self._rows

    def installed_ids(self):
        """Installed app ids: the folder names under the flatpak app directories (instant); `flatpak list` as fallback."""
        folders = [Path("/var/lib/flatpak/app"), Path.home() / ".local/share/flatpak/app"]
        found = {p.name for folder in folders if folder.is_dir() for p in folder.iterdir()}
        if found or not self.available():
            return found
        out = capture(["flatpak", "list", "--app", "--columns=application"])
        return {line.strip() for line in out.splitlines() if line.strip()}

    def search(self, tokens):
        rows = self._load()
        if not rows or not tokens:
            return []
        installed = self.installed_ids()
        results = []
        for app_id, name, summary in rows:
            score = score_item(tokens, app_id.lower(), name.lower(), summary.lower())
            if score is not None:
                results.append((score, Item("flatpak", app_id, name, summary, installed=app_id in installed)))
        return results

    def get(self, ident):
        for app_id, name, summary in self._load():
            if app_id == ident:
                return Item("flatpak", app_id, name, summary, installed=ident in self.installed_ids())
        return Item("flatpak", ident, ident.split(".")[-1], "")

    def installed_items(self):
        if not self.available():
            return []
        out = capture(["flatpak", "list", "--app", "--columns=application,name,installation"])
        items = []
        for line in out.splitlines():
            parts = line.split("\t")
            if parts and parts[0].strip():
                items.append(Item("flatpak", parts[0].strip(), parts[1].strip() if len(parts) > 1 else parts[0],
                                  "", installed=True, extra={"installation": parts[2].strip() if len(parts) > 2 else "system"}))
        return items

    def install_cmds(self, item):
        user = os.environ.get("GETAPP_FLATPAK_SCOPE") == "user"
        cmds = []
        if not have("flatpak"):
            cmds.append(Cmd(["apt-get", "install", "-y", "flatpak"], root=True))
        cmds.append(Cmd(["flatpak", "remote-add", "--if-not-exists"] + (["--user"] if user else []) +
                        [REMOTE, "https://dl.flathub.org/repo/flathub.flatpakrepo"], root=not user))
        cmds.append(Cmd(["flatpak", "install", "-y", "--noninteractive"] + (["--user"] if user else []) + [REMOTE, item.id],
                        root=not user))
        return cmds

    def remove_cmds(self, item):
        user = item.extra.get("installation") == "user"
        return [Cmd(["flatpak", "uninstall", "-y", "--noninteractive", item.id], root=not user)]

    def preview(self, item):
        lines = [item.name, item.id, "", item.summary, ""]
        lines.append("Installed." if item.installed else f"Installs with: flatpak install {REMOTE} {item.id}")
        lines.append("Flatpak apps are sandboxed and come from Flathub.")
        return "\n".join(lines)

    def status(self):
        if not self.available():
            return "flatpak is not installed (getapp setup flatpak)"
        n = len(self._load())
        return f"{n} apps from {REMOTE}" if n else f"no apps listed; is the {REMOTE} remote set up? (getapp setup flatpak)"
