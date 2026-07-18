"""
AI Observability service for chat requests.

Responsibilities
----------------
* Record reliable operational telemetry for document-chat requests.
* Measure stage durations using monotonic timing.
* Capture retrieval and generation metrics.
* Preserve request IDs throughout the pipeline.
* Safely log structured events without exposing sensitive data.
* Persist records without breaking successful requests.

Nothing in this module handles UI, dashboards, or external services —
it focuses on internal telemetry collection and structured logging.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_OBSERVABILITY_ENABLED = True
_DEFAULT_OBSERVABILITY_PERSIST = True
_DEFAULT_OBSERVABILITY_LOG_LEVEL = "INFO"


def _get_observability_enabled() -> bool:
    """Check if observability is enabled."""
    value = os.environ.get("DOCPILOT_OBSERVABILITY_ENABLED", str(_DEFAULT_OBSERVABILITY_ENABLED))
    return value.lower() in ("true", "1", "yes")


def _get_observability_persist() -> bool:
    """Check if observability records should be persisted to database."""
    value = os.environ.get("DOCPILOT_OBSERVABILITY_PERSIST", str(_DEFAULT_OBSERVABILITY_PERSIST))
    return value.lower() in ("true", "1", "yes")


def _get_observability_log_level() -> str:
    """Get the log level for observability events."""
    return os.environ.get("DOCPILOT_OBSERVABILITY_LOG_LEVEL", _DEFAULT_OBSERVABILITY_LOG_LEVEL)


# ---------------------------------------------------------------------------
# Status and failure stages
# ---------------------------------------------------------------------------


class Status:
    """Stable status values for chat requests."""
    SUCCESS = "success"
    FAILED = "failed"


class FailureStage:
    """Stable failure stage values."""
    AUTHORIZATION = "authorization"
    DOCUMENT_LOADING = "document_loading"
    QUESTION_EMBEDDING = "question_embedding"
    RETRIEVAL = "retrieval"
    CONTEXT_ASSEMBLY = "context_assembly"
    GENERATION = "generation"
    RESPONSE_VALIDATION = "response_validation"
    DATABASE_PERSISTENCE = "database_persistence"
    UNKNOWN = "unknown"


class ProviderErrorType:
    """Safe provider error categories."""
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    CONFIGURATION = "configuration"
    UNKNOWN_PROVIDER_ERROR = "unknown_provider_error"


# ---------------------------------------------------------------------------
# Observability data structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatObservabilityRecord:
    """Complete telemetry for one document-chat request."""

    # Identifiers
    request_id: str
    user_id: int
    document_id: str

    # Status
    status: str  # Status.SUCCESS or Status.FAILED
    failure_stage: Optional[str] = None

    # Timing (milliseconds, monotonic)
    total_duration_ms: float = 0.0
    question_embedding_duration_ms: float = 0.0
    retrieval_duration_ms: float = 0.0
    generation_duration_ms: float = 0.0

    # Document and retrieval
    candidate_chunk_count: int = 0
    embedded_candidate_count: int = 0
    retrieved_chunk_count: int = 0
    retrieved_chunk_ids: list[int] = field(default_factory=list)
    retrieval_scores: list[float] = field(default_factory=list)
    retrieval_top_k: int = 0
    retrieval_min_score: float = 0.0

    # Generation
    prompt_character_count: int = 0
    response_character_count: int = 0
    citation_count: int = 0

    # Models
    ai_model: str = ""
    embedding_model: str = ""
    embedding_dimension: int = 0

    # Optional token usage (may be None if not available)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    # Errors
    provider_error_type: Optional[str] = None

    # Timestamp
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Observability recorder
# ---------------------------------------------------------------------------


class ChatObservabilityRecorder:
    """Record and manage observability data for one chat request."""

    def __init__(self, request_id: str, user_id: int, document_id: str):
        self.request_id = request_id
        self.user_id = user_id
        self.document_id = document_id

        # Status tracking
        self.status = Status.SUCCESS
        self.failure_stage: Optional[str] = None

        # Timing (monotonic)
        self._start_time = time.perf_counter()
        self._stage_starts: dict[str, float] = {}
        self._stage_durations: dict[str, float] = {}

        # Retrieval
        self.candidate_chunk_count = 0
        self.embedded_candidate_count = 0
        self.retrieved_chunk_count = 0
        self.retrieved_chunk_ids: list[int] = []
        self.retrieval_scores: list[float] = []
        self.retrieval_top_k = 0
        self.retrieval_min_score = 0.0

        # Generation
        self.prompt_character_count = 0
        self.response_character_count = 0
        self.citation_count = 0

        # Models
        self.ai_model = ""
        self.embedding_model = ""
        self.embedding_dimension = 0

        # Tokens
        self.input_tokens: Optional[int] = None
        self.output_tokens: Optional[int] = None
        self.total_tokens: Optional[int] = None

        # Errors
        self.provider_error_type: Optional[str] = None

    def start_stage(self, stage_name: str) -> None:
        """Mark the start of a named stage."""
        self._stage_starts[stage_name] = time.perf_counter()

    def end_stage(self, stage_name: str) -> None:
        """Mark the end of a named stage and record its duration."""
        if stage_name in self._stage_starts:
            duration_ms = (
                (time.perf_counter() - self._stage_starts[stage_name]) * 1000
            )
            self._stage_durations[stage_name] = duration_ms

    def record_stage_duration(self, stage_name: str, duration_ms: float) -> None:
        """Manually record a stage duration."""
        self._stage_durations[stage_name] = duration_ms

    def record_question_embedding(
        self,
        model: str,
        dimension: int,
        duration_ms: float,
    ) -> None:
        """Record question embedding generation."""
        self.embedding_model = model
        self.embedding_dimension = dimension
        self.record_stage_duration("question_embedding", duration_ms)

    def record_retrieval(
        self,
        candidate_count: int,
        embedded_candidate_count: int,
        retrieved_count: int,
        chunk_ids: list[int],
        scores: list[float],
        top_k: int,
        min_score: float,
        duration_ms: float,
    ) -> None:
        """Record retrieval results."""
        self.candidate_chunk_count = candidate_count
        self.embedded_candidate_count = embedded_candidate_count
        self.retrieved_chunk_count = retrieved_count
        self.retrieved_chunk_ids = chunk_ids
        self.retrieval_scores = scores
        self.retrieval_top_k = top_k
        self.retrieval_min_score = min_score
        self.record_stage_duration("retrieval", duration_ms)

    def record_generation(
        self,
        model: str,
        prompt_char_count: int,
        response_char_count: int,
        citation_count: int,
        duration_ms: float,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
    ) -> None:
        """Record AI generation results."""
        self.ai_model = model
        self.prompt_character_count = prompt_char_count
        self.response_character_count = response_char_count
        self.citation_count = citation_count
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = total_tokens
        self.record_stage_duration("generation", duration_ms)

    def mark_failure(
        self,
        failure_stage: str,
        provider_error_type: Optional[str] = None,
    ) -> None:
        """Mark request as failed."""
        self.status = Status.FAILED
        self.failure_stage = failure_stage
        self.provider_error_type = provider_error_type

    def build_record(self) -> ChatObservabilityRecord:
        """Build the final observability record."""
        from datetime import datetime, timezone

        total_ms = (time.perf_counter() - self._start_time) * 1000

        return ChatObservabilityRecord(
            request_id=self.request_id,
            user_id=self.user_id,
            document_id=self.document_id,
            status=self.status,
            failure_stage=self.failure_stage,
            total_duration_ms=total_ms,
            question_embedding_duration_ms=self._stage_durations.get(
                "question_embedding", 0.0
            ),
            retrieval_duration_ms=self._stage_durations.get("retrieval", 0.0),
            generation_duration_ms=self._stage_durations.get("generation", 0.0),
            candidate_chunk_count=self.candidate_chunk_count,
            embedded_candidate_count=self.embedded_candidate_count,
            retrieved_chunk_count=self.retrieved_chunk_count,
            retrieved_chunk_ids=self.retrieved_chunk_ids,
            retrieval_scores=self.retrieval_scores,
            retrieval_top_k=self.retrieval_top_k,
            retrieval_min_score=self.retrieval_min_score,
            prompt_character_count=self.prompt_character_count,
            response_character_count=self.response_character_count,
            citation_count=self.citation_count,
            ai_model=self.ai_model,
            embedding_model=self.embedding_model,
            embedding_dimension=self.embedding_dimension,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=self.total_tokens,
            provider_error_type=self.provider_error_type,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def emit_log(self) -> None:
        """Emit a structured log event for this request."""
        record = self.build_record()

        # Determine log level and message
        if record.status == Status.SUCCESS:
            level = logging.INFO
            event_name = "document_chat_completed"
        else:
            level = logging.WARNING
            event_name = "document_chat_failed"

        # Safe logging fields (no sensitive data)
        log_data = {
            "event": event_name,
            "request_id": record.request_id,
            "user_id": record.user_id,
            "document_id": record.document_id,
            "status": record.status,
            "failure_stage": record.failure_stage,
            "total_duration_ms": round(record.total_duration_ms, 2),
            "embedding_duration_ms": round(record.question_embedding_duration_ms, 2),
            "retrieval_duration_ms": round(record.retrieval_duration_ms, 2),
            "generation_duration_ms": round(record.generation_duration_ms, 2),
            "candidate_chunk_count": record.candidate_chunk_count,
            "embedded_candidate_count": record.embedded_candidate_count,
            "retrieved_chunk_count": record.retrieved_chunk_count,
            "citation_count": record.citation_count,
            "ai_model": record.ai_model,
            "embedding_model": record.embedding_model,
            "embedding_dimension": record.embedding_dimension,
        }

        # Add optional fields if present
        if record.total_tokens is not None:
            log_data["total_tokens"] = record.total_tokens
        if record.provider_error_type:
            log_data["provider_error_type"] = record.provider_error_type

        logger.log(level, f"{event_name}", extra=log_data)


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())


def parse_request_id(value: str) -> Optional[str]:
    """Parse and validate a request ID from an incoming header."""
    if not value or not isinstance(value, str):
        return None
    # Accept UUID format or similar alphanumeric strings
    value = value.strip()
    if len(value) > 100:  # Sanity check
        return None
    return value
