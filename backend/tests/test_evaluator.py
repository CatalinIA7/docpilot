from uuid import uuid4

import evaluator
from evaluator import Evaluator
from models import BenchmarkQuestion, Document, User


def test_evaluator_resolves_documents_from_configured_upload_dir(
    db_session, monkeypatch, tmp_path
):
    user = User(email="evaluator@example.com", password_hash="not-used")
    document = Document(
        id=str(uuid4()),
        owner=user,
        filename="evaluation.docx",
        stored_filename="stored-evaluation.docx",
        file_type="docx",
        size=42,
        text="Evaluation content",
        preview="Evaluation content",
        word_count=2,
        character_count=18,
        paragraph_count=1,
    )
    benchmark = BenchmarkQuestion(
        document=document,
        question="What is evaluated?",
        expected_answer_summary="Evaluation content",
        expected_citation_count=0,
    )
    db_session.add_all([user, document, benchmark])
    db_session.flush()

    parsed_paths = []

    def fake_extract_document_text(path):
        parsed_paths.append(path)
        return {"_sections": []}

    monkeypatch.setattr(evaluator, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(evaluator, "extract_document_text", fake_extract_document_text)
    monkeypatch.setattr(evaluator, "answer_question", lambda **kwargs: ("Answer", []))

    run, results = Evaluator(db_session).run_evaluation(
        [benchmark], user_id=user.id, run_name="deployment-path-test"
    )

    assert parsed_paths == [tmp_path / document.stored_filename]
    assert run.total_questions == 1
    assert len(results) == 1
