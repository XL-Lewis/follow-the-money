from __future__ import annotations

from pathlib import Path

from pdfminer.high_level import extract_text as _extract_text


def extract_text(path: str | Path) -> str:
    return _extract_text(str(path))
