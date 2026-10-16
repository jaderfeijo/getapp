from dataclasses import dataclass, field

SOURCES = ("web", "flatpak", "snap", "apt")        # also the tie-break order when two results score the same


@dataclass
class Item:
    source: str                 # one of SOURCES
    id: str                     # what the source's tool installs (apt package, Flatpak app id, snap name, web slug)
    name: str                   # display name
    summary: str = ""
    installed: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def key(self):
        return f"{self.source}:{self.id}"
