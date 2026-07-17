from pathlib import Path
from docx import Document as DocxDocument
from pypdf import PdfReader


def _result(text: str, paragraph_count: int) -> dict:
    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return {
        "text": cleaned,
        "preview": cleaned[:500],
        "word_count": len(cleaned.split()),
        "character_count": len(cleaned),
        "paragraph_count": paragraph_count,
    }


def extract_document_text(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        document = DocxDocument(path)
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        return _result("\n".join(paragraphs), len(paragraphs))
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        non_empty = [page for page in pages if page]
        return _result("\n".join(non_empty), len(non_empty))
    raise ValueError("Unsupported file type")
