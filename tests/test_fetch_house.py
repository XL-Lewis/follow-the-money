from pathlib import Path

from ftm.fetch import house

FIXTURE = Path(__file__).parent / "fixtures" / "house_register_index.html"


def _by_name():
    return {p.name: p for p in house.discover(FIXTURE.read_text())}


def test_discovers_every_member_row_across_letter_tables():
    found = house.discover(FIXTURE.read_text())
    assert len(found) == 6
    assert {p.chamber for p in found} == {"house"}
    assert {p.format for p in found} == {"pdf"}


def test_parses_titled_member_label():
    abdo = _by_name()["Basem Abdo"]
    assert abdo.electorate_or_state == "Calwell, VIC"
    assert (
        abdo.source_url
        == "https://interests-register-api-public.aph.gov.au/api/members/316915/statement/48"
    )


def test_parses_label_without_title_or_state():
    french = _by_name()["Thomas French"]
    assert french.electorate_or_state == "Moore"


def test_strips_honorific_and_keeps_static_pdf_url():
    albanese = _by_name()["Anthony Albanese"]
    assert albanese.electorate_or_state == "Grayndler, NSW"
    assert albanese.source_url.startswith("https://static.aph.gov.au/")
    assert "Albanese_48P.pdf?rev=" in albanese.source_url


def test_unrecognised_label_falls_back_to_raw_text():
    html = """<table><tr><td class="date">1 July 2025</td>
    <td>Somebody Unexpected</td>
    <td class="format"><a href="/x.pdf">pdf</a></td></tr></table>"""
    [p] = house.discover(html, base_url="https://www.aph.gov.au/Register")
    assert p.name == "Somebody Unexpected"
    assert p.electorate_or_state is None
    assert p.source_url == "https://www.aph.gov.au/x.pdf"
