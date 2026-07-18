# Evaluation Framework

The evaluation framework lets you measure AI response quality, citation accuracy, and performance metrics. It provides a foundation for comparing different approaches (full-document vs. retrieval-based) using the same benchmark.

## Features

- **Benchmark Management**: Create and manage test questions for documents
- **Automated Runs**: Run evaluations against benchmark questions
- **5 Key Metrics**:
  - **Response Latency**: Time to get an AI answer (ms)
  - **Token Usage**: Number of tokens consumed per question
  - **Citation Accuracy**: How well citations match the document (0.0-1.0)
  - **Answer Quality**: Factual correctness rating (0.0-1.0)
  - **Citation Coverage**: % of questions that received citations

- **Historical Tracking**: Store evaluation results in database
- **Run Comparison**: Compare two evaluation runs to measure improvements
- **Dual Interface**: CLI for automation + REST API for the UI

## Architecture

### Database Models

**BenchmarkQuestion** - Test questions for a document
```python
- id: int (primary key)
- document_id: str
- question: str
- expected_answer_summary: str
- expected_citation_count: int
- created_at: datetime
```

**EvaluationRun** - Summary of an evaluation run
```python
- id: int (primary key)
- user_id: int
- run_name: str
- approach: str (default: "full-document")
- total_questions: int
- questions_with_citations: int
- avg_latency_ms: float
- total_tokens_used: int
- avg_tokens_per_question: float
- citation_accuracy_score: float (0.0-1.0)
- answer_quality_score: float (0.0-1.0)
- citation_coverage: float (0.0-1.0)
- created_at: datetime
```

**EvaluationResult** - Per-question result in a run
```python
- id: int (primary key)
- evaluation_run_id: int
- benchmark_question_id: int
- ai_response: str
- citations_returned: int
- latency_ms: float
- tokens_used: int
- citation_accuracy: float
- answer_quality: float
- metadata: dict (JSON)
- created_at: datetime
```

### Metrics Calculation

**Citation Accuracy** (0.0-1.0):
- If expected 0 citations: score 1.0 for 0 citations, 0.8 for any
- If expected >0 citations:
  - 50% weight: citation count match vs expected
  - 50% weight: valid source IDs (1 to max section ID)

**Answer Quality** (0.0-1.0):
- Initially set to 0.0 (to be updated by user or inference)
- Can be manually set via API or derived from expected answer summary

**Citation Coverage**:
- Percentage of questions where AI provided at least one citation

## CLI Usage

### Setup

```bash
cd backend
python eval_cli.py --help
```

### Create Benchmark Questions

```bash
# Interactive creation
python eval_cli.py create-question --document-id=abc-123 --user-id=1

# List existing questions
python eval_cli.py list-questions --document-id=abc-123 --user-id=1
```

Example question creation:
```
Question: What are the main benefits of this product?
Expected answer summary: Lists 3-4 key benefits with specific metrics
Expected number of citations: 2
```

### Run Evaluation

```bash
python eval_cli.py run \
  --document-id=abc-123 \
  --run-name="Baseline - Full Document" \
  --user-id=1
```

Output example:
```
📊 Running evaluation: Baseline - Full Document
   Document: product_guide.pdf
   Questions: 12
   Approach: full-document

✅ Evaluation complete in 15.3s

📈 Results (Run ID: 42):
   Questions evaluated: 12
   Questions with citations: 10 (83.3%)
   Avg latency: 1245.3ms
   Avg tokens per question: 850
   Citation accuracy: 91.7%
   Answer quality: 75.0%
```

### View Results

```bash
# List all runs
python eval_cli.py list-runs --user-id=1

# View details of specific run
python eval_cli.py view-run --run-id=42
```

## REST API Usage

### Create Benchmark Question

```http
POST /evaluation/benchmark-questions?document_id=abc-123
Authorization: Bearer <token>
Content-Type: application/json

{
  "question": "What is the warranty period?",
  "expected_answer_summary": "Product comes with 2-year warranty covering manufacturing defects",
  "expected_citation_count": 1
}
```

Response:
```json
{
  "id": 1,
  "document_id": "abc-123",
  "question": "What is the warranty period?",
  "expected_answer_summary": "...",
  "expected_citation_count": 1,
  "created_at": "2026-07-18T10:30:00Z"
}
```

### List Benchmark Questions

```http
GET /evaluation/benchmark-questions/abc-123
Authorization: Bearer <token>
```

