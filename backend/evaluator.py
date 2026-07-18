"""
Evaluation framework for measuring AI response quality and citation accuracy.
Tracks metrics like latency, token usage, citation accuracy, and answer quality.
"""
import time
import logging
from dataclasses import dataclass
from sqlalchemy.orm import Session
from ai_service import answer_question
from config import UPLOAD_DIR
from document_parser import extract_document_text
from models import BenchmarkQuestion, EvaluationRun, EvaluationResult, Document
from schemas import Citation
from observability import log_event


logger = logging.getLogger("docpilot.evaluation")


@dataclass
class EvaluationMetrics:
    """Container for a single evaluation result."""
    question: str
    ai_response: str
    citations_returned: int
    latency_ms: float
    tokens_used: int
    citation_accuracy: float  # 0.0-1.0
    answer_quality: float  # 0.0-1.0 (user-provided or inferred)


@dataclass
class AggregatedMetrics:
    """Container for aggregated evaluation run metrics."""
    total_questions: int
    questions_with_citations: int
    avg_latency_ms: float
    total_tokens_used: int
    avg_tokens_per_question: float
    citation_accuracy_score: float
    answer_quality_score: float
    citation_coverage: float


class Evaluator:
    """Runs evaluations against benchmark questions and calculates metrics."""

    def __init__(self, db: Session):
        self.db = db

    def run_evaluation(
        self,
        benchmark_questions: list[BenchmarkQuestion],
        user_id: int,
        run_name: str,
        approach: str = "full-document",
    ) -> tuple[EvaluationRun, list[EvaluationResult]]:
        """
        Run evaluation against a set of benchmark questions.
        
        Returns:
            (EvaluationRun with aggregated metrics, list of individual results)
        """
        results = []
        all_metrics = []

        for bq in benchmark_questions:
            # Get the document
            doc = self.db.query(Document).filter(Document.id == bq.document_id).first()
            if not doc:
                continue

            # Parse document to get sections
            doc_path = UPLOAD_DIR / doc.stored_filename
            parsed = extract_document_text(doc_path)
            sections = parsed.get("_sections", [])

            # Measure AI response
            start_time = time.perf_counter()
            try:
                answer, citations = answer_question(
                    sections=sections,
                    question=bq.question
                )
                latency = (time.perf_counter() - start_time) * 1000  # Convert to ms
            except Exception as exc:
                log_event(
                    logger,
                    logging.ERROR,
                    "evaluation_question_failed",
                    "Benchmark question evaluation failed",
                    document_id=doc.id,
                    benchmark_question_id=bq.id,
                    error_type=type(exc).__name__,
                )
                continue

            # Extract token usage from response metadata (if available)
            tokens_used = 0  # This will be enhanced when we track OpenAI usage

            # Calculate citation accuracy
            citation_accuracy = self._calculate_citation_accuracy(
                citations,
                bq.expected_citation_count,
                sections
            )

            # Create evaluation result
            result = EvaluationResult(
                benchmark_question_id=bq.id,
                ai_response=answer,
                citations_returned=len(citations),
                latency_ms=latency,
                tokens_used=tokens_used,
                citation_accuracy=citation_accuracy,
                answer_quality=0.0,  # Will be set by user or inferred
                eval_metadata={
                    "approach": approach,
                    "section_count": len(sections),
                }
            )
            results.append(result)

            # Collect for aggregation
            metrics = EvaluationMetrics(
                question=bq.question,
                ai_response=answer,
                citations_returned=len(citations),
                latency_ms=latency,
                tokens_used=tokens_used,
                citation_accuracy=citation_accuracy,
                answer_quality=0.0,
            )
            all_metrics.append(metrics)

        # Calculate aggregated metrics
        agg = self._aggregate_metrics(all_metrics)

        # Create evaluation run
        run = EvaluationRun(
            user_id=user_id,
            run_name=run_name,
            approach=approach,
            total_questions=len(all_metrics),
            questions_with_citations=agg.questions_with_citations,
            avg_latency_ms=agg.avg_latency_ms,
            total_tokens_used=agg.total_tokens_used,
            avg_tokens_per_question=agg.avg_tokens_per_question,
            citation_accuracy_score=agg.citation_accuracy_score,
            answer_quality_score=agg.answer_quality_score,
            citation_coverage=agg.citation_coverage,
        )

        # Link results to run
        for result in results:
            result.evaluation_run = run

        return run, results

    @staticmethod
    def _calculate_citation_accuracy(
        citations: list[Citation],
        expected_count: int,
        sections: list
    ) -> float:
        """
        Calculate citation accuracy as a 0.0-1.0 score.
        
        Factors:
        - At least some citations provided if expected
        - Citations reference valid source IDs
        - Citation page/paragraph numbers are reasonable
        """
        if expected_count == 0:
            return 1.0 if len(citations) == 0 else 0.8

        if len(citations) == 0:
            return 0.0

        # Check that citation sources are valid
        max_source_id = len(sections)
        valid_citations = 0
        for c in citations:
            if 1 <= c.source_id <= max_source_id:
                valid_citations += 1

        # Score: combination of citation count match and validity
        count_match = min(len(citations) / expected_count, 1.0) * 0.5
        validity = (valid_citations / len(citations)) * 0.5
        return count_match + validity

    @staticmethod
    def _aggregate_metrics(metrics_list: list[EvaluationMetrics]) -> AggregatedMetrics:
        """Aggregate individual metrics into run-level statistics."""
        if not metrics_list:
            return AggregatedMetrics(
                total_questions=0,
                questions_with_citations=0,
                avg_latency_ms=0.0,
                total_tokens_used=0,
                avg_tokens_per_question=0.0,
                citation_accuracy_score=0.0,
                answer_quality_score=0.0,
                citation_coverage=0.0,
            )

        total_questions = len(metrics_list)
        questions_with_citations = sum(1 for m in metrics_list if m.citations_returned > 0)
        avg_latency_ms = sum(m.latency_ms for m in metrics_list) / total_questions
        total_tokens_used = sum(m.tokens_used for m in metrics_list)
        avg_tokens_per_question = total_tokens_used / total_questions if total_questions > 0 else 0.0
        citation_accuracy_score = sum(m.citation_accuracy for m in metrics_list) / total_questions
        answer_quality_score = sum(m.answer_quality for m in metrics_list) / total_questions
        citation_coverage = questions_with_citations / total_questions

        return AggregatedMetrics(
            total_questions=total_questions,
            questions_with_citations=questions_with_citations,
            avg_latency_ms=avg_latency_ms,
            total_tokens_used=total_tokens_used,
            avg_tokens_per_question=avg_tokens_per_question,
            citation_accuracy_score=citation_accuracy_score,
            answer_quality_score=answer_quality_score,
            citation_coverage=citation_coverage,
        )
