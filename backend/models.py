from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Float, Boolean, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paragraph_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    owner: Mapped[User] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_section_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[Document] = relationship(back_populates="chunks")


class BenchmarkQuestion(Base):
    __tablename__ = "benchmark_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer_summary: Mapped[str] = mapped_column(Text, nullable=False)
    expected_citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[Document] = relationship()
    evaluation_results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="benchmark_question", cascade="all, delete-orphan"
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    run_name: Mapped[str] = mapped_column(String(255), nullable=False)
    approach: Mapped[str] = mapped_column(String(50), nullable=False, default="full-document")
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    questions_with_citations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_tokens_per_question: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    citation_accuracy_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    answer_quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    citation_coverage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship()
    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="evaluation_run", cascade="all, delete-orphan"
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluation_run_id: Mapped[int] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    benchmark_question_id: Mapped[int] = mapped_column(ForeignKey("benchmark_questions.id", ondelete="CASCADE"), index=True, nullable=False)
    ai_response: Mapped[str] = mapped_column(Text, nullable=False)
    citations_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    citation_accuracy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    answer_quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    eval_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    evaluation_run: Mapped[EvaluationRun] = relationship(back_populates="results")
    benchmark_question: Mapped[BenchmarkQuestion] = relationship(back_populates="evaluation_results")
