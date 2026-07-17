from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import create_access_token, create_user, get_current_user_dependency, get_db_session, get_user_by_email, verify_password
from database import init_db
from document_parser import extract_document_text
from document_store import get_document_chunks, get_document_embeddings, list_user_documents, store_document
from models import User
from schemas import UserLogin, UserRegister, UserResponse
from semantic_search import build_embeddings, rank_chunks, split_text


app = FastAPI(
    title="DocPilot API",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
init_db()

DOCUMENT_STORE = {}
ALLOWED_EXTENSIONS = {".docx", ".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_SEARCH_RESULTS = 5

class SearchRequest(BaseModel):
    query: str


class ChatRequest(BaseModel):
    question: str


@app.get("/")
def root():
    return {
        "message": "DocPilot backend is running",
        "version": "2.2.0",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db_session)):
    if get_user_by_email(db, str(payload.email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = create_user(db, payload)
    return {
        "id": user.id,
        "email": user.email,
        "created_at": user.created_at.isoformat(),
    }


@app.post("/auth/login")
def login(payload: UserLogin, db: Session = Depends(get_db_session)):
    user = get_user_by_email(db, str(payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(subject=user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
    }


@app.get("/auth/me", response_model=UserResponse)
def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db_session)):
    user = get_current_user_dependency(authorization, db)
    return {
        "id": user.id,
        "email": user.email,
        "created_at": user.created_at.isoformat(),
    }


@app.post("/documents", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db_session),
):
    user = get_current_user_dependency(authorization, db)
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file must have a filename.",
        )

    extension = Path(file.filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only DOCX and PDF files are supported right now.",
        )

    file_contents = await file.read()

    if not file_contents:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    if len(file_contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="The uploaded file exceeds the 10 MB limit.",
        )

    document_id = str(uuid4())
    stored_filename = f"{document_id}{extension}"
    stored_path = UPLOAD_FOLDER / stored_filename

    try:
        stored_path.write_bytes(file_contents)
        document_data = extract_document_text(stored_path)
    except Exception as error:
        if stored_path.exists():
            stored_path.unlink()

        raise HTTPException(
            status_code=400,
            detail="The document could not be processed. Please upload a valid DOCX or PDF file.",
        ) from error

    text = document_data.get("text", "")
    chunks = split_text(text)
    embeddings = build_embeddings(chunks)
    embedding_vectors = embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings

    stored_record = store_document(
        db,
        user_id=user.id,
        filename=file.filename,
        stored_filename=stored_filename,
        file_type=extension.removeprefix("."),
        size=len(file_contents),
        text=text,
        chunks=chunks,
        embeddings=embedding_vectors,
    )

    return {
        "id": stored_record.id,
        "filename": stored_record.filename,
        "stored_filename": stored_record.stored_filename,
        "file_type": stored_record.file_type,
        "size": stored_record.size,
        "status": stored_record.status,
        "document": document_data,
        "text": stored_record.text,
        "user_id": stored_record.user_id,
    }


@app.post("/search")
def search_documents(
    payload: SearchRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db_session),
):
    user = get_current_user_dependency(authorization, db)
    query = payload.query.strip().lower()
    if not query:
        return {"results": []}

    results = []
    for record in list_user_documents(db, user.id):
        chunks = get_document_chunks(record)
        embeddings = get_document_embeddings(record)
        if not chunks or not embeddings:
            continue

        ranked = rank_chunks(query, chunks, np.array(embeddings, dtype=float))
        top_chunks = [item for item in ranked if item["score"] > 0.15][:2]
        for item in top_chunks:
            results.append({
                "id": record.id,
                "filename": record.filename,
                "snippet": item["text"],
                "score": item["score"],
            })

    results.sort(key=lambda item: item["score"], reverse=True)
    return {"results": results[:MAX_SEARCH_RESULTS]}


@app.post("/chat")
def chat_with_documents(
    payload: ChatRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db_session),
):
    user = get_current_user_dependency(authorization, db)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="A question is required.")

    if not list_user_documents(db, user.id):
        return {
            "answer": "Please upload a document first so I can search it.",
            "citations": [],
        }

    ranked_matches = []
    for record in list_user_documents(db, user.id):
        chunks = get_document_chunks(record)
        embeddings = get_document_embeddings(record)
        if not chunks or not embeddings:
            continue

        ranked = rank_chunks(question, chunks, np.array(embeddings, dtype=float))
        best_chunk = ranked[0] if ranked else None
        if best_chunk and best_chunk["score"] > 0.15:
            ranked_matches.append((best_chunk["score"], record, best_chunk["text"]))

    if not ranked_matches:
        return {
            "answer": "I couldn’t find a strong match in the uploaded documents.",
            "citations": [],
        }

    ranked_matches.sort(key=lambda item: item[0], reverse=True)
    best_score, best_document, best_chunk = ranked_matches[0]
    answer = (
        f"Based on {best_document.filename}, the most relevant passage is: {best_chunk[:400]}"
    )
    citations = [{
        "documentName": best_document.filename,
        "meta": best_document.file_type,
    }]

    return {"answer": answer, "citations": citations}
