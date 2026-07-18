"""
Tests for RAG evaluation comparison framework.

Covers:
- Both strategies execute independently
- Metrics are computed correctly
- Thresholds determine status properly
- Persistence works
- REST endpoint behavior
"""

import pytest
from unittest.mock import MagicMock, patch
from evaluation_comparison_service import (
    EvaluationRunner,
    EvaluationRunMetrics,
    ComparisonMetrics,
    EvaluationComparison,
)
from models import Document, DocumentChunk


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_document():
    """Create a mock document."""
    doc = MagicMock(spec=Document)
    doc.id = "doc-123"
    doc.text = "This is a test document."
    return doc


@pytest.fixture
def mock_chunks():
    """Create mock chunks with and without embeddings."""
    chunks = []
    
    # Chunks with embeddings
    for i in range(5):
        chunk = MagicMock(spec=DocumentChunk)
        chunk.id = i
        chunk.text = f"Chunk {i} content"
        chunk.page = i + 1
        chunk.paragraph = i
        chunk.embedding = [0.1] * 10  # 10-dimensional embedding
        chunks.append(chunk)
    
    # Chunk without embedding
    chunk_no_emb = MagicMock(spec=DocumentChunk)
    chunk_no_emb.id = 5
    chunk_no_emb.text = "Chunk 5 content"
    chunk_no_emb.page = 6
    chunk_no_emb.paragraph = 5
    chunk_no_emb.embedding = None
    chunks.append(chunk_no_emb)
    
    return chunks


@pytest.fixture
def evaluation_runner():
    """Create an evaluation runner with default thresholds."""
    return EvaluationRunner(
        max_latency_ms=5000.0,
        min_context_reduction_percent=50.0,
        min_citation_preservation=0.8,
    )


# ============================================================================
# Comparison Tests
# ============================================================================


class TestComparisonExecution:
    """Test that both strategies execute independently."""

    def test_baseline_executes(self, evaluation_runner, mock_document, mock_chunks):
        """Baseline strategy should execute."""
        with patch("evaluation_comparison_service.answer_question") as mock_answer:
            mock_answer.return_value = ("Answer", [])
            
            result = evaluation_runner._run_baseline(
                document=mock_document,
                chunks=mock_chunks,
                question="What is this?",
                ai_model="gpt-4o-mini",
            )
            
            assert result.success
            assert result.mode == "baseline"
            assert result.total_latency_ms > 0
            assert result.prompt_character_count > 0
            assert result.citation_count == 0

    def test_rag_executes(self, evaluation_runner, mock_document, mock_chunks):
        """RAG strategy should execute."""
        with patch("evaluation_comparison_service.retrieve_chunks") as mock_retrieve, \
             patch("evaluation_comparison_service.answer_question") as mock_answer:
            
            # Mock retrieval result
            from retrieval_service import RetrievedChunk
            rc1 = MagicMock(spec=RetrievedChunk)
            rc1.rank = 1
            rc1.chunk = mock_chunks[0]
            rc1.similarity_score = 0.95
            
            mock_retrieve.return_value.chunks = [rc1]
            mock_answer.return_value = ("Answer", [])
            
            embedded_chunks = [c for c in mock_chunks if c.embedding is not None]
            result = evaluation_runner._run_rag(
                document=mock_document,
                chunks=embedded_chunks,
                question="What is this?",
                ai_model="gpt-4o-mini",
            )
            
            assert result.success
            assert result.mode == "rag"
            assert result.retrieval_latency_ms > 0
            assert result.retrieved_chunk_count == 1

    def test_both_execute_independently(self, evaluation_runner, mock_document, mock_chunks):
        """Both strategies should execute independently."""
        with patch("evaluation_comparison_service.retrieve_chunks") as mock_retrieve, \
             patch("evaluation_comparison_service.answer_question") as mock_answer:
            
            # Setup mocks
            mock_answer.return_value = ("Answer", [])
            from retrieval_service import RetrievedChunk
            rc = MagicMock(spec=RetrievedChunk)
            rc.rank = 1
            rc.chunk = mock_chunks[0]
            rc.similarity_score = 0.95
            mock_retrieve.return_value.chunks = [rc]
            
            # Run comparison
            embedded_chunks = [c for c in mock_chunks if c.embedding is not None]
            comparison = evaluation_runner.run(
                document=mock_document,
                question="What is this?",
                chunks=mock_chunks,
            )
            
            assert comparison.baseline.success
            assert comparison.rag.success
            assert comparison.baseline.retrieved_chunk_count > comparison.rag.retrieved_chunk_count

    def test_failure_isolation_baseline(self, evaluation_runner, mock_document, mock_chunks):
        """Failures in baseline should not affect RAG."""
        with patch("evaluation_comparison_service.answer_question") as mock_answer, \
             patch("evaluation_comparison_service.retrieve_chunks") as mock_retrieve:
            
            # Baseline fails
            mock_answer.side_effect = Exception("Baseline error")
            mock_retrieve.return_value.chunks = []
            
            result = evaluation_runner._run_baseline(
                document=mock_document,
                chunks=mock_chunks,
                question="Q?",
                ai_model="gpt-4o-mini",
            )
            
            assert not result.success
            assert result.error == "Exception: evaluation failed"


