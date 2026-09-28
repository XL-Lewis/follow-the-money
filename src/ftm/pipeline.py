from __future__ import annotations

import logging
from pathlib import Path

import requests
from slugify import slugify

from . import db as db_module
from .config import Config
from .declarations import Declaration
from .fetch import house, senate
from .fetch.client import USER_AGENT, get_with_cache
from .fetch.politician import DiscoveredPolitician
from .parse import house_pdf, senate_json

logger = logging.getLogger(__name__)


def _slug(p: DiscoveredPolitician) -> str:
    return slugify(f"{p.name}-{p.chamber}")


def _get(url: str, session: requests.Session) -> requests.Response:
    resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    resp.raise_for_status()
    return resp


def _discover_senate(cfg: Config, session: requests.Session) -> list[DiscoveredPolitician]:
    found: list[DiscoveredPolitician] = []
    page = 1
    while True:
        payload = _get(senate.list_url(cfg.senate_api_base, page), session).json()
        found += senate.discover(payload, api_base=cfg.senate_api_base)
        if page >= int(payload["pageCount"]):
            return found
        page += 1


def run_fetch(cfg: Config, *, session: requests.Session | None = None) -> None:
    cfg.ensure_dirs()
    db_module.init(cfg.db_path)
    sess = session or requests.Session()
    conn = db_module.connect(cfg.db_path)
    try:
        house_html = _get(cfg.house_index_url, sess).text
        discovered = house.discover(house_html, base_url=cfg.house_index_url)
        discovered += _discover_senate(cfg, sess)

        for p in discovered:
            pid = db_module.upsert_politician(
                conn,
                slug=_slug(p),
                name=p.name,
                chamber=p.chamber,
                party=p.party,
                electorate_or_state=p.electorate_or_state,
                aph_profile_url=p.profile_url,
            )
            did = db_module.upsert_document(
                conn, politician_id=pid, source_url=p.source_url, format=p.format
            )
            latest = db_module.latest_version_for_document(conn, did)
            prev_etag = latest["etag"] if latest else None
            prev_lm = latest["last_modified"] if latest else None
            prev_sha = latest["content_sha256"] if latest else None

            result = get_with_cache(
                p.source_url,
                prev_etag=prev_etag,
                prev_lm=prev_lm,
                prev_sha=prev_sha,
                session=sess,
            )

            if result.status == "unchanged":
                logger.info("unchanged: %s", p.source_url)
                if latest is not None and (
                    result.etag != prev_etag or result.last_modified != prev_lm
                ):
                    db_module.record_version(
                        conn,
                        document_id=did,
                        content_sha256=latest["content_sha256"],
                        file_path=latest["file_path"],
                        etag=result.etag,
                        last_modified=result.last_modified,
                    )
                continue

            assert result.body is not None and result.sha256 is not None
            file_path = cfg.raw_dir / f"{result.sha256}.{p.format}"
            if not file_path.exists():
                file_path.write_bytes(result.body)
            db_module.record_version(
                conn,
                document_id=did,
                content_sha256=result.sha256,
                file_path=str(file_path),
                etag=result.etag,
                last_modified=result.last_modified,
            )
            logger.info("%s: %s", result.status, p.source_url)
    finally:
        conn.close()


def _parse_document(path: Path, format: str) -> list[Declaration]:
    if format == "json":
        return senate_json.parse(path.read_bytes())
    return house_pdf.parse(path)


def run_parse(cfg: Config) -> None:
    db_module.init(cfg.db_path)
    conn = db_module.connect(cfg.db_path)
    try:
        docs = conn.execute("SELECT id, format FROM documents").fetchall()
        for doc in docs:
            latest = db_module.latest_version_for_document(conn, int(doc["id"]))
            if latest is None:
                continue
            file_path = Path(latest["file_path"])
            if not file_path.exists():
                logger.warning("missing file for version %s: %s", latest["id"], file_path)
                continue
            try:
                items, error = _parse_document(file_path, doc["format"]), None
            except house_pdf.UnsupportedDocument as exc:
                logger.warning("unparseable document %s: %s", latest["id"], exc)
                items, error = [], str(exc)
            db_module.replace_declarations(
                conn,
                document_version_id=int(latest["id"]),
                items=items,
                parse_error=error,
            )
    finally:
        conn.close()
