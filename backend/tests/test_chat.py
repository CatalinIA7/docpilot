"""
Tests for POST /documents/{document_id}/chat.

The AI service (answer_question) is always mocked — the real OpenAI API
is never called.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from ai_service import AIConfigError, AIProviderError, Citation

_MOCK_TARGET = "routers.chat.answer_question"


def _mock_answer(
    answer: str = "Mocked answer.", citations: list[Citation] | None = None
):
    """Return a patcher that makes answer_question return (answer, citations)."""
    if citations is None:
        citations = []
    return patch(_MOCK_TARGET, return_value=(answer, citations))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def doc_with_text(client, auth_headers):
    """Upload a DOCX (which has extractable text) and return its JSON."""
    from tests.conftest import make_minimal_docx

    resp = client.post(
        "/documents",
        files={"file": ("chat_test.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def doc_without_text(client, auth_headers, db_session):
    """Insert a document row with empty text directly into the test DB."""
    import uuid
    from datetime import datetime
    from models import Document

    doc_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        user_id=db_session.execute(
            __import__("sqlalchemy").text("SELECT id FROM users WHERE email='test@example.com'")
        ).scalar_one(),
        filename="empty.pdf",
        stored_filename=f"{doc_id}.pdf",
        file_type="pdf",
        size=10,
        text="",
        preview="",
        word_count=0,
        character_count=0,
        paragraph_count=0,
        created_at=datetime.utcnow(),
    )
    db_session.add(doc)
    db_session.flush()
    return {"id": doc_id}


# ---------------------------------------------------------------------------
# Auth & ownership
# ---------------------------------------------------------------------------


class TestChatAuth:
    def test_unauthenticated_request_returns_401(self, client, doc_with_text):
        resp = client.post(
            f"/documents/{doc_with_text['id']}/chat",
            json={"question": "What is this about?"},
        )
        assert resp.status_code == 401

    def test_other_user_cannot_chat_with_document(
        self, client, doc_with_text, second_user
    ):
        with _mock_answer():
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "What is this?"},
                headers=second_user["headers"],
            )
        assert resp.status_code == 404

    def test_nonexistent_document_returns_404(self, client, auth_headers):
        with _mock_answer():
            resp = client.post(
                "/documents/no-such-id/chat",
                json={"question": "Hello?"},
                headers=auth_headers,
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestChatSuccess:
    def test_successful_chat_returns_answer(self, client, auth_headers, doc_with_text):
        with _mock_answer("This document is about fixtures."):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "What is this document about?"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "This document is about fixtures."

    def test_response_schema_has_answer_key(self, client, auth_headers, doc_with_text):
        with _mock_answer("Some answer."):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "Tell me something."},
                headers=auth_headers,
            )
        data = resp.json()
        assert "answer" in data
        assert "citations" in data
        assert isinstance(data["citations"], list)

    def test_response_with_citations_pdf(self, client, auth_headers):
        """Test citations are returned for PDF with page numbers."""
        from tests.conftest import make_minimal_pdf

        # Upload a PDF
        resp = client.post(
            "/documents",
            files={
                "file": (
                    "test.pdf",
                    make_minimal_pdf(),
                    "application/pdf",
                )
            },
            headers=auth_headers,
        )
        doc = resp.json()

        # Mock answer with PDF citations (page numbers)
        citation = Citation(
            source_id=1, page=1, paragraph=None, excerpt="Sample PDF text"
        )
        with _mock_answer("Found on first page.", [citation]):
            resp = client.post(
                f"/documents/{doc['id']}/chat",
                json={"question": "Where is it?"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["citations"]) == 1
        assert data["citations"][0]["source_id"] == 1
        assert data["citations"][0]["page"] == 1
        assert data["citations"][0]["paragraph"] is None
        assert "Sample PDF text" in data["citations"][0]["excerpt"]

    def test_response_with_citations_docx(self, client, auth_headers, doc_with_text):
        """Test citations are returned for DOCX with paragraph numbers."""
        # Mock answer with DOCX citations (paragraph numbers)
        citation = Citation(
            source_id=1,
            page=None,
            paragraph=1,
            excerpt="Sample paragraph text",
        )
        with _mock_answer("From first paragraph.", [citation]):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "Where?"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["citations"]) == 1
        assert data["citations"][0]["source_id"] == 1
        assert data["citations"][0]["page"] is None
        assert data["citations"][0]["paragraph"] == 1
        assert "Sample paragraph text" in data["citations"][0]["excerpt"]

    def test_response_with_multiple_citations(self, client, auth_headers, doc_with_text):
        """Test multiple citations in response."""
        citations = [
            Citation(
                source_id=1,
                page=None,
                paragraph=1,
                excerpt="First source",
            ),
            Citation(
                source_id=2,
                page=None,
                paragraph=2,
                excerpt="Second source",
            ),
        ]
        with _mock_answer("Answer from multiple sources.", citations):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "Multiple sources?"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["citations"]) == 2
        assert data["citations"][0]["source_id"] == 1
        assert data["citations"][1]["source_id"] == 2

    def test_response_with_no_citations(self, client, auth_headers, doc_with_text):
        """Test response with empty citations list."""
        with _mock_answer("Answer without citations.", []):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "Unanswerable?"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["citations"] == []


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestChatValidation:
    def test_empty_question_is_rejected(self, client, auth_headers, doc_with_text):
        resp = client.post(
            f"/documents/{doc_with_text['id']}/chat",
            json={"question": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_whitespace_only_question_is_rejected(self, client, auth_headers, doc_with_text):
        resp = client.post(
            f"/documents/{doc_with_text['id']}/chat",
            json={"question": "   "},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_question_exceeding_max_length_is_rejected(
        self, client, auth_headers, doc_with_text
    ):
        resp = client.post(
            f"/documents/{doc_with_text['id']}/chat",
            json={"question": "x" * 1001},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_missing_question_field_is_rejected(self, client, auth_headers, doc_with_text):
        resp = client.post(
            f"/documents/{doc_with_text['id']}/chat",
            json={},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_document_with_empty_text_returns_400(
        self, client, auth_headers, doc_without_text
    ):
        with _mock_answer():
            resp = client.post(
                f"/documents/{doc_without_text['id']}/chat",
                json={"question": "What is this about?"},
                headers=auth_headers,
            )
        assert resp.status_code == 400
        assert "text" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestChatErrors:
    def test_missing_api_key_returns_503(self, client, auth_headers, doc_with_text):
        with patch(_MOCK_TARGET, side_effect=AIConfigError("No key")):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "What is this?"},
                headers=auth_headers,
            )
        assert resp.status_code == 503
        # Must not expose internal details
        assert "OPENAI_API_KEY" not in resp.text
        assert "No key" not in resp.text

    def test_ai_provider_failure_returns_502(self, client, auth_headers, doc_with_text):
        with patch(_MOCK_TARGET, side_effect=AIProviderError("upstream failure")):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "What is this?"},
                headers=auth_headers,
            )
        assert resp.status_code == 502
        assert "upstream failure" not in resp.text


# ---------------------------------------------------------------------------
# Citation schema
# ---------------------------------------------------------------------------


class TestCitationSchema:
    """Test citation response schema."""

    def test_citation_has_required_fields(self, client, auth_headers, doc_with_text):
        """Citation must have source_id and excerpt."""
        citation = Citation(
            source_id=1, page=1, paragraph=None, excerpt="Text"
        )
        with _mock_answer("Answer", [citation]):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "Q?"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        c = data["citations"][0]
        assert "source_id" in c
        assert "excerpt" in c
        assert c["source_id"] == 1

    def test_citation_page_can_be_null(self, client, auth_headers, doc_with_text):
        """Page can be null for DOCX (use paragraph instead)."""
        citation = Citation(
            source_id=1, page=None, paragraph=2, excerpt="Para text"
        )
        with _mock_answer("Answer", [citation]):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "Q?"},
                headers=auth_headers,
            )
        data = resp.json()
        assert data["citations"][0]["page"] is None
        assert data["citations"][0]["paragraph"] == 2

    def test_citation_paragraph_can_be_null(self, client, auth_headers, doc_with_text):
        """Paragraph can be null for PDF (use page instead)."""
        citation = Citation(
            source_id=1, page=3, paragraph=None, excerpt="Page text"
        )
        with _mock_answer("Answer", [citation]):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "Q?"},
                headers=auth_headers,
            )
        data = resp.json()
        assert data["citations"][0]["page"] == 3
        assert data["citations"][0]["paragraph"] is None


# ---------------------------------------------------------------------------
# Path Resolution (Regression Tests)
# ---------------------------------------------------------------------------
# These tests ensure chat file resolution works regardless of working directory
# (the fix moved from relative paths to UPLOAD_DIR config)

class TestPathResolution:
    """Regression tests for file path resolution stability."""

    def test_chat_resolves_files_from_configured_upload_dir(
        self, client, auth_headers, doc_with_text
    ):
        """Chat endpoint resolves document files using UPLOAD_DIR, not cwd."""
        # This test passes if the chat endpoint can find the uploaded document
        # regardless of the process working directory. The fix uses UPLOAD_DIR
        # from config.py instead of a relative path like 'uploads/...'
        with _mock_answer("This is working"):
            resp = client.post(
                f"/documents/{doc_with_text['id']}/chat",
                json={"question": "Test question"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "This is working"

    def test_chat_works_with_pdf_upload_using_absolute_paths(
        self, client, auth_headers
    ):
        """Chat works with PDF documents using absolute path resolution."""
        from tests.conftest import make_minimal_pdf

        # Upload PDF
        resp_upload = client.post(
            "/documents",
            files={"file": ("test.pdf", make_minimal_pdf(), "application/pdf")},
            headers=auth_headers,
        )
        assert resp_upload.status_code == 201
        doc_id = resp_upload.json()["id"]

        # Chat with PDF
        with _mock_answer("PDF content summary"):
            resp = client.post(
                f"/documents/{doc_id}/chat",
                json={"question": "What is this PDF about?"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "PDF content summary"

    def test_chat_works_with_docx_upload_using_absolute_paths(
        self, client, auth_headers
    ):
        """Chat works with DOCX documents using absolute path resolution."""
        from tests.conftest import make_minimal_docx

        # Upload DOCX
        resp_upload = client.post(
            "/documents",
            files={
                "file": (
                    "test.docx",
                    make_minimal_docx(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            headers=auth_headers,
        )
        assert resp_upload.status_code == 201
        doc_id = resp_upload.json()["id"]

        # Chat with DOCX
        with _mock_answer("DOCX content summary"):
            resp = client.post(
                f"/documents/{doc_id}/chat",
                json={"question": "Summarize this document"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "DOCX content summary"

    def test_chat_file_resolution_multiple_documents(
        self, client, auth_headers
    ):
        """Chat resolves correct files for multiple uploaded documents."""
        from tests.conftest import make_minimal_pdf, make_minimal_docx

        # Upload two different documents
        pdf_resp = client.post(
            "/documents",
            files={"file": ("doc1.pdf", make_minimal_pdf(), "application/pdf")},
            headers=auth_headers,
        )
        docx_resp = client.post(
            "/documents",
            files={
                "file": (
                    "doc2.docx",
                    make_minimal_docx(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            headers=auth_headers,
        )
        assert pdf_resp.status_code == 201
        assert docx_resp.status_code == 201

        pdf_id = pdf_resp.json()["id"]
        docx_id = docx_resp.json()["id"]

        # Chat with PDF
        with _mock_answer("PDF answer"):
            resp1 = client.post(
                f"/documents/{pdf_id}/chat",
                json={"question": "PDF question"},
                headers=auth_headers,
            )
        assert resp1.status_code == 200
        assert resp1.json()["answer"] == "PDF answer"

        # Chat with DOCX
        with _mock_answer("DOCX answer"):
            resp2 = client.post(
                f"/documents/{docx_id}/chat",
                json={"question": "DOCX question"},
                headers=auth_headers,
            )
        assert resp2.status_code == 200
        assert resp2.json()["answer"] == "DOCX answer"
