from __future__ import annotations

import re
from typing import Iterable, Iterator

CATEGORIES: list[str] = [
    "shareholdings",
    "trusts",
    "real_estate",
    "directorships",
    "partnerships",
    "liabilities",
    "bonds",
    "savings",
    "other_assets",
    "income",
    "gifts",
    "travel",
    "memberships",
    "other",
]

# Match the leading word(s) of each numbered section heading. The form text is
# verbose; we anchor on the first few distinctive words.
_HEADING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("shareholdings", re.compile(r"^\s*1\.\s*Shareholdings\b", re.IGNORECASE)),
    ("trusts", re.compile(r"^\s*2\.\s*Family and business trusts\b", re.IGNORECASE)),
    ("real_estate", re.compile(r"^\s*3\.\s*Real estate\b", re.IGNORECASE)),
    ("directorships", re.compile(r"^\s*4\.\s*Registered directorships\b", re.IGNORECASE)),
    ("partnerships", re.compile(r"^\s*5\.\s*Partnerships\b", re.IGNORECASE)),
    ("liabilities", re.compile(r"^\s*6\.\s*Liabilities\b", re.IGNORECASE)),
    ("bonds", re.compile(r"^\s*7\.\s*(The nature of any )?bonds\b", re.IGNORECASE)),
    ("savings", re.compile(r"^\s*8\.\s*Savings\b", re.IGNORECASE)),
    (
        "other_assets",
        re.compile(r"^\s*9\.\s*(The nature of any )?other assets\b", re.IGNORECASE),
    ),
    (
        "income",
        re.compile(
            r"^\s*10\.\s*(The nature of any )?other substantial sources of income\b",
            re.IGNORECASE,
        ),
    ),
    ("gifts", re.compile(r"^\s*11\.\s*Gifts\b", re.IGNORECASE)),
    (
        "travel",
        re.compile(r"^\s*12\.\s*(Any )?sponsored travel\b", re.IGNORECASE),
    ),
    ("memberships", re.compile(r"^\s*13\.\s*Membership", re.IGNORECASE)),
    ("other", re.compile(r"^\s*14\.\s*(Any )?other interests\b", re.IGNORECASE)),
]

_NUMBERED_HEADING_RE = re.compile(r"^\s*\d{1,2}\.\s+\S")
_NIL_RE = re.compile(r"^\s*nil\.?\s*$", re.IGNORECASE)
_PAGE_RE = re.compile(r"^\s*page\s+\d+\s*$", re.IGNORECASE)


def _classify_heading(line: str) -> str | None:
    for cat, pattern in _HEADING_PATTERNS:
        if pattern.match(line):
            return cat
    return None


def _is_unknown_heading(line: str) -> bool:
    return bool(_NUMBERED_HEADING_RE.match(line))


def _split_into_items(body_lines: list[str]) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for raw in body_lines:
        line = raw.rstrip()
        if _PAGE_RE.match(line):
            continue
        if not line.strip():
            if current:
                items.append(" ".join(current).strip())
                current = []
            continue
        current.append(line.strip())
    if current:
        items.append(" ".join(current).strip())
    items = [it for it in items if it and not _NIL_RE.match(it)]
    return items


def split_into_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {cat: [] for cat in CATEGORIES}

    lines = text.splitlines()
    current_cat: str | None = None
    body: list[str] = []

    def flush():
        nonlocal body
        if current_cat is not None:
            sections[current_cat] = _split_into_items(body)
        body = []

    for line in lines:
        cat = _classify_heading(line)
        if cat is not None:
            flush()
            current_cat = cat
            body = []
            continue
        if current_cat is not None and _is_unknown_heading(line):
            # Unknown numbered heading: drop the section we were collecting and
            # stop accumulating until the next known heading.
            flush()
            current_cat = None
            body = []
            continue
        if current_cat is not None:
            body.append(line)

    flush()
    return sections


def iter_items(sections: dict[str, list[str]]) -> Iterator[tuple[str, str]]:
    for cat in CATEGORIES:
        for item in sections.get(cat, []):
            yield cat, item
