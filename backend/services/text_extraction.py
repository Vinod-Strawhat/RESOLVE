"""Minimal text extraction for uploaded documents (plain text + PDF)."""

import io
from pathlib import Path

from pypdf import PdfReader

TEXT_EXTENSIONS = {".txt", ".md"}
PDF_EXTENSIONS = {".pdf"}


def extract_text(filename: str, content: bytes) -> str:
    """Extract readable text from an uploaded file.

    Returns the extracted text, or an empty string when no readable text could
    be found (for example a scanned/image-only PDF).
    """
    extension = Path(filename).suffix.lower()
    if extension in TEXT_EXTENSIONS:
        return _decode_text(content)
    if extension in PDF_EXTENSIONS:
        return _extract_pdf_text(content)
    return ""


def _decode_text(content: bytes) -> str:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return content.decode("utf-16").strip()
        except (UnicodeDecodeError, UnicodeError):
            pass
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding).strip()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return content.decode("latin-1", errors="replace").strip()


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception:
        return ""
    pages = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(text)
    return "\n".join(pages).strip()