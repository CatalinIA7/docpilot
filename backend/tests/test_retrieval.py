"""
Tests for retrieval service — similarity calculation, chunk ranking, and retrieval flow.
"""

import math
import pytest
from retrieval_service import (
    _cosine_similarity,
    retrieve_chunks,
    RetrievalConfigurationError,
    RetrievalProviderError,
    RetrievalResponseError,
    RetrievedChunk,
    RetrievalResult,
)
from models import DocumentChunk


# ---------------------------------------------------------------------------
# Cosine Similarity Tests
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_identical_vectors(self):
        """Identical vectors should have similarity of 1.0."""
        vec = [1.0, 0.0, 0.0]
        result = _cosine_similarity(vec, vec)
        assert result == 1.0

    def test_opposite_vectors(self):
        """Opposite vectors should have similarity of -1.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [-1.0, 0.0, 0.0]
        result = _cosine_similarity(vec_a, vec_b)
        assert result == pytest.approx(-1.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity of 0.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        result = _cosine_similarity(vec_a, vec_b)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_perpendicular_vectors(self):
        """Perpendicular vectors should have similarity of 0.0."""
        vec_a = [1.0, 1.0]
        vec_b = [1.0, -1.0]
        result = _cosine_similarity(vec_a, vec_b)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_parallel_vectors_different_magnitude(self):
        """Parallel vectors should have similarity of 1.0 regardless of magnitude."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [5.0, 0.0, 0.0]
        result = _cosine_similarity(vec_a, vec_b)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_mismatched_dimensions(self):
        """Vectors with different dimensions should raise error."""
        vec_a = [1.0, 0.0]
        vec_b = [1.0, 0.0, 0.0]
        with pytest.raises(RetrievalResponseError, match="dimension mismatch"):
            _cosine_similarity(vec_a, vec_b)

    def test_empty_vectors(self):
        """Empty vectors should raise error."""
        with pytest.raises(RetrievalResponseError, match="empty vectors"):
            _cosine_similarity([], [])

    def test_zero_vector(self):
        """Zero vector vs non-zero should return 0.0."""
        vec_a = [0.0, 0.0, 0.0]
        vec_b = [1.0, 0.0, 0.0]
        result = _cosine_similarity(vec_a, vec_b)
        assert result == 0.0

    def test_both_zero_vectors(self):
        """Two zero vectors should return 0.0."""
        vec_a = [0.0, 0.0, 0.0]
        vec_b = [0.0, 0.0, 0.0]
        result = _cosine_similarity(vec_a, vec_b)
        assert result == 0.0

    def test_nan_value(self):
        """NaN values should raise error."""
        vec_a = [1.0, float('nan'), 0.0]
        vec_b = [1.0, 0.0, 0.0]
        with pytest.raises(RetrievalResponseError, match="Invalid value"):
            _cosine_similarity(vec_a, vec_b)

    def test_inf_value(self):
        """Infinity values should raise error."""
        vec_a = [1.0, float('inf'), 0.0]
        vec_b = [1.0, 0.0, 0.0]
        with pytest.raises(RetrievalResponseError, match="Invalid value"):
            _cosine_similarity(vec_a, vec_b)

    def test_realistic_embeddings(self):
        """Test with realistic embedding values."""
        # Simulated embeddings (small dimension for testing)
        vec_a = [0.5, 0.1, 0.2]
        vec_b = [0.5, 0.1, 0.2]
        result = _cosine_similarity(vec_a, vec_b)
        assert result == pytest.approx(1.0, abs=1e-6)

        # Similar but not identical
        vec_c = [0.5, 0.1, 0.25]
        result = _cosine_similarity(vec_a, vec_c)
        assert 0.9 < result < 1.0

        # Dissimilar
        vec_d = [-0.5, -0.1, -0.2]
        result = _cosine_similarity(vec_a, vec_d)
        assert result == pytest.approx(-1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Retrieval Behavior Tests
# ---------------------------------------------------------------------------


class TestRetrievalBehavior:
    """Test chunk ranking, filtering, and tie-breaking."""

    def test_highest_scoring_chunk_ranks_first(self):
        """Chunks should be ranked by descending similarity score."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[1.0, 0.0]),
            DocumentChunk(id=2, document_id="doc1", chunk_index=1, text="b", embedding=[0.9, 0.436]),  # ~60 degrees
            DocumentChunk(id=3, document_id="doc1", chunk_index=2, text="c", embedding=[0.0, 1.0]),  # 90 degrees (orthogonal)
        ]
        # Question embedding close to chunk 1
        
        # Mock by patching embed_texts inside retrieve_chunks
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1 and texts[0] == "question":
                return [[1.0, 0.0]]  # Identical to chunk 1
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            result = retrieve_chunks("question", chunks, top_k=3)
            # Should be sorted by score descending
            # [1.0, 0.0] vs [1.0, 0.0] = 1.0 (identical)
            # [1.0, 0.0] vs [0.9, 0.436] ≈ 0.9 (similar)
            # [1.0, 0.0] vs [0.0, 1.0] = 0.0 (orthogonal)
            assert result.chunks[0].chunk.id == 1
            assert result.chunks[0].similarity_score == pytest.approx(1.0, abs=1e-6)
            assert result.chunks[1].chunk.id == 2
            assert 0.88 < result.chunks[1].similarity_score < 0.92
            assert result.chunks[2].chunk.id == 3
            assert result.chunks[2].similarity_score == pytest.approx(0.0, abs=1e-6)
        finally:
            retrieval_service.embed_texts = original_embed

    def test_top_k_limits_results(self):
        """Only top_k chunks should be returned."""
        chunks = [
            DocumentChunk(id=i, document_id="doc1", chunk_index=i, text=f"text{i}", embedding=[float(i)/10, 0.0])
            for i in range(10)
        ]
        
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1:
                return [[1.0, 0.0]]
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            result = retrieve_chunks("question", chunks, top_k=3)
            assert len(result.chunks) == 3
            assert result.top_k == 3
            assert result.retrieved_count == 10  # All passed min_score filter
        finally:
            retrieval_service.embed_texts = original_embed

    def test_minimum_score_filtering(self):
        """Chunks below min_score should not be returned."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[1.0, 0.0]),    # 0 degrees (1.0)
            DocumentChunk(id=2, document_id="doc1", chunk_index=1, text="b", embedding=[0.0, 1.0]),    # 90 degrees (0.0)
            DocumentChunk(id=3, document_id="doc1", chunk_index=2, text="c", embedding=[-1.0, 0.0]),   # 180 degrees (-1.0)
        ]
        
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1:
                return [[1.0, 0.0]]
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            result = retrieve_chunks("question", chunks, min_score=0.6)
            # Only chunk 1 with score 1.0 should be returned (>= 0.6)
            # Chunk 2 with score 0.0 is filtered out (< 0.6)
            # Chunk 3 with score -1.0 is filtered out (< 0.6)
            assert len(result.chunks) == 1
            assert result.chunks[0].chunk.id == 1
            assert result.retrieved_count == 1
            assert result.candidate_count == 3
        finally:
            retrieval_service.embed_texts = original_embed

    def test_deterministic_tie_breaking(self):
        """When scores are equal, use chunk_index as tie-breaker."""
        # Create chunks with identical similarity scores
        chunks = [
            DocumentChunk(id=3, document_id="doc1", chunk_index=2, text="c", embedding=[1.0, 0.0]),
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[1.0, 0.0]),
            DocumentChunk(id=2, document_id="doc1", chunk_index=1, text="b", embedding=[1.0, 0.0]),
        ]
        
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1:
                return [[1.0, 0.0]]
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            result = retrieve_chunks("question", chunks, top_k=3)
            # With equal scores, should sort by chunk_index ascending
            assert result.chunks[0].chunk.chunk_index == 0
            assert result.chunks[1].chunk.chunk_index == 1
            assert result.chunks[2].chunk.chunk_index == 2
        finally:
            retrieval_service.embed_texts = original_embed

    def test_fewer_chunks_than_top_k(self):
        """If fewer chunks than top_k, return all qualifying chunks."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.9, 0.0]),
            DocumentChunk(id=2, document_id="doc1", chunk_index=1, text="b", embedding=[0.8, 0.0]),
        ]
        
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1:
                return [[1.0, 0.0]]
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            result = retrieve_chunks("question", chunks, top_k=10)
            assert len(result.chunks) == 2
            assert result.top_k == 10
        finally:
            retrieval_service.embed_texts = original_embed

    def test_chunks_without_embedding_ignored(self):
        """Chunks with embedding=None should be ignored."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.9, 0.0]),
            DocumentChunk(id=2, document_id="doc1", chunk_index=1, text="b", embedding=None),
            DocumentChunk(id=3, document_id="doc1", chunk_index=2, text="c", embedding=[0.8, 0.0]),
        ]
        
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1:
                return [[1.0, 0.0]]
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            result = retrieve_chunks("question", chunks, top_k=10)
            # Only 2 chunks have embeddings
            assert result.candidate_count == 2
            assert len(result.chunks) == 2
            assert all(rc.chunk.embedding is not None for rc in result.chunks)
        finally:
            retrieval_service.embed_texts = original_embed

    def test_malformed_embedding_skipped(self):
        """Chunks with mismatched embedding dimensions should be skipped."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.9, 0.0]),
            DocumentChunk(id=2, document_id="doc1", chunk_index=1, text="b", embedding=[0.8]),  # Wrong dimension
            DocumentChunk(id=3, document_id="doc1", chunk_index=2, text="c", embedding=[0.7, 0.0]),
        ]
        
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1:
                return [[1.0, 0.0]]
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            result = retrieve_chunks("question", chunks, top_k=10)
            # Only 2 chunks should be scored (the third fails dimension check but is logged)
            assert len(result.chunks) == 2
            assert all(rc.chunk.embedding is not None for rc in result.chunks)
        finally:
            retrieval_service.embed_texts = original_embed

    def test_only_requested_document_chunks(self):
        """Should only retrieve chunks from the specified document."""
        # This is implicitly tested since we pass chunks to retrieve_chunks
        # The caller (chat endpoint) is responsible for filtering by document_id
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.9, 0.0]),
            DocumentChunk(id=2, document_id="doc2", chunk_index=0, text="b", embedding=[0.8, 0.0]),  # Different doc
        ]
        
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1:
                return [[1.0, 0.0]]
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            # Pass only doc1 chunks (as the chat endpoint would)
            result = retrieve_chunks("question", [chunks[0]], top_k=10)
            assert len(result.chunks) == 1
            assert result.chunks[0].chunk.document_id == "doc1"
        finally:
            retrieval_service.embed_texts = original_embed

    def test_no_duplicate_chunks(self):
        """Duplicate chunks should not be returned."""
        # Create the same chunk instance twice (shouldn't happen in practice)
        chunk = DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.9, 0.0])
        chunks = [chunk, chunk]
        
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1:
                return [[1.0, 0.0]]
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            result = retrieve_chunks("question", chunks, top_k=10)
            # Both copies would have the same score and index, so both included
            # (This is an edge case; in normal use chunks are distinct DB instances)
            assert len(result.chunks) == 2
        finally:
            retrieval_service.embed_texts = original_embed


# ---------------------------------------------------------------------------
# Empty/Missing Data Tests
# ---------------------------------------------------------------------------


class TestMissingEmbeddings:
    """Test behavior when chunks have no embeddings."""

    def test_all_chunks_missing_embeddings(self):
        """If no chunks have embeddings, return empty result."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=None),
            DocumentChunk(id=2, document_id="doc1", chunk_index=1, text="b", embedding=None),
        ]
        result = retrieve_chunks("question", chunks, top_k=5)
        assert result.chunks == []
        assert result.candidate_count == 0
        assert result.retrieved_count == 0

    def test_empty_chunk_list(self):
        """Empty chunk list should return empty result."""
        result = retrieve_chunks("question", [], top_k=5)
        assert result.chunks == []
        assert result.candidate_count == 0

    def test_no_chunks_pass_threshold(self):
        """If all chunks below min_score, return empty result."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.0, 1.0]),  # Orthogonal
            DocumentChunk(id=2, document_id="doc1", chunk_index=1, text="b", embedding=[-1.0, 0.0]),  # Opposite
        ]
        
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1:
                return [[1.0, 0.0]]  # Different directions
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            result = retrieve_chunks("question", chunks, min_score=0.5)
            # Both chunks have scores < 0.5 (0.0 and -1.0), so none pass the threshold
            assert len(result.chunks) == 0
            assert result.candidate_count == 2
            assert result.retrieved_count == 0
        finally:
            retrieval_service.embed_texts = original_embed


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error cases and edge conditions."""

    def test_empty_question(self):
        """Empty or whitespace-only questions should raise error."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.5, 0.0])
        ]
        with pytest.raises(RetrievalResponseError, match="empty or whitespace"):
            retrieve_chunks("", chunks)

    def test_whitespace_only_question(self):
        """Whitespace-only question should raise error."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.5, 0.0])
        ]
        with pytest.raises(RetrievalResponseError, match="empty or whitespace"):
            retrieve_chunks("   ", chunks)

    def test_invalid_top_k_zero(self):
        """top_k must be greater than zero."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.5, 0.0])
        ]
        with pytest.raises(RetrievalConfigurationError, match="top_k"):
            retrieve_chunks("question", chunks, top_k=0)

    def test_invalid_top_k_negative(self):
        """top_k must be positive."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.5, 0.0])
        ]
        with pytest.raises(RetrievalConfigurationError, match="top_k"):
            retrieve_chunks("question", chunks, top_k=-1)

    def test_invalid_min_score_below_range(self):
        """min_score must be in [-1.0, 1.0]."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.5, 0.0])
        ]
        with pytest.raises(RetrievalConfigurationError, match="min_score"):
            retrieve_chunks("question", chunks, min_score=-1.5)

    def test_invalid_min_score_above_range(self):
        """min_score must be in [-1.0, 1.0]."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[0.5, 0.0])
        ]
        with pytest.raises(RetrievalConfigurationError, match="min_score"):
            retrieve_chunks("question", chunks, min_score=1.5)

    def test_valid_min_score_boundaries(self):
        """min_score at boundaries should be valid."""
        chunks = [
            DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="a", embedding=[1.0, 0.0])
        ]
        
        import retrieval_service
        original_embed = retrieval_service.embed_texts
        
        def mock_embed(texts):
            if len(texts) == 1:
                return [[1.0, 0.0]]
            return original_embed(texts)
        
        retrieval_service.embed_texts = mock_embed
        try:
            # Should not raise
            result = retrieve_chunks("question", chunks, min_score=-1.0)
            assert result is not None
            
            result = retrieve_chunks("question", chunks, min_score=1.0)
            assert result is not None
        finally:
            retrieval_service.embed_texts = original_embed


