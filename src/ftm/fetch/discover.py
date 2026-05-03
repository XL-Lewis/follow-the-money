from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

DocKind = Literal["statement", "alteration"]

_STATEMENT_RE = re.compile(r"\bStatement of Registrable Interests\b", re.IGNORECASE)
_ALTERATION_RE = re.compile(r"\bNotification of Alteration\b", re.IGNORECASE)


@dataclass(frozen=True)
class DiscoveredPolitician:
    name: str
    chamber: str
    party: str | None
    electorate_or_state: str | None
    profile_url: str | None
    documents: list[tuple[DocKind, str]] = field(default_factory=list)


def _classify(text: str) -> DocKind | None:
    if _STATEMENT_RE.search(text):
        return "statement"
    if _ALTERATION_RE.search(text):
        return "alteration"
    return None


def _row_documents(row: Tag, base_url: str) -> list[tuple[DocKind, str]]:
    docs: list[tuple[DocKind, str]] = []
    for a in row.find_all("a", href=True):
        kind = _classify(a.get_text(" ", strip=True))
        if kind is None:
            continue
        docs.append((kind, urljoin(base_url, a["href"])))
    return docs


def _row_politician_anchor(row: Tag) -> Tag | None:
    a = row.find("a", class_="member-name", href=True)
    if a is not None:
        return a
    a = row.find("a", href=True)
    return a


def discover_from_html(
    html: str, *, base_url: str, chamber: str
) -> list[DiscoveredPolitician]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[DiscoveredPolitician] = []
    for row in soup.find_all("tr"):
        docs = _row_documents(row, base_url)
        if not docs:
            continue
        name_a = _row_politician_anchor(row)
        if name_a is None:
            logger.warning("row with declarations but no name anchor: %s", row)
            continue
        name = name_a.get_text(" ", strip=True)
        profile_url = urljoin(base_url, name_a["href"]) if name_a.get("href") else None

        cells = row.find_all("td")
        party = cells[1].get_text(" ", strip=True) if len(cells) > 1 else None
        electorate = cells[2].get_text(" ", strip=True) if len(cells) > 2 else None

        out.append(
            DiscoveredPolitician(
                name=name,
                chamber=chamber,
                party=party or None,
                electorate_or_state=electorate or None,
                profile_url=profile_url,
                documents=docs,
            )
        )
    return out
