from pathlib import Path

from docx import Document
from pypdf import PdfReader


def extract_docx_text(file_path: Path) -> dict:
    document = Document(file_path)

    paragraphs = []

    for paragraph in document.paragraphs:
        cleaned_text = paragraph.text.strip()

        if cleaned_text:
            paragraphs.append(cleaned_text)

    extracted_text = "\n".join(paragraphs)
    words = extracted_text.split()

    return {
        "text": extracted_text,
        "preview": extracted_text[:500],
        "word_count": len(words),
        "character_count": len(extracted_text),
        "paragraph_count": len(paragraphs),
    }


def extract_pdf_text(file_path: Path) -> dict:
    reader = PdfReader(str(file_path))
    pages = reader.pages

    paragraphs = []
    for page in pages:
        text = page.extract_text() or ""
        cleaned_text = text.strip()
        if cleaned_text:
            paragraphs.append(cleaned_text)

    extracted_text = "\n".join(paragraphs)
    words = extracted_text.split()

    return {
        "text": extracted_text,
        "preview": extracted_text[:500],
        "word_count": len(words),
        "character_count": len(extracted_text),
        "paragraph_count": len(paragraphs),
        "page_count": len(pages),
    }


def extract_document_text(file_path: Path) -> dict:
    extension = file_path.suffix.lower()

    if extension == ".docx":
        return extract_docx_text(file_path)

    if extension == ".pdf":
        return extract_pdf_text(file_path)

    raise ValueError(f"Unsupported file type: {extension}")