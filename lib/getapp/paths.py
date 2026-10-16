"""Where getapp keeps things. Every location can be overridden through the environment (used by the tests)."""
import os
from pathlib import Path


def _xdg(var, default):
    return Path(os.environ.get(var) or Path.home() / default)


def cache_dir():
    p = Path(os.environ.get("GETAPP_CACHE_DIR") or _xdg("XDG_CACHE_HOME", ".cache") / "getapp")
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir():
    return Path(os.environ.get("GETAPP_CONFIG_DIR") or _xdg("XDG_CONFIG_HOME", ".config") / "getapp")


def data_home():
    return Path(os.environ.get("GETAPP_DATA_HOME") or _xdg("XDG_DATA_HOME", ".local/share"))


def applications_dir():
    return data_home() / "applications"


def icons_dir():
    return data_home() / "icons" / "hicolor" / "256x256" / "apps"


def shipped_data_dir():
    """The folder with webapps.tsv: next to the package when installed, or in the source tree."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "data", here.parent.parent / "data", here.parent / "data"):
        if (candidate / "webapps.tsv").exists():
            return candidate
    return here / "data"
