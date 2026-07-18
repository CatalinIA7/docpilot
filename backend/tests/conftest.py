"""
Pytest fixtures shared across all DocPilot backend tests.

Key design decisions
---------------------
* A fresh in-memory SQLite database is created for every test session.
* The FastAPI ``get_db`` dependency is overridden so tests never touch the
  development database.
* Minimal valid PDF / DOCX byte blobs are generated in-process so the upload
  tests require no fixture files on disk.
"""

import io
import struct
import zlib
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Bootstrap: ensure the backend package is importable even when pytest is
# invoked from the project root.
# ---------------------------------------------------------------------------
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, get_db  # noqa: E402  (import after path fix)
from main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal in-process file blobs
# ---------------------------------------------------------------------------

def make_minimal_pdf() -> bytes:
    """Return a structurally valid single-page PDF with the word 'hello'."""
    content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>
stream
BT /F1 12 Tf 100 700 Td (hello world) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f\r
0000000009 00000 n\r
0000000058 00000 n\r
0000000115 00000 n\r
0000000266 00000 n\r
0000000360 00000 n\r
trailer<</Size 6/Root 1 0 R>>
startxref
441
%%EOF"""
    return content


def make_minimal_docx() -> bytes:
    """
    Return a minimal valid .docx (ZIP) with the words 'fixture document'.
    A .docx is a ZIP archive containing word/document.xml.
    """
    word_document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"'
        ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:p><w:r><w:t>fixture document</w:t></w:r></w:p>"
        "</w:body>"
        "</w:document>"
    ).encode()

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml"'
        ' ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    ).encode()

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/>'
        "</Relationships>"
    ).encode()

    buf = io.BytesIO()
    import zipfile

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("word/document.xml", word_document_xml)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def engine():
    """Single in-memory SQLite engine shared for the whole test session."""
    _engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=_engine)
    yield _engine
    _engine.dispose()


@pytest.fixture()
def db_session(engine):
    """
    Per-test transactional session that rolls back after each test so every
    test starts with a clean slate without recreating the schema.
    """
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = TestingSessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# TestClient fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with the get_db dependency overridden."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User / auth fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registered_user(client):
    """Register a user and return (email, password, response_json)."""
    email = "test@example.com"
    password = "password123"
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return {"email": email, "password": password, "data": resp.json()}


@pytest.fixture()
def auth_headers(registered_user):
    """Authorization headers for the registered test user."""
    token = registered_user["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def second_user(client):
    """A second registered user used for cross-user isolation tests."""
    email = "other@example.com"
    password = "password123"
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"email": email, "password": password, "headers": {"Authorization": f"Bearer {token}"}}


# ---------------------------------------------------------------------------
# Embedding service mock
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_embed_texts(monkeypatch):
    """Mock embed_texts to return deterministic mock embeddings for all tests."""
    def mock_embeddings(texts):
        """Return mock embeddings that match the number of input texts."""
        if not texts:
            return []
        # Return a simple list of embeddings for testing
        # In real use, this would be 384-dimensional vectors from text-embedding-3-small
        return [[float(i) * 0.01 for _ in range(10)] for i in range(len(texts))]
    
    # Patch where embed_texts is imported and used in multiple places
    import routers.documents
    import retrieval_service
    monkeypatch.setattr(routers.documents, "embed_texts", mock_embeddings)
    monkeypatch.setattr(retrieval_service, "embed_texts", mock_embeddings)


# ---------------------------------------------------------------------------
# Uploaded-document fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def uploaded_doc(client, auth_headers):
    """Upload a minimal DOCX and return the document response JSON."""
    docx_bytes = make_minimal_docx()
    resp = client.post(
        "/documents",
        files={"file": ("test.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
