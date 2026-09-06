from pypdf import PdfWriter

from backend.services.text_extraction import extract_text


def _make_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(body)
    body += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets:
        body += f"{offset:010d} 00000 n \n".encode()
    body += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return bytes(body)


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    import io

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_extract_text_from_utf8():
    text = extract_text("invoice.txt", "Product: ASUS Vivobook\nAmount: 35000".encode("utf-8"))
    assert "ASUS Vivobook" in text
    assert "35000" in text


def test_extract_text_from_marksown():
    text = extract_text("warranty.md", b"# Warranty\nClaim rejected.")
    assert "Warranty" in text
    assert "rejected" in text


def test_extract_text_latin1_fallback():
    raw = "Seller: Jos\u00e9".encode("latin-1")
    text = extract_text("notes.txt", raw)
    assert "Jos\u00e9" in text


def test_extract_text_unsupported_extension_returns_empty():
    assert extract_text("photo.png", b"not text") == ""


def test_extract_pdf_text():
    pdf = _make_pdf("Product: ASUS Vivobook Review this warranty case")
    text = extract_text("invoice.pdf", pdf)
    assert "Product: ASUS Vivobook" in text


def test_extract_pdf_empty_page_returns_empty():
    text = extract_text("scan.pdf", _blank_pdf())
    assert text == ""


def test_extract_pdf_corrupt_bytes_returns_empty():
    assert extract_text("broken.pdf", b"this is not a pdf") == ""


def test_extract_pdf_empty_bytes_returns_empty():
    assert extract_text("empty.pdf", b"") == ""