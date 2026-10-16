"""Snaps from the Snap Store. The Store is searched live (there is no list of everything), with a one-hour cache.
Searching works even if snapd is not installed; installing one offers to install snapd first."""
import hashlib
import json
import os

from .. import paths
from ..fuzzy import score_item
from ..model import Item
from ..runner import Cmd
from .base import Source, capture, fresh, have, write_atomic

API = "https://api.snapcraft.io/v2/snaps"
MAX_AGE = 3600
TIMEOUT = 2.5


def _get(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"Snap-Device-Series": "16", "User-Agent": "getapp"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return json.load(response)


def _cached(name, url):
    """JSON from the Store, cached on disk; None if offline and not cached."""
    folder = paths.cache_dir() / "snap"
    folder.mkdir(exist_ok=True)
    path = folder / (hashlib.sha1(name.encode()).hexdigest() + ".json")
    if fresh(path, MAX_AGE):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            pass
    if os.environ.get("GETAPP_OFFLINE"):
        return None
    try:
        data = _get(url)
    except Exception:
        return None
    write_atomic(path, json.dumps(data))
    return data


class SnapSource(Source):
    name = "snap"
    label = "Snap Store"

    def available(self):
        return True

    def installed_ids(self):
        if not have("snap"):
            return set()
        lines = capture(["snap", "list"]).splitlines()[1:]
        return {line.split()[0] for line in lines if line.split()}

    @staticmethod
    def parse_results(data):
        items = []
        for r in (data or {}).get("results", []):
            snap, rev = r.get("snap", {}), r.get("revision", {})
            items.append(Item("snap", r["name"], snap.get("title") or r["name"], snap.get("summary", ""),
                              extra={"publisher": (snap.get("publisher") or {}).get("display-name", ""),
                                     "verified": (snap.get("publisher") or {}).get("validation") == "verified",
                                     "version": rev.get("version", ""), "confinement": rev.get("confinement", "")}))
        return items

    def search(self, tokens):
        query = " ".join(tokens)
        if len(query) < 3:
            return []
        from urllib.parse import quote
        url = f"{API}/find?q={quote(query)}&fields=title,summary,publisher,version,confinement"
        items = self.parse_results(_cached("find:" + query, url))
        installed = self.installed_ids()
        results = []
        for rank, item in enumerate(items):
            item.installed = item.id in installed
            score = score_item(tokens, item.id.lower(), item.name.lower(), item.summary.lower())
            results.append(((score if score is not None else 150) - rank, item))    # the Store's own order breaks ties
        return results

    def get(self, ident):
        from urllib.parse import quote
        urllib_quote = quote
        url = f"{API}/info/{urllib_quote(ident)}?fields=title,summary,description,publisher,license,website,contact,store-url"
        data = _cached("info:" + ident, url)
        snap = (data or {}).get("snap") or {}
        found = self.parse_results(_cached("find:" + ident, f"{API}/find?q={urllib_quote(ident)}&fields=title,summary,publisher,version,confinement"))
        confinement = next((i.extra.get("confinement", "") for i in found if i.id == ident), "")
        item = Item("snap", ident, snap.get("title") or ident, snap.get("summary", ""),
                    installed=ident in self.installed_ids(),
                    extra={"description": snap.get("description", ""), "license": snap.get("license", ""),
                           "website": snap.get("website", ""), "store": snap.get("store-url", ""),
                           "publisher": (snap.get("publisher") or {}).get("display-name", ""), "confinement": confinement})
        return item

    def installed_items(self):
        if not have("snap"):
            return []
        items = []
        for line in capture(["snap", "list"]).splitlines()[1:]:
            parts = line.split()
            if parts:
                items.append(Item("snap", parts[0], parts[0], "", installed=True))
        return items

    def install_cmds(self, item):
        cmds = []
        if not have("snap"):
            cmds.append(Cmd(["apt-get", "install", "-y", "snapd"], root=True))
        classic = item.extra.get("confinement") == "classic"
        cmds.append(Cmd(["snap", "install", item.id] + (["--classic"] if classic else []), root=True))
        return cmds

    def remove_cmds(self, item):
        return [Cmd(["snap", "remove", item.id], root=True)]

    def preview(self, item):
        x = item.extra
        lines = [f"{item.name}  ({item.id})", ""]
        if item.summary:
            lines += [item.summary, ""]
        if x.get("description"):
            lines += [x["description"].strip(), ""]
        for key, label in (("publisher", "Publisher"), ("version", "Version"), ("license", "License"),
                           ("confinement", "Confinement"), ("website", "Website"), ("store", "Store page")):
            if x.get(key):
                tick = " (verified)" if key == "publisher" and x.get("verified") else ""
                lines.append(f"{label}: {x[key]}{tick}")
        lines.append("")
        if item.installed:
            lines.append("Installed.")
        else:
            lines.append("Installs with: sudo snap install " + item.id + (" --classic" if x.get("confinement") == "classic" else ""))
            if not have("snap"):
                lines.append("snapd is not installed here: getapp will offer to install it first.")
        return "\n".join(lines)

    def status(self):
        return "snapd installed" if have("snap") else "snapd not installed (searching works; installing offers to set it up)"
