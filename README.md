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
docker compose logs migrate
docker compose logs -f frontend
```

## Database Migrations

Alembic migrations are the production source of truth for the database schema. The
backend no longer creates tables during application import or startup.

With Docker Compose, the one-shot `migrate` service runs `alembic upgrade head`
after PostgreSQL is healthy. The backend starts only after that migration succeeds,
so a fresh database is initialized by the normal startup command:

```bash
docker compose up --build
```

Useful migration commands:

```bash
docker compose run --rm migrate
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic history
docker compose run --rm migrate alembic check
```

For a non-Docker backend run, activate the backend virtual environment and run
`alembic upgrade head` from the `backend` directory before starting Uvicorn.

### Adopting An Existing Pre-Alembic Database

The baseline migration represents the schema previously created by
`Base.metadata.create_all(...)`. Applying that create-table migration directly to
an existing DocPilot database would fail because the tables already exist.

Before adopting an existing database, take a database backup and verify that its
schema matches the current nine DocPilot tables. Then record the reviewed baseline
without running its DDL and validate that the models have no pending differences:

```bash
docker compose up -d db
docker compose build migrate
docker compose run --rm --no-deps migrate alembic stamp 20260718_0001
docker compose run --rm --no-deps migrate alembic check
docker compose up -d
```

`stamp` only writes the Alembic revision marker; it does not create, alter, or drop
application tables. Do not stamp a database whose schema differs from the baseline.
Future migrations should be applied normally with `alembic upgrade head`.

## Tests

Run the backend test suite in containers:

```bash
docker compose run --rm backend pytest
```

## Continuous Integration

GitHub Actions CI is defined in `.github/workflows/ci.yml`.

It runs on:

- Pull requests targeting `main`
- Pushes to `main`
- Manual dispatch (`workflow_dispatch`)

CI validates:

- Alembic upgrade to the latest revision on a fresh PostgreSQL database
- Migration drift with `alembic check`
- Full backend test suite using the repository command (`docker compose run --rm backend pytest`)
- Frontend Docker image build (frontend is static and has no npm build step)
- Docker Compose configuration (`docker compose config`)
- Backend and frontend Docker image builds (`docker compose build backend frontend`)

CI in this repository does not deploy infrastructure and does not publish container images.

Local equivalents:

```bash
docker compose run --rm migrate
docker compose run --rm migrate alembic check
docker compose run --rm backend pytest
docker compose config
docker compose build backend frontend
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
alembic upgrade head
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
python -m http.server 5500
```
