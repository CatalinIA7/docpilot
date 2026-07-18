from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
