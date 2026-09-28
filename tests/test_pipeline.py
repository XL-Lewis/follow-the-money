import hashlib
import json
from pathlib import Path

import pytest
import responses

from ftm import db as db_module
from ftm.config import Config
from ftm.pipeline import run_fetch, run_parse

FIXTURES = Path(__file__).parent / "fixtures"
HOUSE_INDEX = "https://example.test/house"
SENATE_API = "https://example.test/api"
JANE_PDF_URL = "https://example.test/files/jane.pdf"

HOUSE_HTML = f"""
<table class="members-interests__table"><tbody>
<tr>
  <td class="date">10 October 2025 </td>
  <td>Doe, Ms Jane, Member for Wentworth, NSW</td>
  <td class="format"><a download="Doe" href="{JANE_PDF_URL}"><img alt="PDF format"/></a></td>
</tr>
</tbody></table>
"""


def _senate_list(cdap_ids: list[str], *, page: int = 1, page_count: int = 1) -> dict:
    return {
        "statementOfRegisterableInterests": [
            {"cdapId": c, "name": f"Senator, {c}", "state": "Victoria", "senatorParty": "Greens"}
            for c in cdap_ids
        ],
        "currentPage": page,
        "pageCount": page_count,
        "wasSuccessful": True,
        "errors": None,
    }


SENATE_STATEMENT = (FIXTURES / "senate_statement.json").read_bytes()
HOUSE_PDF = (FIXTURES / "house_statement_abdo.pdf").read_bytes()


def _list_url(page: int) -> str:
    return f"{SENATE_API}/queryStatements?pageSize=100&currentPage={page}"


def _statement_url(cdap_id: str) -> str:
    return f"{SENATE_API}/getSenatorStatement?cdapid={cdap_id}"


@pytest.fixture
def cfg(tmp_data_dir: Path) -> Config:
    c = Config(data_dir=tmp_data_dir, house_index_url=HOUSE_INDEX, senate_api_base=SENATE_API)
    c.ensure_dirs()
    db_module.init(c.db_path)
    return c


@pytest.fixture
def jane_pdf(tmp_path: Path, pdf_builder) -> bytes:
    return pdf_builder(tmp_path / "_jane.pdf", ["1. Shareholdings", "BHP Group Ltd"])


def _add_indexes(rsps):
    rsps.add(responses.GET, HOUSE_INDEX, body=HOUSE_HTML)
    rsps.add(responses.GET, _list_url(1), json=_senate_list(["317026"]))


def _add_first_run(rsps, jane_pdf: bytes):
    _add_indexes(rsps)
    rsps.add(responses.GET, JANE_PDF_URL, body=jane_pdf, headers={"ETag": 'W/"jane-1"'})
    rsps.add(responses.GET, _statement_url("317026"), body=SENATE_STATEMENT)


