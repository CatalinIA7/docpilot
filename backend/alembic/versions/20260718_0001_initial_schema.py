"""Create the initial DocPilot schema.

Revision ID: 20260718_0001
Revises:
Create Date: 2026-07-18
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260718_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the schema represented by the current SQLAlchemy models."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("preview", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("paragraph_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename"),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"], unique=False)

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("run_name", sa.String(length=255), nullable=False),
        sa.Column("approach", sa.String(length=50), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("questions_with_citations", sa.Integer(), nullable=False),
        sa.Column("avg_latency_ms", sa.Float(), nullable=False),
        sa.Column("total_tokens_used", sa.Integer(), nullable=False),
        sa.Column("avg_tokens_per_question", sa.Float(), nullable=False),
        sa.Column("citation_accuracy_score", sa.Float(), nullable=False),
        sa.Column("answer_quality_score", sa.Float(), nullable=False),
        sa.Column("citation_coverage", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_runs_user_id", "evaluation_runs", ["user_id"], unique=False)

    op.create_table(
        "benchmark_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer_summary", sa.Text(), nullable=False),
        sa.Column("expected_citation_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_benchmark_questions_document_id",
        "benchmark_questions",
        ["document_id"],
        unique=False,
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_created_at", "conversations", ["created_at"], unique=False)
    op.create_index("ix_conversations_document_id", "conversations", ["document_id"], unique=False)
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"], unique=False)
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"], unique=False)

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("paragraph", sa.Integer(), nullable=True),
        sa.Column("source_section_id", sa.Integer(), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"], unique=False)

    op.create_table(
        "rag_evaluation_comparisons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("baseline_success", sa.Boolean(), nullable=False),
        sa.Column("baseline_latency_ms", sa.Float(), nullable=False),
        sa.Column("baseline_prompt_chars", sa.Integer(), nullable=False),
        sa.Column("baseline_response_chars", sa.Integer(), nullable=False),
        sa.Column("baseline_citation_count", sa.Integer(), nullable=False),
        sa.Column("baseline_error", sa.String(length=255), nullable=True),
        sa.Column("rag_success", sa.Boolean(), nullable=False),
        sa.Column("rag_latency_ms", sa.Float(), nullable=False),
        sa.Column("rag_prompt_chars", sa.Integer(), nullable=False),
        sa.Column("rag_response_chars", sa.Integer(), nullable=False),
        sa.Column("rag_citation_count", sa.Integer(), nullable=False),
        sa.Column("rag_retrieved_chunk_count", sa.Integer(), nullable=False),
        sa.Column("rag_retrieved_chunk_ids", sa.JSON(), nullable=False),
        sa.Column("rag_retrieval_scores", sa.JSON(), nullable=False),
        sa.Column("rag_error", sa.String(length=255), nullable=True),
        sa.Column("context_reduction_percent", sa.Float(), nullable=False),
        sa.Column("latency_difference_ms", sa.Float(), nullable=False),
        sa.Column("citation_difference", sa.Integer(), nullable=False),
        sa.Column("avg_similarity_score", sa.Float(), nullable=False),
        sa.Column("comparison_status", sa.String(length=50), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=False),
        sa.Column("ai_model", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rag_evaluation_comparisons_created_at",
        "rag_evaluation_comparisons",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_rag_evaluation_comparisons_document_id",
        "rag_evaluation_comparisons",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_rag_evaluation_comparisons_user_id",
        "rag_evaluation_comparisons",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evaluation_run_id", sa.Integer(), nullable=False),
        sa.Column("benchmark_question_id", sa.Integer(), nullable=False),
        sa.Column("ai_response", sa.Text(), nullable=False),
        sa.Column("citations_returned", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("citation_accuracy", sa.Float(), nullable=False),
        sa.Column("answer_quality", sa.Float(), nullable=False),
        sa.Column("eval_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["benchmark_question_id"],
            ["benchmark_questions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_results_benchmark_question_id",
        "evaluation_results",
        ["benchmark_question_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_results_evaluation_run_id",
        "evaluation_results",
        ["evaluation_run_id"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"], unique=False)
    op.create_index("ix_messages_created_at", "messages", ["created_at"], unique=False)


def downgrade() -> None:
    """Drop the initial schema in reverse dependency order."""
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_evaluation_results_evaluation_run_id", table_name="evaluation_results")
    op.drop_index("ix_evaluation_results_benchmark_question_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")

    op.drop_index("ix_rag_evaluation_comparisons_user_id", table_name="rag_evaluation_comparisons")
    op.drop_index("ix_rag_evaluation_comparisons_document_id", table_name="rag_evaluation_comparisons")
    op.drop_index("ix_rag_evaluation_comparisons_created_at", table_name="rag_evaluation_comparisons")
    op.drop_table("rag_evaluation_comparisons")

    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_conversations_updated_at", table_name="conversations")
    op.drop_index("ix_conversations_document_id", table_name="conversations")
    op.drop_index("ix_conversations_created_at", table_name="conversations")
    op.drop_table("conversations")

    op.drop_index("ix_benchmark_questions_document_id", table_name="benchmark_questions")
    op.drop_table("benchmark_questions")

    op.drop_index("ix_evaluation_runs_user_id", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")

    op.drop_index("ix_documents_user_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
