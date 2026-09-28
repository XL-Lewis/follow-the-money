from pathlib import Path

import pytest

from ftm.declarations import Declaration
from ftm.parse import house_pdf
from ftm.parse.house_pdf import _alteration_items, _Item, _statement_items

ABDO = Path(__file__).parent / "fixtures" / "house_statement_abdo.pdf"


@pytest.fixture(scope="module")
def abdo() -> list[Declaration]:
    return house_pdf.parse(ABDO)


def test_statement_rows_pair_columns_and_holders(abdo):
    assert Declaration("real_estate", "Greenvale, VIC — Residential", holder="self") in abdo
    assert (
        Declaration("savings", "Savings — Deutsche Kreditbank (DKB)", holder="spouse")
        in abdo
    )
    assert Declaration("memberships", "Community and Public Sector Union", holder="self") in abdo


def test_deleted_interests_are_deletions_not_current_holdings(abdo):
    digital = [d for d in abdo if d.item_text == "Digital Currency"]
    assert digital == [
        Declaration(
            "other_assets", "Digital Currency", change="deletion", holder="self", changed_on="2025-08-18"
        )
    ]


def test_alterations_take_their_own_notification_date(abdo):
    assert (
        Declaration(
            "gifts",
            "ETU contribution to catering for Maiden Speech event (valued at $620.40)",
            change="addition",
            holder="self",
            changed_on="2025-08-18",
        )
        in abdo
    )
    assert (
        Declaration(
            "other",
            "Spouse receiving Paid Parental Leave",
            change="addition",
            holder="spouse",
            changed_on="2025-10-10",
        )
        in abdo
    )


def test_form_labels_and_placeholders_are_not_items(abdo):
    texts = {d.item_text for d in abdo}
    for noise in ("Not Applicable", "Self", "Spouse/ Partner", "Name of company", "Details"):
        assert noise not in texts
    assert not any("Submitted Date" in t or "Not Applicable" in t for t in texts)


def test_non_template_pdf_is_unsupported(tmp_path: Path, pdf_builder):
    scan = tmp_path / "scan.pdf"
    pdf_builder(scan, ["11. Gifts", "Bottle of wine"])
    with pytest.raises(house_pdf.UnsupportedDocument):
        house_pdf.parse(scan)


def test_statement_items_rejoin_a_line_split_off_by_extra_spacing():
    # "Investment account (via SMSF jointly with" / "spouse)" landed as two items
    # in the first column; the second column has the true item boundaries.
    first = [_Item(0, "Car loan"), _Item(15, "Investment account (via SMSF jointly with"), _Item(27, "spouse)")]
    second = [_Item(0, "Plenti"), _Item(15, "Macquarie")]
    assert _statement_items([first, second]) == [
        "Car loan — Plenti",
        "Investment account (via SMSF jointly with spouse) — Macquarie",
    ]


def test_statement_items_drop_placeholder_fields():
    assert _statement_items([[_Item(0, "Not Applicable")], [_Item(0, "Not Applicable")]]) == []
    assert _statement_items([[_Item(0, "Residence")], [_Item(0, "NA")]]) == ["Residence"]


def test_alteration_details_align_to_labels_when_counts_differ():
    labels = [_Item(0, "11. Gifts"), _Item(30, "12. Travel Or Hospitality")]
    details = [_Item(0, "Wine"), _Item(12, "Value: $50"), _Item(34, "Flights to Perth")]
    assert _alteration_items([labels, details], None) == [
        ("gifts", "Wine Value: $50"),
        ("travel", "Flights to Perth"),
    ]


def test_alteration_continuation_without_labels_uses_previous_category():
    details = [_Item(0, "Tickets to the cricket")]
    assert _alteration_items([[], details], "travel") == [("travel", "Tickets to the cricket")]
