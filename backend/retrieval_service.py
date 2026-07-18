"""
Retrieval service for RAG — chunk selection based on question similarity.

Responsibilities
----------------
* Generate embeddings for user questions using the embedding service.
* Calculate cosine similarity between question and chunk embeddings.
* Rank and filter chunks based on similarity scores and thresholds.
* Handle missing embeddings gracefully.
* Surface errors as typed exceptions.
* Provide observability-ready result structures.

Nothing in this module is route-specific or database-aware — it is a pure
service that can be called from any part of the application.
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass

from embedding_service import (
    embed_texts,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    EmbeddingResponseError,
)
from models import DocumentChunk
from observability import log_event

logger = logging.getLogger("docpilot.retrieval")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_TOP_K = 5
_DEFAULT_MIN_SCORE = 0.0


def _get_top_k() -> int:
    """Get the configured top-k for retrieval."""
    try:
        value = int(os.environ.get("DOCPILOT_RETRIEVAL_TOP_K", _DEFAULT_TOP_K))
        if value <= 0:
            raise ValueError("top_k must be greater than zero")
        return value
    except (ValueError, TypeError) as exc:
        raise RetrievalConfigurationError(
            f"Invalid DOCPILOT_RETRIEVAL_TOP_K: {exc}"
        ) from exc


def _get_min_score() -> float:
    """Get the configured minimum similarity score for retrieval."""
    try:
        value = float(os.environ.get("DOCPILOT_RETRIEVAL_MIN_SCORE", _DEFAULT_MIN_SCORE))
        if not (-1.0 <= value <= 1.0):
            raise ValueError("min_score must be between -1.0 and 1.0")
        return value
    except (ValueError, TypeError) as exc:
        raise RetrievalConfigurationError(
            f"Invalid DOCPILOT_RETRIEVAL_MIN_SCORE: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class RetrievalConfigurationError(RuntimeError):
    """Raised when retrieval configuration is missing or invalid."""


class RetrievalProviderError(RuntimeError):
    """Raised when embedding provider fails during retrieval."""


class RetrievalResponseError(RuntimeError):
    """Raised when retrieval response is malformed or incomplete."""


# ---------------------------------------------------------------------------
# Similarity calculation
# ---------------------------------------------------------------------------


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Validates:
    - Vectors have matching dimensions
    - Vectors are not empty
    - Handles zero-magnitude vectors safely

    Returns a value between -1.0 and 1.0.

    Raises
    ------
    RetrievalResponseError
        If vectors have mismatched dimensions, are empty, or contain NaN/inf.
    """
    # Validate dimensions
    if len(vec_a) != len(vec_b):
        raise RetrievalResponseError(
            f"Vector dimension mismatch: {len(vec_a)} vs {len(vec_b)}"
        )

    if len(vec_a) == 0:
        raise RetrievalResponseError("Cannot compute similarity for empty vectors")

    # Validate no NaN or inf values
    for i, val in enumerate(vec_a):
        if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
            raise RetrievalResponseError(
                f"Invalid value in vector_a at index {i}: {val}"
            )
    for i, val in enumerate(vec_b):
        if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
            raise RetrievalResponseError(
                f"Invalid value in vector_b at index {i}: {val}"
            )

    # Calculate dot product
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))

    # Calculate magnitudes
    magnitude_a = math.sqrt(sum(a * a for a in vec_a))
    magnitude_b = math.sqrt(sum(b * b for b in vec_b))

    # Handle zero-magnitude vectors safely
    if magnitude_a == 0.0 or magnitude_b == 0.0:
        # Two zero vectors are orthogonal (no meaningful similarity)
        # Zero vector vs non-zero is also orthogonal
        return 0.0

    # Return cosine similarity (stable numeric value)
    return dot_product / (magnitude_a * magnitude_b)


# ---------------------------------------------------------------------------
# Observability types (no persistence)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk retrieved for a question with its similarity score and rank."""

    chunk: DocumentChunk
    similarity_score: float
    rank: int  # 1-based rank in result set


