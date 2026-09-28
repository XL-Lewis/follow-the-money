import json
from pathlib import Path

import pytest

from ftm.fetch import senate

FIXTURE = Path(__file__).parent / "fixtures" / "senate_statements_list.json"


def test_discovers_senators_with_party_state_and_statement_url():
    found = senate.discover(json.loads(FIXTURE.read_text()), api_base="https://api.test")
    whitten = found[0]
    assert whitten.name == "Tyron Whitten"
    assert whitten.chamber == "senate"
    assert whitten.party == "One Nation"
    assert whitten.electorate_or_state == "Western Australia"
    assert whitten.source_url == "https://api.test/getSenatorStatement?cdapid=317026"
    assert whitten.format == "json"
    assert [p.name for p in found] == ["Tyron Whitten", "Lisa Darmanin"]


def test_unsuccessful_list_response_raises():
    with pytest.raises(ValueError):
        senate.discover({"wasSuccessful": False, "errors": ["boom"]})
