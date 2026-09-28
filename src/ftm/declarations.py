from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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

Change = Literal["statement", "addition", "deletion"]
CHANGES: tuple[Change, ...] = ("statement", "addition", "deletion")

Holder = Literal["self", "spouse", "dependent"]
HOLDERS: tuple[Holder, ...] = ("self", "spouse", "dependent")


@dataclass(frozen=True)
class Declaration:
    """One declared interest, or one alteration to the original statement.

    `changed_on` is an ISO date (YYYY-MM-DD) and only applies to alterations.
    `holder` is None when the source does not say whose interest it is.
    """

    category: str
    item_text: str
    change: Change = "statement"
    holder: Holder | None = None
    changed_on: str | None = None