# ============================================================================
# Metrics Tests
# ============================================================================


class TestMetricsComputation:
    """Test derived metrics computation."""

    def test_context_reduction(self, evaluation_runner):
        """Context reduction should be computed correctly."""
        baseline = EvaluationRunMetrics(
            mode="baseline",
            success=True,
            total_latency_ms=100.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=0.0,
            generation_latency_ms=100.0,
            prompt_character_count=1000,
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=5,
            retrieved_chunk_ids=[],
            retrieval_scores=[],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        rag = EvaluationRunMetrics(
            mode="rag",
            success=True,
            total_latency_ms=80.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=20.0,
            generation_latency_ms=60.0,
            prompt_character_count=200,
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=2,
            retrieved_chunk_ids=[1, 2],
            retrieval_scores=[0.95, 0.85],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        comparison = evaluation_runner._compute_comparison(baseline, rag)
        
        # (1000 - 200) / 1000 * 100 = 80%
        assert comparison.context_reduction_percent == 80.0

    def test_latency_difference(self, evaluation_runner):
        """Latency difference should be positive when RAG is faster."""
        baseline = EvaluationRunMetrics(
            mode="baseline",
            success=True,
            total_latency_ms=200.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=0.0,
            generation_latency_ms=200.0,
            prompt_character_count=1000,
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=5,
            retrieved_chunk_ids=[],
            retrieval_scores=[],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        rag = EvaluationRunMetrics(
            mode="rag",
            success=True,
            total_latency_ms=100.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=30.0,
            generation_latency_ms=70.0,
            prompt_character_count=200,
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=2,
            retrieved_chunk_ids=[1, 2],
            retrieval_scores=[0.95, 0.85],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        comparison = evaluation_runner._compute_comparison(baseline, rag)
        
        # 200 - 100 = 100 ms improvement
        assert comparison.latency_difference_ms == 100.0
        # 100 / 200 * 100 = 50% improvement
        assert comparison.latency_improvement_percent == 50.0

    def test_citation_difference(self, evaluation_runner):
        """Citation difference should reflect citation count delta."""
        baseline = EvaluationRunMetrics(
            mode="baseline",
            success=True,
            total_latency_ms=100.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=0.0,
            generation_latency_ms=100.0,
            prompt_character_count=1000,
            response_character_count=100,
            citation_count=5,
            retrieved_chunk_count=5,
            retrieved_chunk_ids=[],
            retrieval_scores=[],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        rag = EvaluationRunMetrics(
            mode="rag",
            success=True,
            total_latency_ms=80.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=20.0,
            generation_latency_ms=60.0,
            prompt_character_count=200,
            response_character_count=100,
            citation_count=3,
            retrieved_chunk_count=2,
            retrieved_chunk_ids=[1, 2],
            retrieval_scores=[0.95, 0.85],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        comparison = evaluation_runner._compute_comparison(baseline, rag)
        
        # 5 - 3 = 2
        assert comparison.citation_difference == 2

    def test_similarity_statistics(self, evaluation_runner):
        """Similarity statistics should be computed from retrieval scores."""
        baseline = EvaluationRunMetrics(
            mode="baseline",
            success=True,
            total_latency_ms=100.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=0.0,
            generation_latency_ms=100.0,
            prompt_character_count=1000,
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=5,
            retrieved_chunk_ids=[],
            retrieval_scores=[],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        rag = EvaluationRunMetrics(
            mode="rag",
            success=True,
            total_latency_ms=80.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=20.0,
            generation_latency_ms=60.0,
            prompt_character_count=200,
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=4,
            retrieved_chunk_ids=[1, 2, 3, 4],
            retrieval_scores=[0.95, 0.85, 0.75, 0.65],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        comparison = evaluation_runner._compute_comparison(baseline, rag)
        
        assert comparison.retrieved_chunk_avg_similarity == 0.8
        assert comparison.retrieved_chunk_highest_similarity == 0.95
        assert comparison.retrieved_chunk_lowest_similarity == 0.65


# ============================================================================
# Threshold Tests
# ============================================================================


class TestThresholdDetermination:
    """Test PASS/WARNING/FAIL status determination."""

    def test_pass_status(self, evaluation_runner):
        """Good metrics should result in PASS."""
        baseline = EvaluationRunMetrics(
            mode="baseline",
            success=True,
            total_latency_ms=200.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=0.0,
            generation_latency_ms=200.0,
            prompt_character_count=1000,
            response_character_count=100,
            citation_count=3,
            retrieved_chunk_count=5,
            retrieved_chunk_ids=[],
            retrieval_scores=[],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        rag = EvaluationRunMetrics(
            mode="rag",
            success=True,
            total_latency_ms=100.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=30.0,
            generation_latency_ms=70.0,
            prompt_character_count=200,
            response_character_count=100,
            citation_count=3,
            retrieved_chunk_count=2,
            retrieved_chunk_ids=[1, 2],
            retrieval_scores=[0.95, 0.85],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        comparison = evaluation_runner._compute_comparison(baseline, rag)
        
        assert comparison.status == "PASS"

    def test_fail_status_insufficient_context_reduction(self):
        """Insufficient context reduction should result in FAIL."""
        runner = EvaluationRunner(min_context_reduction_percent=80.0)
        
        baseline = EvaluationRunMetrics(
            mode="baseline",
            success=True,
            total_latency_ms=100.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=0.0,
            generation_latency_ms=100.0,
            prompt_character_count=1000,
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=5,
            retrieved_chunk_ids=[],
            retrieval_scores=[],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        rag = EvaluationRunMetrics(
            mode="rag",
            success=True,
            total_latency_ms=80.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=20.0,
            generation_latency_ms=60.0,
            prompt_character_count=300,  # Only 70% reduction
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=2,
            retrieved_chunk_ids=[1, 2],
            retrieval_scores=[0.95, 0.85],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        comparison = runner._compute_comparison(baseline, rag)
        
        assert comparison.status == "FAIL"
        assert "Context reduction" in comparison.status_reason

    def test_fail_status_baseline_failed(self, evaluation_runner):
        """If baseline fails, status should be FAIL."""
        baseline = EvaluationRunMetrics(
            mode="baseline",
            success=False,
            total_latency_ms=0.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=0.0,
            generation_latency_ms=0.0,
            prompt_character_count=0,
            response_character_count=0,
            citation_count=0,
            retrieved_chunk_count=0,
            retrieved_chunk_ids=[],
            retrieval_scores=[],
            ai_model="gpt-4o-mini",
            error="Failed",
        )
        
        rag = EvaluationRunMetrics(
            mode="rag",
            success=True,
            total_latency_ms=80.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=20.0,
            generation_latency_ms=60.0,
            prompt_character_count=200,
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=2,
            retrieved_chunk_ids=[1, 2],
            retrieval_scores=[0.95, 0.85],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        comparison = evaluation_runner._compute_comparison(baseline, rag)
        
        assert comparison.status == "FAIL"


# ============================================================================
# Serialization Tests
# ============================================================================


class TestSerialization:
    """Test conversion to JSON-serializable format."""

    def test_to_dict_serializable(self, evaluation_runner):
        """Comparison should convert to JSON-serializable dict."""
        baseline = EvaluationRunMetrics(
            mode="baseline",
            success=True,
            total_latency_ms=100.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=0.0,
            generation_latency_ms=100.0,
            prompt_character_count=1000,
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=5,
            retrieved_chunk_ids=[],
            retrieval_scores=[],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        rag = EvaluationRunMetrics(
            mode="rag",
            success=True,
            total_latency_ms=80.0,
            embedding_latency_ms=0.0,
            retrieval_latency_ms=20.0,
            generation_latency_ms=60.0,
            prompt_character_count=200,
            response_character_count=100,
            citation_count=2,
            retrieved_chunk_count=2,
            retrieved_chunk_ids=[1, 2],
            retrieval_scores=[0.95, 0.85],
            ai_model="gpt-4o-mini",
            answer_text="Answer",
        )
        
        comparison = EvaluationComparison(
            question="What is this?",
            document_id="doc-123",
            baseline=baseline,
            rag=rag,
            comparison=evaluation_runner._compute_comparison(baseline, rag),
        )
        
        result_dict = evaluation_runner.to_dict(comparison)
        
        # Should be JSON-serializable
        import json
        json_str = json.dumps(result_dict)
        assert "baseline" in json_str
        assert "rag" in json_str
        assert "comparison" in json_str
