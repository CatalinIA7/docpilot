import sys
from io import BytesIO
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app, DOCUMENT_STORE


client = TestClient(app)


def _get_auth_headers() -> dict[str, str]:
    email = "search-chat@example.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    login_response = client.post("/auth/login", json={"email": email, "password": password})
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def setup_function():
    DOCUMENT_STORE.clear()


def test_search_returns_relevant_results():
    payload = _create_docx_bytes("The launch date is planned for September 2026.")
    upload_response = client.post(
        "/documents",
        files={"file": ("plan.docx", payload, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=_get_auth_headers(),
    )

    assert upload_response.status_code == 201

    response = client.post("/search", json={"query": "launch date"}, headers=_get_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["results"]
    assert any("September 2026" in item["snippet"] for item in body["results"])


def test_chat_returns_answer_based_on_document_content():
    payload = _create_docx_bytes("The launch date is planned for September 2026.")
    upload_response = client.post(
        "/documents",
        files={"file": ("plan.docx", payload, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=_get_auth_headers(),
    )

    assert upload_response.status_code == 201

    response = client.post("/chat", json={"question": "When is the launch date?"}, headers=_get_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert "September 2026" in body["answer"]
    assert body["citations"]
