from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

import pdfplumber
from pdfplumber.page import Page
from pdfplumber.table import Table

from ..declarations import CATEGORIES, Change, Declaration, Holder

logger = logging.getLogger(__name__)

STATEMENT_HEADERS: dict[tuple[str, ...], str] = {
    ("Name of company",): "shareholdings",
    ("Name of trust/nominee company", "Nature of its operation", "Beneficial interests"): "trusts",
    ("Name of trust/nominee company", "Nature of operation", "Beneficiary of the trust"): "trusts",
    ("Location", "Purpose for which owned"): "real_estate",
    ("Name of company", "Activities of company"): "directorships",
    ("Name", "Nature of interest", "Activities of partnership"): "partnerships",
    ("Nature of liability", "Creditor"): "liabilities",
    ("Type of investment", "Body in which investment is held"): "bonds",
    ("Nature of account", "Name of bank/institution"): "savings",
    ("Nature of any other assets",): "other_assets",
    ("Nature of income",): "income",
    ("Detail of gifts",): "gifts",
    ("Details of travel/hospitality",): "travel",
    ("Name of organisation",): "memberships",
    ("Nature of interest",): "other",
}
ALTERATION_HEADERS: dict[tuple[str, ...], Change] = {
    ("ADDITION Item", "Details"): "addition",
    ("DELETION Item", "Details"): "deletion",
}
HOLDERS: dict[str, Holder] = {
    "Self": "self",
    "Spouse/ Partner": "spouse",
    "Dependent Children": "dependent",
}
_PLACEHOLDERS = {"not applicable", "nil applicable", "n/a", "na", "nil", "none", "no", "-"}
_ITEM_LABEL_RE = re.compile(r"^\s*(\d{1,2})\.")
_SUBMITTED_RE = re.compile(r"Submitted Date:\s*(\d{1,2})/(\d{1,2})/(\d{4})")
# Line gaps (pt) above which a new item starts. Wrapped lines sit ~2pt apart;
# statement items ~5pt; alteration entries ~20pt, with ~5pt between paragraphs
# of a single entry.
_STATEMENT_ITEM_GAP = 3.5
_ALTERATION_ITEM_GAP = 10.0


def _norm(text: str | None) -> str:
    return " ".join((text or "").split())


@dataclass
class _Context:
    category: str | None = None
    change: Change | None = None
    holder: Holder | None = None


@dataclass
class _Result:
    declarations: list[Declaration] = field(default_factory=list)
    pending: list[int] = field(default_factory=list)
    recognised_tables: int = 0


@dataclass(frozen=True)
class _Item:
    top: float
    text: str


def _cell_items(page: Page, bbox, item_gap: float) -> list[_Item]:
    items: list[_Item] = []
    parts: list[str] = []
    top = prev_bottom = 0.0
    for line in page.crop(bbox).extract_text_lines(strip=True):
        text = _norm(line["text"])
        if not text:
            continue
        if parts and line["top"] - prev_bottom > item_gap:
            items.append(_Item(top, " ".join(parts)))
            parts = []
        if not parts:
            top = line["top"]
        parts.append(text)
        prev_bottom = line["bottom"]
    if parts:
        items.append(_Item(top, " ".join(parts)))
    return items


def _row_cells(
    page: Page, table: Table, width: int, item_gap: float
) -> list[tuple[str, list[list[_Item]]]]:
    rows = []
    for row in table.rows:
        cells = list(row.cells) + [None] * (width - len(row.cells))
        label = _norm(page.crop(cells[0]).extract_text()) if cells[0] else ""
        values = [_cell_items(page, c, item_gap) if c else [] for c in cells[1:width]]
        rows.append((label, values))
    return rows


def _align(anchors: list[_Item], others: list[_Item]) -> list[list[str]]:
    """Group `others` under the anchor they start beside (or below)."""
    if len(anchors) == len(others):
        return [[o.text] for o in others]
    groups: list[list[str]] = [[] for _ in anchors]
    for o in others:
        idx = max((i for i, a in enumerate(anchors) if a.top <= o.top + 1.0), default=0)
        groups[idx].append(o.text)
    return groups


def _category_for_label(label: str) -> str | None:
    m = _ITEM_LABEL_RE.match(label)
    if m is None:
        return None
    n = int(m.group(1))
    return CATEGORIES[n - 1] if 1 <= n <= len(CATEGORIES) else None


