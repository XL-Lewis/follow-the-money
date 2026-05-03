import hashlib
from pathlib import Path

import pytest
import responses

from ftm import db as db_module
from ftm.config import Config
from ftm.pipeline import run_fetch, run_parse


HOUSE_INDEX = "https://example.test/house"
SENATE_INDEX = "https://example.test/senate"

HOUSE_HTML_TEMPLATE = """
<html><body><table>
  <tr>
    <td><a class="member-name" href="/profile/jane">Jane DOE</a></td>
    <td>Liberal</td><td>Wentworth, NSW</td>
    <td>
      <a href="/files/jane-statement.pdf">Statement of Registrable Interests</a>
    </td>
  </tr>
</table></body></html>
"""

SENATE_HTML_TEMPLATE = """
<html><body><table>
  <tr>
    <td><a class="member-name" href="/profile/alice">Alice JONES</a></td>
    <td>Greens</td><td>VIC</td>
    <td>
      <a href="/files/alice-statement.pdf">Statement of Registrable Interests</a>
    </td>
  </tr>
</table></body></html>
"""


@pytest.fixture
def cfg(tmp_data_dir: Path) -> Config:
    c = Config(
        data_dir=tmp_data_dir,
        house_index_url=HOUSE_INDEX,
        senate_index_url=SENATE_INDEX,
    )
    c.ensure_dirs()
    db_module.init(c.db_path)
    return c


def _statement_pdf(pdf_builder, path: Path, body_lines: list[str]) -> bytes:
    return pdf_builder(path, body_lines)


def _setup_first_run(rsps, jane_pdf: bytes, alice_pdf: bytes):
    rsps.add(responses.GET, HOUSE_INDEX, body=HOUSE_HTML_TEMPLATE, status=200)
    rsps.add(responses.GET, SENATE_INDEX, body=SENATE_HTML_TEMPLATE, status=200)
    rsps.add(
        responses.GET,
        "https://example.test/files/jane-statement.pdf",
        body=jane_pdf,
        status=200,
        headers={"ETag": 'W/"jane-1"'},
    )
    rsps.add(
        responses.GET,
        "https://example.test/files/alice-statement.pdf",
        body=alice_pdf,
        status=200,
        headers={"ETag": 'W/"alice-1"'},
    )


@responses.activate
def test_run_fetch_inserts_politicians_documents_and_versions(
    cfg: Config, tmp_path: Path, pdf_builder
):
    jane_pdf = _statement_pdf(
        pdf_builder, tmp_path / "_jane.pdf", ["1. Shareholdings", "BHP"]
    )
    alice_pdf = _statement_pdf(
        pdf_builder, tmp_path / "_alice.pdf", ["1. Shareholdings", "CBA"]
    )
    _setup_first_run(responses, jane_pdf, alice_pdf)

    run_fetch(cfg)

    conn = db_module.connect(cfg.db_path)
    pols = conn.execute("SELECT name, chamber FROM politicians ORDER BY name").fetchall()
    assert [(r[0], r[1]) for r in pols] == [
        ("Alice JONES", "senate"),
        ("Jane DOE", "house"),
    ]
    docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    versions = conn.execute("SELECT COUNT(*) FROM document_versions").fetchone()[0]
    assert docs == 2
    assert versions == 2

    # Files written under raw_dir keyed by sha
    expected_jane = hashlib.sha256(jane_pdf).hexdigest()
    assert (cfg.raw_dir / f"{expected_jane}.pdf").exists()


@responses.activate
def test_run_fetch_is_noop_on_second_run_when_304(
    cfg: Config, tmp_path: Path, pdf_builder
):
    jane_pdf = _statement_pdf(
        pdf_builder, tmp_path / "_jane.pdf", ["1. Shareholdings", "BHP"]
    )
    alice_pdf = _statement_pdf(
        pdf_builder, tmp_path / "_alice.pdf", ["1. Shareholdings", "CBA"]
    )
    _setup_first_run(responses, jane_pdf, alice_pdf)
    run_fetch(cfg)

    responses.reset()
    responses.add(responses.GET, HOUSE_INDEX, body=HOUSE_HTML_TEMPLATE, status=200)
    responses.add(responses.GET, SENATE_INDEX, body=SENATE_HTML_TEMPLATE, status=200)
    responses.add(
        responses.GET, "https://example.test/files/jane-statement.pdf", status=304
    )
    responses.add(
        responses.GET, "https://example.test/files/alice-statement.pdf", status=304
    )

    run_fetch(cfg)

    conn = db_module.connect(cfg.db_path)
    versions = conn.execute("SELECT COUNT(*) FROM document_versions").fetchone()[0]
    assert versions == 2  # unchanged


