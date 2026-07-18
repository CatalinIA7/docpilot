"""
AI service for document Q&A.

Responsibilities
----------------
* Build the prompt (system + user message) so the model answers only
  from the supplied document text.
* Call the OpenAI Chat Completions API.
* Surface configuration and provider errors as typed exceptions that the
  route layer can convert to appropriate HTTP responses.

Nothing in this module is route-specific — it can be called from any
part of the application or swapped for a different provider later.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Max characters of document text we pass to the model in this MVP.
# GPT-4o-mini context window is ~128k tokens (~500k chars); we stay well
# under that while keeping the limit sensible for typical documents.
_TEXT_CHAR_LIMIT = 120_000

_DEFAULT_MODEL = "gpt-4o-mini"


def _get_model() -> str:
    return os.environ.get("DOCPILOT_AI_MODEL", _DEFAULT_MODEL)


def _get_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise AIConfigError("OpenAI API key is not configured.")
    return key


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class AIConfigError(RuntimeError):
    """Raised when required AI configuration (e.g. API key) is missing."""


class AIProviderError(RuntimeError):
    """Raised when the upstream AI provider returns an error."""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def answer_question(*, document_text: str, question: str) -> str:
    """
    Ask `question` about `document_text` using the configured AI model.

    Returns the model's answer as a plain string.

    Raises
    ------
    AIConfigError  – API key or model not configured.
    AIProviderError – OpenAI returned an error.
    """
    api_key = _get_api_key()  # raises AIConfigError if missing

    # Truncate document text silently if it exceeds the character limit.
    # We log a warning so it's visible in server logs without exposing content.
    text = document_text
    if len(text) > _TEXT_CHAR_LIMIT:
        logger.warning(
            "Document text truncated from %d to %d chars for AI request.",
            len(text),
            _TEXT_CHAR_LIMIT,
        )
        text = text[:_TEXT_CHAR_LIMIT]

    system_prompt = (
        "You are a helpful assistant that answers questions strictly based on "
        "the document text provided by the user. "
        "Do not use any external knowledge. "
        "If the document does not contain enough information to answer the "
        "question, say exactly: \"I cannot find the answer in this document.\""
    )

    user_message = (
        f"Document text:\n\"\"\"\n{text}\n\"\"\"\n\n"
        f"Question: {question}"
    )

    try:
        from openai import OpenAI, OpenAIError

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1024,
            temperature=0,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        # Log without the key or full document text.
        logger.error("OpenAI API call failed: %s", type(exc).__name__)
        raise AIProviderError("The AI provider returned an error. Please try again later.") from exc
