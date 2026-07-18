#!/usr/bin/env python
"""
CLI tool for running evaluation benchmarks against documents.
Usage:
    python eval_cli.py run --document-id=<id> --run-name="My Eval" --user-id=<id>
    python eval_cli.py list-runs --user-id=<id>
    python eval_cli.py create-question --document-id=<id>
"""
import sys
import time
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User, Document, BenchmarkQuestion, EvaluationRun
from evaluator import Evaluator
import argparse


def get_session() -> Session:
    """Get database session."""
    return SessionLocal()


def run_evaluation(document_id: str, run_name: str, user_id: int, approach: str = "full-document"):
    """Run evaluation for a document."""
    db = get_session()
    
    try:
        # Verify document and ownership
        doc = db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == user_id
        ).first()
        
        if not doc:
            print(f"❌ Document not found or not owned by user {user_id}")
            return
        
        # Get benchmark questions
        questions = db.query(BenchmarkQuestion).filter(
            BenchmarkQuestion.document_id == document_id
        ).all()
        
        if not questions:
            print(f"❌ No benchmark questions found for document {document_id}")
            print("   Create some with: python eval_cli.py create-question")
            return
        
        print(f"\n📊 Running evaluation: {run_name}")
        print(f"   Document: {doc.filename}")
        print(f"   Questions: {len(questions)}")
        print(f"   Approach: {approach}\n")
        
        # Run evaluation
        evaluator = Evaluator(db)
        start_time = time.time()
        run, results = evaluator.run_evaluation(
            benchmark_questions=questions,
            user_id=user_id,
            run_name=run_name,
            approach=approach,
        )
        
        # Save to database
        db.add(run)
        for result in results:
            db.add(result)
        db.commit()
        
        elapsed = time.time() - start_time
        
        # Display results
        print(f"✅ Evaluation complete in {elapsed:.1f}s\n")
        print(f"📈 Results (Run ID: {run.id}):")
        print(f"   Questions evaluated: {run.total_questions}")
        print(f"   Questions with citations: {run.questions_with_citations} ({run.citation_coverage*100:.1f}%)")
        print(f"   Avg latency: {run.avg_latency_ms:.1f}ms")
        print(f"   Avg tokens per question: {run.avg_tokens_per_question:.0f}")
        print(f"   Citation accuracy: {run.citation_accuracy_score*100:.1f}%")
        print(f"   Answer quality: {run.answer_quality_score*100:.1f}%")
        print(f"\n   View details: python eval_cli.py view-run --run-id={run.id}")
        
    finally:
        db.close()


def list_runs(user_id: int):
    """List all evaluation runs for a user."""
    db = get_session()
    
    try:
        runs = db.query(EvaluationRun).filter(
            EvaluationRun.user_id == user_id
        ).order_by(EvaluationRun.created_at.desc()).all()
        
        if not runs:
            print(f"No evaluation runs found for user {user_id}")
            return
        
        print(f"\n📊 Evaluation Runs for user {user_id}:\n")
        print(f"{'ID':<5} {'Name':<30} {'Questions':<10} {'Accuracy':<10} {'Date':<19}")
        print("-" * 74)
        
        for run in runs:
            date_str = run.created_at.strftime("%Y-%m-%d %H:%M:%S")
            accuracy = f"{run.citation_accuracy_score*100:.1f}%"
            print(f"{run.id:<5} {run.run_name:<30} {run.total_questions:<10} {accuracy:<10} {date_str:<19}")
        
        print(f"\nView details: python eval_cli.py view-run --run-id=<id>")
        
    finally:
        db.close()


