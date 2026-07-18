# Evaluation Framework - Quick Start Guide

## What You Now Have

A complete evaluation system to measure AI response quality and citation accuracy. This enables data-driven comparison between your current full-document approach and future RAG implementation.

## 5 Core Metrics

1. **Response Latency** - How fast AI responds (milliseconds)
2. **Token Usage** - Cost tracking per question
3. **Citation Accuracy** - How well sources are cited (0-100%)
4. **Answer Quality** - Factual correctness (0-100%)
5. **Citation Coverage** - % of questions with citations

## Next Steps (In Order)

### Step 1: Create a Benchmark Dataset (10-15 minutes)

```bash
cd backend

# Create your first benchmark question interactively
python eval_cli.py create-question \
  --document-id=<your-doc-id> \
  --user-id=1

# Create 10-15 questions representing different aspects of your document
# Focus on questions that need citations
```

Example questions:
- "What is the main purpose of this document?"
- "What are the key features described?"
- "What support options are available?"
- "What is the pricing structure?"

### Step 2: Run Baseline Evaluation

```bash
# Run evaluation against all benchmark questions
python eval_cli.py run \
  --document-id=<your-doc-id> \
  --run-name="Baseline: Full Document" \
  --user-id=1

# Note the Run ID from the output (e.g., Run ID: 42)
```

This creates a baseline to measure future improvements against.

### Step 3: View Results

```bash
# See all your evaluation runs
python eval_cli.py list-runs --user-id=1

# View detailed results
python eval_cli.py view-run --run-id=42
```

### Step 4: Prepare for RAG

When you implement Retrieval-Augmented Generation (chunking + retrieval):

```bash
# Run evaluation with RAG approach
python eval_cli.py run \
  --document-id=<your-doc-id> \
  --run-name="RAG: Chunked Retrieval" \
  --user-id=1 \
  --approach=rag-chunked

# Note the new Run ID (e.g., 43)
```

### Step 5: Compare Results

```bash
# Compare baseline vs RAG
python eval_cli.py view-run --run-id=42
python eval_cli.py view-run --run-id=43

# Calculate improvement percentages:
# - Faster latency = better (lower is better)
# - Better citation accuracy = better (higher is better)
```

## REST API Examples

### Create Benchmark Question

```bash
curl -X POST http://localhost:8000/evaluation/benchmark-questions?document_id=abc \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the warranty?",
    "expected_answer_summary": "2-year warranty covering all parts",
    "expected_citation_count": 1
  }'
```

### Run Evaluation

```bash
curl -X POST http://localhost:8000/evaluation/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "run_name": "Baseline",
    "document_id": "abc",
    "approach": "full-document"
  }'
```

### Compare Two Runs

```bash
curl http://localhost:8000/evaluation/compare/42/43 \
  -H "Authorization: Bearer $TOKEN"
```

## Database Models

Three new tables have been created:

- `benchmark_questions` - Test questions per document
- `evaluation_runs` - Summary metrics for each evaluation
- `evaluation_results` - Per-question details (citations, latency, etc.)

## Key Features to Note

✅ **Already Implemented:**
- Citation accuracy calculation
- Response latency measurement
- Citation coverage tracking
- Per-question result storage
- Run comparison with improvement percentages

⏳ **Ready for Future Enhancement:**
- OpenAI token tracking (update ai_service.py to return tokens)
- LLM-based answer quality scoring
- Scheduled evaluations
- Results export (CSV/JSON)
- Frontend dashboard

## Important Notes

1. **Answer Quality**: Currently set to 0.0. You can:
   - Manually review and set via API
   - Use an LLM to auto-grade against expected summary
   - Implement keyword matching logic

2. **Token Usage**: Infrastructure ready, but currently 0 values. To enable:
   - Capture `response.usage.total_tokens` from OpenAI
   - Return from `ai_service.answer_question()`
   - Evaluator automatically stores it

3. **Citation Accuracy Scoring**:
   - Checks if citation IDs are valid (1 to max sections)
   - Scores based on count match + validity
   - Formula: (count_match × 0.5) + (validity × 0.5)

## Next Major Feature: RAG Implementation

Once you have a baseline evaluation, the next step is:

1. Implement document chunking
2. Add vector embeddings
3. Create retrieval logic
4. Re-run evaluation with RAG approach
5. Compare metrics to measure improvements

The evaluation framework will prove the value of RAG with real numbers!

## Need Help?

See full documentation in `backend/EVALUATION.md`:
- Complete API reference
- Database schema details
- CLI command reference
- Sample benchmark structure
- Integration patterns
