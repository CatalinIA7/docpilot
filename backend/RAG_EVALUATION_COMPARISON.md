# RAG Evaluation Comparison Framework

## Overview

The RAG evaluation comparison framework objectively measures the effectiveness of retrieval-augmented generation (RAG) against baseline full-document chat. It executes both strategies independently on the same question and document, then compares their outputs across multiple dimensions.

**Use Case**: Regression testing and performance benchmarking after code changes.

---

## Evaluation Modes

### Baseline Strategy

**What it does:**
- Takes all chunks from a document
- Sends full document as context to AI model
- Records latency, response size, citation count

**Prompt size:** Entire document

**Speed:** Baseline

**Metric focus:** Full-context completeness

### RAG Strategy

**What it does:**
- Embeds the question
- Retrieves top-k similar chunks based on semantic similarity
- Sends only relevant chunks to AI model
- Records latency, response size, retrieval metrics

**Prompt size:** Typically 50-90% smaller

**Speed:** Often 10-50% faster due to smaller context

**Metric focus:** Context efficiency, retrieval quality

### Both Strategies

**Use the same:**
- Question
- Document
- AI model (gpt-4o-mini)
- Output schema (answer + citations)
- Execution path

**Execute independently:**
- No shared state
- Failures in one don't affect the other
- Both results returned even if one fails

---

## Comparison Metrics

### Context Reduction

```
(baseline_prompt_chars - rag_prompt_chars) / baseline_prompt_chars * 100
```

**Target:** ≥ 50% reduction (configurable via `DOCPILOT_EVAL_MIN_CONTEXT_REDUCTION`)

**Example:**
- Baseline prompt: 10,000 chars
- RAG prompt: 3,000 chars
- Reduction: 70%

### Latency Difference

```
baseline_total_latency - rag_total_latency
```

**Target:** Positive value (RAG is faster)

**Example:**
- Baseline: 1,500 ms
- RAG: 1,000 ms
- Difference: +500 ms improvement (33% faster)

### Citation Preservation

```
rag_citation_count / baseline_citation_count
```

**Target:** ≥ 80% preservation (configurable via `DOCPILOT_EVAL_MIN_CITATION_PRESERVATION`)

**Example:**
- Baseline citations: 5
- RAG citations: 4
- Preservation: 80%

### Retrieval Quality

**Retrieved chunk count:** Number of chunks selected by retrieval

**Similarity scores:** Vector similarity (0.0 to 1.0) for each retrieved chunk

**Average similarity:** Mean of all retrieval scores

**Example:**
```
Retrieved: [chunk_1 (0.95), chunk_2 (0.87), chunk_3 (0.76)]
Average: 0.86
Highest: 0.95
Lowest: 0.76
```

---

## Status Determination

Evaluation results are labeled PASS, WARNING, or FAIL based on thresholds:

### PASS
✅ All conditions met:
- Both strategies succeeded
- Context reduction ≥ minimum threshold
- RAG latency ≤ maximum threshold
- Citation preservation ≥ minimum threshold

### FAIL
❌ One or more conditions violated:
- Either strategy failed
- Context reduction below minimum
- RAG latency exceeds maximum
- Citation preservation below minimum

**Example failures:**
- "Context reduction 30.0% < minimum 50.0%"
- "RAG latency 6000ms > max 5000ms"
- "Citation preservation 0.60 < minimum 0.80"

---

## Configuration

### Environment Variables

```bash
# Maximum acceptable latency for RAG (milliseconds)
DOCPILOT_EVAL_MAX_LATENCY_MS=5000.0

# Minimum context reduction required (percentage)
DOCPILOT_EVAL_MIN_CONTEXT_REDUCTION=50.0

# Minimum citation preservation ratio
DOCPILOT_EVAL_MIN_CITATION_PRESERVATION=0.8

# Whether to persist evaluation results to database
DOCPILOT_EVAL_PERSIST_RESULTS=true
```

### Example: Strict Mode

```bash
# Very strict thresholds
export DOCPILOT_EVAL_MAX_LATENCY_MS=3000.0
export DOCPILOT_EVAL_MIN_CONTEXT_REDUCTION=80.0
export DOCPILOT_EVAL_MIN_CITATION_PRESERVATION=0.9
```

### Example: Lenient Mode

```bash
# More forgiving thresholds
export DOCPILOT_EVAL_MAX_LATENCY_MS=10000.0
export DOCPILOT_EVAL_MIN_CONTEXT_REDUCTION=30.0
export DOCPILOT_EVAL_MIN_CITATION_PRESERVATION=0.5
```

