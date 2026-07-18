"""
Embedding service for generating vector embeddings for document chunks.

Responsibilities
----------------
* Generate batch embeddings for document chunk text using OpenAI API.
* Validate provider responses for completeness and correctness.
* Handle input validation (reject empty/whitespace text).
* Surface configuration and provider errors as typed exceptions.
* Maintain deterministic mapping between input text and returned embeddings.
* Support observability measurement without persisting metrics.

Nothing in this module is route-specific or database-aware — it is a pure
service that can be called from any part of the application.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_DEFAULT_BATCH_SIZE = 100


def _get_embedding_model() -> str:
    """Get the configured embedding model name."""
    return os.environ.get("DOCPILOT_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL)


def _get_batch_size() -> int:
    """Get the configured batch size for embedding requests."""
    try:
        size = int(os.environ.get("DOCPILOT_EMBEDDING_BATCH_SIZE", _DEFAULT_BATCH_SIZE))
        if size <= 0:
            raise ValueError("Batch size must be greater than zero")
        return size
    except (ValueError, TypeError) as exc:
        raise EmbeddingConfigurationError(
            f"Invalid DOCPILOT_EMBEDDING_BATCH_SIZE: {exc}"
        ) from exc


def _get_api_key() -> str:
    """Get the OpenAI API key from environment."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise EmbeddingConfigurationError("OpenAI API key is not configured.")
    return key


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class EmbeddingConfigurationError(RuntimeError):
    """Raised when required embedding configuration is missing or invalid."""


class EmbeddingProviderError(RuntimeError):
    """Raised when the upstream embedding provider returns an error."""


class EmbeddingResponseError(RuntimeError):
    """Raised when the provider response is malformed or incomplete."""


# ---------------------------------------------------------------------------
# Observability types (no persistence)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddingBatchResult:
    """Result of batch embedding generation (observability-ready)."""

    embeddings: list[list[float]]
    model: str
    vector_dimension: int
    batch_count: int
    chunks_processed: int


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def _validate_and_normalize_texts(texts: list[str]) -> tuple[list[str], list[int]]:
    """
    Validate texts and return normalized list with indices of non-empty texts.

    Empty and whitespace-only texts are filtered out. Returns normalized list
    and a list of indices corresponding to the original texts list.

    Parameters
    ----------
    texts : list[str]
        Input texts to validate.

    Returns
    -------
    normalized_texts : list[str]
        Non-empty, non-whitespace texts.
    original_indices : list[int]
        Indices in the original texts list for each normalized text.

    Raises
    ------
    EmbeddingResponseError
        If all texts are empty/whitespace.
    """
    normalized = []
    indices = []

    for i, text in enumerate(texts):
        if text and text.strip():
            normalized.append(text.strip())
            indices.append(i)

    if not normalized:
        raise EmbeddingResponseError(
            f"All {len(texts)} input texts are empty or whitespace-only."
        )

    return normalized, indices


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts using OpenAI API.

    Uses batch processing with configurable batch size. Preserves order of
    input texts in the returned embeddings.

    Parameters
    ----------
    texts : list[str]
        List of texts to embed. Empty and whitespace-only texts will raise
        an error.

    Returns
    -------
    list[list[float]]
        List of embeddings, one per input text, in the same order as the
        input list.

    Raises
    ------
    EmbeddingConfigurationError
        If API key or batch size is not configured or invalid.
    EmbeddingProviderError
        If the OpenAI API call fails.
    EmbeddingResponseError
        If the provider response is malformed, incomplete, or all inputs
        are empty/whitespace.
    """
    if not texts:
        raise EmbeddingResponseError("No texts provided for embedding.")

    # Validate inputs
    normalized_texts, original_indices = _validate_and_normalize_texts(texts)

    # Get configuration
    api_key = _get_api_key()  # raises EmbeddingConfigurationError if missing
    model = _get_embedding_model()
    batch_size = _get_batch_size()

    # Call OpenAI API with batch processing
    all_embeddings = []
    batch_count = 0

    try:
        from openai import OpenAI, APIError, RateLimitError, AuthenticationError

        client = OpenAI(api_key=api_key)

        # Process in batches
        for batch_start in range(0, len(normalized_texts), batch_size):
            batch_end = min(batch_start + batch_size, len(normalized_texts))
            batch_texts = normalized_texts[batch_start:batch_end]

            logger.debug(
                "Requesting embeddings for batch %d (%d texts)",
                batch_count + 1,
                len(batch_texts),
            )

            response = client.embeddings.create(
                model=model,
                input=batch_texts,
            )

            # Validate response completeness
            if not response.data:
                raise EmbeddingResponseError(
                    f"OpenAI returned empty embeddings for {len(batch_texts)} texts."
                )

            if len(response.data) != len(batch_texts):
                raise EmbeddingResponseError(
                    f"Expected {len(batch_texts)} embeddings but received "
                    f"{len(response.data)}. Mismatch indicates incomplete response."
                )

            # Extract embeddings
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            batch_count += 1

        # Validate vector dimension (all embeddings should have same dimension)
        if all_embeddings:
            first_dim = len(all_embeddings[0])
            if not all(len(e) == first_dim for e in all_embeddings):
                raise EmbeddingResponseError(
                    "Inconsistent vector dimensions in provider response."
                )

        logger.info(
            "Successfully generated embeddings for %d texts in %d batch(es)",
            len(normalized_texts),
            batch_count,
        )

        return all_embeddings

    except (RateLimitError, AuthenticationError) as exc:
        logger.error("OpenAI API authentication or rate-limit error: %s", type(exc).__name__)
        raise EmbeddingProviderError(
            "The embedding service is temporarily unavailable. Please try again later."
        ) from exc
    except APIError as exc:
        logger.error("OpenAI API error: %s", type(exc).__name__)
        raise EmbeddingProviderError(
            "The embedding service returned an error. Please try again later."
        ) from exc
    except EmbeddingResponseError:
        # Re-raise our own validation errors
        raise
    except Exception as exc:
        logger.error("Unexpected error during embedding: %s", type(exc).__name__)
        raise EmbeddingProviderError(
            "An unexpected error occurred while generating embeddings."
        ) from exc


def embed_texts_with_observability(
    texts: list[str],
) -> tuple[list[list[float]], EmbeddingBatchResult]:
    """
    Generate embeddings with observability metrics.

    Returns both the embeddings and a result object containing metrics for
    observability measurement.

    Parameters
    ----------
    texts : list[str]
        List of texts to embed.

    Returns
    -------
    embeddings : list[list[float]]
        The generated embeddings.
    result : EmbeddingBatchResult
        Observability metrics including model name, vector dimension,
        and batch count.

    Raises
    ------
    EmbeddingConfigurationError, EmbeddingProviderError, EmbeddingResponseError
        Same as embed_texts().
    """
    embeddings = embed_texts(texts)

    vector_dim = len(embeddings[0]) if embeddings else 0
    batch_size = _get_batch_size()
    batch_count = (len(texts) + batch_size - 1) // batch_size

    result = EmbeddingBatchResult(
        embeddings=embeddings,
        model=_get_embedding_model(),
        vector_dimension=vector_dim,
        batch_count=batch_count,
        chunks_processed=len(texts),
    )

    return embeddings, result
