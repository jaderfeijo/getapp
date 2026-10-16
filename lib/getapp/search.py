"""One ranked list across all sources, and the line format fzf shows."""
from .fuzzy import parse_query
from .model import SOURCES
from .sources import all_sources, by_name

BADGES = {"web": ("web", "35"), "flatpak": ("flatpak", "34"), "snap": ("snap", "33"), "apt": ("apt", "32")}
SNAP_WAIT = 1.0                    # seconds to wait for the Snap Store before showing the other results


def search(query, limit=300):
    tokens, only = parse_query(query)
    sources = [s for s in all_sources() if only in (None, s.name)]
    order = {name: i for i, name in enumerate(SOURCES)}
    results = []
    slow = [s for s in sources if s.name == "snap" and len(" ".join(tokens)) >= 3]      # the one that may use the network
    fast = [s for s in sources if s.name != "snap"]
    pending = {}
    pool = None
    if slow:
        import concurrent.futures
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        pending = {pool.submit(s.search, tokens): s for s in slow}            # runs while the local sources work
    for s in fast:
        try:
            results += [(sc, order[s.name], item) for sc, item in s.search(tokens)]
        except Exception:
            pass
    for future, s in pending.items():
        try:
            results += [(sc, order[s.name], item) for sc, item in future.result(timeout=SNAP_WAIT)]
        except Exception:
            pass
    if pool:
        pool.shutdown(wait=False, cancel_futures=True)
    results.sort(key=lambda r: (-r[0], r[1], len(r[2].id), r[2].id))
    return [r[2] for r in results[:limit]]


def format_line(item, color=True):
    """`key<TAB>display` : fzf shows the display part and hands back the key."""
    name, code = BADGES[item.source]
    mark = "✓" if item.installed else " "
    summary = " ".join(item.summary.split())[:140]
    if color:
        mark = f"\033[1;32m{mark}\033[0m" if item.installed else mark
        badge = f"\033[{code}m{name:<8}\033[0m"
        title = f"\033[1m{item.name[:30]:<30}\033[0m"
        summary = f"\033[2m{summary}\033[0m"
    else:
        badge, title = f"{name:<8}", f"{item.name[:30]:<30}"
    return f"{item.key}\t{mark} {badge} {title} {summary}"


def resolve(key):
    """Item for a `source:id` key, or None."""
    source, _, ident = key.partition(":")
    src = by_name().get(source)
    return src.get(ident) if src else None
