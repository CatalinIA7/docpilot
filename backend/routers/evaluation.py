"""
Evaluation endpoints for running benchmarks and viewing results.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from database import get_db
from auth import get_current_user
from models import User, BenchmarkQuestion, EvaluationRun, EvaluationResult, Document, DocumentChunk, RAGEvaluationComparison
from schemas import (
    BenchmarkQuestionCreate,
    BenchmarkQuestionResponse,
    EvaluationRunCreateRequest,
    EvaluationRunResponse,
    EvaluationRunDetailResponse,
    EvaluationComparisonResponse,
    RAGEvaluationComparisonSchema,
    RAGEvaluationComparisonRequest,
    RAGEvaluationComparisonResponse,
)
from evaluator import Evaluator
from evaluation_comparison_service import EvaluationRunner
from config import EVAL_MAX_LATENCY_MS, EVAL_MIN_CONTEXT_REDUCTION, EVAL_MIN_CITATION_PRESERVATION, EVAL_PERSIST_RESULTS
from observability import log_event

logger = logging.getLogger("docpilot.evaluation.routes")

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/benchmark-questions", response_model=BenchmarkQuestionResponse)
async def create_benchmark_question(
    document_id: str,
    question_data: BenchmarkQuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a benchmark question for a document."""
    # Verify ownership
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    bq = BenchmarkQuestion(
        document_id=document_id,
        question=question_data.question,
        expected_answer_summary=question_data.expected_answer_summary,
        expected_citation_count=question_data.expected_citation_count,
    )
    db.add(bq)
    db.commit()
    db.refresh(bq)
    return bq


