from pathlib import Path

from ftm.fetch.house import discover

FIXTURE = Path(__file__).parent / "fixtures" / "house_register_index.html"
BASE = "https://www.aph.gov.au/Senators_and_Members/Members/Register"


def _load() -> list:
    return discover(FIXTURE.read_text(), base_url=BASE)


def test_parses_politicians_from_index():
    pols = _load()
    names = [p.name for p in pols]
    assert "Jane DOE" in names
    assert "John SMITH" in names
    assert all(p.chamber == "house" for p in pols)
    # Skip rows without declaration links
    assert len(pols) == 2


def test_party_and_electorate_extracted():
    pols = {p.name: p for p in _load()}
    jane = pols["Jane DOE"]
    assert jane.party == "Liberal Party of Australia"
    assert jane.electorate_or_state == "Wentworth, NSW"


def test_classifies_statement_vs_alteration_links():
    pols = {p.name: p for p in _load()}
    jane_kinds = [k for k, _ in pols["Jane DOE"].documents]
    assert "statement" in jane_kinds
    assert "alteration" in jane_kinds

    john_kinds = [k for k, _ in pols["John SMITH"].documents]
    assert john_kinds == ["statement"]


def test_relative_urls_resolved_to_absolute():
    pols = {p.name: p for p in _load()}
    jane_urls = [u for _, u in pols["Jane DOE"].documents]
    assert all(u.startswith("https://www.aph.gov.au/") for u in jane_urls)

    john_urls = dict(pols["John SMITH"].documents)
    assert john_urls["statement"] == "https://www.aph.gov.au/files/john-statement.pdf"


def test_profile_url_resolved():
    pols = {p.name: p for p in _load()}
    assert pols["Jane DOE"].profile_url and pols["Jane DOE"].profile_url.startswith(
        "https://www.aph.gov.au/"
    )


def test_skips_unrecognised_links():
    # The "About the register" link should be ignored.
    pols = {p.name: p for p in _load()}
    john_urls = [u for _, u in pols["John SMITH"].documents]
    assert all("About-the-register" not in u for u in john_urls)
