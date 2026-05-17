"""Flux RSS suivis pour le Flash Info Karukera."""

from dataclasses import dataclass
from pathlib import Path
from urllib.request import pathname2url


@dataclass(frozen=True)
class RssSource:
    name: str
    url: str
    category: str  # "specialisee" | "magazine" | "equipementier"
    pays: str      # "International"


RSS_SOURCES: list[RssSource] = [
    # Sources spécialisées freinage
    RssSource(
        name="The BRAKE Report",
        url="https://thebrakereport.com/feed",
        category="specialisee",
        pays="International",
    ),
    RssSource(
        name="Dynamic Friction Company (DFC)",
        url="https://dynamicfriction.com/blog/feed",
        category="specialisee",
        pays="International",
    ),
    RssSource(
        name="DON Brakes (TMD Friction)",
        url="https://don-brakes.com/feed",
        category="specialisee",
        pays="International",
    ),
    RssSource(
        name="Advanced Braking Technology (ABT)",
        url="https://advancedbraking.com/feed",
        category="specialisee",
        pays="International",
    ),
    RssSource(
        name="Brakestoyou",
        url="https://brakestoyou.com/blog-feed.xml",
        category="specialisee",
        pays="International",
    ),

    # Magazines automobile (rubrique freinage)
    RssSource(
        name="Vehicle Dynamics International (général)",
        url="https://www.vehicledynamicsinternational.com/feed",
        category="magazine",
        pays="International",
    ),
    RssSource(
        name="Vehicle Dynamics International (freinage uniquement)",
        url="https://www.vehicledynamicsinternational.com/news/braking/feed",
        category="magazine",
        pays="International",
    ),
    RssSource(
        name="Autotechnician Magazine",
        url="https://www.autotechnician.co.uk/feed",
        category="magazine",
        pays="International",
    ),

    # Équipementiers freinage
    RssSource(
        name="Akebono Brakes",
        url="https://www.akebonobrakes.com/feed",
        category="equipementier",
        pays="International",
    ),
    RssSource(
        name="MGM Brakes",
        url="https://www.mgmbrakes.com/feed",
        category="equipementier",
        pays="International",
    ),
]

RSS_FEEDS: list[str] = [s.url for s in RSS_SOURCES]
