# AI Observability Foundation

## Overview

The AI observability foundation captures reliable operational telemetry for every document-chat request. This enables developers to understand performance, resource usage, and failure modes without exposing sensitive data.

## What is Recorded

Every chat request produces a complete observability record containing:

### Identifiers
- `request_id`: Unique UUID for request tracing (generated or from `X-Request-ID` header)
- `user_id`: User who initiated the request
- `document_id`: Document being queried

### Status & Failures
- `status`: `"success"` or `"failed"`
- `failure_stage`: When failed, indicates the stage where failure occurred
  - `authorization` — User not authorized for document
  - `document_loading` — Could not load document or chunks
  - `question_embedding` — Question embedding generation failed
  - `retrieval` — Chunk retrieval/ranking failed
  - `context_assembly` — Prompt construction failed
  - `generation` — AI model call failed
  - `response_validation` — Response validation failed
  - `database_persistence` — Observability record persistence failed
  - `unknown` — Unexpected error
- `provider_error_type`: Safe error category from provider
  - `authentication` — Auth/credential issue
  - `rate_limit` — Rate limiting
  - `quota` — Quota exceeded
  - `timeout` — Timeout
  - `invalid_response` — Malformed provider response
  - `configuration` — Configuration error
  - `unknown_provider_error` — Other provider error

### Timing (milliseconds, monotonic)
- `total_duration_ms` — Total request time
- `question_embedding_duration_ms` — Question embedding generation
- `retrieval_duration_ms` — Chunk retrieval and ranking
- `generation_duration_ms` — AI model response generation

### Retrieval Metrics
- `candidate_chunk_count` — Total chunks loaded for document
- `embedded_candidate_count` — Chunks with usable embeddings
- `retrieved_chunk_count` — Chunks selected after filtering
- `retrieved_chunk_ids` — Database IDs of retrieved chunks (preserves order)
- `retrieval_scores` — Similarity scores (preserves order)
- `retrieval_top_k` — Configured max chunks to retrieve
- `retrieval_min_score` — Configured minimum similarity threshold

### Generation Metrics
- `prompt_character_count` — Characters in assembled context
- `response_character_count` — Characters in AI response
- `citation_count` — Number of citations in response
- `ai_model` — Model name used (e.g., `"gpt-4o-mini"`)
- `embedding_model` — Embedding model name
- `embedding_dimension` — Vector dimension of embeddings
- `input_tokens` — Tokens consumed (optional, provider-dependent)
- `output_tokens` — Tokens generated (optional, provider-dependent)
- `total_tokens` — Total tokens used (optional, provider-dependent)

### Metadata
- `created_at` — ISO 8601 timestamp of record creation

## What is Intentionally Excluded

For privacy and security, the following are **never** recorded:

- Raw question text
- AI response/answer content
- Chunk text content
- Prompt content (only character count)
- Embedding vectors
- API keys or credentials
- Request headers (authorization, bearer tokens)
- Complete provider payloads
- Stack traces or exception details (only safe category names)
- User IP addresses
- File names

## Configuration

Three environment variables control observability behavior:

```bash
# Enable/disable observability capture entirely
# Default: true
DOCPILOT_OBSERVABILITY_ENABLED=true

# Persist records to database (independent of logging)
# Default: true
DOCPILOT_OBSERVABILITY_PERSIST=true

# Log level for observability events
# Default: INFO
DOCPILOT_OBSERVABILITY_LOG_LEVEL=INFO
```

### Disable Observability Entirely
```bash
DOCPILOT_OBSERVABILITY_ENABLED=false
```
When disabled:
- No observability recorder is created
- No database metrics are persisted
- No observability summary logs are emitted
- Chat behavior is unchanged

### Disable Only Database Persistence
```bash
DOCPILOT_OBSERVABILITY_PERSIST=false
```
When disabled:
- Structured logs are still emitted
- Database records are not created
- Chat behavior is unchanged

### Configure Log Level
```bash
DOCPILOT_OBSERVABILITY_LOG_LEVEL=DEBUG
```
Standard Python logging levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

