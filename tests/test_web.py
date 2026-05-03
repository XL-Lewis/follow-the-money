from pathlib import Path

import pytest

from ftm import db as db_module
from ftm.config import Config
from ftm.web.app import create_app


@pytest.fixture
def seeded(tmp_data_dir: Path, pdf_builder):
    cfg = Config(data_dir=tmp_data_dir)
    cfg.ensure_dirs()
    db_module.init(cfg.db_path)
    conn = db_module.connect(cfg.db_path)

    jane_pdf = tmp_data_dir / "raw" / "aaa.pdf"
    pdf_builder(jane_pdf, ["Jane DOE statement"])
    alice_pdf = tmp_data_dir / "raw" / "bbb.pdf"
    pdf_builder(alice_pdf, ["Alice JONES statement"])

    jane_id = db_module.upsert_politician(
        conn,
        slug="jane-doe-house",
        name="Jane DOE",
        chamber="house",
        party="Liberal",
        electorate_or_state="Wentworth, NSW",
        aph_profile_url=None,
    )
    alice_id = db_module.upsert_politician(
        conn,
        slug="alice-jones-senate",
        name="Alice JONES",
        chamber="senate",
        party="Greens",
        electorate_or_state="VIC",
        aph_profile_url=None,
    )
    jane_doc = db_module.upsert_document(
        conn,
        politician_id=jane_id,
        kind="statement",
        source_url="https://example.test/jane.pdf",
    )
    alice_doc = db_module.upsert_document(
        conn,
        politician_id=alice_id,
        kind="statement",
        source_url="https://example.test/alice.pdf",
    )
    # Rename files to match content sha for the route to find them
    import hashlib

    jane_sha = hashlib.sha256(jane_pdf.read_bytes()).hexdigest()
    jane_path = tmp_data_dir / "raw" / f"{jane_sha}.pdf"
    jane_pdf.rename(jane_path)

    alice_sha = hashlib.sha256(alice_pdf.read_bytes()).hexdigest()
    alice_path = tmp_data_dir / "raw" / f"{alice_sha}.pdf"
    alice_pdf.rename(alice_path)

    jane_v = db_module.record_version(
        conn,
        document_id=jane_doc,
        content_sha256=jane_sha,
        file_path=str(jane_path),
        etag=None,
        last_modified=None,
    )
    alice_v = db_module.record_version(
        conn,
        document_id=alice_doc,
        content_sha256=alice_sha,
        file_path=str(alice_path),
        etag=None,
        last_modified=None,
    )

    db_module.replace_declarations(
        conn,
        document_version_id=jane_v,
        items=[
            ("shareholdings", "BHP Group Ltd"),
            ("gifts", "Bottle of wine"),
        ],
    )
    db_module.replace_declarations(
        conn,
        document_version_id=alice_v,
        items=[("real_estate", "House, Carlton VIC")],
    )
    conn.close()

    return cfg, jane_sha, alice_sha


def test_index_lists_politicians(seeded):
    cfg, *_ = seeded
    app = create_app(cfg)
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Jane DOE" in body
    assert "Alice JONES" in body
    assert "Liberal" in body
    assert "Greens" in body


def test_index_filters_by_chamber(seeded):
    cfg, *_ = seeded
    client = create_app(cfg).test_client()
    body = client.get("/?chamber=house").get_data(as_text=True)
    assert "Jane DOE" in body
    assert "Alice JONES" not in body
    body = client.get("/?chamber=senate").get_data(as_text=True)
    assert "Alice JONES" in body
    assert "Jane DOE" not in body


def test_index_filters_by_q_substring(seeded):
    cfg, *_ = seeded
    client = create_app(cfg).test_client()
    body = client.get("/?q=alice").get_data(as_text=True)
    assert "Alice JONES" in body
    assert "Jane DOE" not in body


def test_politician_page_shows_categories_and_links(seeded):
    cfg, jane_sha, _ = seeded
    client = create_app(cfg).test_client()
    resp = client.get("/p/jane-doe-house")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "BHP Group Ltd" in body
    assert "Bottle of wine" in body
    # Section labels
    assert "Shareholdings" in body
    assert "Gifts" in body
    # Link to PDF by sha
    assert f"/raw/{jane_sha}.pdf" in body


def test_politician_page_404_for_unknown_slug(seeded):
    cfg, *_ = seeded
    client = create_app(cfg).test_client()
    assert client.get("/p/nope").status_code == 404


def test_raw_pdf_route_serves_known_sha(seeded):
    cfg, jane_sha, _ = seeded
    client = create_app(cfg).test_client()
    resp = client.get(f"/raw/{jane_sha}.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF-")


def test_raw_pdf_route_404s_for_unknown_sha(seeded):
    cfg, *_ = seeded
    client = create_app(cfg).test_client()
    bogus = "0" * 64
    assert client.get(f"/raw/{bogus}.pdf").status_code == 404


def test_raw_pdf_route_404s_for_invalid_sha_format(seeded):
    cfg, *_ = seeded
    client = create_app(cfg).test_client()
    # Path traversal attempt and non-hex names rejected
    assert client.get("/raw/..%2Fetc%2Fpasswd.pdf").status_code == 404
    assert client.get("/raw/notahex.pdf").status_code == 404
