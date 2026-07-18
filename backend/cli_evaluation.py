#!/usr/bin/env python
"""
CLI utility for running RAG evaluation comparisons.

Usage:
    python -m cli_evaluation compare <document_id> <question> [--json] [--no-persist]
    python -m cli_evaluation results <document_id> [--json]
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Optional

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent))

from database import SessionLocal
from models import Document, DocumentChunk
from evaluation_comparison_service import EvaluationRunner
from config import EVAL_MAX_LATENCY_MS, EVAL_MIN_CONTEXT_REDUCTION, EVAL_MIN_CITATION_PRESERVATION, EVAL_PERSIST_RESULTS


def format_comparison_report(comparison) -> str:
    """Format comparison as human-readable report."""
    lines = []
    lines.append("=" * 80)
    lines.append("RAG Evaluation Report")
    lines.append("=" * 80)
    lines.append("")
    
    # Question
    lines.append("Question")
    lines.append("-" * 80)
    lines.append(comparison.question)
    lines.append("")
    
    # Baseline
    baseline = comparison.baseline
    lines.append("Baseline (Full Document)")
    lines.append("-" * 80)
    lines.append(f"Status              {baseline.success}")
    if baseline.success:
        lines.append(f"Latency             {baseline.total_latency_ms:.1f} ms")
        lines.append(f"Generation time     {baseline.generation_latency_ms:.1f} ms")
        lines.append(f"Prompt chars        {baseline.prompt_character_count:,}")
        lines.append(f"Response chars      {baseline.response_character_count:,}")
        lines.append(f"Citations           {baseline.citation_count}")
        lines.append(f"Chunks used         {baseline.retrieved_chunk_count}")
    else:
        lines.append(f"Error               {baseline.error}")
    lines.append("")
    
    # RAG
    rag = comparison.rag
    lines.append("RAG (Retrieval-Augmented)")
    lines.append("-" * 80)
    lines.append(f"Status              {rag.success}")
    if rag.success:
        lines.append(f"Latency             {rag.total_latency_ms:.1f} ms")
        lines.append(f"Embedding time      {rag.embedding_latency_ms:.1f} ms")
        lines.append(f"Retrieval time      {rag.retrieval_latency_ms:.1f} ms")
        lines.append(f"Generation time     {rag.generation_latency_ms:.1f} ms")
        lines.append(f"Prompt chars        {rag.prompt_character_count:,}")
        lines.append(f"Response chars      {rag.response_character_count:,}")
        lines.append(f"Citations           {rag.citation_count}")
        lines.append(f"Chunks retrieved    {rag.retrieved_chunk_count}")
        
        if rag.retrieval_scores:
            lines.append(f"Similarity scores   {', '.join(f'{s:.2f}' for s in rag.retrieval_scores)}")
            avg_sim = sum(rag.retrieval_scores) / len(rag.retrieval_scores)
            lines.append(f"Avg similarity      {avg_sim:.2f}")
    else:
        lines.append(f"Error               {rag.error}")
    lines.append("")
    
    # Comparison
    comp = comparison.comparison
    lines.append("Comparison Metrics")
    lines.append("-" * 80)
    lines.append(f"Context reduction   {comp.context_reduction_percent:.1f}%")
    lines.append(f"Latency change      {comp.latency_difference_ms:+.1f} ms ({comp.latency_improvement_percent:+.1f}%)")
    lines.append(f"Gen latency change  {comp.generation_latency_difference_ms:+.1f} ms")
    lines.append(f"Citation change     {comp.citation_difference:+d}")
    lines.append("")
    
    # Status
    lines.append("Evaluation Status")
    lines.append("-" * 80)
    lines.append(f"Result              {comp.status}")
    lines.append(f"Reason              {comp.status_reason}")
    lines.append("=" * 80)
    
    return "\n".join(lines)


def format_comparison_json(comparison, runner) -> str:
    """Format comparison as JSON."""
    result_dict = runner.to_dict(comparison)
    return json.dumps(result_dict, indent=2, default=str)


def run_comparison(
    document_id: str,
    question: str,
    json_output: bool = False,
    persist: bool = True,
) -> int:
    """
    Run an evaluation comparison.

    Args:
        document_id: ID of document to evaluate
        question: Question to answer
        json_output: Whether to output as JSON
        persist: Whether to persist results

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    db = SessionLocal()
    try:
        # Get document
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            print(f"Error: Document {document_id} not found", file=sys.stderr)
            return 1

        # Get chunks
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

        if not chunks:
            print(f"Error: Document {document_id} has no chunks", file=sys.stderr)
            return 1

        # Run evaluation
        runner = EvaluationRunner(
            max_latency_ms=EVAL_MAX_LATENCY_MS,
            min_context_reduction_percent=EVAL_MIN_CONTEXT_REDUCTION,
            min_citation_preservation=EVAL_MIN_CITATION_PRESERVATION,
        )

        comparison = runner.run(
            document=document,
            question=question,
            chunks=chunks,
        )

        # Output results
        if json_output:
            output = format_comparison_json(comparison, runner)
        else:
            output = format_comparison_report(comparison)

        print(output)

        # Exit code based on status
        if comparison.comparison.status == "PASS":
            return 0
        elif comparison.comparison.status == "WARNING":
            return 1
        else:  # FAIL
            return 2

    except Exception as exc:
        print(f"Error: {str(exc)}", file=sys.stderr)
        return 1
    finally:
        db.close()


