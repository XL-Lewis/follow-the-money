from pathlib import Path

from ftm.fetch.senate import discover

FIXTURE = Path(__file__).parent / "fixtures" / "senate_register_index.html"
BASE = "https://www.aph.gov.au/Senators_and_Members/Senators/Register_of_Senators_Interests"


def _load() -> list:
    return discover(FIXTURE.read_text(), base_url=BASE)


def test_parses_senators_with_chamber_senate():
    pols = _load()
    assert {p.name for p in pols} == {"Alice JONES", "Bob LEE"}
    assert all(p.chamber == "senate" for p in pols)


def test_state_captured_in_electorate_or_state_field():
    pols = {p.name: p for p in _load()}
    assert pols["Alice JONES"].electorate_or_state == "VIC"
    assert pols["Bob LEE"].electorate_or_state == "NSW"


def test_alteration_classified():
    pols = {p.name: p for p in _load()}
    bob_kinds = [k for k, _ in pols["Bob LEE"].documents]
    assert "alteration" in bob_kinds
    assert bob_kinds.count("statement") == 1