---

## REST API

### Endpoint: Run Evaluation Comparison

**Request:**
```http
POST /evaluation/compare/baseline-vs-rag/{document_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "question": "What is the refund policy?",
  "store_result": true
}
```

**Response (200 OK):**
```json
{
  "question": "What is the refund policy?",
  "document_id": "doc-abc123",
  "baseline": {
    "mode": "baseline",
    "success": true,
    "total_latency_ms": 1234.5,
    "embedding_latency_ms": 0.0,
    "retrieval_latency_ms": 0.0,
    "generation_latency_ms": 1234.5,
    "prompt_character_count": 31842,
    "response_character_count": 250,
    "citation_count": 5,
    "retrieved_chunk_count": 127,
    "retrieved_chunk_ids": [0, 1, 2, ..., 126],
    "retrieval_scores": [],
    "ai_model": "gpt-4o-mini",
    "embedding_model": null,
    "embedding_dimension": null,
    "answer_text": "The refund policy...",
    "error": null
  },
  "rag": {
    "mode": "rag",
    "success": true,
    "total_latency_ms": 874.2,
    "embedding_latency_ms": 0.0,
    "retrieval_latency_ms": 123.5,
    "generation_latency_ms": 750.7,
    "prompt_character_count": 3720,
    "response_character_count": 250,
    "citation_count": 5,
    "retrieved_chunk_count": 5,
    "retrieved_chunk_ids": [10, 20, 30, 40, 50],
    "retrieval_scores": [0.91, 0.87, 0.83, 0.81, 0.74],
    "ai_model": "gpt-4o-mini",
    "embedding_model": "text-embedding-3-small",
    "embedding_dimension": 1536,
    "answer_text": "The refund policy...",
    "error": null
  },
  "comparison": {
    "context_reduction_percent": 88.3,
    "latency_difference_ms": 360.3,
    "latency_improvement_percent": 29.2,
    "generation_latency_difference_ms": 483.8,
    "citation_difference": 0,
    "retrieved_chunk_avg_similarity": 0.8320,
    "retrieved_chunk_highest_similarity": 0.91,
    "retrieved_chunk_lowest_similarity": 0.74,
    "status": "PASS",
    "status_reason": "All thresholds met"
  }
}
```

**Error Responses:**

```http
404 Not Found
{
  "detail": "Document not found"
}
```

```http
400 Bad Request
{
  "detail": "Document has no extractable content"
}
```

```http
500 Internal Server Error
{
  "detail": "Evaluation failed: ..."
}
```

### Endpoint: List Comparison Results

**Request:**
```http
GET /evaluation/comparison-results/{document_id}
Authorization: Bearer {token}
```

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "question": "What is the refund policy?",
    "document_id": "doc-abc123",
    "baseline_latency_ms": 1234.5,
    "rag_latency_ms": 874.2,
    "context_reduction_percent": 88.3,
    "citation_difference": 0,
    "comparison_status": "PASS",
    "created_at": "2026-07-18T10:30:00Z"
  },
  {
    "id": 2,
    "question": "How do I contact support?",
    "document_id": "doc-abc123",
    "baseline_latency_ms": 987.3,
    "rag_latency_ms": 654.1,
    "context_reduction_percent": 85.2,
    "citation_difference": 1,
    "comparison_status": "PASS",
    "created_at": "2026-07-18T10:25:00Z"
  }
]
```

---

## CLI Usage

### Run Comparison (Text Output)

```bash
python cli_evaluation.py compare doc-abc123 "What is the refund policy?"
```

**Output:**
```
================================================================================
RAG Evaluation Report
================================================================================

Question
--------------------------------------------------------------------------------
What is the refund policy?

Baseline (Full Document)
--------------------------------------------------------------------------------
Status              True
Latency             1234.5 ms
Generation time     1234.5 ms
Prompt chars        31,842
Response chars      250
Citations           5
Chunks used         127

RAG (Retrieval-Augmented)
--------------------------------------------------------------------------------
Status              True
Latency             874.2 ms
Embedding time      0.0 ms
Retrieval time      123.5 ms
Generation time     750.7 ms
Prompt chars        3,720
Response chars      250
Citations           5
Chunks retrieved    5
Similarity scores   0.91, 0.87, 0.83, 0.81, 0.74
Avg similarity      0.83

Comparison Metrics
--------------------------------------------------------------------------------
Context reduction   88.3%
Latency change      +360.3 ms (+29.2%)
Gen latency change  +483.8 ms
Citation change     +0

