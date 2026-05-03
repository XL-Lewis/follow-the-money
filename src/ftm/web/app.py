from __future__ import annotations

import re
from pathlib import Path

from flask import Flask, abort, g, render_template, request, send_from_directory

from .. import db as db_module
from ..config import Config
from ..parse.sections import CATEGORIES

CATEGORY_LABELS: dict[str, str] = {
    "shareholdings": "Shareholdings",
    "trusts": "Family / business trusts",
    "real_estate": "Real estate",
    "directorships": "Directorships",
    "partnerships": "Partnerships",
    "liabilities": "Liabilities",
    "bonds": "Bonds, debentures",
    "savings": "Savings / investment accounts",
    "other_assets": "Other assets",
    "income": "Other sources of income",
    "gifts": "Gifts",
    "travel": "Sponsored travel / hospitality",
    "memberships": "Memberships",
    "other": "Other interests",
}

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def create_app(cfg: Config) -> Flask:
    app = Flask(__name__)
    app.config["FTM_CONFIG"] = cfg

    def get_conn():
        if "conn" not in g:
            g.conn = db_module.connect(cfg.db_path)
        return g.conn

    @app.teardown_appcontext
    def close_conn(_exc):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    @app.route("/")
    def index():
        chamber = request.args.get("chamber") or None
        q = (request.args.get("q") or "").strip()
        sql = "SELECT * FROM politicians WHERE 1=1"
        params: list = []
        if chamber in {"house", "senate"}:
            sql += " AND chamber = ?"
            params.append(chamber)
        if q:
            sql += " AND name LIKE ?"
            params.append(f"%{q}%")
        sql += " ORDER BY name"
        pols = get_conn().execute(sql, params).fetchall()
        return render_template(
            "index.html",
            politicians=pols,
            chamber=chamber,
            q=q,
        )

    @app.route("/p/<slug>")
    def politician(slug: str):
        conn = get_conn()
        pol = conn.execute(
            "SELECT * FROM politicians WHERE slug = ?", (slug,)
        ).fetchone()
        if pol is None:
            abort(404)
        documents = conn.execute(
            """
            SELECT d.id AS document_id, d.kind, d.source_url
            FROM documents d
            WHERE d.politician_id = ?
            ORDER BY d.kind, d.id
            """,
            (pol["id"],),
        ).fetchall()
        per_doc = []
        for doc in documents:
            latest = db_module.latest_version_for_document(conn, int(doc["document_id"]))
            if latest is None:
                continue
            items_by_cat: dict[str, list[str]] = {c: [] for c in CATEGORIES}
            for r in conn.execute(
                "SELECT category, item_text FROM declarations "
                "WHERE document_version_id = ? ORDER BY ordinal",
                (int(latest["id"]),),
            ).fetchall():
                items_by_cat.setdefault(r["category"], []).append(r["item_text"])
            per_doc.append(
                {
                    "kind": doc["kind"],
                    "source_url": doc["source_url"],
                    "version": latest,
                    "items_by_cat": items_by_cat,
                }
            )
        return render_template(
            "politician.html",
            politician=pol,
            documents=per_doc,
            categories=CATEGORIES,
            category_labels=CATEGORY_LABELS,
        )

    @app.route("/raw/<sha>.pdf")
    def raw_pdf(sha: str):
        if not _SHA_RE.match(sha):
            abort(404)
        row = get_conn().execute(
            "SELECT file_path FROM document_versions WHERE content_sha256 = ? LIMIT 1",
            (sha,),
        ).fetchone()
        if row is None:
            abort(404)
        file_path = Path(row["file_path"])
        if not file_path.exists():
            abort(404)
        return send_from_directory(
            file_path.parent, file_path.name, mimetype="application/pdf"
        )

    return app


def run(cfg: Config, *, host: str = "127.0.0.1", port: int = 5000) -> None:
    create_app(cfg).run(host=host, port=port)
