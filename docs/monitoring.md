# Production Monitoring

DocPilot uses structured application logs and platform-native health/log
collection. This keeps the operational footprint proportional to a single-service
portfolio application while preserving enough context to diagnose failures.

## Logging Architecture

The backend writes one JSON object per application event to stdout. Render and
Docker collect that stream directly. The application does not require a log file,
sidecar, metrics database, Prometheus, Grafana, or ELK deployment.

Each JSON record contains these common fields:

| Field | Meaning |
| --- | --- |
| `timestamp` | UTC ISO-8601 event time |
| `level` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `service` | Configured service name, default `docpilot-backend` |
| `logger` | Application subsystem |
| `event` | Stable event name for filtering |
| `message` | Short operator-facing description |
| `request_id` | Correlation ID when the event belongs to an HTTP request |

Event-specific numeric and identifier fields are added at the top level. Durations
are milliseconds. Logs intentionally omit authorization headers, JWTs, passwords,
OpenAI keys, request bodies, prompts, questions, document text, original
filenames, SQL statements, SQL parameters, and raw exception messages. JSON
exception records retain the exception type and stack locations needed to find
the failing code without serializing provider responses or driver error text.

Example:

```json
{"timestamp":"2026-07-18T20:15:04.120Z","level":"INFO","service":"docpilot-backend","logger":"docpilot.http","event":"http_request_completed","message":"HTTP request completed","request_id":"a63b59cc-6390-44df-951c-720ba94dd637","method":"GET","path":"/documents","status_code":200,"duration_ms":18.204}
```

For local development, set `DOCPILOT_LOG_FORMAT=text` for readable single-line
output. Production should retain JSON.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DOCPILOT_LOG_LEVEL` | `INFO` | Minimum application log level |
| `DOCPILOT_LOG_FORMAT` | `json` | `json` for structured logs or `text` locally |
| `DOCPILOT_SLOW_QUERY_MS` | `250` | Warning threshold for database operations |
| `DOCPILOT_SERVICE_NAME` | `docpilot-backend` | Optional service label in JSON records |

`DEBUG` records include timing for every database operation. At `INFO`, normal
database queries remain quiet while queries above the threshold emit
`database_slow_query` warnings. Database and session failures are always errors.

## Event Catalog

### HTTP and lifecycle

- `application_startup`
- `application_shutdown`
- `http_request_completed`
- `http_request_failed`
- `health_check`

Every response contains `X-Request-ID`. A syntactically safe incoming value is
preserved; otherwise the backend generates a UUID. The same ID is attached to
downstream application events using request-local context.

### Database and migrations

- `database_query_completed` at `DEBUG`
- `database_slow_query` at `WARNING`
- `database_query_failed`
- `database_session_failed`
- `migration_started`
- `migration_completed`
- `migration_failed`

The database logger records only the operation category such as `SELECT` or
`INSERT`, duration, and error type. It never records statement text or bound
parameters.

### Retrieval and AI providers

- `retrieval_completed`
- `retrieval_failed`
- `retrieval_chunk_skipped`
- `embedding_request_completed`
- `embedding_request_failed`
- `embedding_response_invalid`
- `llm_request_completed`
- `llm_request_failed`
- `chat_completed`
- `chat_retrieval_failed`
- `chat_generation_failed`
- `chat_citation_rejected`

Provider events include provider/model names, counts, and latency. They do not
contain input text or provider response content.

### Documents and conversations

- `document_upload_completed`
- `document_storage_failed`
- `document_parsing_failed`
- `document_chunking_failed`
- `document_embedding_failed`
- `conversation_message_persisted`
- `conversation_persistence_failed`
- `conversation_creation_failed`
- `evaluation_baseline_failed`
- `evaluation_rag_failed`
- `evaluation_persistence_failed`

Upload records contain the internal document ID, file type, size, section/chunk
counts, and duration. The original filename and extracted content are excluded.

## Health Verification

Local Docker:

```bash
docker compose ps
curl -i http://127.0.0.1:8000/health
docker compose logs --tail=100 backend migrate db
```

Production:

```text
https://<backend-service-host>/health
https://<frontend-service-host>/
```

A successful backend response is:

```json
{"status":"healthy"}
```

The health request produces a `health_check` event and an `X-Request-ID` response
header. The endpoint is deliberately a lightweight liveness check. It does not
call PostgreSQL or OpenAI; provider and database availability are diagnosed from
their own operational events.

## Diagnosis Workflows

### Browser or API request failed

1. Copy `X-Request-ID` from the response.
2. Filter backend logs for that exact value.
3. Start with the terminal HTTP event and status code.
4. Follow any database, retrieval, embedding, LLM, upload, or persistence event
   carrying the same ID.
5. Use `error_type` and duration metadata to determine whether the problem is
   local validation, storage, PostgreSQL, or an external provider.

### Deployment failed before startup

1. Inspect Render's pre-deploy logs.
2. Find `migration_started`, followed by either `migration_completed` or
   `migration_failed`.
3. If the migration succeeded, inspect backend startup logs for
   `application_startup`.
4. Do not bypass a failed migration by changing the startup command.

### Chat is slow

1. Find `chat_completed` for the request ID and note total duration.
2. Compare `retrieval_completed`, `embedding_request_completed`, and
   `llm_request_completed` durations.
3. Check for `database_slow_query` warnings.
4. Correlate provider latency with Render resource utilization before changing
   retrieval limits or models.

### Upload failed

Filter by request ID for the first of:

- `document_storage_failed`
- `document_parsing_failed`
- `document_chunking_failed`
- `document_embedding_failed`

Check disk attachment and permissions for storage failures, input validity for
parsing failures, and provider availability for embedding failures. Do not place
uploaded customer documents into issue reports or log messages.

### Database failures

`database_query_failed` identifies the operation and driver exception type.
`database_session_failed` confirms the request transaction failed and was rolled
back. Review managed PostgreSQL status, connection limits, credentials, and the
latest migration before retrying writes.

## Error Reporting Decision

No hosted error-reporting SDK is added in this milestone. Render already retains
container logs and health status, and the repository does not yet have an agreed
Sentry-style account, data-retention policy, or alert destination. Adding an SDK
without those decisions would create an unused dependency and a risk of exporting
document-related context.

A hosted error tracker can be added later by forwarding only the structured error
metadata defined here. Prompt, document, credential, SQL, and request-body data
must remain excluded.

## Current Limitations

- Logs are retained according to the hosting platform plan; the application does
  not archive them independently.
- There is no alert routing, uptime monitor, or hosted error tracker yet.
- Request IDs correlate work inside one backend process but are not OpenTelemetry
  trace IDs.
- The health endpoint is liveness-only.
- Database timing is query-level; it is not a full distributed trace.
- Metrics dashboards and service-level objectives are intentionally outside this
  lightweight milestone.
