from .apt import AptSource
from .flatpak import FlatpakSource
from .snap import SnapSource
from .web import WebSource


def all_sources():
    return [WebSource(), FlatpakSource(), SnapSource(), AptSource()]


def by_name():
    return {s.name: s for s in all_sources()}
