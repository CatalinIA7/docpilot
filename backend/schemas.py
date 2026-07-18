from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    file_type: str
    size: int
    preview: str
    word_count: int
    character_count: int
    paragraph_count: int
    created_at: datetime


class DocumentDetailResponse(DocumentResponse):
    text: str


class DocumentSearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    file_type: str
    created_at: datetime
    word_count: int
    preview: str


class Citation(BaseModel):
    """A citation pointing to a source section in the document."""

    source_id: int
    page: int | None = None
    paragraph: int | None = None
    excerpt: str


class ChatResponse(BaseModel):
    """Response to a chat question."""

    answer: str
    citations: list[Citation] = []


class BenchmarkQuestionCreate(BaseModel):
    """Create a benchmark question for a document."""

    question: str = Field(min_length=10, max_length=1000)
    expected_answer_summary: str = Field(min_length=10, max_length=2000)
    expected_citation_count: int = Field(ge=0, le=10)


class BenchmarkQuestionResponse(BenchmarkQuestionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: str
    created_at: datetime


class EvaluationResultResponse(BaseModel):
    """Result for a single question in an evaluation run."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    benchmark_question_id: int
    ai_response: str
    citations_returned: int
    latency_ms: float
    tokens_used: int
    citation_accuracy: float
    answer_quality: float
    created_at: datetime


class EvaluationRunResponse(BaseModel):
    """Summary of an evaluation run."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    run_name: str
    approach: str
    total_questions: int
    questions_with_citations: int
    avg_latency_ms: float
    total_tokens_used: int
    avg_tokens_per_question: float
    citation_accuracy_score: float
    answer_quality_score: float
    citation_coverage: float
    created_at: datetime


class EvaluationRunDetailResponse(EvaluationRunResponse):
    """Detailed evaluation run with all individual results."""

    results: list[EvaluationResultResponse]


class EvaluationRunCreateRequest(BaseModel):
    """Request to run an evaluation."""

    run_name: str = Field(min_length=1, max_length=255)
    document_id: str
    approach: str = "full-document"


class EvaluationComparisonResponse(BaseModel):
    """Comparison between two evaluation runs."""

    model_config = ConfigDict(from_attributes=True)
    run1: EvaluationRunResponse
    run2: EvaluationRunResponse
    latency_improvement: float  # Percentage improvement (negative = slower)
    token_improvement: float  # Percentage improvement
    citation_accuracy_improvement: float
    answer_quality_improvement: float


# ============================================================================
# RAG Evaluation Comparison Schemas
# ============================================================================


class EvaluationRunMetricsSchema(BaseModel):
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
    retrieved_chunk_ids: list[int]
    retrieval_scores: list[float]
    ai_model: str
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    answer_text: str = ""
    error: str | None = None


class ComparisonMetricsSchema(BaseModel):
    """Derived metrics comparing baseline vs RAG."""

    context_reduction_percent: float
    latency_difference_ms: float
    latency_improvement_percent: float
    generation_latency_difference_ms: float
    citation_difference: int
    retrieved_chunk_avg_similarity: float
    retrieved_chunk_highest_similarity: float
    retrieved_chunk_lowest_similarity: float
    status: str  # "PASS", "WARNING", "FAIL"
    status_reason: str


class RAGEvaluationComparisonSchema(BaseModel):
    """Complete comparison result between baseline and RAG."""

    question: str
    document_id: str
    baseline: EvaluationRunMetricsSchema
    rag: EvaluationRunMetricsSchema
    comparison: ComparisonMetricsSchema


class RAGEvaluationComparisonRequest(BaseModel):
    """Request to run a RAG evaluation comparison."""

    question: str = Field(..., min_length=1, max_length=1000)
    store_result: bool = True  # Whether to persist the comparison


class RAGEvaluationComparisonResponse(BaseModel):
    """Stored evaluation comparison response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    document_id: str
    baseline_latency_ms: float
    rag_latency_ms: float
    context_reduction_percent: float
    citation_difference: int
    comparison_status: str
    created_at: str


# Conversation and Message schemas

class MessageSchema(BaseModel):
    """Message in a conversation."""
    id: str
    role: str  # "user" or "assistant"
    content: str
    citations: list[dict] = []
    created_at: str

    class Config:
        from_attributes = True


class ConversationCreateRequest(BaseModel):
    """Create a new conversation."""
    title: str | None = Field(None, max_length=255)
    question: str | None = Field(None, max_length=1000, description="Optional first message")

    @field_validator("title")
    @classmethod
    def title_strip(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            raise ValueError("Title must not be empty")
        return v.strip() if v else None

    @field_validator("question")
    @classmethod
    def question_strip(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            raise ValueError("Question must not be empty")
        return v.strip() if v else None


class ConversationResponse(BaseModel):
    """Response for a conversation."""
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int | None = None
    last_message_at: str | None = None

    class Config:
        from_attributes = True


class ConversationDetailResponse(ConversationResponse):
    """Detailed response including messages."""
    messages: list[MessageSchema] = []

    class Config:
        from_attributes = True


class ContinueChatRequest(BaseModel):
    """Request to continue a conversation."""
    conversation_id: str
    question: Annotated[str, Field(min_length=1, max_length=1000)]

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Question must not be empty or whitespace.")
        return v.strip()
