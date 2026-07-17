import sys
from io import BytesIO
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base, engine
from main import app

client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _create_docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_documents_persist_across_requests_for_same_user():
    register = client.post("/auth/register", json={"email": "persist@example.com", "password": "StrongPass123!"})
    assert register.status_code == 201

    login = client.post("/auth/login", json={"email": "persist@example.com", "password": "StrongPass123!"})
    token = login.json()["access_token"]

    upload_response = client.post(
        "/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("persist.docx", _create_docx_bytes("Quarterly planning update"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert upload_response.status_code == 201

    search_response = client.post(
        "/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "planning"},
    )

    assert search_response.status_code == 200
    assert search_response.json()["results"]