## Request IDs

Every chat request has a unique request ID for distributed tracing:

### Incoming Header
Clients may provide a request ID via the `X-Request-ID` header:
```
POST /documents/{doc_id}/chat
X-Request-ID: my-custom-trace-id-123
```

If the header is:
- Valid (alphanumeric, ≤ 100 chars) — it is used
- Invalid or missing — a new UUID is generated

### Response Header
The `X-Request-ID` is returned in response headers (both success and failure):
```
X-Request-ID: my-custom-trace-id-123
```

Use this to correlate logs, metrics, and user support requests.

## Structured Logging

A summary structured log event is emitted for every completed or failed chat request:

### Success Event
```
event: document_chat_completed
request_id: 550e8400-e29b-41d4-a716-446655440000
user_id: 42
document_id: doc-uuid-1234
status: success
failure_stage: null
total_duration_ms: 1234.56
embedding_duration_ms: 45.23
retrieval_duration_ms: 123.45
generation_duration_ms: 1065.88
candidate_chunk_count: 127
embedded_candidate_count: 127
retrieved_chunk_count: 5
citation_count: 2
ai_model: gpt-4o-mini
embedding_model: text-embedding-3-small
embedding_dimension: 1536
```

### Failure Event
```
event: document_chat_failed
request_id: 550e8400-e29b-41d4-a716-446655440001
user_id: 42
document_id: doc-uuid-1234
status: failed
failure_stage: retrieval
total_duration_ms: 123.45
provider_error_type: rate_limit
...
```

Logs do **not** contain questions, answers, or other sensitive content.

## Database Schema

Observability records are persisted to the `ai_request_metrics` table:

```python
class AIRequestMetric(Base):
    id: int                                    # Primary key
    request_id: str                           # Unique, indexed
    user_id: int                              # Indexed (no FK constraint)
    document_id: str | None                   # Nullable, indexed (no FK constraint)
    status: str                               # "success" or "failed"
    failure_stage: str | None                 # See status & failures section
    
    # Timing
    total_duration_ms: float
    question_embedding_duration_ms: float
    retrieval_duration_ms: float
    generation_duration_ms: float
    
    # Retrieval
    candidate_chunk_count: int
    embedded_candidate_count: int
    retrieved_chunk_count: int
    retrieved_chunk_ids: list[int]            # JSON array, preserves order
    retrieval_scores: list[float]             # JSON array, preserves order
    retrieval_top_k: int
    retrieval_min_score: float
    
    # Generation
    prompt_character_count: int
    response_character_count: int
    citation_count: int
    ai_model: str
    embedding_model: str
    embedding_dimension: int
    
    # Token usage (optional)
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    
    # Errors
    provider_error_type: str | None           # See status & failures section
    
    # Metadata
    created_at: datetime                      # UTC, indexed
```

### Lifecycle

**Records are NOT automatically deleted** with documents or users:

- Deleting a document does NOT cascade-delete its observability records
- Deleting a user does NOT cascade-delete their observability records
- `user_id` and `document_id` are stored as integers/strings, not foreign keys
- Records persist indefinitely for historical analysis
- Manual deletion/archival of old records is the responsibility of operations

### Query Examples

Retrieve all requests for a user:
```sql
SELECT * FROM ai_request_metrics 
WHERE user_id = 42 
ORDER BY created_at DESC;
```

Find failed requests in the last hour:
```sql
SELECT * FROM ai_request_metrics 
WHERE status = 'failed' 
  AND created_at > datetime('now', '-1 hour');
```

Analyze retrieval performance:
```sql
SELECT 
  document_id,
  COUNT(*) as request_count,
  AVG(retrieval_duration_ms) as avg_retrieval_ms,
  AVG(retrieved_chunk_count) as avg_chunks_retrieved
FROM ai_request_metrics 
WHERE status = 'success'
GROUP BY document_id;
```

## Persistence Failure Policy

**Observability must never break a successful request.**

