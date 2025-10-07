"""Utilities for loading text from a text field or a file."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

try:  # Optional dependency for Word documents
    import docx  # type: ignore
except Exception:  # pragma: no cover - handled gracefully during runtime
    docx = None  # type: ignore

try:  # Optional dependency for EPUB files
    from ebooklib import epub  # type: ignore
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - handled gracefully during runtime
    epub = None  # type: ignore
    BeautifulSoup = None  # type: ignore

ENCODINGS_TO_TRY = ("utf-8", "utf-16", "latin-1")


def normalise_newlines(text: str) -> str:
    """Normalise various newline styles and collapse repeated blank lines."""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", unified).strip()


def read_text_file(path: Path) -> str:
    """Read a plain text file trying a couple of common encodings."""
    last_error: Optional[Exception] = None
    for encoding in ENCODINGS_TO_TRY:
        try:
            with path.open("r", encoding=encoding) as f:
                return normalise_newlines(f.read())
        except Exception as exc:  # pragma: no cover - difficult to trigger reliably
            logging.debug("Failed to read %s with %s: %s", path, encoding, exc)
            last_error = exc
    if last_error:
        raise last_error
    raise IOError(f"Unable to read text file: {path}")


def read_docx_file(path: Path) -> str:
    """Extract text from a Microsoft Word document."""
    if docx is None:
        raise ImportError(
            "python-docx is required to parse .docx files but is not installed."
        )
    document = docx.Document(str(path))
    paragraphs = [para.text for para in document.paragraphs if para.text.strip()]
    return normalise_newlines("\n\n".join(paragraphs))


def read_epub_file(path: Path) -> str:
    """Extract text from an EPUB document using BeautifulSoup for HTML parsing."""
    if epub is None or BeautifulSoup is None:
        raise ImportError(
            "ebooklib and beautifulsoup4 are required to parse .epub files but are"
            " not installed."
        )
    book = epub.read_epub(str(path))
    chapters = []
    for item in book.get_items():
        if item.get_type() == epub.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_body_content(), "html.parser")
            text = soup.get_text(" ", strip=True)
            if text:
                chapters.append(text)
    return normalise_newlines("\n\n".join(chapters))


def load_text(text: Optional[str], file_path: Optional[Path]) -> str:
    """Resolve the input text coming either from the UI textbox or a file."""
    if text and text.strip():
        logging.debug("Using direct text input (%d characters).", len(text))
        return normalise_newlines(text)

    if not file_path:
        raise ValueError("Either direct text input or a file must be provided.")

    suffix = file_path.suffix.lower()
    logging.debug("Loading text from %s", file_path)
    if suffix == ".txt":
        return read_text_file(file_path)
    if suffix == ".docx":
        return read_docx_file(file_path)
    if suffix == ".epub":
        return read_epub_file(file_path)

    raise ValueError(f"Unsupported file format: {file_path.suffix}")

