from pathlib import Path

import pytest


def make_simple_pdf(path: Path, lines: list[str]) -> bytes:
    """Build a minimal valid PDF with the given lines (Helvetica)."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    text_ops = ["BT", "/F1 12 Tf", "50 750 Td"]
    for i, ln in enumerate(lines):
        if i > 0:
            text_ops.append("0 -16 Td")
        text_ops.append(f"({esc(ln)}) Tj")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("ascii")

    objects: list[bytes] = []

    def add(content: bytes) -> int:
        objects.append(content)
        return len(objects)

    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    add(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    add(
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    )
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    data = bytes(out)
    path.write_bytes(data)
    return data


@pytest.fixture
def pdf_builder():
    return make_simple_pdf


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    return tmp_path


@pytest.fixture
def db_path(tmp_data_dir: Path) -> Path:
    return tmp_data_dir / "ftm.sqlite"


@pytest.fixture
def db(db_path: Path):
    from ftm import db as db_module

    db_module.init(db_path)
    conn = db_module.connect(db_path)
    yield conn
    conn.close()