def _is_placeholder(text: str) -> bool:
    return text.strip(" .").lower() in _PLACEHOLDERS


def _statement_items(values: list[list[_Item]]) -> list[str]:
    columns = [c for c in values if c]
    if not columns:
        return []
    # A stray wrapped line splits one item in two, never the reverse, so the
    # column with the fewest items has the most trustworthy boundaries.
    anchors = min(columns, key=len)
    aligned = [_align(anchors, c) for c in columns]
    out = []
    for i in range(len(anchors)):
        fields = [" ".join(col[i]) for col in aligned]
        text = " — ".join(f for f in fields if f and not _is_placeholder(f))
        if text:
            out.append(text)
    return out


def _alteration_items(
    values: list[list[_Item]], fallback: str | None
) -> list[tuple[str | None, str]]:
    labels, details = (values + [[], []])[:2]
    details = [d for d in details if not _is_placeholder(d.text)]
    if not details:
        return []
    if not labels:
        return [(fallback, d.text) for d in details]
    cats = [_category_for_label(l.text) or fallback for l in labels]
    if len(set(cats)) == 1:
        return [(cats[0], d.text) for d in details]
    groups = _align(labels, details)
    return [(cat, " ".join(g)) for cat, g in zip(cats, groups) if g]


def _handle_table(page: Page, table: Table, ctx: _Context, out: _Result) -> None:
    data = table.extract()
    if not data or not data[0]:
        return
    header = tuple(_norm(c) for c in data[0][1:] if _norm(c))
    first = _norm(data[0][0])
    if first.startswith("FAMILY NAME") or (header == () and first == "Notes"):
        ctx.category = ctx.change = ctx.holder = None
        return
    is_alteration = header in ALTERATION_HEADERS or (
        header not in STATEMENT_HEADERS and ctx.change in ("addition", "deletion")
    )
    gap = _ALTERATION_ITEM_GAP if is_alteration else _STATEMENT_ITEM_GAP
    rows = _row_cells(page, table, len(data[0]), gap)
    if header in STATEMENT_HEADERS and first == "":
        ctx.category, ctx.change, ctx.holder = STATEMENT_HEADERS[header], "statement", None
        rows = rows[1:]
        out.recognised_tables += 1
    elif header in ALTERATION_HEADERS and first == "":
        ctx.category, ctx.change, ctx.holder = None, ALTERATION_HEADERS[header], None
        rows = rows[1:]
        out.recognised_tables += 1
    elif ctx.change is None:
        logger.debug("skipping unrecognised table: %r", data[0])
        return

    for label, values in rows:
        if label:
            holder = HOLDERS.get(label)
            if holder is None:
                logger.debug("unknown holder label %r", label)
                continue
            ctx.holder = holder
        if ctx.change == "statement":
            assert ctx.category is not None
            for text in _statement_items(values):
                out.declarations.append(
                    Declaration(ctx.category, text, holder=ctx.holder)
                )
        else:
            for cat, text in _alteration_items(values, ctx.category):
                if cat is None:
                    logger.warning("alteration without item number: %r", text)
                    continue
                ctx.category = cat
                out.pending.append(len(out.declarations))
                out.declarations.append(
                    Declaration(cat, text, change=ctx.change, holder=ctx.holder)
                )


def _apply_date(out: _Result, day: str, month: str, year: str) -> None:
    iso = datetime(int(year), int(month), int(day)).date().isoformat()
    for i in out.pending:
        out.declarations[i] = replace(out.declarations[i], changed_on=iso)
    out.pending.clear()


class UnsupportedDocument(ValueError):
    """The PDF is not the machine-generated register template (e.g. a scan)."""


def parse(path: str | Path) -> list[Declaration]:
    out = _Result()
    ctx = _Context()
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            events: list[tuple[float, int, object]] = [
                (t.bbox[1], 0, t) for t in page.find_tables()
            ]
            for line in page.extract_text_lines():
                m = _SUBMITTED_RE.search(line["text"])
                if m:
                    events.append((line["top"], 1, m))
            for _, kind, obj in sorted(events, key=lambda e: (e[0], e[1])):
                if kind == 0:
                    _handle_table(page, obj, ctx, out)  # type: ignore[arg-type]
                else:
                    _apply_date(out, *obj.groups())  # type: ignore[union-attr]
    if out.recognised_tables == 0:
        raise UnsupportedDocument(f"no register template tables in {path}")
    return out.declarations
