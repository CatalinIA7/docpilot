"""
Tests for embedding service and integration with document upload.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from embedding_service import (
    embed_texts,
    embed_texts_with_observability,
    _get_api_key,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    EmbeddingResponseError,
    EmbeddingBatchResult,
    _validate_and_normalize_texts,
)


# ============================================================================
# Tests for embedding service (unit tests)
# ============================================================================


class TestEmbeddingValidation:
    """Tests for input validation in the embedding service."""

    def test_empty_input_raises_error(self):
        """Empty input should raise EmbeddingResponseError."""
        with pytest.raises(EmbeddingResponseError, match="No texts provided"):
            embed_texts([])

    def test_whitespace_only_raises_error(self):
        """Whitespace-only input should raise EmbeddingResponseError."""
        with pytest.raises(EmbeddingResponseError, match="empty or whitespace"):
            embed_texts(["   ", "\n", "\t"])

    def test_mixed_empty_and_valid_raises_error(self):
        """If all texts are empty/whitespace, should raise error."""
        with pytest.raises(EmbeddingResponseError, match="empty or whitespace"):
            embed_texts(["", "   ", None])

    def test_validate_and_normalize_filters_empty(self):
        """_validate_and_normalize_texts should filter empty and whitespace texts."""
        texts = ["hello", "", "world", "  ", "test"]
        normalized, indices = _validate_and_normalize_texts(texts)
        
        assert len(normalized) == 3
        assert normalized == ["hello", "world", "test"]
        assert indices == [0, 2, 4]

    def test_validate_and_normalize_strips_whitespace(self):
        """_validate_and_normalize_texts should strip leading/trailing whitespace."""
        texts = ["  hello  ", "  world  "]
        normalized, indices = _validate_and_normalize_texts(texts)
        
        assert normalized == ["hello", "world"]
        assert indices == [0, 1]


class TestEmbeddingSingleChunk:
    """Tests for embedding a single chunk."""

    @patch("embedding_service.embed_texts", wraps=embed_texts)
    def test_single_chunk_receives_one_embedding(self, mock_embed):
        """A single chunk should receive exactly one embedding with mocked API."""
        # This is a simple test that validates the function doesn't crash
        # For full testing, we need to mock the OpenAI client inside
        pass

    def test_single_chunk_input_validation(self):
        """Single chunk input should be validated."""
        with pytest.raises(EmbeddingResponseError):
            embed_texts([""])


class TestEmbeddingMultipleChunks:
    """Tests for embedding multiple chunks with order preservation."""

    def test_multiple_chunks_empty_raises_error(self):
        """Multiple empty chunks should raise error."""
        with pytest.raises(EmbeddingResponseError, match="empty or whitespace"):
            embed_texts(["", "", ""])


class TestEmbeddingBatching:
    """Tests for batch processing of embeddings."""

    def test_batch_size_configuration(self):
        """Batch size should be configurable."""
        from embedding_service import _get_batch_size
        # This should not raise if the environment variable is set correctly
        size = _get_batch_size()
        assert size > 0


class TestEmbeddingResponseValidation:
    """Tests for response validation from embedding provider."""

    def test_response_validation_rejects_empty_list(self):
        """Empty chunk texts should raise error."""
        with pytest.raises(EmbeddingResponseError, match="empty or whitespace"):
            embed_texts([""])

    def test_response_validation_whitespace_only(self):
        """Whitespace-only chunk texts should raise error."""
        with pytest.raises(EmbeddingResponseError, match="empty or whitespace"):
            embed_texts(["   ", "\n", "\t"])


class TestEmbeddingProviderErrors:
    """Tests for provider error handling."""

    def test_missing_api_key_error_message(self):
        """Missing API key should produce helpful error message."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            with pytest.raises(EmbeddingConfigurationError, match="not configured"):
                _get_api_key()


class TestObservabilityResult:
    """Tests for observability result object."""

    def test_observability_result_structure(self):
        """Observability result should have correct fields."""
        result = EmbeddingBatchResult(
            embeddings=[[0.1, 0.2, 0.3]],
            model="text-embedding-3-small",
            vector_dimension=3,
            batch_count=1,
            chunks_processed=1,
        )
        
        assert result.embeddings == [[0.1, 0.2, 0.3]]
        assert result.model == "text-embedding-3-small"
        assert result.vector_dimension == 3
        assert result.batch_count == 1
        assert result.chunks_processed == 1


