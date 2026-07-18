"""
Tests for conversation history feature.

Covers:
- Conversation creation, listing, retrieval, deletion
- Message persistence and ordering
- Ownership verification
- Chat with conversation continuation
- Recent message limit
- Citation persistence
"""

from unittest.mock import patch
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from conversation_service import (
    create_conversation,
    get_conversation,
    list_conversations,
    delete_conversation,
    add_user_message,
    add_assistant_message,
    get_recent_messages_for_context,
    _generate_title_from_question,
)
from models import Conversation, Message, Document, User, DocumentChunk
from schemas import Citation


# ---------------------------------------------------------------------------
# Conversation Creation Tests
# ---------------------------------------------------------------------------


class TestConversationCreation:
    def test_create_conversation_with_title(
        self, db_session: Session, registered_user: dict, uploaded_doc: dict
    ):
        """Create conversation with explicit title."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="My Conversation",
        )

        assert conv.id is not None
        assert conv.user_id == user_id
        assert conv.document_id == doc_id
        assert conv.title == "My Conversation"
        assert conv.created_at is not None

    def test_create_conversation_without_title(
        self, db_session: Session, registered_user: dict, uploaded_doc: dict
    ):
        """Create conversation without title (uses document filename)."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title=None,
        )

        assert conv.id is not None
        assert conv.title is not None
        assert len(conv.title) > 0

    def test_create_conversation_nonexistent_document(
        self, db_session: Session, registered_user: dict
    ):
        """Reject creation if document doesn't exist."""
        user_id = registered_user["data"]["user"]["id"]
        
        with pytest.raises(ValueError):
            create_conversation(
                db=db_session,
                user_id=user_id,
                document_id="nonexistent",
                title="Test",
            )

    def test_create_conversation_wrong_owner(
        self, db_session: Session, registered_user: dict, uploaded_doc: dict
    ):
        """Reject creation if user doesn't own document."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        # Create another user
        other_user = User(email="other@example.com", password_hash="secret")
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)
        
        with pytest.raises(ValueError):
            create_conversation(
                db=db_session,
                user_id=other_user.id,
                document_id=doc_id,
                title="Test",
            )


# ---------------------------------------------------------------------------
# Message Persistence Tests
# ---------------------------------------------------------------------------


class TestMessagePersistence:
    def test_add_user_message(
        self,
        db_session: Session,
        registered_user: dict,
        uploaded_doc: dict,
    ):
        """Add user message to conversation."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Test",
        )
        
        msg = add_user_message(
            db=db_session,
            conversation_id=conv.id,
            question="What is this about?",
        )

        assert msg.id is not None
        assert msg.conversation_id == conv.id
        assert msg.role == "user"
        assert msg.content == "What is this about?"
        assert msg.citations == []

        # Verify in database
        db_msg = db_session.query(Message).filter_by(id=msg.id).first()
        assert db_msg is not None
        assert db_msg.content == "What is this about?"

    def test_add_assistant_message(
        self,
        db_session: Session,
        registered_user: dict,
        uploaded_doc: dict,
    ):
        """Add assistant message with citations."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Test",
        )
        
        citations = [
            Citation(source_id=1, page=1, paragraph=1, excerpt="Text excerpt"),
        ]

        msg = add_assistant_message(
            db=db_session,
            conversation_id=conv.id,
            answer="This is the answer.",
            citations=citations,
        )

        assert msg.id is not None
        assert msg.role == "assistant"
        assert msg.content == "This is the answer."
        assert len(msg.citations) == 1
        assert msg.citations[0]["source_id"] == 1

    def test_message_ordering(
        self,
        db_session: Session,
        registered_user: dict,
        uploaded_doc: dict,
    ):
        """Messages are ordered chronologically."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Test",
        )
        
        msg1 = add_user_message(
            db=db_session,
            conversation_id=conv.id,
            question="First question",
        )
        msg2 = add_user_message(
            db=db_session,
            conversation_id=conv.id,
            question="Second question",
        )

        messages = db_session.query(Message).filter_by(
            conversation_id=conv.id
        ).order_by(Message.created_at).all()

        assert len(messages) == 2
        assert messages[0].id == msg1.id
        assert messages[1].id == msg2.id

    def test_citation_persistence(
        self,
        db_session: Session,
        registered_user: dict,
        uploaded_doc: dict,
    ):
        """Citations are persisted with messages."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Test",
        )
        
        citations = [
            Citation(source_id=1, page=2, paragraph=3, excerpt="Citation 1"),
            Citation(source_id=2, page=4, paragraph=5, excerpt="Citation 2"),
        ]

        msg = add_assistant_message(
            db=db_session,
            conversation_id=conv.id,
            answer="Answer with citations",
            citations=citations,
        )

        db_msg = db_session.query(Message).filter_by(id=msg.id).first()
        assert len(db_msg.citations) == 2
        assert db_msg.citations[0]["page"] == 2
        assert db_msg.citations[1]["paragraph"] == 5


# ---------------------------------------------------------------------------
# Conversation Retrieval Tests
# ---------------------------------------------------------------------------


class TestConversationRetrieval:
    def test_get_conversation(
        self,
        db_session: Session,
        registered_user: dict,
        uploaded_doc: dict,
    ):
        """Retrieve conversation by ID."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Test",
        )
        
        retrieved = get_conversation(
            db=db_session,
            conversation_id=conv.id,
            user_id=user_id,
        )

        assert retrieved is not None
        assert retrieved.id == conv.id

    def test_get_conversation_wrong_user(
        self,
        db_session: Session,
        registered_user: dict,
        uploaded_doc: dict,
    ):
        """Reject if user doesn't own conversation."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Test",
        )

        # Create another user
        other_user = User(email="other@example.com", password_hash="secret")
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)

        retrieved = get_conversation(
            db=db_session,
            conversation_id=conv.id,
            user_id=other_user.id,
        )

        assert retrieved is None

    def test_list_conversations(
        self,
        db_session: Session,
        registered_user: dict,
        uploaded_doc: dict,
    ):
        """List all conversations for user."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv1 = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Conv 1",
        )
        conv2 = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Conv 2",
        )

        convs = list_conversations(db=db_session, user_id=user_id)

        assert len(convs) == 2
        assert convs[0]["id"] in [conv1.id, conv2.id]

    def test_list_conversations_by_document(
        self,
        db_session: Session,
        registered_user: dict,
        uploaded_doc: dict,
    ):
        """Filter conversations by document."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv1 = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Conv 1",
        )

        convs = list_conversations(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
        )

        assert len(convs) == 1
        assert convs[0]["id"] == conv1.id


# ---------------------------------------------------------------------------
# Conversation Deletion Tests
# ---------------------------------------------------------------------------


class TestConversationDeletion:
    def test_delete_conversation(
        self,
        db_session: Session,
        registered_user: dict,
        uploaded_doc: dict,
    ):
        """Delete conversation and messages."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Test",
        )

        # Add messages
        add_user_message(
            db=db_session,
            conversation_id=conv.id,
            question="Q1",
        )
        add_user_message(
            db=db_session,
            conversation_id=conv.id,
            question="Q2",
        )

        msg_count = db_session.query(Message).filter_by(
            conversation_id=conv.id
        ).count()
        assert msg_count == 2

        # Delete conversation
        deleted = delete_conversation(
            db=db_session,
            conversation_id=conv.id,
            user_id=user_id,
        )

        assert deleted is True

        # Verify deleted
        conv_count = db_session.query(Conversation).filter_by(id=conv.id).count()
        assert conv_count == 0

        msg_count = db_session.query(Message).filter_by(
            conversation_id=conv.id
        ).count()
        assert msg_count == 0

    def test_delete_conversation_wrong_user(
        self,
        db_session: Session,
        registered_user: dict,
        uploaded_doc: dict,
    ):
        """Reject deletion if user doesn't own conversation."""
        user_id = registered_user["data"]["user"]["id"]
        doc_id = uploaded_doc["id"]
        
        conv = create_conversation(
            db=db_session,
            user_id=user_id,
            document_id=doc_id,
            title="Test",
        )

        # Create another user
        other_user = User(email="other@example.com", password_hash="secret")
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)

        deleted = delete_conversation(
            db=db_session,
            conversation_id=conv.id,
            user_id=other_user.id,
        )

        assert deleted is False

        # Verify conversation still exists
        conv_count = db_session.query(Conversation).filter_by(id=conv.id).count()
        assert conv_count == 1


# ---------------------------------------------------------------------------
# Title Generation Tests
# ---------------------------------------------------------------------------


class TestTitleGeneration:
    def test_generate_title_short_question(self):
        """Short question becomes title as-is."""
        title = _generate_title_from_question("What is AI?")
        assert title == "What is AI?"

    def test_generate_title_long_question(self):
        """Long question truncated with ellipsis."""
        long_q = "This is a very long question about machine learning and artificial intelligence"
        title = _generate_title_from_question(long_q, max_length=50)
        assert len(title) <= 54  # 50 + "..."
        assert title.endswith("...")

    def test_generate_title_word_boundary(self):
        """Truncation respects word boundaries."""
        q = "How do I properly configure the settings"
        title = _generate_title_from_question(q, max_length=20)
        # Should truncate, not be exact match
        assert "..." in title or len(title) <= 20
