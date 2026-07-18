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
from document_parser import extract_document_text
from models import Document, User
from schemas import ChatResponse

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

    # 2. Require usable extracted text.
    if not document.text or not document.text.strip():
        raise HTTPException(
            status_code=400,
            detail="This document has no extractable text and cannot be used for chat.",
        )

    # 3. Extract document sections (for prompting and citations).
    # Note: extract_document_text() returns _sections in a special key
    # that is not stored in the DB, only used for AI requests.
    extracted = extract_document_text(
        UPLOAD_DIR / document.stored_filename
    )
    sections = extracted.get("_sections", [])

    # 4. Call AI service with sections.
    try:
        answer, citations = answer_question(
            sections=sections,
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

    # Convert ai_service.Citation to schemas.Citation for response
    from schemas import Citation as SchemaCitation

    response_citations = [
        SchemaCitation(
            source_id=c.source_id,
            page=c.page,
            paragraph=c.paragraph,
            excerpt=c.excerpt,
        )
        for c in citations
    ]

    return ChatResponse(answer=answer, citations=response_citations)
