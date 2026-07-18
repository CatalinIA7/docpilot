"""
Evaluation comparison service for baseline vs RAG strategies.

Compares full-document chat against retrieval-augmented chat to measure:
- Context reduction (prompt size)
- Latency improvements
- Citation preservation
- Retrieval quality metrics
"""

import time
import logging
from dataclasses import dataclass, asdict
from typing import Optional

from document_parser import SourceSection, extract_document_text
from ai_service import answer_question, Citation
from retrieval_service import retrieve_chunks
from models import Document, DocumentChunk

logger = logging.getLogger(__name__)


# ============================================================================
# Models
# ============================================================================


@dataclass(frozen=True)
class EvaluationRunMetrics:
    """Metrics for a single evaluation mode run (baseline or RAG)."""

    mode: str  # "baseline" or "rag"
    success: bool
    total_latency_ms: float
    embedding_latency_ms: float
    retrieval_latency_ms: float
    generation_latency_ms: float
    prompt_character_count: int
    response_character_count: int
    citation_count: int
    retrieved_chunk_count: int
    retrieved_chunk_ids: list[int]  # IDs of retrieved chunks
    retrieval_scores: list[float]  # Similarity scores for retrieved chunks
    ai_model: str
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    answer_text: str = ""  # Safe to store in evaluation data
    error: Optional[str] = None


@dataclass(frozen=True)
class ComparisonMetrics:
    """Derived metrics comparing baseline vs RAG."""

    context_reduction_percent: float  # (baseline - rag) / baseline * 100
    latency_difference_ms: float  # baseline - rag (positive = rag is faster)
    latency_improvement_percent: float
    generation_latency_difference_ms: float
    citation_difference: int  # baseline - rag
    retrieved_chunk_avg_similarity: float  # Average similarity of retrieved chunks
    retrieved_chunk_highest_similarity: float
    retrieved_chunk_lowest_similarity: float
    status: str  # "PASS", "WARNING", "FAIL"
    status_reason: str  # Explanation of status


@dataclass(frozen=True)
class EvaluationComparison:
    """Complete comparison result between baseline and RAG."""

    question: str
    document_id: str
    baseline: EvaluationRunMetrics
    rag: EvaluationRunMetrics
    comparison: ComparisonMetrics


# ============================================================================
# Evaluation Runner
# ============================================================================


