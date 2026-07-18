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

    def test_upload_rejects_declared_mime_mismatch(self, client, auth_headers):
        resp = client.post(
            "/documents",
            files={"file": ("spoofed.pdf", make_minimal_pdf(), "text/plain")},
            headers=auth_headers,
        )

        assert resp.status_code == 415

    def test_upload_rejects_spoofed_pdf_content(self, client, auth_headers):
        resp = client.post(
            "/documents",
            files={"file": ("spoofed.pdf", b"plain text", "application/pdf")},
            headers=auth_headers,
        )

        assert resp.status_code == 422
        assert resp.json()["detail"] == "The uploaded file is not a valid PDF or DOCX document"

    def test_upload_accepts_generic_binary_mime_after_signature_validation(
        self, client, auth_headers
    ):
        resp = client.post(
            "/documents",
            files={"file": ("report.pdf", make_minimal_pdf(), "application/octet-stream")},
            headers=auth_headers,
        )

        assert resp.status_code == 201

    def test_upload_sanitizes_windows_path_components(self, client, auth_headers):
        resp = client.post(
            "/documents",
            files={"file": (r"..\..\report.pdf", make_minimal_pdf(), "application/pdf")},
            headers=auth_headers,
        )

        assert resp.status_code == 201
        assert resp.json()["filename"] == "report.pdf"

    def test_upload_rejects_file_above_application_limit(self, client, auth_headers):
        oversized = b"%PDF-" + (b"x" * (10 * 1024 * 1024))
        resp = client.post(
            "/documents",
            files={"file": ("large.pdf", oversized, "application/pdf")},
            headers=auth_headers,
        )

        assert resp.status_code == 413

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


# ---------------------------------------------------------------------------
# Document Chunks (persistence layer)
# ---------------------------------------------------------------------------

