from pathlib import Path

from ftm.parse.pdf import extract_text


def test_extract_text_returns_known_strings(tmp_path: Path, pdf_builder):
    pdf = tmp_path / "tiny.pdf"
    pdf_builder(
        pdf,
        [
            "Statement of Registrable Interests",
            "1. Shareholdings",
            "BHP Group Ltd",
        ],
    )

    text = extract_text(pdf)

    assert "Statement of Registrable Interests" in text
    assert "Shareholdings" in text
    assert "BHP Group Ltd" in text


def test_extract_text_accepts_str_path(tmp_path: Path, pdf_builder):
    pdf = tmp_path / "tiny.pdf"
    pdf_builder(pdf, ["hello world"])
    assert "hello world" in extract_text(str(pdf))
