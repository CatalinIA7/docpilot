"""
POST /documents/{document_id}/chat
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_service import AIConfigError, AIProviderError, answer_question
from auth import get_current_user
from config import UPLOAD_DIR
from database import get_db
from document_parser import extract_document_text, SourceSection
from models import Document, DocumentChunk, User
from schemas import ChatResponse
from retrieval_service import (
    retrieve_chunks,
    RetrievalConfigurationError,
    RetrievalProviderError,
    RetrievalResponseError,
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
) -> ChatResponse:
    # 1. Ownership check — intentionally returns 404 (not 403) so the route
    #    does not confirm whether the document exists for other users.
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

    # 4. Retrieve relevant chunks using RAG
    try:
        retrieval_result = retrieve_chunks(
            question=body.question,
            chunks=embedded_chunks,
        )
    except RetrievalConfigurationError as exc:
        logger.error("Retrieval configuration error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Retrieval service is not configured. Please contact the administrator.",
        ) from exc
    except RetrievalProviderError as exc:
        logger.error("Retrieval provider error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="The embedding service is temporarily unavailable. Please try again later.",
        ) from exc
    except RetrievalResponseError as exc:
        logger.error("Retrieval response error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve relevant content. Please try again later.",
        ) from exc

    # 5. Check if retrieval returned any chunks
    if not retrieval_result.chunks:
        raise HTTPException(
            status_code=400,
            detail="Could not find relevant content in this document to answer your question.",
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

    # 7. Call AI service with retrieved chunks (not full document)
    try:
        answer, citations = answer_question(
            sections=source_sections,
            question=body.question,
        )
    except AIConfigError as exc:
        logger.error("AI configuration error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured. Please contact the administrator.",
        ) from exc
    except AIProviderError as exc:
        logger.error("AI provider error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="The AI service is temporarily unavailable. Please try again later.",
        ) from exc

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

    return ChatResponse(answer=answer, citations=response_citations)