class EvaluationRunner:
    """Executes both baseline and RAG strategies independently and compares them."""

    def __init__(
        self,
        max_latency_ms: float = 5000.0,
        min_context_reduction_percent: float = 50.0,
        min_citation_preservation: float = 0.8,
    ):
        """
        Initialize evaluation runner with thresholds.

        Args:
            max_latency_ms: Maximum acceptable latency in milliseconds
            min_context_reduction_percent: Minimum context reduction for RAG
            min_citation_preservation: Minimum citation preservation ratio
        """
        self.max_latency_ms = max_latency_ms
        self.min_context_reduction_percent = min_context_reduction_percent
        self.min_citation_preservation = min_citation_preservation

    def run(
        self,
        document: Document,
        question: str,
        chunks: list[DocumentChunk],
        ai_model: str = "gpt-4o-mini",
    ) -> EvaluationComparison:
        """
        Run evaluation comparison between baseline and RAG strategies.

        Args:
            document: Document to evaluate
            question: Question to answer
            chunks: All chunks for the document
            ai_model: AI model to use

        Returns:
            EvaluationComparison with metrics from both strategies
        """
        # Filter chunks with embeddings for RAG
        embedded_chunks = [c for c in chunks if c.embedding is not None]

        # Run both strategies
        baseline_result = self._run_baseline(
            document=document,
            chunks=chunks,
            question=question,
            ai_model=ai_model,
        )

        rag_result = self._run_rag(
            document=document,
            chunks=embedded_chunks,
            question=question,
            ai_model=ai_model,
        )

        # Compute comparison metrics
        comparison_metrics = self._compute_comparison(baseline_result, rag_result)

        return EvaluationComparison(
            question=question,
            document_id=document.id,
            baseline=baseline_result,
            rag=rag_result,
            comparison=comparison_metrics,
        )

    def _run_baseline(
        self,
        document: Document,
        chunks: list[DocumentChunk],
        question: str,
        ai_model: str,
    ) -> EvaluationRunMetrics:
        """
        Run baseline strategy: full document context to LLM.

        Uses all chunks as source sections.
        """
        try:
            # Build source sections from all chunks
            source_sections = [
                SourceSection(
                    source_id=i + 1,
                    text=chunk.text,
                    page=chunk.page,
                    paragraph=chunk.paragraph,
                )
                for i, chunk in enumerate(chunks)
            ]

            # Assemble prompt
            prompt_text = self._assemble_prompt(source_sections, question)
            prompt_char_count = len(prompt_text)

            # Measure AI generation
            gen_start = time.perf_counter()
            answer, citations = answer_question(
                sections=source_sections,
                question=question,
            )
            generation_latency_ms = (time.perf_counter() - gen_start) * 1000

            total_latency_ms = generation_latency_ms
            response_char_count = len(answer)
            citation_count = len(citations)

            return EvaluationRunMetrics(
                mode="baseline",
                success=True,
                total_latency_ms=total_latency_ms,
                embedding_latency_ms=0.0,
                retrieval_latency_ms=0.0,
                generation_latency_ms=generation_latency_ms,
                prompt_character_count=prompt_char_count,
                response_character_count=response_char_count,
                citation_count=citation_count,
                retrieved_chunk_count=len(chunks),
                retrieved_chunk_ids=[chunk.id for chunk in chunks],
                retrieval_scores=[],  # Not applicable for baseline
                ai_model=ai_model,
                answer_text=answer,
            )

        except Exception as exc:
            logger.error("Baseline evaluation failed: %s", exc)
            return EvaluationRunMetrics(
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
                ai_model=ai_model,
                error=str(exc),
            )

    def _run_rag(
        self,
        document: Document,
        chunks: list[DocumentChunk],
        question: str,
        ai_model: str,
    ) -> EvaluationRunMetrics:
        """
        Run RAG strategy: retrieve relevant chunks, then LLM.
        """
        if not chunks:
            return EvaluationRunMetrics(
                mode="rag",
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
                ai_model=ai_model,
                error="No embedded chunks available for RAG",
            )

        try:
            total_start = time.perf_counter()

            # Measure retrieval
            retrieval_start = time.perf_counter()
            retrieval_result = retrieve_chunks(question=question, chunks=chunks)
            retrieval_latency_ms = (time.perf_counter() - retrieval_start) * 1000

            # Extract retrieved chunks
            retrieved_chunks = retrieval_result.chunks
            if not retrieved_chunks:
                return EvaluationRunMetrics(
                    mode="rag",
                    success=False,
                    total_latency_ms=(time.perf_counter() - total_start) * 1000,
                    embedding_latency_ms=0.0,
                    retrieval_latency_ms=retrieval_latency_ms,
                    generation_latency_ms=0.0,
                    prompt_character_count=0,
                    response_character_count=0,
                    citation_count=0,
                    retrieved_chunk_count=0,
                    retrieved_chunk_ids=[],
                    retrieval_scores=[],
                    ai_model=ai_model,
                    error="Retrieval returned no chunks",
                )

            # Build source sections from retrieved chunks
            source_sections = [
                SourceSection(
                    source_id=rc.rank,
                    text=rc.chunk.text,
                    page=rc.chunk.page,
                    paragraph=rc.chunk.paragraph,
                )
                for rc in retrieved_chunks
            ]

            # Assemble prompt
            prompt_text = self._assemble_prompt(source_sections, question)
            prompt_char_count = len(prompt_text)

            # Measure AI generation
            gen_start = time.perf_counter()
            answer, citations = answer_question(
                sections=source_sections,
                question=question,
            )
            generation_latency_ms = (time.perf_counter() - gen_start) * 1000

            total_latency_ms = (time.perf_counter() - total_start) * 1000
            response_char_count = len(answer)
            citation_count = len(citations)

            # Extract retrieval metrics
            chunk_ids = [rc.chunk.id for rc in retrieved_chunks]
            scores = [rc.similarity_score for rc in retrieved_chunks]

            return EvaluationRunMetrics(
                mode="rag",
                success=True,
                total_latency_ms=total_latency_ms,
                embedding_latency_ms=0.0,  # Not exposed in current implementation
                retrieval_latency_ms=retrieval_latency_ms,
                generation_latency_ms=generation_latency_ms,
                prompt_character_count=prompt_char_count,
                response_character_count=response_char_count,
                citation_count=citation_count,
                retrieved_chunk_count=len(retrieved_chunks),
                retrieved_chunk_ids=chunk_ids,
                retrieval_scores=scores,
                ai_model=ai_model,
                answer_text=answer,
            )

        except Exception as exc:
            logger.error("RAG evaluation failed: %s", exc)
            return EvaluationRunMetrics(
                mode="rag",
                success=False,
                total_latency_ms=(time.perf_counter() - total_start) * 1000,
                embedding_latency_ms=0.0,
                retrieval_latency_ms=0.0,
                generation_latency_ms=0.0,
                prompt_character_count=0,
                response_character_count=0,
                citation_count=0,
                retrieved_chunk_count=0,
                retrieved_chunk_ids=[],
                retrieval_scores=[],
                ai_model=ai_model,
                error=str(exc),
            )

    @staticmethod
    def _assemble_prompt(source_sections: list[SourceSection], question: str) -> str:
        """Assemble prompt text for character count measurement."""
        prompt = "Context:\n\n"
        for section in source_sections:
            prompt += f"[{section.source_id}] {section.text}\n\n"
        prompt += f"Question: {question}\n\nAnswer:\n"
        return prompt

    def _compute_comparison(
        self,
        baseline: EvaluationRunMetrics,
        rag: EvaluationRunMetrics,
    ) -> ComparisonMetrics:
        """Compute derived metrics comparing baseline and RAG."""

        # Context reduction
        if baseline.prompt_character_count > 0:
            context_reduction_percent = (
                (baseline.prompt_character_count - rag.prompt_character_count)
                / baseline.prompt_character_count
                * 100
            )
        else:
            context_reduction_percent = 0.0

        # Latency difference (positive = RAG is faster)
        latency_difference_ms = baseline.total_latency_ms - rag.total_latency_ms
        if baseline.total_latency_ms > 0:
            latency_improvement_percent = (latency_difference_ms / baseline.total_latency_ms) * 100
        else:
            latency_improvement_percent = 0.0

        generation_latency_diff = baseline.generation_latency_ms - rag.generation_latency_ms

        # Citation difference (positive = baseline has more citations)
        citation_difference = baseline.citation_count - rag.citation_count

        # Retrieval similarity statistics
        if rag.retrieval_scores:
            avg_similarity = sum(rag.retrieval_scores) / len(rag.retrieval_scores)
            highest_similarity = max(rag.retrieval_scores)
            lowest_similarity = min(rag.retrieval_scores)
        else:
            avg_similarity = 0.0
            highest_similarity = 0.0
            lowest_similarity = 0.0

        # Determine status
        status, reason = self._determine_status(
            baseline=baseline,
            rag=rag,
            context_reduction_percent=context_reduction_percent,
            latency_difference_ms=latency_difference_ms,
            citation_difference=citation_difference,
        )

        return ComparisonMetrics(
            context_reduction_percent=context_reduction_percent,
            latency_difference_ms=latency_difference_ms,
            latency_improvement_percent=latency_improvement_percent,
            generation_latency_difference_ms=generation_latency_diff,
            citation_difference=citation_difference,
            retrieved_chunk_avg_similarity=avg_similarity,
            retrieved_chunk_highest_similarity=highest_similarity,
            retrieved_chunk_lowest_similarity=lowest_similarity,
            status=status,
            status_reason=reason,
        )

    def _determine_status(
        self,
        baseline: EvaluationRunMetrics,
        rag: EvaluationRunMetrics,
        context_reduction_percent: float,
        latency_difference_ms: float,
        citation_difference: int,
    ) -> tuple[str, str]:
        """Determine PASS/WARNING/FAIL status based on thresholds."""

        reasons = []

        # Both must succeed
        if not baseline.success or not rag.success:
            reasons.append("One or both strategies failed")
            return "FAIL", "; ".join(reasons)

        # Context reduction check
        if context_reduction_percent < self.min_context_reduction_percent:
            reasons.append(
                f"Context reduction {context_reduction_percent:.1f}% "
                f"< minimum {self.min_context_reduction_percent}%"
            )

        # Latency check
        if rag.total_latency_ms > self.max_latency_ms:
            reasons.append(f"RAG latency {rag.total_latency_ms:.0f}ms > max {self.max_latency_ms}ms")

        # Citation preservation
        if baseline.citation_count > 0:
            citation_preservation = rag.citation_count / baseline.citation_count
            if citation_preservation < self.min_citation_preservation:
                reasons.append(
                    f"Citation preservation {citation_preservation:.1%} "
                    f"< minimum {self.min_citation_preservation:.1%}"
                )

        if reasons:
            return "FAIL", "; ".join(reasons)

        return "PASS", "All thresholds met"

    def to_dict(self, comparison: EvaluationComparison) -> dict:
        """Convert comparison to JSON-serializable dict."""
        return {
            "question": comparison.question,
            "document_id": comparison.document_id,
            "baseline": asdict(comparison.baseline),
            "rag": asdict(comparison.rag),
            "comparison": asdict(comparison.comparison),
        }
