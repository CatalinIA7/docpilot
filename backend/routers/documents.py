import io
import logging
from pathlib import Path, PurePosixPath
import time
from uuid import uuid4
import zipfile
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from auth import get_current_user
from config import (
    ALLOWED_EXTENSIONS,
    MAX_DOCX_ENTRIES,
    MAX_DOCX_UNCOMPRESSED_SIZE,
    MAX_UPLOAD_SIZE,
    UPLOAD_DIR,
)
from database import get_db
from document_parser import extract_document_text
from chunking import Chunker, ChunkingConfig
from embedding_service import (
    embed_texts,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    EmbeddingResponseError,
)
from models import Document, DocumentChunk, User
from schemas import DocumentResponse, DocumentSearchResponse, DocumentDetailResponse
from observability import log_event

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger("docpilot.documents")

_ALLOWED_CONTENT_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
}
_DOCX_REQUIRED_ENTRIES = {"[Content_Types].xml", "word/document.xml"}


def _sanitize_upload_filename(raw_filename: str | None) -> str:
    """Return a bounded display filename with both path separator styles removed."""
    normalized = (raw_filename or "").replace("\\", "/")
    filename = Path(normalized).name.strip()
    if (
        filename in {"", ".", ".."}
        or len(filename) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in filename)
    ):
        raise ValueError("Invalid upload filename")
    return filename


def _validate_declared_content_type(extension: str, content_type: str | None) -> None:
    normalized = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if normalized not in _ALLOWED_CONTENT_TYPES[extension]:
        raise ValueError("Declared content type does not match the file extension")


def _validate_file_structure(extension: str, content: bytes) -> None:
    """Validate signatures and bound DOCX archive expansion before parsing."""
    if extension == ".pdf":
        if b"%PDF-" not in content[:1024]:
            raise ValueError("Invalid PDF signature")
        return

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if len(entries) > MAX_DOCX_ENTRIES:
                raise ValueError("DOCX archive has too many entries")
            if not _DOCX_REQUIRED_ENTRIES.issubset(names):
                raise ValueError("DOCX archive is missing required entries")
            if sum(entry.file_size for entry in entries) > MAX_DOCX_UNCOMPRESSED_SIZE:
                raise ValueError("DOCX archive expands beyond the configured limit")
            for entry in entries:
                normalized_name = entry.filename.replace("\\", "/")
                parts = PurePosixPath(normalized_name).parts
                if (
                    PurePosixPath(normalized_name).is_absolute()
                    or ".." in parts
                    or entry.flag_bits & 0x1
                ):
                    raise ValueError("DOCX archive contains an unsafe entry")
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError("Invalid DOCX archive") from exc


def _safe_upload_path(stored_filename: str) -> Path:
    """Resolve a storage name without allowing a database value to escape uploads."""
    if Path(stored_filename).name != stored_filename or "\\" in stored_filename:
        raise ValueError("Unsafe stored filename")
    upload_root = UPLOAD_DIR.resolve()
    candidate = (upload_root / stored_filename).resolve()
    if candidate.parent != upload_root:
        raise ValueError("Unsafe stored filename")
    return candidate