@router.get("/benchmark-questions/{document_id}", response_model=list[BenchmarkQuestionResponse])
async def list_benchmark_questions(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List benchmark questions for a document."""
    # Verify ownership
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    questions = db.query(BenchmarkQuestion).filter(
        BenchmarkQuestion.document_id == document_id
    ).all()
    return questions


@router.delete("/benchmark-questions/{question_id}")
async def delete_benchmark_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a benchmark question."""
    bq = db.query(BenchmarkQuestion).filter(BenchmarkQuestion.id == question_id).first()
    if not bq:
        raise HTTPException(status_code=404, detail="Question not found")

    # Verify ownership through document
    doc = db.query(Document).filter(
        Document.id == bq.document_id,
        Document.user_id == current_user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=403, detail="Unauthorized")

    db.delete(bq)
    db.commit()
    return {"status": "deleted"}


@router.post("/runs", response_model=EvaluationRunDetailResponse)
async def run_evaluation(
    request: EvaluationRunCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run evaluation against benchmark questions for a document."""
    # Verify ownership
    doc = db.query(Document).filter(
        Document.id == request.document_id,
        Document.user_id == current_user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get benchmark questions
    questions = db.query(BenchmarkQuestion).filter(
        BenchmarkQuestion.document_id == request.document_id
    ).all()

    if not questions:
        raise HTTPException(
            status_code=400,
            detail="No benchmark questions found for this document"
        )

    # Run evaluation
    evaluator = Evaluator(db)
    try:
        run, results = evaluator.run_evaluation(
            benchmark_questions=questions,
            user_id=current_user.id,
            run_name=request.run_name,
            approach=request.approach,
        )
        db.add(run)
        for result in results:
            db.add(result)
        db.commit()
        db.refresh(run)
        return run
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.get("/runs", response_model=list[EvaluationRunResponse])
async def list_evaluation_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all evaluation runs for the user."""
    runs = db.query(EvaluationRun).filter(
        EvaluationRun.user_id == current_user.id
    ).order_by(EvaluationRun.created_at.desc()).all()
    return runs


@router.get("/runs/{run_id}", response_model=EvaluationRunDetailResponse)
async def get_evaluation_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed results for an evaluation run."""
    run = db.query(EvaluationRun).filter(
        EvaluationRun.id == run_id,
        EvaluationRun.user_id == current_user.id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/compare/{run1_id}/{run2_id}", response_model=EvaluationComparisonResponse)
async def compare_evaluation_runs(
    run1_id: int,
    run2_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compare two evaluation runs."""
    run1 = db.query(EvaluationRun).filter(
        EvaluationRun.id == run1_id,
        EvaluationRun.user_id == current_user.id
    ).first()
    run2 = db.query(EvaluationRun).filter(
        EvaluationRun.id == run2_id,
        EvaluationRun.user_id == current_user.id
    ).first()

    if not run1 or not run2:
        raise HTTPException(status_code=404, detail="One or both runs not found")

    # Calculate improvements (positive = better, negative = worse)
    def calc_improvement(old_val: float, new_val: float, invert: bool = False) -> float:
        if old_val == 0:
            return 0.0
        diff = (new_val - old_val) / old_val * 100
        return diff if not invert else -diff

    return EvaluationComparisonResponse(
        run1=run1,
        run2=run2,
        latency_improvement=calc_improvement(run1.avg_latency_ms, run2.avg_latency_ms, invert=True),
        token_improvement=calc_improvement(run1.avg_tokens_per_question, run2.avg_tokens_per_question, invert=True),
        citation_accuracy_improvement=calc_improvement(run1.citation_accuracy_score, run2.citation_accuracy_score),
        answer_quality_improvement=calc_improvement(run1.answer_quality_score, run2.answer_quality_score),
    )


@router.delete("/runs/{run_id}")
async def delete_evaluation_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an evaluation run."""
    run = db.query(EvaluationRun).filter(
        EvaluationRun.id == run_id,
        EvaluationRun.user_id == current_user.id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    db.delete(run)
    db.commit()
    return {"status": "deleted"}


# ============================================================================
# RAG Evaluation Comparison Endpoints
# ============================================================================


@router.post(
    "/compare/baseline-vs-rag/{document_id}",
    response_model=RAGEvaluationComparisonSchema,
    status_code=status.HTTP_200_OK,
)
async def run_rag_evaluation_comparison(
    document_id: str,
    request: RAGEvaluationComparisonRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run evaluation comparison between baseline and RAG strategies.

    Compares full-document chat against retrieval-augmented chat to measure:
    - Context reduction
    - Latency improvements
    - Citation preservation
    - Retrieval quality

    Results can optionally be persisted for regression tracking.
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

    # Load chunks for the document
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
            detail="Document has no extractable content",
        )

    # Run evaluation comparison
    runner = EvaluationRunner(
        max_latency_ms=EVAL_MAX_LATENCY_MS,
        min_context_reduction_percent=EVAL_MIN_CONTEXT_REDUCTION,
        min_citation_preservation=EVAL_MIN_CITATION_PRESERVATION,
    )

    try:
        comparison = runner.run(
            document=document,
            question=request.question,
            chunks=chunks,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Evaluation failed: {str(exc)}",
        ) from exc

    # Optionally persist the comparison
    if request.store_result and EVAL_PERSIST_RESULTS:
        try:
            eval_record = RAGEvaluationComparison(
                user_id=current_user.id,
                document_id=document_id,
                question=comparison.question,
                baseline_success=comparison.baseline.success,
                baseline_latency_ms=comparison.baseline.total_latency_ms,
                baseline_prompt_chars=comparison.baseline.prompt_character_count,
                baseline_response_chars=comparison.baseline.response_character_count,
                baseline_citation_count=comparison.baseline.citation_count,
                baseline_error=comparison.baseline.error,
                rag_success=comparison.rag.success,
                rag_latency_ms=comparison.rag.total_latency_ms,
                rag_prompt_chars=comparison.rag.prompt_character_count,
                rag_response_chars=comparison.rag.response_character_count,
                rag_citation_count=comparison.rag.citation_count,
                rag_retrieved_chunk_count=comparison.rag.retrieved_chunk_count,
                rag_retrieved_chunk_ids=comparison.rag.retrieved_chunk_ids,
                rag_retrieval_scores=comparison.rag.retrieval_scores,
                rag_error=comparison.rag.error,
                context_reduction_percent=comparison.comparison.context_reduction_percent,
                latency_difference_ms=comparison.comparison.latency_difference_ms,
                citation_difference=comparison.comparison.citation_difference,
                avg_similarity_score=comparison.comparison.retrieved_chunk_avg_similarity,
                comparison_status=comparison.comparison.status,
                status_reason=comparison.comparison.status_reason,
                ai_model=comparison.baseline.ai_model,
            )
            db.add(eval_record)
            db.commit()
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "evaluation_persistence_failed",
                "Evaluation comparison could not be persisted",
                exc_info=True,
                document_id=document_id,
                user_id=current_user.id,
                error_type=type(exc).__name__,
            )
            # Persistence failure is not fatal; return results anyway

    return comparison


@router.get(
    "/comparison-results/{document_id}",
    response_model=list[RAGEvaluationComparisonResponse],
    status_code=status.HTTP_200_OK,
)
async def list_comparison_results(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all RAG evaluation comparisons for a document."""
    # Verify document ownership
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get comparisons
    comparisons = db.query(RAGEvaluationComparison).filter(
        RAGEvaluationComparison.document_id == document_id,
        RAGEvaluationComparison.user_id == current_user.id,
    ).order_by(RAGEvaluationComparison.created_at.desc()).all()

    return comparisons
