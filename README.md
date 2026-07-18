# DocPilot

A full-stack document workspace built with FastAPI, vanilla JavaScript, and Docker Compose.

## Features

- Email/password registration and login
- Argon2 password hashing
- JWT-protected API routes
- Per-user document ownership
- DOCX and PDF text extraction
- Upload, list, and delete documents
- Semantic retrieval, citations, evaluation, and conversation history
- 10 MB upload limit

## Prerequisites

- Docker Desktop (or Docker Engine)
- Docker Compose v2 plugin (`docker compose`)

## Initial Setup

```bash
cp .env.example .env
```

Then update required secrets in `.env`:

- `JWT_SECRET_KEY` (required)
- `OPENAI_API_KEY` (required only for AI-backed endpoints)

## Build And Start

```bash
docker compose up --build
```

Detached mode:

```bash
docker compose up -d --build
```

## Service URLs

- Frontend: http://127.0.0.1:5500
- Backend API: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Health endpoint: http://127.0.0.1:8000/health

## Logs

```bash
docker compose logs -f
docker compose logs -f backend
docker compose logs -f db
docker compose logs -f frontend
```

## Database Migrations

This repository currently does not use Alembic or another migration framework.

Current behavior:

- the backend creates tables at startup via SQLAlchemy metadata (`Base.metadata.create_all(...)`)
- startup requires a reachable database and uses `db` as the hostname in Compose

Manual schema initialization command (rarely needed because startup already does this):

```bash
docker compose run --rm backend python -c "from database import Base, engine; import models; Base.metadata.create_all(bind=engine)"
```

## Tests

Run the backend test suite in containers:

```bash
docker compose run --rm backend pytest
```

## Stop

```bash
docker compose down
```

## Full Reset

```bash
docker compose down -v
```

Warning: this removes all persisted PostgreSQL data and uploaded files stored in Docker volumes.

## Rebuild Without Cache

```bash
docker compose build --no-cache
```

## Data Persistence

Docker volumes are used for:

- PostgreSQL data: named volume `db_data` mounted at `/var/lib/postgresql/data`
- Uploaded files: named volume `uploads_data` mounted at `/app/uploads` in backend container

Restart behavior:

- `docker compose down` keeps both volumes
- `docker compose down -v` deletes both volumes

## Troubleshooting

- Port already in use: change `BACKEND_PORT` or `FRONTEND_PORT` in `.env`, then restart.
- Database never becomes healthy: check credentials in `.env` (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`) and inspect `docker compose logs -f db`.
- Missing environment variables: ensure `.env` exists and includes `JWT_SECRET_KEY` at minimum.
- Frontend cannot call backend: verify backend is reachable at `http://127.0.0.1:8000` and frontend is served from `http://127.0.0.1:5500`.
- Stale build cache: rebuild with `docker compose build --no-cache`.
- Upload permission issues: reset volume ownership by restarting backend, or run a full reset with `docker compose down -v`.
- Apple Silicon: the selected Python, Postgres, and Nginx images are multi-arch and run on arm64.

## Legacy Non-Docker Local Run

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export JWT_SECRET_KEY="replace-with-a-long-random-secret"
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
python -m http.server 5500
```
