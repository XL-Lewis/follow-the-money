from __future__ import annotations

from .discover import DiscoveredPolitician, discover_from_html

INDEX_URL = "https://www.aph.gov.au/Senators_and_Members/Members/Register"


def discover(html: str, *, base_url: str = INDEX_URL) -> list[DiscoveredPolitician]:
    return discover_from_html(html, base_url=base_url, chamber="house")