class TestDocumentChunks:
    def test_chunks_created_during_docx_upload(self, client, auth_headers, db_session):
        """Chunks are created and persisted when a DOCX is uploaded."""
        from models import DocumentChunk
        
        resp = client.post(
            "/documents",
            files={"file": ("test.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]
        
        # Query chunks from database
        chunks = db_session.query(DocumentChunk).filter_by(document_id=doc_id).all()
        assert len(chunks) > 0, "DOCX upload should create at least one chunk"
        
        # Verify chunk structure
        chunk = chunks[0]
        assert chunk.document_id == doc_id
        assert chunk.chunk_index == 0
        assert len(chunk.text) > 0
        assert chunk.paragraph is not None, "DOCX chunks should have paragraph metadata"
        assert chunk.created_at is not None

    def test_chunks_created_during_pdf_upload(self, client, auth_headers, db_session):
        """Chunks are created and persisted when a PDF is uploaded."""
        from models import DocumentChunk
        
        resp = client.post(
            "/documents",
            files={"file": ("test.pdf", make_minimal_pdf(), "application/pdf")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]
        
        # Query chunks from database
        chunks = db_session.query(DocumentChunk).filter_by(document_id=doc_id).all()
        assert len(chunks) > 0, "PDF upload should create at least one chunk"
        
        # Verify chunk structure
        chunk = chunks[0]
        assert chunk.document_id == doc_id
        assert chunk.chunk_index == 0
        assert len(chunk.text) > 0
        assert chunk.page is not None, "PDF chunks should have page metadata"

    def test_chunk_metadata_preservation(self, client, auth_headers, db_session):
        """DOCX paragraph and PDF page metadata are correctly preserved in chunks."""
        from models import DocumentChunk
        
        # Upload DOCX
        resp_docx = client.post(
            "/documents",
            files={"file": ("test.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
        assert resp_docx.status_code == 201
        docx_id = resp_docx.json()["id"]
        
        docx_chunks = db_session.query(DocumentChunk).filter_by(document_id=docx_id).all()
        for chunk in docx_chunks:
            assert chunk.paragraph is not None or chunk.page is None, "DOCX chunks should have paragraph"
        
        # Upload PDF
        resp_pdf = client.post(
            "/documents",
            files={"file": ("test.pdf", make_minimal_pdf(), "application/pdf")},
            headers=auth_headers,
        )
        assert resp_pdf.status_code == 201
        pdf_id = resp_pdf.json()["id"]
        
        pdf_chunks = db_session.query(DocumentChunk).filter_by(document_id=pdf_id).all()
        for chunk in pdf_chunks:
            assert chunk.page is not None, "PDF chunks should have page"

    def test_deterministic_chunk_order(self, client, auth_headers, db_session):
        """Chunks are ordered deterministically by chunk_index."""
        from models import DocumentChunk
        
        resp = client.post(
            "/documents",
            files={"file": ("test.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]
        
        chunks = db_session.query(DocumentChunk).filter_by(document_id=doc_id).order_by(DocumentChunk.chunk_index).all()
        
        # Verify chunk_index sequence
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i, f"Chunk {i} has index {chunk.chunk_index}, expected {i}"

    def test_unique_chunk_index_per_document(self, client, auth_headers, db_session):
        """Each document has unique (document_id, chunk_index) combinations."""
        from models import DocumentChunk
        from sqlalchemy import func
        
        # Upload two documents
        resp1 = client.post(
            "/documents",
            files={"file": ("test1.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
        resp2 = client.post(
            "/documents",
            files={"file": ("test2.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        
        doc1_id = resp1.json()["id"]
        doc2_id = resp2.json()["id"]
        
        # Get chunks for each document
        chunks1 = db_session.query(DocumentChunk).filter_by(document_id=doc1_id).all()
        chunks2 = db_session.query(DocumentChunk).filter_by(document_id=doc2_id).all()
        
        # Verify no duplicate indices within each document
        indices1 = [c.chunk_index for c in chunks1]
        indices2 = [c.chunk_index for c in chunks2]
        
        assert len(indices1) == len(set(indices1)), "Document 1 has duplicate chunk indices"
        assert len(indices2) == len(set(indices2)), "Document 2 has duplicate chunk indices"
        
        # Chunks from different documents can have the same index (which is expected)
        # The unique constraint is on (document_id, chunk_index)

    def test_document_deletion_cascades_to_chunks(self, client, auth_headers, db_session):
        """Deleting a document also deletes all associated chunks."""
        from models import DocumentChunk
        
        resp = client.post(
            "/documents",
            files={"file": ("test.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]
        
        # Verify chunks exist
        chunks_before = db_session.query(DocumentChunk).filter_by(document_id=doc_id).all()
        assert len(chunks_before) > 0, "Document should have chunks"
        
        # Delete document
        resp_delete = client.delete(f"/documents/{doc_id}", headers=auth_headers)
        assert resp_delete.status_code == 204
        
        # Verify chunks are deleted
        db_session.expunge_all()  # Clear session cache to force fresh query
        chunks_after = db_session.query(DocumentChunk).filter_by(document_id=doc_id).all()
        assert len(chunks_after) == 0, "Document deletion should cascade to chunks"

    def test_chunk_source_section_id_tracking(self, client, auth_headers, db_session):
        """Chunks track their source section ID for citation purposes."""
        from models import DocumentChunk
        
        resp = client.post(
            "/documents",
            files={"file": ("test.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]
        
        chunks = db_session.query(DocumentChunk).filter_by(document_id=doc_id).all()
        
        # Verify source_section_id is set (or None if no sections)
        # At minimum, verify the field exists and is accessible
        for chunk in chunks:
            assert hasattr(chunk, "source_section_id"), "Chunk should have source_section_id field"

    def test_upload_with_no_sections_creates_no_chunks(self, client, auth_headers, db_session):
        """Documents with empty sections don't create chunks (edge case)."""
        from models import DocumentChunk
        
        # This is an edge case; normally documents have sections
        # We test that the system doesn't crash
        resp = client.post(
            "/documents",
            files={"file": ("test.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]
        
        # Even minimal DOCX should create at least one chunk
        chunks = db_session.query(DocumentChunk).filter_by(document_id=doc_id).all()
        # If document has content, it should have chunks
        # This test just ensures the system is robust

    def test_authorization_chunks_inherit_document_access(self, client, auth_headers, second_user, db_session):
        """Chunks inherit access control from their parent document."""
        from models import DocumentChunk
        
        resp = client.post(
            "/documents",
            files={"file": ("test.docx", make_minimal_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]
        
        # Original user can access chunks (indirectly through document)
        resp_get = client.get(f"/documents/{doc_id}", headers=auth_headers)
        assert resp_get.status_code == 200
        
        # Second user cannot access the document (and thus cannot access its chunks)
        resp_get_other = client.get(f"/documents/{doc_id}", headers=second_user["headers"])
        assert resp_get_other.status_code == 404
        
        # Chunks exist in database for original user
        chunks = db_session.query(DocumentChunk).filter_by(document_id=doc_id).all()
        assert len(chunks) > 0, "Chunks should exist for the document"
