from __future__ import annotations

import logging
from pathlib import Path

import requests
from slugify import slugify

from . import db as db_module
from .config import Config
from .fetch import house, senate
from .fetch.client import USER_AGENT, get_with_cache
from .fetch.discover import DiscoveredPolitician
from .parse import pdf as pdf_parse
from .parse.sections import iter_items, split_into_sections

logger = logging.getLogger(__name__)


def _slug(p: DiscoveredPolitician) -> str:
    return slugify(f"{p.name}-{p.chamber}")


def _fetch_index(url: str, session: requests.Session) -> str:
    resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    resp.raise_for_status()
    return resp.text


def run_fetch(cfg: Config, *, session: requests.Session | None = None) -> None:
    cfg.ensure_dirs()
    db_module.init(cfg.db_path)
    sess = session or requests.Session()
    conn = db_module.connect(cfg.db_path)
    try:
        house_html = _fetch_index(cfg.house_index_url, sess)
        senate_html = _fetch_index(cfg.senate_index_url, sess)
        discovered: list[DiscoveredPolitician] = []
        discovered += house.discover(house_html, base_url=cfg.house_index_url)
        discovered += senate.discover(senate_html, base_url=cfg.senate_index_url)

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
            for kind, url in p.documents:
                did = db_module.upsert_document(
                    conn, politician_id=pid, kind=kind, source_url=url
                )
                latest = db_module.latest_version_for_document(conn, did)
                prev_etag = latest["etag"] if latest else None
                prev_lm = latest["last_modified"] if latest else None
                prev_sha = latest["content_sha256"] if latest else None

                result = get_with_cache(
                    url,
                    prev_etag=prev_etag,
                    prev_lm=prev_lm,
                    prev_sha=prev_sha,
                    session=sess,
                )

                if result.status == "unchanged":
                    logger.info("unchanged: %s", url)
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
                file_path = cfg.raw_dir / f"{result.sha256}.pdf"
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
                logger.info("%s: %s", result.status, url)
    finally:
        conn.close()


def run_parse(cfg: Config) -> None:
    db_module.init(cfg.db_path)
    conn = db_module.connect(cfg.db_path)
    try:
        docs = conn.execute("SELECT id FROM documents").fetchall()
        for doc in docs:
            latest = db_module.latest_version_for_document(conn, int(doc["id"]))
            if latest is None:
                continue
            file_path = Path(latest["file_path"])
            if not file_path.exists():
                logger.warning("missing file for version %s: %s", latest["id"], file_path)
                continue
            text = pdf_parse.extract_text(file_path)
            sections = split_into_sections(text)
            db_module.replace_declarations(
                conn,
                document_version_id=int(latest["id"]),
                items=list(iter_items(sections)),
            )
    finally:
        conn.close()