@responses.activate
def test_run_fetch_creates_new_version_when_content_changes(
    cfg: Config, tmp_path: Path, pdf_builder
):
    jane_pdf = _statement_pdf(
        pdf_builder, tmp_path / "_jane.pdf", ["1. Shareholdings", "BHP"]
    )
    alice_pdf = _statement_pdf(
        pdf_builder, tmp_path / "_alice.pdf", ["1. Shareholdings", "CBA"]
    )
    _setup_first_run(responses, jane_pdf, alice_pdf)
    run_fetch(cfg)

    jane_pdf_v2 = _statement_pdf(
        pdf_builder,
        tmp_path / "_jane2.pdf",
        ["1. Shareholdings", "BHP", "Telstra"],
    )
    responses.reset()
    responses.add(responses.GET, HOUSE_INDEX, body=HOUSE_HTML_TEMPLATE, status=200)
    responses.add(responses.GET, SENATE_INDEX, body=SENATE_HTML_TEMPLATE, status=200)
    responses.add(
        responses.GET,
        "https://example.test/files/jane-statement.pdf",
        body=jane_pdf_v2,
        status=200,
        headers={"ETag": 'W/"jane-2"'},
    )
    responses.add(
        responses.GET, "https://example.test/files/alice-statement.pdf", status=304
    )

    run_fetch(cfg)

    conn = db_module.connect(cfg.db_path)
    jane_versions = conn.execute(
        """
        SELECT v.* FROM document_versions v
        JOIN documents d ON d.id = v.document_id
        JOIN politicians p ON p.id = d.politician_id
        WHERE p.name = 'Jane DOE'
        ORDER BY v.id
        """
    ).fetchall()
    assert len(jane_versions) == 2
    assert jane_versions[0]["content_sha256"] != jane_versions[1]["content_sha256"]


@responses.activate
def test_run_parse_populates_declarations(
    cfg: Config, tmp_path: Path, pdf_builder
):
    jane_pdf = _statement_pdf(
        pdf_builder,
        tmp_path / "_jane.pdf",
        [
            "Statement of Registrable Interests",
            "1. Shareholdings",
            "BHP Group Ltd",
            "11. Gifts",
            "Bottle of wine",
        ],
    )
    alice_pdf = _statement_pdf(
        pdf_builder, tmp_path / "_alice.pdf", ["1. Shareholdings", "CBA"]
    )
    _setup_first_run(responses, jane_pdf, alice_pdf)
    run_fetch(cfg)
    run_parse(cfg)

    conn = db_module.connect(cfg.db_path)
    cats = dict(
        conn.execute(
            "SELECT category, COUNT(*) FROM declarations GROUP BY category"
        ).fetchall()
    )
    assert cats.get("shareholdings", 0) >= 1
    assert cats.get("gifts", 0) >= 1


@responses.activate
def test_run_parse_is_idempotent(cfg: Config, tmp_path: Path, pdf_builder):
    jane_pdf = _statement_pdf(
        pdf_builder,
        tmp_path / "_jane.pdf",
        ["1. Shareholdings", "BHP Group Ltd"],
    )
    alice_pdf = _statement_pdf(
        pdf_builder, tmp_path / "_alice.pdf", ["1. Shareholdings", "CBA"]
    )
    _setup_first_run(responses, jane_pdf, alice_pdf)
    run_fetch(cfg)
    run_parse(cfg)
    first = (
        db_module.connect(cfg.db_path)
        .execute("SELECT COUNT(*) FROM declarations")
        .fetchone()[0]
    )
    run_parse(cfg)
    second = (
        db_module.connect(cfg.db_path)
        .execute("SELECT COUNT(*) FROM declarations")
        .fetchone()[0]
    )
    assert first == second and first > 0