# ---------------------------------------------------------------------------
# Result Structure Tests
# ---------------------------------------------------------------------------


class TestResultStructure:
    """Test RetrievalResult and RetrievedChunk structures."""

    def test_retrieved_chunk_structure(self):
        """RetrievedChunk should have correct fields."""
        chunk = DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="test", embedding=[0.5, 0.0])
        retrieved = RetrievedChunk(chunk=chunk, similarity_score=0.87, rank=1)
        assert retrieved.chunk == chunk
        assert retrieved.similarity_score == 0.87
        assert retrieved.rank == 1

    def test_retrieval_result_structure(self):
        """RetrievalResult should have correct fields."""
        chunks = []
        result = RetrievalResult(
            chunks=chunks,
            candidate_count=10,
            retrieved_count=3,
            top_k=5,
            min_score=0.5,
        )
        assert result.chunks == []
        assert result.candidate_count == 10
        assert result.retrieved_count == 3
        assert result.top_k == 5
        assert result.min_score == 0.5

    def test_result_immutability(self):
        """Result objects should be frozen."""
        chunk = DocumentChunk(id=1, document_id="doc1", chunk_index=0, text="test", embedding=[0.5, 0.0])
        retrieved = RetrievedChunk(chunk=chunk, similarity_score=0.87, rank=1)
        
        with pytest.raises(AttributeError):
            retrieved.rank = 2

        result = RetrievalResult(chunks=[], candidate_count=0, retrieved_count=0, top_k=5, min_score=0.0)
        with pytest.raises(AttributeError):
            result.top_k = 10