### Run Evaluation

```http
POST /evaluation/runs
Authorization: Bearer <token>
Content-Type: application/json

{
  "run_name": "Baseline - Full Document",
  "document_id": "abc-123",
  "approach": "full-document"
}
```

Response includes detailed results for all questions plus aggregated metrics.

### List Evaluation Runs

```http
GET /evaluation/runs
Authorization: Bearer <token>
```

### Get Run Details

```http
GET /evaluation/runs/42
Authorization: Bearer <token>
```

### Compare Two Runs

```http
GET /evaluation/compare/41/42
Authorization: Bearer <token>
```

Response:
```json
{
  "run1": { /* full run 1 data */ },
  "run2": { /* full run 2 data */ },
  "latency_improvement": -5.2,
  "token_improvement": -8.1,
  "citation_accuracy_improvement": 12.5,
  "answer_quality_improvement": 8.3
}
```

Positive values indicate improvement.

## Example Workflow

### Step 1: Create Sample Benchmark Dataset

```bash
# Create questions for a document
python eval_cli.py create-question --document-id=sales-doc-1 --user-id=1
# ... repeat for 10-15 questions
python eval_cli.py list-questions --document-id=sales-doc-1 --user-id=1
```

### Step 2: Run Baseline Evaluation

```bash
python eval_cli.py run \
  --document-id=sales-doc-1 \
  --run-name="Baseline: Full Document" \
  --user-id=1 \
  --approach=full-document
```

Save the run ID (e.g., 42).

### Step 3: Later, Run with RAG Approach

```bash
# After implementing chunking and retrieval...
python eval_cli.py run \
  --document-id=sales-doc-1 \
  --run-name="RAG: Chunked Retrieval" \
  --user-id=1 \
  --approach=rag-chunked
```

Save the new run ID (e.g., 43).

### Step 4: Compare Results

```bash
python eval_cli.py view-run --run-id=42
python eval_cli.py view-run --run-id=43
```

Or via API:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/evaluation/compare/42/43
```

## Sample Benchmark Dataset

Here's a structure for a reference benchmark with 12-15 questions across different categories:

### Document: "Sales & Support Guide"

**Category 1: Product Information (3 questions)**
1. "What are the main product features?" → Expected citations: 2
2. "What is the warranty period?" → Expected citations: 1
3. "What file formats are supported?" → Expected citations: 2

**Category 2: Support & Troubleshooting (4 questions)**
4. "How do I reset my password?" → Expected citations: 1
5. "What should I do if the app crashes?" → Expected citations: 2
6. "How do I contact support?" → Expected citations: 1
7. "Is there a mobile app?" → Expected citations: 1

**Category 3: Pricing & Plans (3 questions)**
8. "What are the pricing tiers?" → Expected citations: 3
9. "Can I change my plan?" → Expected citations: 1
10. "Is there a free trial?" → Expected citations: 1

**Category 4: Specific Details (3 questions)**
11. "What is the maximum file size?" → Expected citations: 1
12. "How is my data stored?" → Expected citations: 2
13. "Can I export my data?" → Expected citations: 1

## Integration Notes

### Token Tracking (Future)

Currently, `tokens_used` is set to 0. To enable token tracking:

1. Capture token usage from OpenAI API responses
2. Store in `ai_service.answer_question()` return tuple
3. Update `Evaluator` to extract and store token counts

```python
# In ai_service.py
response = client.chat.completions.create(...)
tokens_used = response.usage.total_tokens
return answer, citations, tokens_used
```

### Answer Quality Scoring (Future)

Options for scoring answer quality (0.0-1.0):

1. **Manual Review**: User sets scores via API
2. **LLM-Based**: Use another LLM to grade against expected summary
3. **Keyword Matching**: Check if expected key terms appear in answer
4. **Hybrid**: Combination of above

### Scheduled Evaluations

DocPilot does not ship an application scheduler. An external trusted job can call
the existing CLI or authenticated API if recurring evaluation becomes necessary;
provider cost and benchmark data should be reviewed before enabling it.

## Operating Workflow

1. Populate a representative benchmark dataset.
2. Run full-context and RAG evaluations against the same questions.
3. Compare context reduction, latency, retrieval, and citation results.
4. Investigate regressions before changing model or retrieval configuration.
5. Keep provider-backed evaluation out of automated tests and unapproved accounts.
