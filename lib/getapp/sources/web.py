"""Web apps: a site installed as a standalone window with Chromium's --app mode (no tabs, no address bar).
A catalog is shipped; any URL typed into the search can be installed too."""
import os
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from .. import paths
from ..fuzzy import score_item
from ..model import Item
from ..runner import Cmd
from .base import Source, have

BROWSERS = ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "brave-browser",
            "microsoft-edge-stable", "vivaldi")
MARKER = "X-Getapp-Source=web"
URL_RE = re.compile(r"^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(:\d+)?(/\S*)?$", re.I)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "app"


def normalize_url(text):
    url = text.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url):
        url = "https://" + url
    if re.search(r"\s", url) or not re.match(r"^https?://", url, re.I):
        raise ValueError("a web app needs an http(s) address without spaces")
    return url


def window_class(url):
    """The window class Chromium gives an --app window, so the desktop entry can claim it (StartupWMClass)."""
    address = url.split("://", 1)[-1]
    address = re.split(r"[?#]", address, maxsplit=1)[0]
    host, _, path = address.partition("/")
    host = host.rpartition("@")[2].split(":")[0].lower()
    path = "/" + path if path else "/"
    return re.sub("/", "_", f"chrome-{host}_{path}-Default")


def find_browser():
    return next((b for b in BROWSERS if have(b)), None)


def desktop_escape(value):
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")


def exec_quote(value):
    return '"' + re.sub(r'(["`$\\])', r"\\\1", value).replace("%", "%%") + '"'


def desktop_text(name, url, browser, icon):
    return "\n".join([
        "[Desktop Entry]", "Version=1.0", "Type=Application",
        f"Name={desktop_escape(name)}", f"Comment={desktop_escape(name)} (web app)",
        f"Exec={browser} --app={exec_quote(url)}", f"Icon={icon}", "Terminal=false", "StartupNotify=true",
        f"StartupWMClass={window_class(url)}", "Categories=Network;", MARKER, f"X-Getapp-URL={desktop_escape(url)}", ""])


def fetch_icon(url, dest):
    """Download the site's icon to `dest` (PNG). Returns True on success. Tries the site's own touch icon first."""
    if os.environ.get("GETAPP_OFFLINE"):
        return False

    def get(u, limit=2_000_000):
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 getapp"})
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.read(limit), r.headers.get_content_type()

    origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(url))
    candidates = []
    try:
        html = get(url, 100_000)[0].decode("utf-8", "replace")
        m = re.search(r"<link[^>]*rel=[\"'][^\"']*apple-touch-icon[^\"']*[\"'][^>]*>", html, re.I)
        href = re.search(r"href=[\"']([^\"']+)", m.group(0), re.I).group(1) if m else None
        if href:
            candidates.append(urllib.parse.urljoin(url, href))
    except Exception:
        pass
    candidates += [origin + "/apple-touch-icon.png",
                   "https://www.google.com/s2/favicons?domain=" + urllib.parse.quote(url, safe="") + "&sz=256"]
    for candidate in candidates:
        try:
            data, kind = get(candidate)
        except Exception:
            continue
        if data and kind.startswith("image/"):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return True
    return False


class WebSource(Source):
    name = "web"
    label = "Web apps"

    # ---- catalog -------------------------------------------------------------------------------------
    def catalog(self):
        rows = []
        for path in (paths.shipped_data_dir() / "webapps.tsv", paths.config_dir() / "webapps.tsv"):
            try:
                text = path.read_text()
            except OSError:
                continue
            for line in text.splitlines():
                if line.strip() and not line.startswith("#"):
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        rows.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
        return rows

    def _installed_files(self):
        folder = paths.applications_dir()
        if not folder.is_dir():
            return {}
        found = {}
        for f in folder.glob("getapp-*.desktop"):
            try:
                text = f.read_text()
            except OSError:
                continue
            if MARKER in text:
                found[f.stem[len("getapp-"):]] = f
        return found

    def installed_ids(self):
        return set(self._installed_files())

    def _items(self):
        installed = self.installed_ids()
        return [Item("web", slugify(n), n, f"{d}  ({u.split('://', 1)[-1].rstrip('/')})" if d else u,
                     installed=slugify(n) in installed, extra={"url": u}) for n, u, d in self.catalog()]

    def custom_item(self, tokens):
        for t in tokens:
            if URL_RE.match(t):
                try:
                    url = normalize_url(t)
                except ValueError:
                    continue
                host = urllib.parse.urlparse(url).netloc
                return Item("web", "custom:" + url, f"Web app: {url}", f"Install {host} as its own window", extra={"url": url})
        return None

    def search(self, tokens):
        results = []
        for item in self._items():
            score = score_item(tokens, item.id, item.name.lower(), item.summary.lower()) if tokens else 400
            if score is not None:
                results.append((score, item))
        custom = self.custom_item(tokens)
        if custom:
            results.append((900, custom))                      # a typed address is a strong hint
        return results

    def get(self, ident):
        if ident.startswith("custom:"):
            return self.custom_item([ident[len("custom:"):]])
        return next((i for i in self._items() if i.id == ident), None)

    def installed_items(self):
        items = []
        for slug, f in self._installed_files().items():
            text = f.read_text()
            name = re.search(r"^Name=(.*)$", text, re.M)
            url = re.search(r"^X-Getapp-URL=(.*)$", text, re.M)
            items.append(Item("web", slug, name.group(1) if name else slug, url.group(1) if url else "", installed=True,
                              extra={"url": url.group(1) if url else "", "file": str(f)}))
        return items

    # ---- doing things --------------------------------------------------------------------------------
    def install_cmds(self, item):
        url = item.extra["url"]
        name = item.name if not item.id.startswith("custom:") else (urllib.parse.urlparse(url).netloc.removeprefix("www."))
        slug = slugify(name)
        cmds = []
        if find_browser() is None:
            cmds.append(Cmd(["apt-get", "install", "-y", "chromium"], root=True))

        def create():
            browser = find_browser() or "chromium"
            icon_name = slug
            icon_path = paths.icons_dir() / f"getapp-{slug}.png"
            icon_name = f"getapp-{slug}" if fetch_icon(url, icon_path) else "web-browser"
            target = paths.applications_dir() / f"getapp-{slug}.desktop"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(desktop_text(name.title() if item.id.startswith("custom:") else name, url, browser, icon_name))
            target.chmod(0o755)
            return True
        cmds.append(Cmd(call=create, label=f"create the launcher for {name} ({url}) and fetch its icon"))
        return cmds

    def remove_cmds(self, item):
        def remove():
            f = Path(item.extra.get("file") or paths.applications_dir() / f"getapp-{item.id}.desktop")
            f.unlink(missing_ok=True)
            (paths.icons_dir() / f"getapp-{item.id}.png").unlink(missing_ok=True)
            return True
        return [Cmd(call=remove, label=f"remove the launcher for {item.name}")]

    def preview(self, item):
        url = item.extra.get("url", "")
        lines = [item.name, "", item.summary if not item.id.startswith("custom:") else "", f"Address: {url}", "",
                 "Opens as its own window: no tabs, no address bar. Uses " + (find_browser() or "Chromium (will be installed)") + ".",
                 "Shows up in your app launcher like any other app.", ""]
        lines.append("Installed." if item.installed else "Installs as a launcher: no software is added to the system.")
        return "\n".join(l for l in lines if l is not None)

    def status(self):
        n = len(self.catalog())
        browser = find_browser()
        return f"{n} apps in the catalog; browser: {browser or 'none yet (Chromium will be offered)'}"
