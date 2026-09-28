import json
from pathlib import Path

import pytest

from ftm.declarations import Declaration
from ftm.parse import senate_json

FIXTURE = Path(__file__).parent / "fixtures" / "senate_statement.json"


def _parse() -> list[Declaration]:
    return senate_json.parse(FIXTURE.read_bytes())


def test_statement_interests_join_fields_and_normalise_whitespace():
    decls = _parse()
    assert Declaration("real_estate", "Upper Swan, WA — Investment (jointly held)") in decls
    assert Declaration("liabilities", "Car loan — Plenti") in decls
    assert (
        Declaration(
            "trusts",
            "T & A Whitten Family Trust — Business Investment — "
            "Discretionary beneficiary — trustee",
        )
        in decls
    )


def test_alterations_keep_type_and_canberra_local_date():
    decls = _parse()
    assert (
        Declaration(
            "shareholdings",
            "Whittens Group Pty Ltd",
            change="deletion",
            changed_on="2026-06-04",
        )
        in decls
    )
    # 2025-09-01T22:00:00Z is the morning of 2 September in Canberra.
    assert (
        Declaration(
            "travel",
            "Virgin Australia Beyond Lounge",
            change="addition",
            changed_on="2025-09-02",
        )
        in decls
    )


def test_categories_follow_register_order():
    from ftm.declarations import CATEGORIES

    order = [CATEGORIES.index(d.category) for d in _parse()]
    assert order == sorted(order)


def test_unsuccessful_statement_raises():
    body = json.loads(FIXTURE.read_text())
    body["wasSuccessful"] = "False"
    with pytest.raises(ValueError):
        senate_json.parse(json.dumps(body).encode())


def test_missing_section_raises_rather_than_dropping_data():
    body = json.loads(FIXTURE.read_text())
    del body["gifts"]
    with pytest.raises(KeyError):
        senate_json.parse(json.dumps(body).encode())