def list_results(document_id: str, json_output: bool = False) -> int:
    """
    List evaluation results for a document.

    Args:
        document_id: ID of document
        json_output: Whether to output as JSON

    Returns:
        Exit code
    """
    db = SessionLocal()
    try:
        from models import RAGEvaluationComparison

        # Get comparisons
        comparisons = (
            db.query(RAGEvaluationComparison)
            .filter(RAGEvaluationComparison.document_id == document_id)
            .order_by(RAGEvaluationComparison.created_at.desc())
            .all()
        )

        if not comparisons:
            print(f"No evaluation results found for document {document_id}")
            return 0

        if json_output:
            results = [
                {
                    "id": c.id,
                    "question": c.question,
                    "baseline_latency_ms": c.baseline_latency_ms,
                    "rag_latency_ms": c.rag_latency_ms,
                    "context_reduction_percent": c.context_reduction_percent,
                    "status": c.comparison_status,
                    "created_at": c.created_at.isoformat(),
                }
                for c in comparisons
            ]
            print(json.dumps(results, indent=2))
        else:
            print("=" * 80)
            print("Evaluation Results")
            print("=" * 80)
            for i, c in enumerate(comparisons, 1):
                print(f"\n{i}. {c.question[:60]}...")
                print(f"   Baseline: {c.baseline_latency_ms:.0f}ms | RAG: {c.rag_latency_ms:.0f}ms")
                print(f"   Context reduction: {c.context_reduction_percent:.1f}%")
                print(f"   Status: {c.comparison_status}")
                print(f"   Created: {c.created_at.isoformat()}")
            print("=" * 80)

        return 0

    except Exception as exc:
        print(f"Error: {str(exc)}", file=sys.stderr)
        return 1
    finally:
        db.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="RAG Evaluation Comparison CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a comparison
  python cli_evaluation.py compare doc-123 "What is the refund policy?"
  
  # Run comparison and output JSON
  python cli_evaluation.py compare doc-123 "What is the refund policy?" --json
  
  # List results for a document
  python cli_evaluation.py results doc-123
  
  # List results as JSON
  python cli_evaluation.py results doc-123 --json
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Run evaluation comparison")
    compare_parser.add_argument("document_id", help="Document ID")
    compare_parser.add_argument("question", help="Question to answer")
    compare_parser.add_argument("--json", action="store_true", help="Output as JSON")
    compare_parser.add_argument("--no-persist", action="store_true", help="Don't persist results")

    # Results command
    results_parser = subparsers.add_parser("results", help="List evaluation results")
    results_parser.add_argument("document_id", help="Document ID")
    results_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command == "compare":
        exit_code = run_comparison(
            document_id=args.document_id,
            question=args.question,
            json_output=args.json,
            persist=not args.no_persist,
        )
    elif args.command == "results":
        exit_code = list_results(
            document_id=args.document_id,
            json_output=args.json,
        )
    else:
        parser.print_help()
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
