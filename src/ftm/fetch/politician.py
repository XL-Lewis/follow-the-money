from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DocFormat = Literal["pdf", "json"]


@dataclass(frozen=True)
class DiscoveredPolitician:
    name: str
    chamber: str
    party: str | None
    electorate_or_state: str | None
    profile_url: str | None
    source_url: str
    format: DocFormat