def _count(cfg: Config, table: str) -> int:
    conn = db_module.connect(cfg.db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


@responses.activate
def test_run_fetch_stores_house_pdf_and_senate_json(cfg: Config, jane_pdf: bytes):
    _add_first_run(responses, jane_pdf)

    run_fetch(cfg)

    conn = db_module.connect(cfg.db_path)
    rows = conn.execute(
        "SELECT p.name, p.chamber, p.electorate_or_state, d.format FROM politicians p "
        "JOIN documents d ON d.politician_id = p.id ORDER BY p.chamber"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("Jane Doe", "house", "Wentworth, NSW", "pdf"),
        ("317026 Senator", "senate", "Victoria", "json"),
    ]
    assert (cfg.raw_dir / f"{hashlib.sha256(jane_pdf).hexdigest()}.pdf").exists()
    assert (cfg.raw_dir / f"{hashlib.sha256(SENATE_STATEMENT).hexdigest()}.json").exists()


@responses.activate
def test_run_fetch_follows_senate_pagination(cfg: Config, jane_pdf: bytes):
    responses.add(responses.GET, HOUSE_INDEX, body=HOUSE_HTML)
    responses.add(responses.GET, JANE_PDF_URL, body=jane_pdf)
    responses.add(responses.GET, _list_url(1), json=_senate_list(["1"], page=1, page_count=2))
    responses.add(responses.GET, _list_url(2), json=_senate_list(["2"], page=2, page_count=2))
    for cdap_id in ("1", "2"):
        responses.add(responses.GET, _statement_url(cdap_id), body=SENATE_STATEMENT)

    run_fetch(cfg)

    assert _count(cfg, "politicians") == 3


@responses.activate
def test_run_fetch_is_noop_on_second_run_when_unchanged(cfg: Config, jane_pdf: bytes):
    _add_first_run(responses, jane_pdf)
    run_fetch(cfg)

    responses.reset()
    _add_indexes(responses)
    responses.add(responses.GET, JANE_PDF_URL, status=304)
    responses.add(responses.GET, _statement_url("317026"), body=SENATE_STATEMENT)
    run_fetch(cfg)

    assert _count(cfg, "document_versions") == 2


@responses.activate
def test_run_fetch_moves_document_when_url_changes(cfg: Config, jane_pdf: bytes, tmp_path, pdf_builder):
    _add_first_run(responses, jane_pdf)
    run_fetch(cfg)

    moved_url = "https://example.test/files/jane.pdf?rev=2"
    jane_v2 = pdf_builder(tmp_path / "_jane2.pdf", ["1. Shareholdings", "BHP", "Telstra"])
    responses.reset()
    responses.add(responses.GET, HOUSE_INDEX, body=HOUSE_HTML.replace(JANE_PDF_URL, moved_url))
    responses.add(responses.GET, _list_url(1), json=_senate_list(["317026"]))
    responses.add(responses.GET, moved_url, body=jane_v2)
    responses.add(responses.GET, _statement_url("317026"), body=SENATE_STATEMENT)
    run_fetch(cfg)

    conn = db_module.connect(cfg.db_path)
    docs = conn.execute(
        "SELECT d.source_url, COUNT(v.id) FROM documents d "
        "JOIN politicians p ON p.id = d.politician_id "
        "JOIN document_versions v ON v.document_id = d.id "
        "WHERE p.chamber = 'house' GROUP BY d.id"
    ).fetchall()
    assert [tuple(r) for r in docs] == [(moved_url, 2)]


def _declarations(cfg: Config) -> set[tuple]:
    conn = db_module.connect(cfg.db_path)
    try:
        rows = conn.execute(
            "SELECT p.chamber, dl.category, dl.change, dl.item_text FROM declarations dl "
            "JOIN document_versions v ON v.id = dl.document_version_id "
            "JOIN documents d ON d.id = v.document_id "
            "JOIN politicians p ON p.id = d.politician_id"
        ).fetchall()
    finally:
        conn.close()
    return {tuple(r) for r in rows}


@responses.activate
def test_run_parse_populates_declarations_from_both_formats(cfg: Config):
    _add_first_run(responses, HOUSE_PDF)
    run_fetch(cfg)
    run_parse(cfg)

    rows = _declarations(cfg)
    assert ("house", "other_assets", "deletion", "Digital Currency") in rows
    assert ("senate", "gifts", "addition", "3 Cartons of Beer from the Brewers Association.") in rows


@responses.activate
def test_run_parse_records_unsupported_pdf_and_continues(cfg: Config, jane_pdf: bytes):
    _add_first_run(responses, jane_pdf)
    run_fetch(cfg)
    run_parse(cfg)

    conn = db_module.connect(cfg.db_path)
    errors = conn.execute(
        "SELECT d.format, v.parse_error IS NOT NULL FROM document_versions v "
        "JOIN documents d ON d.id = v.document_id ORDER BY d.format"
    ).fetchall()
    conn.close()
    assert [tuple(r) for r in errors] == [("json", 0), ("pdf", 1)]
    assert {r[0] for r in _declarations(cfg)} == {"senate"}


@responses.activate
def test_run_parse_is_idempotent(cfg: Config):
    _add_first_run(responses, HOUSE_PDF)
    run_fetch(cfg)
    run_parse(cfg)
    first = _count(cfg, "declarations")
    run_parse(cfg)
    assert _count(cfg, "declarations") == first > 0
