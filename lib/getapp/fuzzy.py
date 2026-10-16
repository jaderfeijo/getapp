"""Query parsing and ranking. Every space-separated word of the query must match; the score says how well."""
from .model import SOURCES

NOISE_SUFFIXES = ("-dev", "-dbg", "-dbgsym", "-doc", "-data", "-common", "-l10n", "-i18n", "-locales")
WORD_BREAKS = "-_. /"


def parse_query(query):
    """-> (tokens, only_source). `flatpak:firefox` or `snap: vlc` restricts the search to one source."""
    tokens, only = [], None
    for raw in query.lower().split():
        head, colon, rest = raw.partition(":")
        if colon and head in SOURCES:
            only = head
            if rest:
                tokens.append(rest)
            continue
        tokens.append(raw)
    return tokens, only


def is_subsequence(needle, hay):
    it = iter(hay)
    return all(ch in it for ch in needle)


def subsequence_score(needle, hay):
    """How good a loose (typo-tolerant) match is, 60..120; None if `needle` is not a subsequence of `hay`.
    Tight matches, and ones that start at the beginning, score higher."""
    start = hay.find(needle[0])
    if start < 0:
        return None
    pos, first = start, start
    for ch in needle[1:]:
        pos = hay.find(ch, pos + 1)
        if pos < 0:
            return None
    span = pos - first + 1
    return 60 + int(40 * len(needle) / span) + (20 if first == 0 else 0)


def match_token(token, ident, name, summary):
    """Score of one query word against an item (None = no match). All three texts are already lower-case."""
    best = None
    for text in (ident, name):
        if not text:
            continue
        if text == token:
            return 1000
        if text.startswith(token):
            score = 800
        else:
            i = text.find(token)
            if i >= 0:
                score = 650 if text[i - 1] in WORD_BREAKS else 500
            else:
                score = subsequence_score(token, text) if len(token) >= 3 else None
        if score is not None and (best is None or score > best):
            best = score
    if best is not None:
        return best
    i = summary.find(token)
    if i >= 0:
        return 260 if (i == 0 or summary[i - 1] == " ") else 200
    return None


def is_noise(ident):
    """Libraries, -dev / -dbg / -doc packages and the like: valid hits, but rarely what someone is looking for."""
    return ident.startswith("lib") and (ident[-1:].isdigit() or ident.endswith("t64")) or ident.endswith(NOISE_SUFFIXES)


def score_item(tokens, ident, name, summary):
    """Total score for an item (texts lower-cased), or None if any word does not match."""
    total = 0
    for token in tokens:
        s = match_token(token, ident, name, summary)
        if s is None:
            return None
        total += s
    if is_noise(ident) and not any(t.startswith(("lib", "-")) or t.endswith(NOISE_SUFFIXES) for t in tokens):
        total -= 600
    return total


def sort_key(source_order, score, ident):
    return (-score, source_order, len(ident), ident)
