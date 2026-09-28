from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .politician import DiscoveredPolitician

# Undocumented API behind the Register of Senators' Interests page
# (https://www.aph.gov.au/Parliamentary_Business/Committees/Senate/Senators_Interests/Senators_Interests_Register).
API_BASE = "https://pbs-apim-aqcdgxhvaug7f8em.z01.azurefd.net/api"
PAGE_SIZE = 100


def list_url(api_base: str, page: int) -> str:
    query = urlencode({"pageSize": PAGE_SIZE, "currentPage": page})
    return f"{api_base}/queryStatements?{query}"


def statement_url(api_base: str, cdap_id: str) -> str:
    return f"{api_base}/getSenatorStatement?{urlencode({'cdapid': cdap_id})}"


def _display_name(name: str) -> str:
    surname, _, given = name.partition(",")
    return f"{given.strip()} {surname.strip()}".strip()


def discover(payload: dict[str, Any], *, api_base: str = API_BASE) -> list[DiscoveredPolitician]:
    if not payload.get("wasSuccessful"):
        raise ValueError(f"senate statement list failed: {payload.get('errors')!r}")
    return [
        DiscoveredPolitician(
            name=_display_name(s["name"]),
            chamber="senate",
            party=s.get("senatorParty") or None,
            electorate_or_state=s.get("state") or None,
            profile_url=None,
            source_url=statement_url(api_base, s["cdapId"]),
            format="json",
        )
        for s in payload["statementOfRegisterableInterests"]
    ]
