"""
Conversation management endpoints.

Routes for:
- POST /documents/{document_id}/conversations - Create conversation
- GET /documents/{document_id}/conversations - List conversations
- GET /conversations/{conversation_id} - Get conversation details
- DELETE /conversations/{conversation_id} - Delete conversation
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from conversation_service import (
    create_conversation,
    get_conversation,
    list_conversations,
    delete_conversation,
)
from database import get_db
from models import Document, User
from schemas import (
    ConversationCreateRequest,
    ConversationResponse,
    ConversationDetailResponse,
    MessageSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])


# ---------------------------------------------------------------------------
# Create Conversation
# ---------------------------------------------------------------------------


@router.post(
    "/documents/{document_id}/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_document_conversation(
    document_id: str,
    body: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """Create a new conversation for a document.
    
    Args:
        document_id: Document to converse about
        body: Request with optional title
        current_user: Authenticated user
        db: Database session
    
    Returns:
        ConversationResponse with conversation metadata
    
    Raises:
        404: Document not found or user doesn't own it
    """
    # Verify document ownership
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        conversation = create_conversation(
            db=db,
            user_id=current_user.id,
            document_id=document_id,
            title=body.title,
        )
        
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at.isoformat(),
            updated_at=conversation.updated_at.isoformat(),
            message_count=0,
            last_message_at=None,
        )
    except Exception as exc:
        logger.error("Error creating conversation: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to create conversation",
        ) from exc


# ---------------------------------------------------------------------------
# List Conversations
# ---------------------------------------------------------------------------


@router.get(
    "/documents/{document_id}/conversations",
    response_model=list[ConversationResponse],
    status_code=status.HTTP_200_OK,
)
def list_document_conversations(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConversationResponse]:
    """List conversations for a document.
    
    Args:
        document_id: Document ID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        List of ConversationResponse objects (newest updated first)
    
    Raises:
        404: Document not found or user doesn't own it
    """
    # Verify document ownership
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    
    conversations = list_conversations(
        db=db,
        user_id=current_user.id,
        document_id=document_id,
    )
    
    return [
        ConversationResponse(
            id=c["id"],
            title=c["title"],
            created_at=c["created_at"],
            updated_at=c["updated_at"],
            message_count=c["message_count"],
            last_message_at=c["last_message_at"],
        )
        for c in conversations
    ]


# ---------------------------------------------------------------------------
# Get Conversation Details
# ---------------------------------------------------------------------------


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_200_OK,
)
def get_conversation_details(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationDetailResponse:
    """Get conversation details with full message history.
    
    Args:
        conversation_id: Conversation ID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        ConversationDetailResponse with messages
    
    Raises:
        404: Conversation not found or user doesn't own it
    """
    conversation = get_conversation(
        db=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get all messages for this conversation
    messages = []
    for msg in conversation.messages:
        messages.append(
            MessageSchema(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                citations=msg.citations,
                created_at=msg.created_at.isoformat(),
            )
        )
    
    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
        message_count=len(messages),
        last_message_at=messages[-1].created_at if messages else None,
        messages=messages,
    )


# ---------------------------------------------------------------------------
# Delete Conversation
# ---------------------------------------------------------------------------


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a conversation and all its messages.
    
    Args:
        conversation_id: Conversation ID
        current_user: Authenticated user
        db: Database session
    
    Raises:
        404: Conversation not found or user doesn't own it
    """
    deleted = delete_conversation(
        db=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
