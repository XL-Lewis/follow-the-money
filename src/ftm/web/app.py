from __future__ import annotations

import re
from pathlib import Path

from flask import Flask, abort, g, render_template, request, send_from_directory

from .. import db as db_module
from ..config import Config
from ..declarations import CATEGORIES

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

HOLDER_LABELS: dict[str, str] = {
    "self": "Self",
    "spouse": "Spouse / partner",
    "dependent": "Dependent child",
}

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_MIMETYPES = {"pdf": "application/pdf", "json": "application/json"}


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
        doc = conn.execute(
            "SELECT id, format, source_url FROM documents WHERE politician_id = ?",
            (pol["id"],),
        ).fetchone()
        latest = (
            db_module.latest_version_for_document(conn, int(doc["id"])) if doc else None
        )
        document = None
        if latest is not None:
            sections: dict[str, dict[str, list]] = {
                c: {"statement": [], "alterations": []} for c in CATEGORIES
            }
            for r in conn.execute(
                "SELECT category, change, holder, item_text, changed_on "
                "FROM declarations WHERE document_version_id = ? "
                "ORDER BY changed_on, ordinal",
                (int(latest["id"]),),
            ).fetchall():
                bucket = "statement" if r["change"] == "statement" else "alterations"
                sections.setdefault(
                    r["category"], {"statement": [], "alterations": []}
                )[bucket].append(r)
            document = {
                "format": doc["format"],
                "source_url": doc["source_url"],
                "version": latest,
                "sections": sections,
            }
        return render_template(
            "politician.html",
            politician=pol,
            document=document,
            categories=CATEGORIES,
            category_labels=CATEGORY_LABELS,
            holder_labels=HOLDER_LABELS,
        )

    @app.route("/raw/<sha>.<ext>")
    def raw_document(sha: str, ext: str):
        if not _SHA_RE.match(sha) or ext not in _MIMETYPES:
            abort(404)
        row = get_conn().execute(
            "SELECT file_path FROM document_versions WHERE content_sha256 = ? LIMIT 1",
            (sha,),
        ).fetchone()
        if row is None:
            abort(404)
        file_path = Path(row["file_path"])
        if file_path.suffix != f".{ext}" or not file_path.exists():
            abort(404)
        return send_from_directory(
            file_path.parent, file_path.name, mimetype=_MIMETYPES[ext]
        )

    return app


def run(cfg: Config, *, host: str = "127.0.0.1", port: int = 5000) -> None:
    create_app(cfg).run(host=host, port=port)
