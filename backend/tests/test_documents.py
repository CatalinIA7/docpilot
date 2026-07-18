"""
Document endpoint tests — upload, list, detail, search, delete, isolation.
"""
from .conftest import make_minimal_docx, make_minimal_pdf


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class TestUpload:
    def test_upload_valid_docx(self, client, auth_headers):
        resp = client.post(
            "/documents",
            files={"file": ("report.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["filename"] == "report.docx"
        assert body["file_type"] == "docx"
        assert "id" in body

    def test_upload_valid_pdf(self, client, auth_headers):
        resp = client.post(
            "/documents",
            files={"file": ("paper.pdf", make_minimal_pdf(), "application/pdf")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["filename"] == "paper.pdf"
        assert body["file_type"] == "pdf"

    def test_upload_unsupported_type_returns_400(self, client, auth_headers):
        resp = client.post(
            "/documents",
            files={"file": ("notes.txt", b"hello", "text/plain")},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_upload_empty_file_returns_400(self, client, auth_headers):
        resp = client.post(
            "/documents",
            files={"file": ("empty.pdf", b"", "application/pdf")},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_upload_requires_auth(self, client):
        resp = client.post(
            "/documents",
            files={"file": ("x.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class TestListDocuments:
    def test_empty_list_for_new_user(self, client, auth_headers):
        resp = client.get("/documents", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_uploaded_document_appears_in_list(self, client, auth_headers, uploaded_doc):
        resp = client.get("/documents", headers=auth_headers)
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()]
        assert uploaded_doc["id"] in ids

    def test_list_does_not_include_text_field(self, client, auth_headers, uploaded_doc):
        resp = client.get("/documents", headers=auth_headers)
        assert resp.status_code == 200
        for doc in resp.json():
            assert "text" not in doc, "list response must not include full text"

    def test_list_returns_only_own_documents(self, client, auth_headers, uploaded_doc, second_user):
        resp = client.get("/documents", headers=second_user["headers"])
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()]
        assert uploaded_doc["id"] not in ids


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

class TestDocumentDetail:
    def test_get_detail_returns_text(self, client, auth_headers, uploaded_doc):
        resp = client.get(f"/documents/{uploaded_doc['id']}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == uploaded_doc["id"]
        assert "text" in body  # DocumentDetailResponse includes full text

    def test_get_detail_returns_correct_filename(self, client, auth_headers, uploaded_doc):
        resp = client.get(f"/documents/{uploaded_doc['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["filename"] == uploaded_doc["filename"]

    def test_get_nonexistent_document_returns_404(self, client, auth_headers):
        resp = client.get("/documents/does-not-exist", headers=auth_headers)
        assert resp.status_code == 404

    def test_user_cannot_access_other_users_document(self, client, auth_headers, uploaded_doc, second_user):
        resp = client.get(f"/documents/{uploaded_doc['id']}", headers=second_user["headers"])
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_by_filename(self, client, auth_headers, uploaded_doc):
        # uploaded_doc fixture uploads "test.docx"
        resp = client.get("/documents/search?q=test", headers=auth_headers)
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()]
        assert uploaded_doc["id"] in ids

    def test_search_by_extracted_text(self, client, auth_headers, uploaded_doc):
        # The minimal DOCX fixture contains "fixture document"
        resp = client.get("/documents/search?q=fixture", headers=auth_headers)
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()]
        assert uploaded_doc["id"] in ids

    def test_search_no_match_returns_empty_list(self, client, auth_headers, uploaded_doc):
        resp = client.get("/documents/search?q=zzznomatch", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_empty_query_returns_400(self, client, auth_headers):
        resp = client.get("/documents/search?q=", headers=auth_headers)
        assert resp.status_code == 400

    def test_search_missing_q_returns_400(self, client, auth_headers):
        resp = client.get("/documents/search", headers=auth_headers)
        assert resp.status_code == 400

    def test_search_returns_only_own_documents(self, client, auth_headers, uploaded_doc, second_user):
        resp = client.get("/documents/search?q=fixture", headers=second_user["headers"])
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()]
        assert uploaded_doc["id"] not in ids


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_own_document_returns_204(self, client, auth_headers, uploaded_doc):
        resp = client.delete(f"/documents/{uploaded_doc['id']}", headers=auth_headers)
        assert resp.status_code == 204

    def test_deleted_document_no_longer_appears_in_list(self, client, auth_headers, uploaded_doc):
        client.delete(f"/documents/{uploaded_doc['id']}", headers=auth_headers)
        resp = client.get("/documents", headers=auth_headers)
        ids = [d["id"] for d in resp.json()]
        assert uploaded_doc["id"] not in ids

    def test_deleted_document_returns_404_on_detail(self, client, auth_headers, uploaded_doc):
        client.delete(f"/documents/{uploaded_doc['id']}", headers=auth_headers)
        resp = client.get(f"/documents/{uploaded_doc['id']}", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, client, auth_headers):
        resp = client.delete("/documents/does-not-exist", headers=auth_headers)
        assert resp.status_code == 404

    def test_user_cannot_delete_other_users_document(self, client, auth_headers, uploaded_doc, second_user):
        resp = client.delete(f"/documents/{uploaded_doc['id']}", headers=second_user["headers"])
        assert resp.status_code == 404
        # Verify the document still exists for its owner
        verify = client.get(f"/documents/{uploaded_doc['id']}", headers=auth_headers)
        assert verify.status_code == 200