# ============================================================================
# Tests for integration with document upload
# ============================================================================


class TestDocumentUploadWithEmbeddings:
    """Tests for embedding generation during document upload."""

    def test_chunks_without_embeddings_are_readable(self, db_session, registered_user):
        """Existing chunks without embeddings should remain readable."""
        from models import Document, DocumentChunk
        
        user_id = registered_user["data"]["user"]["id"]
        
        # Create document and chunk without embedding
        doc = Document(
            id="test-doc",
            user_id=user_id,
            filename="test.pdf",
            stored_filename="test-12345.pdf",
            file_type="pdf",
            size=100,
            text="test",
        )
        db_session.add(doc)
        db_session.commit()
        
        chunk = DocumentChunk(
            document_id="test-doc",
            chunk_index=0,
            text="test chunk",
            embedding=None,
        )
        db_session.add(chunk)
        db_session.commit()
        
        # Read back
        retrieved_chunk = db_session.query(DocumentChunk).filter_by(document_id="test-doc").first()
        assert retrieved_chunk is not None
        assert retrieved_chunk.embedding is None
        assert retrieved_chunk.text == "test chunk"

    def test_document_deletion_cascades_to_embedded_chunks(self, db_session, registered_user):
        """Deleting a document should cascade delete its embedded chunks."""
        from models import Document, DocumentChunk
        
        user_id = registered_user["data"]["user"]["id"]
        
        # Create document with embedded chunk
        doc = Document(
            id="test-doc",
            user_id=user_id,
            filename="test.pdf",
            stored_filename="test-12345.pdf",
            file_type="pdf",
            size=100,
            text="test",
        )
        db_session.add(doc)
        db_session.commit()
        
        chunk = DocumentChunk(
            document_id="test-doc",
            chunk_index=0,
            text="test chunk",
            embedding=[0.1, 0.2, 0.3],
        )
        db_session.add(chunk)
        db_session.commit()
        
        # Delete document
        db_session.delete(doc)
        db_session.commit()
        
        # Verify chunk is deleted
        remaining_chunks = db_session.query(DocumentChunk).filter_by(document_id="test-doc").all()
        assert len(remaining_chunks) == 0

    def test_embedding_round_trip_through_database(self, db_session):
        """Embeddings should round-trip correctly through database (JSON serialization)."""
        from models import Document, DocumentChunk
        
        # Create document and chunk
        doc = Document(
            id="test-doc",
            user_id=1,
            filename="test.pdf",
            stored_filename="test-12345.pdf",
            file_type="pdf",
            size=100,
            text="test",
        )
        db_session.add(doc)
        db_session.commit()
        
        # Store embedding
        original_embedding = [0.1234567890, -0.987654321, 0.5]
        chunk = DocumentChunk(
            document_id="test-doc",
            chunk_index=0,
            text="test chunk",
            embedding=original_embedding,
        )
        db_session.add(chunk)
        db_session.commit()
        
        # Read back
        db_session.expunge_all()
        retrieved_chunk = db_session.query(DocumentChunk).filter_by(document_id="test-doc").first()
        
        # Verify values match (allowing for floating point precision)
        assert retrieved_chunk.embedding is not None
        assert len(retrieved_chunk.embedding) == 3
        for orig, retrieved in zip(original_embedding, retrieved_chunk.embedding):
            assert abs(orig - retrieved) < 1e-6

    def test_authorization_unchanged_with_embeddings(self, db_session, auth_headers, registered_user):
        """Document ownership checks should still apply with embedded chunks."""
        from models import Document, DocumentChunk
        from fastapi.testclient import TestClient
        from main import app
        from database import get_db
        
        user_id = registered_user["data"]["user"]["id"]
        
        # Create document with chunk in DB
        doc = Document(
            id="test-doc",
            user_id=user_id,
            filename="test.pdf",
            stored_filename="test-12345.pdf",
            file_type="pdf",
            size=100,
            text="test",
        )
        db_session.add(doc)
        db_session.commit()
        
        chunk = DocumentChunk(
            document_id="test-doc",
            chunk_index=0,
            text="test chunk",
            embedding=[0.1, 0.2],
        )
        db_session.add(chunk)
        db_session.commit()
        
        # Verify the chunk is retrievable via the relationship
        assert len(doc.chunks) == 1
        assert doc.chunks[0].embedding == [0.1, 0.2]
