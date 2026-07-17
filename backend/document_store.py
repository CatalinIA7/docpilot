import json
from typing import Any

from sqlalchemy.orm import Session

from models import DocumentRecord


def store_document(db: Session, *, user_id: int, filename: str, stored_filename: str, file_type: str, size: int, text: str, chunks: list[str], embeddings: list[list[float]]) -> DocumentRecord:
    record = DocumentRecord(
        user_id=user_id,
        filename=filename,
        stored_filename=stored_filename,
        file_type=file_type,
        size=size,
        status="processed",
        text=text,
        chunks=json.dumps(chunks),
        embeddings=json.dumps(embeddings),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_user_documents(db: Session, user_id: int) -> list[DocumentRecord]:
    return db.query(DocumentRecord).filter(DocumentRecord.user_id == user_id).order_by(DocumentRecord.created_at.desc()).all()


def get_document_chunks(record: DocumentRecord) -> list[str]:
    return json.loads(record.chunks or "[]")


def get_document_embeddings(record: DocumentRecord) -> list[list[float]]:
    return json.loads(record.embeddings or "[]")
