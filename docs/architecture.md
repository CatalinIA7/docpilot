# Architecture Reference

DocPilot is a container-first modular monolith: one FastAPI process owns the
application rules and one static Nginx process serves the browser client. The
boundaries below document the current implementation, not a target redesign.

## System Context

```mermaid
flowchart LR
    Browser["Browser"] -->|"static assets"| Frontend["Nginx frontend"]
    Browser -->|"JWT API requests"| Backend["FastAPI backend"]
    Backend --> Database[("PostgreSQL")]
    Backend --> Uploads[("PDF/DOCX storage")]
    Backend --> Provider["OpenAI embeddings + generation"]
    Backend --> Logs["Structured stdout"]
```

Nginx does not proxy or implement application behavior. It serves the static
frontend and writes the configured public API URL into `config.js` at container
startup. The browser calls FastAPI directly.

## Upload and Indexing Flow

```mermaid
sequenceDiagram
    actor User
    participant UI as Static frontend
    participant API as FastAPI
    participant FS as Upload storage
    participant AI as OpenAI embeddings
    participant DB as PostgreSQL

    User->>UI: Select PDF or DOCX
    UI->>API: POST /documents + JWT
    API->>API: Verify user, filename, MIME, size, structure
    API->>FS: Write generated UUID filename
    API->>API: Extract text and deterministic sections/chunks
    API->>AI: Embed chunk batch
    AI-->>API: Embedding vectors
    API->>DB: Commit document + chunks + embeddings
    API-->>UI: Document metadata
```

Parsing, chunking, and embedding failures remove the staged source file where
possible. The database commit is transactional, and failures emit structured
events for operator diagnosis.

## Question and Retrieval Flow

```mermaid
sequenceDiagram
    actor User
    participant UI as Static frontend
    participant API as FastAPI
    participant DB as PostgreSQL
    participant AI as OpenAI

    User->>UI: Ask a document question
    UI->>API: POST /documents/{id}/chat + JWT
    API->>DB: Verify document ownership
    API->>AI: Embed the current question
    AI-->>API: Query vector
    API->>DB: Load that document's persisted chunks
    API->>API: Score and select top-k chunks
    API->>DB: Load bounded recent conversation messages
    API->>AI: System boundary + retrieved sources + history + question
    AI-->>API: Answer + proposed source IDs
    API->>API: Accept IDs only from retrieved chunks
    API->>DB: Optionally persist conversation messages and citations
    API-->>UI: Answer + source excerpts
```

The ordering is intentional. Conversation messages are independent of retrieval
internals, and every new question performs retrieval against the owned document.
Message records do not contain embeddings, retrieval scores, or full prompts.

## Data Ownership

| Data | Persistence | Ownership boundary |
| --- | --- | --- |
| Users and password hashes | PostgreSQL | Account identity |
| Document metadata and extracted text | PostgreSQL | `documents.user_id` |
| Source PDF/DOCX files | Upload volume/disk | Generated filename reached through owned document |
| Chunks and embeddings | PostgreSQL | Parent document |
| Conversations and messages | PostgreSQL | User + document |
| Benchmark questions and evaluation records | PostgreSQL | Owned document/run |
| Runtime frontend API URL | Generated `config.js` | Deployment configuration, no secret |

Authorization queries combine the resource identifier with the current user ID.
Cross-user resources return 404 without disclosing that the identifier exists.

## Local Docker Topology

```mermaid
flowchart TB
    Host["Developer browser"] -->|":5500"| Frontend["frontend<br/>Nginx :8080"]
    Host -->|":8000"| Backend["backend<br/>Uvicorn :8000"]
    Backend --> DB["db<br/>PostgreSQL :5432"]
    Migrate["migrate<br/>alembic upgrade head"] --> DB
    Migrate -.->|"must complete"| Backend
    DB --> DBVol[("db_data")]
    Backend --> UploadVol[("uploads_data")]
```

Compose waits for PostgreSQL health, runs the one-shot migration service, then
starts the backend. The frontend waits for backend health. Normal `down` retains
both named volumes; `down -v` deletes them.

## Production Topology

```mermaid
flowchart TB
    GitHub["GitHub main"] -->|"checks pass"| RF["Render frontend web service"]
    GitHub -->|"checks pass"| RB["Render backend web service"]
    User["Browser"] -->|"HTTPS"| RF
    RF -->|"HTTPS API"| RB
    RB -->|"private DATABASE_URL"| PG[("Managed PostgreSQL 16")]
    RB --> Disk[("Persistent disk<br/>/app/uploads")]
    RB --> OpenAI["OpenAI API"]
    RB --> RenderLogs["Render logs + health"]
    RB -.->|"pre-deploy"| Alembic["alembic upgrade head"]
```

Render terminates HTTPS, injects platform secrets, supplies the database URL and
assigned hostname, and mounts durable upload storage. The persistent disk makes
the current backend a single-instance design. See `deployment-render.md` before
applying the Blueprint.

## Runtime Boundaries

- `auth.py` and authentication routes own password and token behavior.
- document routes own file validation, extraction, chunk creation, persistence,
  ownership checks, search, and deletion.
- embedding and retrieval services own provider calls and similarity scoring.
- chat routes orchestrate retrieval, bounded conversation context, grounded
  generation, citation validation, and message persistence.
- evaluation modules run baseline/RAG comparisons without altering production
  chat behavior.
- observability and security middleware wrap the HTTP boundary without storing
  prompts, credentials, document text, or SQL.
- Alembic owns production schema creation and upgrades; application startup does
  not create tables.

## Deliberate Tradeoffs

The static frontend avoids a Node build toolchain. JSON embeddings and in-process
cosine scoring avoid a vector extension for modest document collections. A
persistent platform disk is simpler than object storage for one instance.
Structured platform-collected logs avoid operating a monitoring stack. Each
choice has an explicit scale limit documented in the README and runbooks.
