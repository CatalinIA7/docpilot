from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from auth import get_current_user
from config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, UPLOAD_DIR
from database import get_db
from document_parser import extract_document_text
from models import Document, User
from schemas import DocumentResponse, DocumentSearchResponse

router = APIRouter(prefix="/documents", tags=["documents"])


def _build_preview(document: Document, query: str) -> str:
    if document.text:
        lowered_query = query.lower()
        lowered_text = document.text.lower()
        match_index = lowered_text.find(lowered_query)
        if match_index != -1:
            start = max(0, match_index - 60)
            end = min(len(document.text), match_index + len(query) + 60)
            preview = document.text[start:end].strip()
            if start > 0:
                preview = "…" + preview
            if end < len(document.text):
                preview = preview + "…"
            return preview
    if query.lower() in document.filename.lower():
        return f"Filename match: {document.filename}"
    return document.preview or ""


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()
    if not original_name or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only DOCX and PDF files are supported")

    content = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB limit")
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")

    document_id = str(uuid4())
    stored_filename = f"{document_id}{extension}"
    stored_path = UPLOAD_DIR / stored_filename
    stored_path.write_bytes(content)

    try:
        parsed = extract_document_text(stored_path)
    except Exception as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Could not parse document: {exc}")

    document = Document(
        id=document_id,
        user_id=current_user.id,
        filename=original_name,
        stored_filename=stored_filename,
        file_type=extension.removeprefix("."),
        size=len(content),
        **parsed,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list(db.scalars(
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
    ))


@router.get("/search", response_model=list[DocumentSearchResponse])
def search_documents(
    q: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter 'q' must not be empty")

    search_term = query.lower()
    documents = db.scalars(
        select(Document)
        .where(Document.user_id == current_user.id)
        .where(
            or_(
                func.lower(Document.filename).contains(search_term),
                func.lower(Document.text).contains(search_term),
            )
        )
        .order_by(Document.created_at.desc())
        .limit(20)
    )

    return [
        DocumentSearchResponse(
            id=document.id,
            filename=document.filename,
            created_at=document.created_at,
            preview=_build_preview(document, query),
        )
        for document in documents
    ]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    (UPLOAD_DIR / document.stored_filename).unlink(missing_ok=True)
    db.delete(document)
    db.commit()