def _build_preview(document: Document, query: str) -> str:
    query_lower = query.lower()
    if document.text:
        lowered_text = document.text.lower()
        match_index = lowered_text.find(query_lower)
        if match_index != -1:
            start = max(0, match_index - 60)
            end = min(len(document.text), match_index + len(query) + 60)
            preview = document.text[start:end].strip()
            if start > 0:
                preview = "…" + preview
            if end < len(document.text):
                preview = preview + "…"
            if len(preview) > 180:
                preview = preview[:177].rstrip() + "..."
            return preview

    if query_lower in document.filename.lower():
        preview = document.text[:180].strip() if document.text else (document.preview or "")
        if len(preview) > 180:
            preview = preview[:177].rstrip() + "..."
        return preview

    return ""


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    started_at = time.perf_counter()
    try:
        original_name = _sanitize_upload_filename(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload filename") from exc
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only DOCX and PDF files are supported")
    try:
        _validate_declared_content_type(extension, file.content_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=415,
            detail="Declared content type does not match the file extension",
        ) from exc

    content = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB limit")
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    try:
        _validate_file_structure(extension, content)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="The uploaded file is not a valid PDF or DOCX document",
        ) from exc

    document_id = str(uuid4())
    stored_filename = f"{document_id}{extension}"
    stored_path = _safe_upload_path(stored_filename)
    try:
        stored_path.write_bytes(content)
    except OSError as exc:
        log_event(
            logger,
            logging.ERROR,
            "document_storage_failed",
            "Uploaded document could not be written",
            document_id=document_id,
            file_type=extension.removeprefix("."),
            size_bytes=len(content),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            error_type=type(exc).__name__,
        )
        raise

    try:
        parsed = extract_document_text(stored_path)
    except Exception as exc:
        stored_path.unlink(missing_ok=True)
        log_event(
            logger,
            logging.ERROR,
            "document_parsing_failed",
            "Uploaded document could not be parsed",
            document_id=document_id,
            file_type=extension.removeprefix("."),
            size_bytes=len(content),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            error_type=type(exc).__name__,
        )
        raise HTTPException(status_code=422, detail="Could not parse the uploaded document")

    # Extract only the fields needed for Document model (exclude internal _sections)
    doc_data = {k: v for k, v in parsed.items() if not k.startswith("_")}
    document = Document(
        id=document_id,
        user_id=current_user.id,
        filename=original_name,
        stored_filename=stored_filename,
        file_type=extension.removeprefix("."),
        size=len(content),
        **doc_data,
    )
    
    # Extract sections for chunking (from the internal _sections list)
    sections = parsed.get("_sections", [])
    chunk_count = 0
    if sections:
        try:
            # Generate chunks using the chunking module
            chunker = Chunker(ChunkingConfig())
            chunks = chunker.chunk(sections)
            chunk_count = len(chunks)
            
            # Create database chunk records (embeddings will be added next)
            db_chunks = [
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    page=chunk.page,
                    paragraph=chunk.paragraph,
                    source_section_id=chunk.source_section_id,
                    embedding=None,  # Will be filled from embedding service
                )
                for chunk in chunks
            ]
            
            # Generate embeddings for all chunks
            try:
                chunk_texts = [chunk.text for chunk in chunks]
                embeddings = embed_texts(chunk_texts)
                
                # Validate deterministic mapping: exactly one embedding per chunk
                if len(embeddings) != len(db_chunks):
                    raise HTTPException(
                        status_code=500,
                        detail=f"Embedding mismatch: expected {len(db_chunks)} embeddings but got {len(embeddings)}"
                    )
                
                # Associate each embedding with its chunk
                for db_chunk, embedding in zip(db_chunks, embeddings):
                    db_chunk.embedding = embedding
            
            except (EmbeddingConfigurationError, EmbeddingProviderError, EmbeddingResponseError) as exc:
                # Embedding generation failed - rollback the transaction
                stored_path.unlink(missing_ok=True)
                db.rollback()
                log_event(
                    logger,
                    logging.ERROR,
                    "document_embedding_failed",
                    "Document chunk embeddings could not be generated",
                    document_id=document_id,
                    file_type=extension.removeprefix("."),
                    chunk_count=chunk_count,
                    duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
                    error_type=type(exc).__name__,
                )
                raise HTTPException(
                    status_code=502,
                    detail="Could not generate embeddings for document chunks"
                )
            
            # Add all chunks to the session
            for chunk in db_chunks:
                db.add(chunk)
        except HTTPException:
            raise
        except Exception as exc:
            stored_path.unlink(missing_ok=True)
            db.rollback()
            log_event(
                logger,
                logging.ERROR,
                "document_chunking_failed",
                "Document chunks could not be generated",
                document_id=document_id,
                file_type=extension.removeprefix("."),
                duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
                error_type=type(exc).__name__,
            )
            raise HTTPException(status_code=422, detail="Could not process document chunks")
    
    db.add(document)
    db.commit()
    db.refresh(document)
    log_event(
        logger,
        logging.INFO,
        "document_upload_completed",
        "Document upload completed",
        document_id=document_id,
        user_id=current_user.id,
        file_type=extension.removeprefix("."),
        size_bytes=len(content),
        section_count=len(sections),
        chunk_count=chunk_count,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
    )
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
            file_type=document.file_type,
            created_at=document.created_at,
            word_count=document.word_count,
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
    try:
        _safe_upload_path(document.stored_filename).unlink(missing_ok=True)
    except ValueError:
        log_event(
            logger,
            logging.ERROR,
            "document_storage_path_rejected",
            "Stored document path failed containment validation",
            document_id=document.id,
        )
    db.delete(document)
    db.commit()


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
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
    return document
