import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from document_parser import extract_document_text


def build_pdf_with_text(text: str) -> bytes:
    content_stream = f"BT /F1 18 Tf 72 72 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    objects[3] = f"<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1") + content_stream + b"\nendstream"

    pdf_data = bytearray(b"%PDF-1.4\n")
    offsets = [0]

    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf_data))
        pdf_data.extend(f"{index} 0 obj\n".encode("latin-1"))
        pdf_data.extend(obj)
        pdf_data.extend(b"\nendobj\n")

    xref_position = len(pdf_data)
    pdf_data.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf_data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf_data.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))

    pdf_data.extend(b"trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n")
    pdf_data.extend(str(xref_position).encode("ascii"))
    pdf_data.extend(b"\n%%EOF\n")
    return bytes(pdf_data)


class PdfSupportTests(unittest.TestCase):
    def test_extract_document_text_supports_pdf_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "sample.pdf"
            pdf_path.write_bytes(build_pdf_with_text("Hello PDF support"))

            result = extract_document_text(pdf_path)

            self.assertIn("text", result)
            self.assertGreater(result["word_count"], 0)
            self.assertGreaterEqual(result["page_count"], 1)


if __name__ == "__main__":
    unittest.main()
