from pathlib import Path

import pytest

from ftm import db as db_module


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def test_init_creates_all_tables(db_path: Path):
    db_module.init(db_path)
    conn = db_module.connect(db_path)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "politicians",
            "documents",
            "document_versions",
            "declarations",
        } <= tables

        assert {
            "id",
            "slug",
            "name",
            "chamber",
            "party",
            "electorate_or_state",
            "aph_profile_url",
        } <= _table_columns(conn, "politicians")

        assert {
            "id",
            "politician_id",
            "kind",
            "source_url",
            "first_seen_at",
        } <= _table_columns(conn, "documents")

        assert {
            "id",
            "document_id",
            "content_sha256",
            "file_path",
            "etag",
            "last_modified",
            "fetched_at",
        } <= _table_columns(conn, "document_versions")

        assert {
            "id",
            "document_version_id",
            "category",
            "item_text",
            "ordinal",
            "parsed_at",
        } <= _table_columns(conn, "declarations")
    finally:
        conn.close()


def test_init_is_idempotent(db_path: Path):
    db_module.init(db_path)
    db_module.init(db_path)  # should not raise


def test_chamber_check_constraint_enforced(db):
    with pytest.raises(Exception):
        db_module.upsert_politician(
            db,
            slug="x-bogus",
            name="X",
            chamber="bogus",
            party=None,
            electorate_or_state=None,
            aph_profile_url=None,
        )


def test_upsert_politician_inserts_then_updates(db):
    pid_a = db_module.upsert_politician(
        db,
        slug="jane-doe-house",
        name="Jane Doe",
        chamber="house",
        party="Independent",
        electorate_or_state="Wentworth",
        aph_profile_url="https://example.test/jane",
    )
    pid_b = db_module.upsert_politician(
        db,
        slug="jane-doe-house",
        name="Jane Doe",
        chamber="house",
        party="Liberal",  # changed
        electorate_or_state="Wentworth",
        aph_profile_url="https://example.test/jane",
    )
    assert pid_a == pid_b
    row = db.execute(
        "SELECT party FROM politicians WHERE id = ?", (pid_a,)
    ).fetchone()
    assert row[0] == "Liberal"


def test_upsert_document_dedupes_by_source_url(db):
    pid = db_module.upsert_politician(
        db,
        slug="jd-house",
        name="JD",
        chamber="house",
        party=None,
        electorate_or_state=None,
        aph_profile_url=None,
    )
    a = db_module.upsert_document(
        db,
        politician_id=pid,
        kind="statement",
        source_url="https://example.test/jd.pdf",
    )
    b = db_module.upsert_document(
        db,
        politician_id=pid,
        kind="statement",
        source_url="https://example.test/jd.pdf",
    )
    assert a == b


def test_record_version_dedupes_on_sha(db, tmp_data_dir):
    pid = db_module.upsert_politician(
        db,
        slug="jd-house",
        name="JD",
        chamber="house",
        party=None,
        electorate_or_state=None,
        aph_profile_url=None,
    )
    did = db_module.upsert_document(
        db,
        politician_id=pid,
        kind="statement",
        source_url="https://example.test/jd.pdf",
    )
    v1 = db_module.record_version(
        db,
        document_id=did,
        content_sha256="aaa",
        file_path=str(tmp_data_dir / "raw" / "aaa.pdf"),
        etag='W/"x"',
        last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
    )
    v1_again = db_module.record_version(
        db,
        document_id=did,
        content_sha256="aaa",
        file_path=str(tmp_data_dir / "raw" / "aaa.pdf"),
        etag='W/"x"',
        last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
    )
    assert v1 == v1_again

    v2 = db_module.record_version(
        db,
        document_id=did,
        content_sha256="bbb",
        file_path=str(tmp_data_dir / "raw" / "bbb.pdf"),
        etag='W/"y"',
        last_modified="Thu, 02 Jan 2025 00:00:00 GMT",
    )
    assert v2 != v1


def test_replace_declarations_is_idempotent(db, tmp_data_dir):
    pid = db_module.upsert_politician(
        db,
        slug="jd-house",
        name="JD",
        chamber="house",
        party=None,
        electorate_or_state=None,
        aph_profile_url=None,
    )
    did = db_module.upsert_document(
        db,
        politician_id=pid,
        kind="statement",
        source_url="https://example.test/jd.pdf",
    )
    vid = db_module.record_version(
        db,
        document_id=did,
        content_sha256="aaa",
        file_path=str(tmp_data_dir / "raw" / "aaa.pdf"),
        etag=None,
        last_modified=None,
    )
    db_module.replace_declarations(
        db,
        document_version_id=vid,
        items=[
            ("shareholdings", "BHP shares"),
            ("gifts", "Bottle of wine"),
        ],
    )
    db_module.replace_declarations(
        db,
        document_version_id=vid,
        items=[
            ("shareholdings", "BHP shares"),
            ("gifts", "Bottle of wine"),
        ],
    )
    rows = db.execute(
        "SELECT category, item_text FROM declarations WHERE document_version_id = ? ORDER BY ordinal",
        (vid,),
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        ("shareholdings", "BHP shares"),
        ("gifts", "Bottle of wine"),
    ]


def test_latest_version_for_document_returns_most_recent(db, tmp_data_dir):
    pid = db_module.upsert_politician(
        db,
        slug="jd-house",
        name="JD",
        chamber="house",
        party=None,
        electorate_or_state=None,
        aph_profile_url=None,
    )
    did = db_module.upsert_document(
        db,
        politician_id=pid,
        kind="statement",
        source_url="https://example.test/jd.pdf",
    )
    db_module.record_version(
        db,
        document_id=did,
        content_sha256="aaa",
        file_path=str(tmp_data_dir / "raw" / "aaa.pdf"),
        etag=None,
        last_modified=None,
    )
    v2 = db_module.record_version(
        db,
        document_id=did,
        content_sha256="bbb",
        file_path=str(tmp_data_dir / "raw" / "bbb.pdf"),
        etag=None,
        last_modified=None,
    )
    latest = db_module.latest_version_for_document(db, did)
    assert latest["id"] == v2
    assert latest["content_sha256"] == "bbb"
