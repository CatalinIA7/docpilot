from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader


@dataclass(frozen=True)
class SourceSection:
    """Source section extracted from a document with location metadata."""

    source_id: int  # 1-indexed position in the document
    text: str  # The extracted text content
    page: int | None = None  # Page number (PDF), 1-indexed
    paragraph: int | None = None  # Paragraph number (DOCX), 1-indexed

    def excerpt(self, max_length: int = 150) -> str:
        """Return a shortened excerpt for citation display."""
        if len(self.text) <= max_length:
            return self.text
        return self.text[:max_length].rstrip() + "..."


def _result(
    text: str, paragraph_count: int, sections: list[SourceSection] | None = None
) -> dict:
    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return {
        "text": cleaned,
        "preview": cleaned[:500],
        "word_count": len(cleaned.split()),
        "character_count": len(cleaned),
        "paragraph_count": paragraph_count,
        "_sections": sections or [],  # Internal; not persisted to DB
    }


def extract_document_text(path: Path) -> dict:
    """Extract document text and return metadata + internal sections.

    The returned dict includes _sections (a list of SourceSection objects)
    which is not stored in the database but used for AI prompting.
    """
    suffix = path.suffix.lower()
    if suffix == ".docx":
        document = DocxDocument(path)
        paragraphs = [
            p.text.strip() for p in document.paragraphs if p.text.strip()
        ]
        sections = [
            SourceSection(source_id=i + 1, text=p, paragraph=i + 1)
            for i, p in enumerate(paragraphs)
        ]
        return _result("\n".join(paragraphs), len(paragraphs), sections)
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        sections = []
        section_id = 1
        for page_num, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                sections.append(
                    SourceSection(source_id=section_id, text=text, page=page_num)
                )
                section_id += 1
        pages_text = [section.text for section in sections]
        return _result("\n".join(pages_text), len(pages_text), sections)
    raise ValueError("Unsupported file type")
