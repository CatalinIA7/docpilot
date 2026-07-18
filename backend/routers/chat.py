"""
POST /documents/{document_id}/chat

Chat with a document, optionally continuing a conversation.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_service import AIConfigError, AIProviderError, answer_question
from auth import get_current_user
from conversation_service import (
    add_user_message,
    add_assistant_message,
    get_conversation,
    get_recent_messages_for_context,
    create_conversation,
    _generate_title_from_question,
)
from database import get_db
from document_parser import extract_document_text, SourceSection
from models import Document, DocumentChunk, User, Conversation
from schemas import ChatResponse, Citation as SchemaCitation
from retrieval_service import (
    retrieve_chunks,
    RetrievalConfigurationError,
    RetrievalProviderError,
    RetrievalResponseError,
)
from observability import log_event

logger = logging.getLogger("docpilot.chat")

router = APIRouter(tags=["chat"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

_MAX_QUESTION_LENGTH = 1_000


class ChatRequest(BaseModel):
    question: Annotated[str, Field(min_length=1, max_length=_MAX_QUESTION_LENGTH
)]
    conversation_id: Annotated[str | None, Field(None, description="Optional conversation ID to continue")] = None

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
    """Chat with a document, optionally continuing a conversation.
    
    If conversation_id is provided:
    - Loads recent messages for context
    - Persists user message before generation
    - Persists assistant message after generation
    
    If conversation_id is not provided:
    - Performs single-turn chat
    - No message persistence
    
    Always performs semantic retrieval on the current question.
    """
    
    started_at = time.perf_counter()

    # 1. Verify document ownership
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # 2. Handle conversation if conversation_id provided
    conversation: Conversation | None = None
    context_messages = []
    
    if body.conversation_id:
        # Verify conversation ownership and document consistency
        conversation = get_conversation(
            db=db,
            conversation_id=body.conversation_id,
            user_id=current_user.id,
        )
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        if conversation.document_id != document_id:
            raise HTTPException(
                status_code=400,
                detail="Conversation does not belong to this document",
            )
        
        # Load recent messages for context
        context_messages = get_recent_messages_for_context(
            db=db,
            conversation_id=body.conversation_id,
        )
        
        # Persist user message immediately
        add_user_message(
            db=db,
            conversation_id=body.conversation_id,
            question=body.question,
        )

    # 3. Load persisted chunks for this document
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

    # 4. Filter chunks with embeddings for retrieval
    embedded_chunks = [c for c in chunks if c.embedding is not None]

    if not embedded_chunks:
        raise HTTPException(
            status_code=400,
            detail="This document does not have embeddings and cannot be used for retrieval-based chat.",
        )

    # 5. Retrieve relevant chunks using RAG
    try:
        retrieval_result = retrieve_chunks(
            question=body.question,
            chunks=embedded_chunks,
        )
    except RetrievalConfigurationError as exc:
        log_event(
            logger,
            logging.ERROR,
            "chat_retrieval_failed",
            "Chat retrieval configuration failed",
            document_id=document_id,
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Retrieval service is not configured. Please contact the administrator.",
        ) from exc
    except RetrievalProviderError as exc:
        log_event(
            logger,
            logging.ERROR,
            "chat_retrieval_failed",
            "Chat retrieval provider failed",
            document_id=document_id,
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="The embedding service is temporarily unavailable. Please try again later.",
        ) from exc
    except RetrievalResponseError as exc:
        log_event(
            logger,
            logging.ERROR,
            "chat_retrieval_failed",
            "Chat retrieval response was invalid",
            document_id=document_id,
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve relevant content. Please try again later.",
        ) from exc

    # 6. Check if retrieval returned any chunks
    if not retrieval_result.chunks:
        raise HTTPException(
            status_code=400,
            detail="Could not find relevant content in this document to answer your question.",
        )

    # 7. Convert retrieved chunks to SourceSection format for AI service
    retrieved_chunks_by_index = {
        rc.rank - 1: rc.chunk for rc in retrieval_result.chunks
    }

    source_sections = [
        SourceSection(
            source_id=rc.rank,
            text=rc.chunk.text,
            page=rc.chunk.page,
            paragraph=rc.chunk.paragraph,
        )
        for rc in retrieval_result.chunks
    ]

    # 8. Call AI service with retrieved chunks
    try:
        answer, citations = answer_question(
            sections=source_sections,
            question=body.question,
        )
    except AIConfigError as exc:
        log_event(
            logger,
            logging.ERROR,
            "chat_generation_failed",
            "Chat AI configuration failed",
            document_id=document_id,
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured. Please contact the administrator.",
        ) from exc
    except AIProviderError as exc:
        log_event(
            logger,
            logging.ERROR,
            "chat_generation_failed",
            "Chat AI provider failed",
            document_id=document_id,
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="The AI service is temporarily unavailable. Please try again later.",
        ) from exc

    # 9. Validate and convert citations
    response_citations = []
    for c in citations:
        if c.source_id < 1 or c.source_id > len(retrieval_result.chunks):
            log_event(
                logger,
                logging.WARNING,
                "chat_citation_rejected",
                "Model citation referenced an unavailable source",
                document_id=document_id,
                source_id=c.source_id,
                retrieved_source_count=len(retrieval_result.chunks),
            )
            continue

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

    # 10. If conversation, persist assistant message
    if conversation:
        add_assistant_message(
            db=db,
            conversation_id=conversation.id,
            answer=answer,
            citations=response_citations,
        )

    log_event(
        logger,
        logging.INFO,
        "chat_completed",
        "Grounded chat request completed",
        document_id=document_id,
        conversation_id=conversation.id if conversation else None,
        retrieved_chunk_count=len(retrieval_result.chunks),
        citation_count=len(response_citations),
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
    )
    return ChatResponse(answer=answer, citations=response_citations)
