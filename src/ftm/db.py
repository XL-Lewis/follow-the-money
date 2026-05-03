from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS politicians (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    chamber TEXT NOT NULL CHECK (chamber IN ('house', 'senate')),
    party TEXT,
    electorate_or_state TEXT,
    aph_profile_url TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    politician_id INTEGER NOT NULL REFERENCES politicians(id),
    kind TEXT NOT NULL CHECK (kind IN ('statement', 'alteration')),
    source_url TEXT NOT NULL UNIQUE,
    first_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_versions (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    content_sha256 TEXT NOT NULL,
    file_path TEXT NOT NULL,
    etag TEXT,
    last_modified TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(document_id, content_sha256)
);

CREATE TABLE IF NOT EXISTS declarations (
    id INTEGER PRIMARY KEY,
    document_version_id INTEGER NOT NULL REFERENCES document_versions(id),
    category TEXT NOT NULL,
    item_text TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    parsed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_politician ON documents(politician_id);
CREATE INDEX IF NOT EXISTS idx_versions_document ON document_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_declarations_version ON declarations(document_version_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def upsert_politician(
    conn: sqlite3.Connection,
    *,
    slug: str,
    name: str,
    chamber: str,
    party: str | None,
    electorate_or_state: str | None,
    aph_profile_url: str | None,
) -> int:
    conn.execute(
        """
        INSERT INTO politicians (slug, name, chamber, party, electorate_or_state, aph_profile_url)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            name = excluded.name,
            chamber = excluded.chamber,
            party = excluded.party,
            electorate_or_state = excluded.electorate_or_state,
            aph_profile_url = excluded.aph_profile_url
        """,
        (slug, name, chamber, party, electorate_or_state, aph_profile_url),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM politicians WHERE slug = ?", (slug,)).fetchone()
    return int(row["id"])


def upsert_document(
    conn: sqlite3.Connection,
    *,
    politician_id: int,
    kind: str,
    source_url: str,
) -> int:
    conn.execute(
        """
        INSERT INTO documents (politician_id, kind, source_url, first_seen_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(source_url) DO UPDATE SET
            politician_id = excluded.politician_id,
            kind = excluded.kind
        """,
        (politician_id, kind, source_url, _now()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM documents WHERE source_url = ?", (source_url,)
    ).fetchone()
    return int(row["id"])


def record_version(
    conn: sqlite3.Connection,
    *,
    document_id: int,
    content_sha256: str,
    file_path: str,
    etag: str | None,
    last_modified: str | None,
) -> int:
    existing = conn.execute(
        "SELECT id FROM document_versions WHERE document_id = ? AND content_sha256 = ?",
        (document_id, content_sha256),
    ).fetchone()
    if existing is not None:
        conn.execute(
            """
            UPDATE document_versions
            SET etag = ?, last_modified = ?
            WHERE id = ?
            """,
            (etag, last_modified, existing["id"]),
        )
        conn.commit()
        return int(existing["id"])

    cur = conn.execute(
        """
        INSERT INTO document_versions
            (document_id, content_sha256, file_path, etag, last_modified, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (document_id, content_sha256, file_path, etag, last_modified, _now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def latest_version_for_document(
    conn: sqlite3.Connection, document_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM document_versions
        WHERE document_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (document_id,),
    ).fetchone()


def replace_declarations(
    conn: sqlite3.Connection,
    *,
    document_version_id: int,
    items: Iterable[tuple[str, str]],
) -> None:
    now = _now()
    conn.execute(
        "DELETE FROM declarations WHERE document_version_id = ?",
        (document_version_id,),
    )
    rows = [
        (document_version_id, category, item_text, ordinal, now)
        for ordinal, (category, item_text) in enumerate(items)
    ]
    if rows:
        conn.executemany(
            """
            INSERT INTO declarations
                (document_version_id, category, item_text, ordinal, parsed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
    conn.commit()