def view_run(run_id: int):
    """View detailed results for a run."""
    db = get_session()
    
    try:
        run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
        
        if not run:
            print(f"❌ Run {run_id} not found")
            return
        
        print(f"\n📊 Evaluation Run #{run.id}: {run.run_name}\n")
        print(f"Approach: {run.approach}")
        print(f"Created: {run.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        print(f"Metrics:")
        print(f"  Total questions: {run.total_questions}")
        print(f"  With citations: {run.questions_with_citations}/{run.total_questions} ({run.citation_coverage*100:.1f}%)")
        print(f"  Avg latency: {run.avg_latency_ms:.1f}ms")
        print(f"  Total tokens: {run.total_tokens_used}")
        print(f"  Avg tokens/question: {run.avg_tokens_per_question:.0f}")
        print(f"  Citation accuracy: {run.citation_accuracy_score*100:.1f}%")
        print(f"  Answer quality: {run.answer_quality_score*100:.1f}%\n")
        
        # Show individual results
        if run.results:
            print(f"Individual Results:\n")
            print(f"{'Q#':<4} {'Citations':<10} {'Latency':<10} {'C.Accuracy':<12} {'Q.Quality':<10}")
            print("-" * 46)
            for i, result in enumerate(run.results, 1):
                print(f"{i:<4} {result.citations_returned:<10} {result.latency_ms:<10.1f} {result.citation_accuracy:<12.1%} {result.answer_quality:<10.1%}")
        
    finally:
        db.close()


def create_question(document_id: str, user_id: int):
    """Interactively create a benchmark question."""
    db = get_session()
    
    try:
        # Verify ownership
        doc = db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == user_id
        ).first()
        
        if not doc:
            print(f"❌ Document not found or not owned by user {user_id}")
            return
        
        print(f"\n📝 Create Benchmark Question for: {doc.filename}\n")
        
        question = input("Question: ").strip()
        if not question:
            print("❌ Question cannot be empty")
            return
        
        summary = input("Expected answer summary: ").strip()
        if not summary:
            print("❌ Summary cannot be empty")
            return
        
        while True:
            try:
                citation_count = int(input("Expected number of citations (0-10): ").strip())
                if 0 <= citation_count <= 10:
                    break
                print("❌ Please enter a number between 0 and 10")
            except ValueError:
                print("❌ Invalid number")
        
        bq = BenchmarkQuestion(
            document_id=document_id,
            question=question,
            expected_answer_summary=summary,
            expected_citation_count=citation_count,
        )
        db.add(bq)
        db.commit()
        
        print(f"\n✅ Question created (ID: {bq.id})")
        
    finally:
        db.close()


def list_questions(document_id: str, user_id: int):
    """List benchmark questions for a document."""
    db = get_session()
    
    try:
        # Verify ownership
        doc = db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == user_id
        ).first()
        
        if not doc:
            print(f"❌ Document not found or not owned by user {user_id}")
            return
        
        questions = db.query(BenchmarkQuestion).filter(
            BenchmarkQuestion.document_id == document_id
        ).all()
        
        if not questions:
            print(f"No benchmark questions for {doc.filename}")
            return
        
        print(f"\n📋 Benchmark Questions for: {doc.filename}\n")
        print(f"{'ID':<4} {'Question':<50} {'Citations':<10}")
        print("-" * 64)
        
        for q in questions:
            question_text = (q.question[:47] + "...") if len(q.question) > 50 else q.question
            print(f"{q.id:<4} {question_text:<50} {q.expected_citation_count:<10}")
        
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="DocPilot Evaluation CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # run command
    run_parser = subparsers.add_parser("run", help="Run evaluation")
    run_parser.add_argument("--document-id", required=True, help="Document ID")
    run_parser.add_argument("--run-name", required=True, help="Name for this evaluation run")
    run_parser.add_argument("--user-id", type=int, required=True, help="User ID")
    run_parser.add_argument("--approach", default="full-document", help="Evaluation approach")
    
    # list-runs command
    list_parser = subparsers.add_parser("list-runs", help="List evaluation runs")
    list_parser.add_argument("--user-id", type=int, required=True, help="User ID")
    
    # view-run command
    view_parser = subparsers.add_parser("view-run", help="View run details")
    view_parser.add_argument("--run-id", type=int, required=True, help="Run ID")
    
    # create-question command
    create_parser = subparsers.add_parser("create-question", help="Create benchmark question")
    create_parser.add_argument("--document-id", required=True, help="Document ID")
    create_parser.add_argument("--user-id", type=int, required=True, help="User ID")
    
    # list-questions command
    questions_parser = subparsers.add_parser("list-questions", help="List benchmark questions")
    questions_parser.add_argument("--document-id", required=True, help="Document ID")
    questions_parser.add_argument("--user-id", type=int, required=True, help="User ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "run":
        run_evaluation(args.document_id, args.run_name, args.user_id, args.approach)
    elif args.command == "list-runs":
        list_runs(args.user_id)
    elif args.command == "view-run":
        view_run(args.run_id)
    elif args.command == "create-question":
        create_question(args.document_id, args.user_id)
    elif args.command == "list-questions":
        list_questions(args.document_id, args.user_id)


if __name__ == "__main__":
    main()