If writing the observability record fails:
1. The successful chat response is **not** rolled back
2. A safe error log is emitted: `"Failed to persist observability record: ..."`
3. The error is **not** exposed to the user
4. The request returns normally with the answer and citations

If the chat request itself fails:
1. The system makes a best-effort attempt to persist a failure record
2. If that persistence also fails, the original chat error takes precedence
3. The original error is returned to the user

Persistence happens on a separate transaction independent of the main chat response.

## HTTP Response Behavior

The chat endpoint preserves its existing JSON response structure:

```json
{
  "answer": "...",
  "citations": [...]
}
```

The `X-Request-ID` header is added to successful responses (status 200) and error responses (4xx, 5xx).

Internal observability data (scores, chunk IDs, timing, config values) is **not** exposed in the public JSON response. These remain server-side telemetry only.

## Service Architecture

Observability is implemented via a dedicated service (`observability_service.py`) that is independent from:

- OpenAI SDK and response parsing
- Embedding calculations
- Cosine similarity logic
- Authentication/authorization
- Frontend behavior

The chat route orchestrates the request and calls the observability service at strategic points to record:
- Stage start/end times
- Retrieval results
- Generation results
- Success or failure

## Future Enhancements

This foundation enables future work:

1. **Diagnostics Endpoint** — Authenticated route to query observability records
   - Filter by time range, user, document, status
   - Return safe summary metrics

2. **Dashboard** — Internal admin UI to visualize:
   - Request volume and latency trends
   - Failure rates and stages
   - Retrieval quality metrics (chunks retrieved, scores)
   - Token usage over time

3. **Alerts** — Rules-based alerting:
   - High error rate in specific stage
   - Unusual latency increase
   - Quota exhaustion

4. **Performance Profiling** — Breakdown by:
   - Document size
   - Question complexity
   - User cohorts
   - Time of day

5. **Cost Analysis** — Token usage aggregation for:
   - Per-user billing
   - Per-document cost
   - ROI analysis

## Development Usage

### Enable Debug-Level Logging
```bash
export DOCPILOT_OBSERVABILITY_LOG_LEVEL=DEBUG
# Now run the application
python -m uvicorn main:app --reload
```

### Query Recent Requests
```bash
sqlite3 docpilot.db
> SELECT request_id, status, total_duration_ms, failure_stage 
  FROM ai_request_metrics 
  ORDER BY created_at DESC 
  LIMIT 10;
```

### Disable Observability Entirely for Testing
```bash
export DOCPILOT_OBSERVABILITY_ENABLED=false
pytest backend/tests/
```

### Inspect a Specific Request
```bash
sqlite3 docpilot.db
> SELECT json_object(
    'request_id', request_id,
    'status', status,
    'duration', total_duration_ms,
    'retrieved_chunks', retrieved_chunk_count,
    'model', ai_model,
    'failure_stage', failure_stage
  ) as request_summary
  FROM ai_request_metrics
  WHERE request_id = '550e8400-e29b-41d4-a716-446655440000';
```

## Privacy Checklist

Before querying or exporting observability data:

- [ ] IDs (request, user, document) are safe to expose (no auth tokens)
- [ ] Numeric metadata (counts, durations, token usage) is safe
- [ ] Never export raw question, answer, or chunk text
- [ ] Never export embedding vectors
- [ ] Never expose API keys or provider payloads
- [ ] Redact failure messages if exposing to external parties

## Testing

Observability is fully tested without requiring live provider access:

```bash
# Run all observability tests
pytest backend/tests/test_observability.py -v

# Run specific test class
pytest backend/tests/test_observability.py::TestRetrievalTelemetry -v

# Run with verbose output
pytest backend/tests/test_observability.py -vv --tb=short
```

Tests cover:
- Timing accuracy (monotonic, non-negative)
- Record completeness
- Retrieval order preservation
- Failure stage tracking
- Privacy protections
- Configuration handling
- Chat integration
- Backward compatibility

All tests use mocked AI and embedding providers.