@dataclass(frozen=True)
class RetrievalResult:
    """Result of retrieving chunks for a question."""

    chunks: list[RetrievedChunk]
    candidate_count: int  # Total chunks evaluated
    retrieved_count: int  # Chunks that passed filtering
    top_k: int
    min_score: float


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def retrieve_chunks(
    question: str,
    chunks: list[DocumentChunk],
    top_k: int | None = None,
    min_score: float | None = None,
) -> RetrievalResult:
    """
    Retrieve the most relevant chunks for a question using embeddings.

    Parameters
    ----------
    question : str
        The user's question to embed and search for.
    chunks : list[DocumentChunk]
        The chunks to search within.
    top_k : int, optional
        Maximum number of chunks to return. If None, uses config default.
    min_score : float, optional
        Minimum similarity score to include a chunk. If None, uses config default.

    Returns
    -------
    RetrievalResult
        Contains retrieved chunks, scores, ranks, and metadata for observability.

    Raises
    ------
    RetrievalConfigurationError
        If configuration is missing or invalid.
    RetrievalProviderError
        If embedding provider fails.
    RetrievalResponseError
        If embedding response is malformed or validation fails.
    """
    started_at = time.perf_counter()

    # Validate and normalize inputs
    if not question or not question.strip():
        raise RetrievalResponseError("Question must not be empty or whitespace-only")

    if top_k is None:
        top_k = _get_top_k()
    if min_score is None:
        min_score = _get_min_score()

    # Validate parameters
    if top_k <= 0:
        raise RetrievalConfigurationError("top_k must be greater than zero")
    if not (-1.0 <= min_score <= 1.0):
        raise RetrievalConfigurationError(
            "min_score must be between -1.0 and 1.0"
        )

    # Filter chunks with embeddings
    embedded_chunks = [c for c in chunks if c.embedding is not None]
    candidate_count = len(embedded_chunks)

    if not embedded_chunks:
        result = RetrievalResult(
            chunks=[],
            candidate_count=candidate_count,
            retrieved_count=0,
            top_k=top_k,
            min_score=min_score,
        )
        log_event(
            logger,
            logging.INFO,
            "retrieval_completed",
            "Semantic retrieval completed",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            candidate_count=0,
            retrieved_count=0,
            top_k=top_k,
            min_score=min_score,
        )
        return result

    # Generate question embedding
    try:
        embeddings = embed_texts([question.strip()])
        if len(embeddings) != 1:
            raise RetrievalResponseError(
                f"Expected 1 embedding for question, got {len(embeddings)}"
            )
        question_embedding = embeddings[0]
    except EmbeddingConfigurationError as exc:
        log_event(
            logger,
            logging.ERROR,
            "retrieval_failed",
            "Semantic retrieval configuration failed",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            candidate_count=candidate_count,
            error_type=type(exc).__name__,
        )
        raise RetrievalConfigurationError(
            f"Embedding service not configured: {exc}"
        ) from exc
    except EmbeddingProviderError as exc:
        log_event(
            logger,
            logging.ERROR,
            "retrieval_failed",
            "Semantic retrieval provider failed",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            candidate_count=candidate_count,
            error_type=type(exc).__name__,
        )
        raise RetrievalProviderError(
            f"Embedding provider failed: {exc}"
        ) from exc
    except EmbeddingResponseError as exc:
        log_event(
            logger,
            logging.ERROR,
            "retrieval_failed",
            "Semantic retrieval response was invalid",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            candidate_count=candidate_count,
            error_type=type(exc).__name__,
        )
        raise RetrievalResponseError(
            f"Invalid embedding response: {exc}"
        ) from exc

    # Validate question embedding
    if not question_embedding:
        raise RetrievalResponseError("Question embedding is empty")

    # Calculate similarity scores
    scored_chunks = []
    for chunk in embedded_chunks:
        try:
            score = _cosine_similarity(question_embedding, chunk.embedding)
            scored_chunks.append((chunk, score))
        except RetrievalResponseError as exc:
            log_event(
                logger,
                logging.WARNING,
                "retrieval_chunk_skipped",
                "Chunk embedding could not be scored",
                chunk_id=chunk.id,
                error_type=type(exc).__name__,
            )
            # Skip malformed embeddings

    # Apply minimum score threshold
    filtered_chunks = [
        (chunk, score)
        for chunk, score in scored_chunks
        if score >= min_score
    ]

    # Sort by descending similarity, then by chunk_index for determinism
    sorted_chunks = sorted(
        filtered_chunks,
        key=lambda x: (-x[1], x[0].chunk_index),  # score desc, index asc
    )

    # Apply top-k limit
    topk_chunks = sorted_chunks[:top_k]

    # Build result with ranks
    retrieved = [
        RetrievedChunk(
            chunk=chunk,
            similarity_score=score,
            rank=i + 1,
        )
        for i, (chunk, score) in enumerate(topk_chunks)
    ]

    result = RetrievalResult(
        chunks=retrieved,
        candidate_count=candidate_count,
        retrieved_count=len(filtered_chunks),
        top_k=top_k,
        min_score=min_score,
    )
    log_event(
        logger,
        logging.INFO,
        "retrieval_completed",
        "Semantic retrieval completed",
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
        candidate_count=candidate_count,
        retrieved_count=len(retrieved),
        qualifying_count=len(filtered_chunks),
        top_k=top_k,
        min_score=min_score,
    )
    return result