Evaluation Status
--------------------------------------------------------------------------------
Result              PASS
Reason              All thresholds met
================================================================================
```

### Run Comparison (JSON Output)

```bash
python cli_evaluation.py compare doc-abc123 "What is the refund policy?" --json
```

**Output:**
```json
{
  "question": "What is the refund policy?",
  "document_id": "doc-abc123",
  "baseline": {
    ...
  },
  "rag": {
    ...
  },
  "comparison": {
    ...
  }
}
```

### List Results (Text)

```bash
python cli_evaluation.py results doc-abc123
```

**Output:**
```
================================================================================
Evaluation Results
================================================================================

1. What is the refund policy?...
   Baseline: 1235ms | RAG: 874ms
   Context reduction: 88.3%
   Status: PASS
   Created: 2026-07-18T10:30:00+00:00

2. How do I contact support?...
   Baseline: 987ms | RAG: 654ms
   Context reduction: 85.2%
   Status: PASS
   Created: 2026-07-18T10:25:00+00:00

================================================================================
```

### List Results (JSON)

```bash
python cli_evaluation.py results doc-abc123 --json
```

---

## Database Persistence

### Schema

```python
class RAGEvaluationComparison(Base):
    __tablename__ = "rag_evaluation_comparisons"
    
    id: int (PK)
    user_id: int (FK users.id)
    document_id: str (FK documents.id)
    question: str
    
    # Baseline
    baseline_success: bool
    baseline_latency_ms: float
    baseline_prompt_chars: int
    baseline_response_chars: int
    baseline_citation_count: int
    baseline_error: str | None
    
    # RAG
    rag_success: bool
    rag_latency_ms: float
    rag_prompt_chars: int
    rag_response_chars: int
    rag_citation_count: int
    rag_retrieved_chunk_count: int
    rag_retrieved_chunk_ids: list[int]  # JSON
    rag_retrieval_scores: list[float]   # JSON
    rag_error: str | None
    
    # Comparison
    context_reduction_percent: float
    latency_difference_ms: float
    citation_difference: int
    avg_similarity_score: float
    comparison_status: str  # "PASS", "WARNING", "FAIL"
    status_reason: str
    
    # Metadata
    ai_model: str
    created_at: datetime (indexed)
```

### Retention Policy

**What's stored:**
- Question text (safe for internal benchmarking)
- Metrics (latency, context size, counts)
- Status and reason
- Chunk IDs and similarity scores

**What's NOT stored:**
- Prompt text (only character count)
- Answer text (character count only)
- Embeddings
- Provider payloads

**Lifecycle:**
- Records persist indefinitely for historical analysis
- Deletion of document/user does NOT cascade-delete evaluation results
- Manual cleanup is responsibility of operations team

### Query Examples

**Recent evaluations:**
```sql
SELECT question, comparison_status, context_reduction_percent, 
       latency_difference_ms, created_at
FROM rag_evaluation_comparisons
WHERE document_id = 'doc-abc123'
ORDER BY created_at DESC
LIMIT 10;
```

**Pass rate:**
```sql
SELECT comparison_status, COUNT(*) as count
FROM rag_evaluation_comparisons
GROUP BY comparison_status;
```

**Average metrics:**
```sql
SELECT 
  AVG(context_reduction_percent) as avg_context_reduction,
  AVG(latency_difference_ms) as avg_latency_improvement,
  AVG(CASE WHEN comparison_status = 'PASS' THEN 1 ELSE 0 END) as pass_rate
FROM rag_evaluation_comparisons
WHERE created_at > datetime('now', '-7 days');
```

---

## Python API

### Basic Usage

```python
from evaluation_comparison_service import EvaluationRunner
from models import Document, DocumentChunk
from database import SessionLocal

db = SessionLocal()

# Get document and chunks
document = db.query(Document).filter(Document.id == "doc-123").first()
chunks = db.query(DocumentChunk).filter(
    DocumentChunk.document_id == "doc-123"
).order_by(DocumentChunk.chunk_index).all()

# Create runner with thresholds
runner = EvaluationRunner(
    max_latency_ms=5000.0,
    min_context_reduction_percent=50.0,
    min_citation_preservation=0.8,
)

# Run comparison
comparison = runner.run(
    document=document,
    question="What is the refund policy?",
    chunks=chunks,
)

# Access results
print(f"Status: {comparison.comparison.status}")
print(f"Context reduction: {comparison.comparison.context_reduction_percent:.1f}%")
print(f"Latency improvement: {comparison.comparison.latency_difference_ms:.0f}ms")

