# DocPilot

A full-stack document workspace built with FastAPI, SQLite, JWT authentication, and vanilla JavaScript.

## Features

- Email/password registration and login
- Argon2 password hashing
- JWT-protected API routes
- Per-user document ownership
- DOCX and PDF text extraction
- Upload, list, and delete documents
- 10 MB upload limit

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# macOS/Linux
export JWT_SECRET_KEY="replace-with-a-long-random-secret"
# Windows PowerShell
# $env:JWT_SECRET_KEY="replace-with-a-long-random-secret"

uvicorn main:app --reload
```

API docs: http://127.0.0.1:8000/docs

### Frontend

In another terminal:

```bash
cd frontend
python -m http.server 5500
```

Open http://127.0.0.1:5500

## Next milestone

Add document search and sourced answers. Keep this separate from authentication and document storage so each feature stays testable.
