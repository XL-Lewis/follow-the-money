from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from ..declarations import Change, Declaration

logger = logging.getLogger(__name__)

# API section key -> canonical category, in register order.
SECTIONS: dict[str, str] = {
    "shareHoldings": "shareholdings",
    "trusts": "trusts",
    "realEstate": "real_estate",
    "registeredDirectorshipsOfCompanies": "directorships",
    "partnerships": "partnerships",
    "liabilities": "liabilities",
    "investments": "bonds",
    "savingsOrInvestmentAccounts": "savings",
    "otherAssets": "other_assets",
    "otherIncome": "income",
    "gifts": "gifts",
    "sponsoredTravelOrHospitality": "travel",
    "officeHolderDonating": "memberships",
    "otherInterest": "other",
}

_CHANGES: dict[str, Change] = {"Addition": "addition", "Deletion": "deletion"}
_CANBERRA = ZoneInfo("Australia/Sydney")


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _local_date(timestamp: str) -> str:
    # Timestamps are UTC; the register day is Canberra-local.
    utc = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return utc.astimezone(_CANBERRA).date().isoformat()


def parse(body: bytes) -> list[Declaration]:
    data = json.loads(body)
    if str(data.get("wasSuccessful")) != "True":
        raise ValueError(f"senate statement not successful: {data.get('errors')!r}")

    unknown = {
        k for k, v in data.items() if isinstance(v, dict) and "interests" in v
    } - SECTIONS.keys()
    if unknown:
        logger.warning("ignoring unknown senate sections: %s", sorted(unknown))

    out: list[Declaration] = []
    for key, category in SECTIONS.items():
        section = data[key]
        for interest in section["interests"]:
            text = " — ".join(
                v for k, raw in interest.items() if k != "id" and (v := _clean(raw))
            )
            if text:
                out.append(Declaration(category=category, item_text=text))
        for alt in section["alterations"]:
            text = _clean(alt["details"])
            if not text:
                continue
            out.append(
                Declaration(
                    category=category,
                    item_text=text,
                    change=_CHANGES[alt["alterationType"]],
                    changed_on=_local_date(alt["createdOn"]),
                )
            )
    return out
