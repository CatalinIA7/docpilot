import sys
from pathlib import Path
from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base, engine
from main import app

client = TestClient(app)


def _create_docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_document_upload_requires_authentication():
    response = client.post(
        "/documents",
        files={"file": ("sample.docx", b"fake", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 401


def test_authenticated_user_can_upload_document():
    register_response = client.post(
        "/auth/register",
        json={"email": "owner@example.com", "password": "StrongPass123!"},
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "StrongPass123!"},
    )
    token = login_response.json()["access_token"]

    response = client.post(
        "/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("sample.docx", _create_docx_bytes("Hello from DocPilot"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 201
