from pathlib import Path

from ftm.parse.sections import CATEGORIES, split_into_sections

FIXTURE = Path(__file__).parent / "fixtures" / "sample_statement.txt"


def _split():
    return split_into_sections(FIXTURE.read_text())


def test_split_returns_all_known_categories():
    sections = _split()
    expected = {
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
    }
    assert expected <= set(sections.keys())
    assert expected == set(CATEGORIES)


def test_categories_canonical_order():
    assert CATEGORIES == [
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


def test_section_yields_per_item_rows_split_on_blank_lines():
    sections = _split()
    assert "BHP Group Ltd" in sections["shareholdings"]
    assert "Commonwealth Bank of Australia" in sections["shareholdings"]
    # Two distinct items
    assert len(sections["shareholdings"]) == 2


def test_section_text_excludes_next_heading():
    sections = _split()
    for items in sections.values():
        for item in items:
            assert not item.lstrip().startswith(("1. ", "2. ", "3. ", "11. "))


def test_gifts_captures_multiple_items():
    sections = _split()
    gift_text = " | ".join(sections["gifts"])
    assert "Acme Corporation" in gift_text
    assert "ANZ Stadium" in gift_text
    assert len(sections["gifts"]) >= 2


def test_travel_section_present():
    sections = _split()
    assert any("Tokyo" in item for item in sections["travel"])


def test_unknown_heading_dropped_not_crashed():
    text = (
        "1. Shareholdings\nBHP\n\n"
        "99. Some unknown heading\nXYZ\n\n"
        "11. Gifts\nGift A\n"
    )
    sections = split_into_sections(text)
    assert "BHP" in sections["shareholdings"]
    assert "Gift A" in sections["gifts"]
    assert "other" in sections  # canonical key always present
    # Unknown heading content not promoted into a real category
    for items in sections.values():
        assert "XYZ" not in " ".join(items)


def test_alteration_with_only_some_sections_works():
    text = "11. Gifts\nNew gift item\n\n12. Sponsored travel\nNew travel\n"
    sections = split_into_sections(text)
    assert sections["gifts"] == ["New gift item"]
    assert sections["travel"] == ["New travel"]
    # Sections not present yield empty lists, not missing keys
    assert sections["shareholdings"] == []


def test_iter_items_helper_returns_category_text_pairs():
    from ftm.parse.sections import iter_items

    sections = _split()
    pairs = list(iter_items(sections))
    assert ("shareholdings", "BHP Group Ltd") in pairs
    assert ("gifts", "Tickets to ANZ Stadium from Sports Australia") in pairs
    # Order: categories in canonical order
    cats_in_order = [c for c, _ in pairs]
    seen_indices = [CATEGORIES.index(c) for c in cats_in_order]
    assert seen_indices == sorted(seen_indices)
