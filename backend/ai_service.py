"""
AI service for document Q&A.

Responsibilities
----------------
* Build the prompt (system + user message) so the model answers only
  from the supplied document sections.
* Request citation source IDs from the model.
* Parse and validate citations.
* Call the OpenAI Chat Completions API.
* Surface configuration and provider errors as typed exceptions that the
  route layer can convert to appropriate HTTP responses.

Nothing in this module is route-specific — it can be called from any
part of the application or swapped for a different provider later.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from document_parser import SourceSection

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


@dataclass(frozen=True)
class Citation:
    """A citation pointing to a source section in the document."""

    source_id: int
    page: int | None = None
    paragraph: int | None = None
    excerpt: str = ""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def _build_prompt_with_sections(
    sections: list[SourceSection], question: str
) -> str:
    """Build a user prompt with numbered source sections.

    Format: [SOURCE 1 | Page X] or [SOURCE N | Para Y].
    """
    prompt_lines = []
    for section in sections:
        if section.page is not None:
            header = f"[SOURCE {section.source_id} | Page {section.page}]"
        elif section.paragraph is not None:
            header = f"[SOURCE {section.source_id} | Paragraph {section.paragraph}]"
        else:
            header = f"[SOURCE {section.source_id}]"
        prompt_lines.append(header)
        prompt_lines.append(section.text)
        prompt_lines.append("")  # Blank line between sections

    prompt_lines.append(f"Question: {question}")
    prompt_lines.append(
        "\nRespond in this format:\nAnswer: <your answer>\nCitations: <source IDs separated by commas, or 'none'>"
    )
    return "\n".join(prompt_lines)


def _parse_response(
    response_text: str, sections: list[SourceSection]
) -> tuple[str, list[Citation]]:
    """Parse model response into (answer, citations).

    Expected format:
    Answer: <answer text>
    Citations: <comma-separated source IDs or 'none'>
    """
    lines = response_text.strip().split("\n")
    answer = ""
    citations_str = ""

    for i, line in enumerate(lines):
        if line.startswith("Answer:"):
            answer = line.replace("Answer:", "", 1).strip()
        elif line.startswith("Citations:"):
            citations_str = line.replace("Citations:", "", 1).strip()

    # Parse and validate citation IDs
    citations = []
    if citations_str and citations_str.lower() != "none":
        try:
            citation_ids = [
                int(sid.strip()) for sid in citations_str.split(",")
            ]
            # Build citation objects, validating source IDs
            seen_ids = set()
            for cid in citation_ids:
                if cid in seen_ids:
                    continue  # Skip duplicates
                seen_ids.add(cid)

                # Find matching section
                section = next(
                    (s for s in sections if s.source_id == cid), None
                )
                if section:
                    citations.append(
                        Citation(
                            source_id=cid,
                            page=section.page,
                            paragraph=section.paragraph,
                            excerpt=section.excerpt(),
                        )
                    )
        except (ValueError, AttributeError):
            logger.warning(
                "Failed to parse citations from model response: %s",
                citations_str,
            )

    return answer, citations


def answer_question(
    *, sections: list[SourceSection], question: str
) -> tuple[str, list[Citation]]:
    """
    Ask `question` about document `sections` using the configured AI model.

    Returns (answer, citations) where citations are validated source references.

    Raises
    ------
    AIConfigError  – API key or model not configured.
    AIProviderError – OpenAI returned an error.
    """
    api_key = _get_api_key()  # raises AIConfigError if missing

    # Truncate sections silently if combined text exceeds the character limit.
    truncated_sections = sections
    combined_len = sum(len(s.text) for s in sections)
    if combined_len > _TEXT_CHAR_LIMIT:
        logger.warning(
            "Document sections truncated from %d to %d chars for AI request.",
            combined_len,
            _TEXT_CHAR_LIMIT,
        )
        # Truncate sections to fit the limit
        truncated_sections = []
        char_count = 0
        for section in sections:
            if char_count + len(section.text) > _TEXT_CHAR_LIMIT:
                break
            truncated_sections.append(section)
            char_count += len(section.text)

    system_prompt = (
        "You are a helpful assistant that answers questions strictly based on "
        "the numbered document sources provided. "
        "Answer only from the source content. "
        "If the document does not contain information to answer the question, "
        "respond with: 'I cannot find the answer in this document.' "
        "Always include source IDs supporting your answer."
    )

    user_message = _build_prompt_with_sections(truncated_sections, question)

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
        response_text = response.choices[0].message.content or ""
        answer, citations = _parse_response(response_text, truncated_sections)
        return answer, citations
    except Exception as exc:
        # Log without the key or full document text.
        logger.error("OpenAI API call failed: %s", type(exc).__name__)
        raise AIProviderError(
            "The AI provider returned an error. Please try again later."
        ) from exc
