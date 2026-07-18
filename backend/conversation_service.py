"""
Conversation history service for managing user-document conversations.

Provides functions for:
- Creating conversations with optional titles
- Loading recent conversation messages (with configurable limit)
- Persisting user and assistant messages
- Retrieving conversation details
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session

from config import CONVERSATION_MAX_MESSAGES
from models import Conversation, Message, Document, User
from schemas import Citation as SchemaCitation

logger = logging.getLogger(__name__)


def _generate_title_from_question(question: str, max_length: int = 50) -> str:
    """Generate a conversation title from the first user question.
    
    Simple truncation without LLM invocation (as per requirements).
    """
    title = question.strip()
    if len(title) > max_length:
        # Truncate at word boundary if possible
        truncated = title[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > 20:  # Ensure we have at least 20 chars
            title = truncated[:last_space] + "..."
        else:
            title = truncated + "..."
    return title


def create_conversation(
    db: Session,
    user_id: str,
    document_id: str,
    title: Optional[str] = None,
) -> Conversation:
    """Create a new conversation.
    
    Args:
        db: Database session
        user_id: User ID (owner)
        document_id: Document ID being discussed
        title: Optional conversation title (required in response, generated if not provided)
    
    Returns:
        Created Conversation object
    
    Raises:
        ValueError: If document doesn't exist or user doesn't own it
    """
    # Verify document exists and user owns it
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
    )
    
    if not document:
        raise ValueError(f"Document {document_id} not found or not owned by user")
    
    # Generate title if not provided
    if not title:
        title = f"Conversation with {document.filename}"
    
    conversation = Conversation(
        id=str(uuid4()),
        user_id=user_id,
        document_id=document_id,
        title=title,
    )
    
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    
    logger.info(
        "Created conversation %s for user %s with document %s",
        conversation.id,
        user_id,
        document_id,
    )
    
    return conversation


def get_conversation(db: Session, conversation_id: str, user_id: str) -> Optional[Conversation]:
    """Get a conversation by ID, verifying ownership.
    
    Args:
        db: Database session
        conversation_id: Conversation ID
        user_id: User ID (for ownership check)
    
    Returns:
        Conversation if found and user owns it, None otherwise
    """
    return db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )


def get_conversation_messages(
    db: Session,
    conversation_id: str,
    limit: Optional[int] = None,
) -> list[Message]:
    """Get messages for a conversation, ordered chronologically.
    
    Args:
        db: Database session
        conversation_id: Conversation ID
        limit: Maximum number of recent messages (None = all)
    
    Returns:
        List of Message objects, ordered by creation time
    """
    query = select(Message).where(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at)
    
    if limit:
        # Get the most recent N messages
        query = query.order_by(desc(Message.created_at)).limit(limit)
        messages = list(db.scalars(query))
        # Reverse to get chronological order
        messages.reverse()
    else:
        messages = list(db.scalars(query))
    
    return messages


def add_user_message(
    db: Session,
    conversation_id: str,
    question: str,
) -> Message:
    """Add a user message to a conversation.
    
    Args:
        db: Database session
        conversation_id: Conversation ID
        question: User's question
    
    Returns:
        Created Message object
    """
    message = Message(
        id=str(uuid4()),
        conversation_id=conversation_id,
        role="user",
        content=question,
        citations=[],
    )
    
    db.add(message)
    db.commit()
    db.refresh(message)
    
    # Update conversation's updated_at timestamp
    conversation = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    if conversation:
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
    
    return message


def add_assistant_message(
    db: Session,
    conversation_id: str,
    answer: str,
    citations: list[SchemaCitation],
) -> Message:
    """Add an assistant message to a conversation with citations.
    
    Args:
        db: Database session
        conversation_id: Conversation ID
        answer: Assistant's answer
        citations: List of Citation objects from AI service
    
    Returns:
        Created Message object
    """
    # Convert citations to JSON-serializable format
    citations_data = [
        {
            "source_id": c.source_id,
            "page": c.page,
            "paragraph": c.paragraph,
            "excerpt": c.excerpt,
        }
        for c in citations
    ]
    
    message = Message(
        id=str(uuid4()),
        conversation_id=conversation_id,
        role="assistant",
        content=answer,
        citations=citations_data,
    )
    
    db.add(message)
    db.commit()
    db.refresh(message)
    
    # Update conversation's updated_at timestamp
    conversation = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    if conversation:
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
    
    return message


def get_recent_messages_for_context(
    db: Session,
    conversation_id: str,
    max_messages: Optional[int] = None,
) -> list[Message]:
    """Get recent messages for inclusion in chat context window.
    
    Returns messages in chronological order suitable for building context.
    
    Args:
        db: Database session
        conversation_id: Conversation ID
        max_messages: Maximum messages to retrieve (defaults to CONVERSATION_MAX_MESSAGES)
    
    Returns:
        List of Message objects in chronological order
    """
    if max_messages is None:
        max_messages = CONVERSATION_MAX_MESSAGES
    
    messages = get_conversation_messages(db, conversation_id, limit=max_messages)
    return messages


def list_conversations(
    db: Session,
    user_id: str,
    document_id: Optional[str] = None,
) -> list[dict]:
    """List conversations for a user, optionally filtered by document.
    
    Returns newest updated conversations first.
    
    Args:
        db: Database session
        user_id: User ID
        document_id: Optional document ID filter
    
    Returns:
        List of conversation dictionaries with metadata
    """
    query = select(Conversation).where(Conversation.user_id == user_id)
    
    if document_id:
        query = query.where(Conversation.document_id == document_id)
    
    # Order by updated_at descending (newest first)
    query = query.order_by(desc(Conversation.updated_at))
    
    conversations = db.scalars(query).all()
    
    # Build response with message counts
    results = []
    for conv in conversations:
        # Count messages
        msg_count = db.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == conv.id
            )
        )
        
        # Get last message timestamp
        last_msg = db.scalar(
            select(Message.created_at).where(
                Message.conversation_id == conv.id
            ).order_by(desc(Message.created_at)).limit(1)
        )
        
        results.append({
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
            "message_count": msg_count,
            "last_message_at": last_msg.isoformat() if last_msg else None,
        })
    
    return results


def delete_conversation(
    db: Session,
    conversation_id: str,
    user_id: str,
) -> bool:
    """Delete a conversation and its messages.
    
    Args:
        db: Database session
        conversation_id: Conversation ID
        user_id: User ID (for ownership check)
    
    Returns:
        True if deleted, False if not found
    """
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    
    if not conversation:
        return False
    
    # Delete all messages (cascaded by model relationship)
    db.delete(conversation)
    db.commit()
    
    logger.info(
        "Deleted conversation %s for user %s",
        conversation_id,
        user_id,
    )
    
    return True