# Convert to JSON
result_dict = runner.to_dict(comparison)
```

### Data Structures

**EvaluationRunMetrics** (frozen dataclass):
```python
mode: str  # "baseline" or "rag"
success: bool
total_latency_ms: float
embedding_latency_ms: float
retrieval_latency_ms: float
generation_latency_ms: float
prompt_character_count: int
response_character_count: int
citation_count: int
retrieved_chunk_count: int
retrieved_chunk_ids: list[int]
retrieval_scores: list[float]
ai_model: str
embedding_model: str | None
embedding_dimension: int | None
answer_text: str
error: str | None
```

**ComparisonMetrics** (frozen dataclass):
```python
context_reduction_percent: float
latency_difference_ms: float
latency_improvement_percent: float
generation_latency_difference_ms: float
citation_difference: int
retrieved_chunk_avg_similarity: float
retrieved_chunk_highest_similarity: float
retrieved_chunk_lowest_similarity: float
status: str  # "PASS", "WARNING", "FAIL"
status_reason: str
```

**EvaluationComparison** (frozen dataclass):
```python
question: str
document_id: str
baseline: EvaluationRunMetrics
rag: EvaluationRunMetrics
comparison: ComparisonMetrics
```

---

## Testing

### Unit Tests

Run tests for evaluation comparison service:

```bash
pytest backend/tests/test_evaluation_comparison.py -v
```

**Coverage:**
- ✅ Both strategies execute independently
- ✅ Failures isolated between strategies
- ✅ Metrics computed correctly
- ✅ Thresholds determine status properly
- ✅ Serialization to JSON

### Regression Testing

Compare baseline vs RAG before and after code changes:

```bash
# Before code change
python cli_evaluation.py compare doc-123 "Question" > before.json

# Make code changes...

# After code change
python cli_evaluation.py compare doc-123 "Question" > after.json

# Compare results
diff before.json after.json
```

---

## Integration with Observability

The evaluation framework is **independent** from production observability:

- ✅ Evaluation data is **internal benchmarking** (can store question/answer text)
- ❌ Production observability **never stores** question/answer/embeddings
- ✅ Evaluation can be disabled without affecting production logging
- ✅ Evaluation metrics are stored in separate `rag_evaluation_comparisons` table

---

## Future Enhancements

1. **Automatic Regression Detection**
   - Compare latest evaluation against baseline
   - Alert if metrics regress beyond threshold
   - Integrate with CI/CD pipeline

2. **Batch Evaluations**
   - Run comparisons on multiple questions simultaneously
   - Generate summary report
   - Export to CSV/Excel

3. **Performance Dashboard**
   - Visualize trends over time
   - Compare improvements by document type
   - Track context reduction across corpus

4. **Cost Analysis**
   - Calculate token cost difference
   - ROI analysis for RAG implementation
   - Cost savings over time

5. **Answer Quality Metrics**
   - BLEU/ROUGE scores (optional)
   - Fact verification
   - Citation accuracy scoring

6. **Advanced Retrieval Analysis**
   - Identify chunks never retrieved
   - Analyze similarity score distribution
   - Optimize top-k parameter

---

## Troubleshooting

### Evaluation Fails: "No embedded chunks available"

**Cause:** Document chunks don't have embeddings

**Solution:**
1. Check that document was uploaded successfully
2. Verify embeddings were generated: `SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL`
3. Re-upload document if needed

### RAG Significantly Slower Than Baseline

**Cause:** Retrieval overhead outweighs context reduction

**Possible fixes:**
- Increase `DOCPILOT_EVAL_MAX_LATENCY_MS` threshold
- Check embedding model configuration
- Profile retrieval service

### Low Context Reduction

**Cause:** Document is small or chunks are large

**Possible fixes:**
- Decrease `DOCPILOT_EVAL_MIN_CONTEXT_REDUCTION` threshold
- Adjust chunking strategy (smaller chunks)

### Citation Preservation Below Threshold

**Cause:** Retrieved chunks contain fewer source sections

**Possible fixes:**
- Increase retrieval `top_k` to get more chunks
- Decrease retrieval `min_score` to be less strict
- Adjust `DOCPILOT_EVAL_MIN_CITATION_PRESERVATION` threshold

---

## See Also

- [Retrieval Service Documentation](RETRIEVAL.md)
- [Embedding Service Documentation](EMBEDDINGS.md)
- [Production Observability Documentation](OBSERVABILITY.md)
