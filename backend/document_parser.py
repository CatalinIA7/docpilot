from pathlib import Path

from docx import Document


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
        "word_count": len(words),
        "character_count": len(extracted_text),
        "paragraph_count": len(paragraphs),
    }