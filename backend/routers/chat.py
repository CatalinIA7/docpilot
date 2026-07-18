"""
POST /documents/{document_id}/chat
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, status, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_service import AIConfigError, AIProviderError, answer_question
from auth import get_current_user
from config import UPLOAD_DIR, OBSERVABILITY_ENABLED, OBSERVABILITY_PERSIST
from database import get_db
from document_parser import extract_document_text, SourceSection
from models import Document, DocumentChunk, User, AIRequestMetric
from schemas import ChatResponse
from retrieval_service import (
    retrieve_chunks,
    RetrievalConfigurationError,
    RetrievalProviderError,
    RetrievalResponseError,
)
from observability_service import (
    ChatObservabilityRecorder,
    generate_request_id,
    parse_request_id,
    Status,
    FailureStage,
    ProviderErrorType,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

_MAX_QUESTION_LENGTH = 1_000


class ChatRequest(BaseModel):
    question: Annotated[str, Field(min_length=1, max_length=_MAX_QUESTION_LENGTH)]

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Question must not be empty or whitespace.")
        return v.strip()


# ---------------------------------------------------------------------------
# Observability helper
# ---------------------------------------------------------------------------


def _persist_observability_record(
    db: Session,
    record_data: dict,
) -> None:
    """Safely persist observability record without breaking the request."""
    if not OBSERVABILITY_PERSIST:
        return

    try:
        metric = AIRequestMetric(**record_data)
        db.add(metric)
        db.commit()
    except Exception as exc:
        # Log but do not raise — observability must never break a successful request
        logger.error("Failed to persist observability record: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


def _map_exception_to_provider_error_type(exc: Exception) -> str | None:
    """Map exceptions to safe provider error categories."""
    exc_name = type(exc).__name__
    if "Authentication" in exc_name or "Unauthorized" in exc_name:
        return ProviderErrorType.AUTHENTICATION
    elif "RateLimit" in exc_name:
        return ProviderErrorType.RATE_LIMIT
    elif "Timeout" in exc_name:
        return ProviderErrorType.TIMEOUT
    elif "Configuration" in exc_name or "Config" in exc_name:
        return ProviderErrorType.CONFIGURATION
    return None


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/documents/{document_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
)
def chat_with_document(
    document_id: str,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_request_id: str | None = Header(None),
) -> Response:
    """
    Chat with a document using RAG retrieval.
    
    Returns ChatResponse with answer and citations, plus X-Request-ID header.
    """
    # Parse or generate request ID
    request_id = parse_request_id(x_request_id) or generate_request_id()
    
    # Initialize observability if enabled
    obs_enabled = OBSERVABILITY_ENABLED
    obs_recorder: ChatObservabilityRecorder | None = None
    if obs_enabled:
        obs_recorder = ChatObservabilityRecorder(
            request_id=request_id,
            user_id=current_user.id,
            document_id=document_id,
        )

    response_obj: ChatResponse | None = None
    try:
        # 1. Authorization/ownership check
        document = db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == current_user.id,
            )
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        # 2. Load persisted chunks for this document
        chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            )
        )

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="This document has no extractable content and cannot be used for chat.",
            )

        # 3. Filter chunks with embeddings for retrieval
        embedded_chunks = [c for c in chunks if c.embedding is not None]

        if not embedded_chunks:
            # No chunks have embeddings — cannot perform RAG retrieval
            raise HTTPException(
                status_code=400,
                detail="This document does not have embeddings and cannot be used for retrieval-based chat.",
            )

        # Record loading completion for observability
        if obs_recorder:
            obs_recorder.candidate_chunk_count = len(chunks)
            obs_recorder.embedded_candidate_count = len(embedded_chunks)

        # 4. Retrieve relevant chunks using RAG
        retrieval_start = time.perf_counter()
        try:
            retrieval_result = retrieve_chunks(
                question=body.question,
                chunks=embedded_chunks,
            )
        except RetrievalConfigurationError as exc:
            if obs_recorder:
                obs_recorder.mark_failure(
                    FailureStage.RETRIEVAL,
                    provider_error_type=ProviderErrorType.CONFIGURATION,
                )
                obs_recorder.emit_log()
                record_dict = _observability_record_to_dict(obs_recorder.build_record())
                _persist_observability_record(db, record_dict)
            logger.error("Retrieval configuration error: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Retrieval service is not configured. Please contact the administrator.",
            ) from exc
        except RetrievalProviderError as exc:
            if obs_recorder:
                obs_recorder.mark_failure(
                    FailureStage.RETRIEVAL,
                    provider_error_type=_map_exception_to_provider_error_type(exc),
                )
                obs_recorder.emit_log()
                record_dict = _observability_record_to_dict(obs_recorder.build_record())
                _persist_observability_record(db, record_dict)
            logger.error("Retrieval provider error: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="The embedding service is temporarily unavailable. Please try again later.",
            ) from exc
        except RetrievalResponseError as exc:
            if obs_recorder:
                obs_recorder.mark_failure(FailureStage.RETRIEVAL)
                obs_recorder.emit_log()
                record_dict = _observability_record_to_dict(obs_recorder.build_record())
                _persist_observability_record(db, record_dict)
            logger.error("Retrieval response error: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="Failed to retrieve relevant content. Please try again later.",
            ) from exc

        retrieval_duration_ms = (time.perf_counter() - retrieval_start) * 1000

        # 5. Check if retrieval returned any chunks
        if not retrieval_result.chunks:
            if obs_recorder:
                obs_recorder.mark_failure(FailureStage.RETRIEVAL)
                obs_recorder.emit_log()
                record_dict = _observability_record_to_dict(obs_recorder.build_record())
                _persist_observability_record(db, record_dict)
            raise HTTPException(
                status_code=400,
                detail="Could not find relevant content in this document to answer your question.",
            )

        # Record retrieval for observability
        if obs_recorder:
            retrieved_ids = [rc.chunk.id for rc in retrieval_result.chunks]
            retrieved_scores = [rc.similarity_score for rc in retrieval_result.chunks]
            obs_recorder.record_retrieval(
                candidate_count=retrieval_result.candidate_count,
                embedded_candidate_count=retrieval_result.candidate_count,
                retrieved_count=retrieval_result.retrieved_count,
                chunk_ids=retrieved_ids,
                scores=retrieved_scores,
                top_k=retrieval_result.top_k,
                min_score=retrieval_result.min_score,
                duration_ms=retrieval_duration_ms,
            )

        # 6. Convert retrieved chunks to SourceSection format for AI service
        # Build a mapping from source_id to chunk metadata for citation validation
        retrieved_chunks_by_index = {
            rc.rank - 1: rc.chunk for rc in retrieval_result.chunks
        }

        source_sections = [
            SourceSection(
                source_id=rc.rank,  # Use rank as source_id for citations
                text=rc.chunk.text,
                page=rc.chunk.page,
                paragraph=rc.chunk.paragraph,
            )
            for rc in retrieval_result.chunks
        ]

        # Measure prompt size
        prompt_size = sum(len(s.text) for s in source_sections)
        if obs_recorder:
            obs_recorder.prompt_character_count = prompt_size

        # 7. Call AI service with retrieved chunks (not full document)
        generation_start = time.perf_counter()
        try:
            answer, citations = answer_question(
                sections=source_sections,
                question=body.question,
            )
        except AIConfigError as exc:
            if obs_recorder:
                obs_recorder.mark_failure(
                    FailureStage.GENERATION,
                    provider_error_type=ProviderErrorType.CONFIGURATION,
                )
                obs_recorder.emit_log()
                record_dict = _observability_record_to_dict(obs_recorder.build_record())
                _persist_observability_record(db, record_dict)
            logger.error("AI configuration error: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="AI service is not configured. Please contact the administrator.",
            ) from exc
        except AIProviderError as exc:
            if obs_recorder:
                obs_recorder.mark_failure(
                    FailureStage.GENERATION,
                    provider_error_type=_map_exception_to_provider_error_type(exc),
                )
                obs_recorder.emit_log()
                record_dict = _observability_record_to_dict(obs_recorder.build_record())
                _persist_observability_record(db, record_dict)
            logger.error("AI provider error: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="The AI service is temporarily unavailable. Please try again later.",
            ) from exc

        generation_duration_ms = (time.perf_counter() - generation_start) * 1000

        # 8. Validate and convert citations
        # Citations from AI service reference source_ids in the retrieved chunks.
        # Validate that they are in range [1, len(retrieved_chunks)].
        from schemas import Citation as SchemaCitation

        response_citations = []
        for c in citations:
            # Validate citation is within the retrieved set
            if c.source_id < 1 or c.source_id > len(retrieval_result.chunks):
                # Skip citations that reference non-existent source IDs
                logger.warning(
                    "Skipping invalid citation source_id %d (only %d sources retrieved)",
                    c.source_id,
                    len(retrieval_result.chunks),
                )
                continue

            # Map back to the actual chunk to get verified metadata
            retrieved_chunk = retrieved_chunks_by_index.get(c.source_id - 1)
            if retrieved_chunk:
                response_citations.append(
                    SchemaCitation(
                        source_id=c.source_id,
                        page=retrieved_chunk.page,
                        paragraph=retrieved_chunk.paragraph,
                        excerpt=retrieved_chunk.text[:150].rstrip() + ("..." if len(retrieved_chunk.text) > 150 else ""),
                    )
                )

        # Record generation for observability
        if obs_recorder:
            obs_recorder.record_generation(
                model="gpt-4o-mini",  # From ai_service default
                prompt_char_count=prompt_size,
                response_char_count=len(answer),
                citation_count=len(response_citations),
                duration_ms=generation_duration_ms,
            )

        # Build response
        response_obj = ChatResponse(answer=answer, citations=response_citations)

        # Mark success for observability
        if obs_recorder:
            # No explicit mark_failure, so status remains Status.SUCCESS
            obs_recorder.emit_log()
            record_dict = _observability_record_to_dict(obs_recorder.build_record())
            _persist_observability_record(db, record_dict)

        return response_obj

    except HTTPException as exc:
        # Let HTTPExceptions pass through (these are intentional errors)
        # but record failure if not already recorded
        if obs_recorder and obs_recorder.status != Status.FAILED:
            obs_recorder.mark_failure(FailureStage.UNKNOWN)
            obs_recorder.emit_log()
            record_dict = _observability_record_to_dict(obs_recorder.build_record())
            _persist_observability_record(db, record_dict)
        
        # Re-raise with request ID header
        response = Response(status_code=exc.status_code)
        response.headers["X-Request-ID"] = request_id
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers={"X-Request-ID": request_id},
        ) from exc

    except Exception as exc:
        # Unexpected error
        if obs_recorder:
            obs_recorder.mark_failure(FailureStage.UNKNOWN)
            obs_recorder.emit_log()
            record_dict = _observability_record_to_dict(obs_recorder.build_record())
            _persist_observability_record(db, record_dict)
        
        logger.exception("Unexpected error in chat endpoint")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
            headers={"X-Request-ID": request_id},
        ) from exc


def _observability_record_to_dict(record) -> dict:
    """Convert observability record to database-compatible dict."""
    return {
        "request_id": record.request_id,
        "user_id": record.user_id,
        "document_id": record.document_id,
        "status": record.status,
        "failure_stage": record.failure_stage,
        "total_duration_ms": record.total_duration_ms,
        "question_embedding_duration_ms": record.question_embedding_duration_ms,
        "retrieval_duration_ms": record.retrieval_duration_ms,
        "generation_duration_ms": record.generation_duration_ms,
        "candidate_chunk_count": record.candidate_chunk_count,
        "embedded_candidate_count": record.embedded_candidate_count,
        "retrieved_chunk_count": record.retrieved_chunk_count,
        "retrieved_chunk_ids": record.retrieved_chunk_ids,
        "retrieval_scores": record.retrieval_scores,
        "retrieval_top_k": record.retrieval_top_k,
        "retrieval_min_score": record.retrieval_min_score,
        "prompt_character_count": record.prompt_character_count,
        "response_character_count": record.response_character_count,
        "citation_count": record.citation_count,
        "ai_model": record.ai_model,
        "embedding_model": record.embedding_model,
        "embedding_dimension": record.embedding_dimension,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "total_tokens": record.total_tokens,
        "provider_error_type": record.provider_error_type,
    }
