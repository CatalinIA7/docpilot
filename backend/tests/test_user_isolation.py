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


def test_users_only_see_their_own_documents():
    user_one = client.post("/auth/register", json={"email": "one@example.com", "password": "StrongPass123!"})
    user_two = client.post("/auth/register", json={"email": "two@example.com", "password": "StrongPass123!"})
    assert user_one.status_code == 201
    assert user_two.status_code == 201

    token_one = client.post("/auth/login", json={"email": "one@example.com", "password": "StrongPass123!"}).json()["access_token"]
    token_two = client.post("/auth/login", json={"email": "two@example.com", "password": "StrongPass123!"}).json()["access_token"]

    client.post(
        "/documents",
        headers={"Authorization": f"Bearer {token_one}"},
        files={"file": ("one.docx", _create_docx_bytes("Alpha team plan"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    client.post(
        "/documents",
        headers={"Authorization": f"Bearer {token_two}"},
        files={"file": ("two.docx", _create_docx_bytes("Beta launch details"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    response_one = client.post(
        "/search",
        headers={"Authorization": f"Bearer {token_one}"},
        json={"query": "launch"},
    )
    response_two = client.post(
        "/search",
        headers={"Authorization": f"Bearer {token_two}"},
        json={"query": "plan"},
    )

    assert response_one.status_code == 200
    assert response_two.status_code == 200
    assert all(item["filename"] != "two.docx" for item in response_one.json()["results"])
    assert all(item["filename"] != "one.docx" for item in response_two.json()["results"])
