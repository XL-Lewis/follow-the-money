from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .politician import DiscoveredPolitician

logger = logging.getLogger(__name__)

INDEX_URL = "https://www.aph.gov.au/Senators_and_Members/Members/Register"

# "Abdo, Mr Basem, Member for Calwell VIC"; title and state are sometimes absent.
_WHO_RE = re.compile(
    r"^(?P<surname>[^,]+),\s*(?P<given>.+?),\s*Member for\s+(?P<division>.+?)"
    r"(?:,?\s+(?P<state>NSW|VIC|QLD|WA|SA|TAS|ACT|NT))?$"
)
_TITLES = {"Hon", "Mr", "Ms", "Mrs", "Miss", "Dr", "Prof"}


def _split_who(who: str) -> tuple[str, str | None]:
    m = _WHO_RE.match(who)
    if m is None:
        logger.warning("unrecognised member label: %r", who)
        return who, None
    given = m["given"].split()
    while given and given[0] in _TITLES:
        given.pop(0)
    name = " ".join([*given, m["surname"].strip()])
    electorate = m["division"] if m["state"] is None else f"{m['division']}, {m['state']}"
    return name, electorate


def discover(html: str, *, base_url: str = INDEX_URL) -> list[DiscoveredPolitician]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[DiscoveredPolitician] = []
    for row in soup.find_all("tr"):
        link = row.select_one("td.format a[href]")
        if link is None:
            continue
        cells = row.find_all("td")
        if len(cells) < 3:
            logger.warning("unexpected register row: %s", row)
            continue
        name, electorate = _split_who(" ".join(cells[1].get_text(" ").split()))
        out.append(
            DiscoveredPolitician(
                name=name,
                chamber="house",
                party=None,
                electorate_or_state=electorate,
                profile_url=None,
                source_url=urljoin(base_url, link["href"]),
                format="pdf",
            )
        )
    return out
