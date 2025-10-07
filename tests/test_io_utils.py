from pathlib import Path

import pytest

from src import io_utils


def test_load_text_prefers_direct_input(tmp_path):
    sample_file = tmp_path / "example.txt"
    sample_file.write_text("Fallback text", encoding="utf-8")
    result = io_utils.load_text("Typed text", sample_file)
    assert result == "Typed text"


def test_load_text_from_text_file(tmp_path):
    sample_file = tmp_path / "example.txt"
    sample_file.write_text("Line one\r\n\r\nLine two", encoding="utf-8")
    result = io_utils.load_text("", sample_file)
    assert result == "Line one\n\nLine two"


def test_load_text_requires_input():
    with pytest.raises(ValueError):
        io_utils.load_text("   ", None)


@pytest.mark.skipif(io_utils.docx is None, reason="python-docx not installed")
def test_read_docx_file():
    fixtures_dir = Path(__file__).parent / "fixtures"
    docx_path = fixtures_dir / "sample.docx"
    text = io_utils.read_docx_file(docx_path)
    assert "sample docx" in text
