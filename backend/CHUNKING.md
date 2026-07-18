# Document Chunking Foundation for RAG

The chunking module provides deterministic, metadata-preserving document chunking for Retrieval-Augmented Generation (RAG).

## Overview

The chunker converts extracted document sections (from PDF or DOCX) into smaller, overlapping chunks while preserving citation metadata (page numbers for PDF, paragraph numbers for DOCX).

## Architecture

### Core Components

**DocumentChunk** dataclass:
```python
@dataclass
class DocumentChunk:
    chunk_index: int              # Global sequence position (0-indexed)
    text: str                     # Chunk content
    page: int | None              # Page number (PDF)
    paragraph: int | None         # Paragraph number (DOCX)
    source_section_id: int | None # ID of source section
    char_start: int | None        # Start offset in original section
    char_end: int | None          # End offset in original section
```

**ChunkingConfig** class:
- `chunk_size`: Maximum characters per chunk (default: 500)
- `overlap`: Overlapping characters between consecutive chunks (default: 50)
- Validates: chunk_size > 0, overlap >= 0, overlap < chunk_size

**Chunker** class:
- Accepts `ChunkingConfig` and `SourceSection` list
- Returns ordered list of `DocumentChunk` objects
- Preserves metadata across all chunks from a section

## Algorithm

### Process

1. **Per-section processing**: Each section is chunked independently to preserve metadata
2. **Size check**: If section ≤ chunk_size, return as single chunk
3. **Intelligent splitting**:
   - **Sentence boundaries** (preferred): Uses regex to split at sentence endings
   - **Character-based** (fallback): Uses sliding window with overlap for text without clear boundaries
4. **Overlap application**: Consecutive chunks share the last N characters (configurable)
5. **Sequential indexing**: All chunks assigned global indices in order

### Boundary Preservation

- **PDF sections**: All chunks retain the page number
- **DOCX sections**: All chunks retain the paragraph number
- **No cross-boundary mixing**: Content from different pages/paragraphs stays separate
- **Source tracking**: All chunks retain their source section ID

## Usage

### Basic Usage

```python
from document_parser import extract_document_text
from chunking import Chunker, ChunkingConfig
from pathlib import Path

# Extract document
extracted = extract_document_text(Path("document.pdf"))
sections = extracted["_sections"]

# Create chunker with defaults (500 char chunks, 50 char overlap)
chunker = Chunker()
chunks = chunker.chunk(sections)

# Or with custom config
config = ChunkingConfig(chunk_size=1000, overlap=100)
chunker = Chunker(config)
chunks = chunker.chunk(sections)
```

### Working with Chunks

```python
for chunk in chunks:
    print(f"Chunk {chunk.chunk_index}")
    if chunk.page:
        print(f"  From PDF page {chunk.page}")
    elif chunk.paragraph:
        print(f"  From DOCX paragraph {chunk.paragraph}")
    print(f"  Text: {chunk.text[:100]}...")
```

## Metadata Preservation

### Example: PDF Document

```python
sections = [
    SourceSection(source_id=1, text="Page 1 content...", page=1),
    SourceSection(source_id=2, text="Page 2 content...", page=2),
]
chunks = Chunker().chunk(sections)

# All chunks from section 1 will have page=1
# All chunks from section 2 will have page=2
# No mixing of page numbers across chunks
```

### Example: DOCX Document

```python
sections = [
    SourceSection(source_id=1, text="Paragraph 1...", paragraph=1),
    SourceSection(source_id=2, text="Paragraph 2...", paragraph=2),
]
chunks = Chunker().chunk(sections)

# All chunks from section 1 will have paragraph=1
# All chunks from section 2 will have paragraph=2
```

## Overlap Behavior

With `chunk_size=500, overlap=50`:

```
Original text:
[0.................................... 500)

Chunk 1: [0............................... 500)
Chunk 2:                         [450....... 950)
         ^-- Last 50 chars repeated as overlap

Chunk 3:                                 [900..... 1400)
         ^-- Last 50 chars repeated as overlap
```

The overlap ensures:
- Smooth information flow between chunks
- Context preservation at chunk boundaries
- Reduced information loss during retrieval

## Configuration

### Default Values

- **chunk_size**: 500 characters (balance between context and granularity)
- **overlap**: 50 characters (10% overlap for smooth transitions)

### Validation

Invalid configurations raise `ValueError`:

```python
ChunkingConfig(chunk_size=0)        # ❌ chunk_size must be > 0
ChunkingConfig(chunk_size=100, overlap=100)  # ❌ overlap must be < chunk_size
ChunkingConfig(chunk_size=100, overlap=-1)   # ❌ overlap must be >= 0
```

## Test Coverage

### Configuration Tests (5)
- Valid and default configs
- Validation for chunk_size > 0
- Validation for overlap >= 0
- Validation for overlap < chunk_size

### Basic Behavior Tests (4)
- Empty sections → no chunks
- Short text (≤ chunk_size) → single chunk
- No empty chunks produced
- Sequential chunk indexing

### Metadata Preservation Tests (4)
- PDF page numbers preserved in all chunks
- DOCX paragraph numbers preserved in all chunks
- Source section ID tracking
- Multiple sections with independent metadata

### Advanced Tests (13)
- Deterministic output consistency
- Overlap text duplication
- Zero overlap behavior
- Multiple section ordering
- Long text without sentence boundaries
- Character offset tracking
- Single long words
- Whitespace handling
- Mixed PDF/DOCX sections
- Sentence boundary preference
- DocumentChunk dataclass

**Total: 26 tests, 100% passing**

## Non-Invasive Design

The chunking module is designed to be independent and reusable:

- ✅ No database dependencies
- ✅ No authentication requirements
- ✅ No FastAPI coupling
- ✅ No OpenAI dependencies
- ✅ No retrieval logic mixed in
- ✅ Pure Python dataclasses and functions
- ✅ Easy to integrate later into chat endpoint, embedding pipeline, etc.

## Future Extensions

The foundation is designed to support:

1. **Embedding generation** (one chunk = one embedding later)
2. **Vector storage** (chunks → embeddings → vector DB)
3. **Semantic retrieval** (similarity search over chunks)
4. **RAG integration** (retrieve chunks, augment prompt)
5. **Token-aware chunking** (track token count instead of characters)
6. **Hierarchical chunking** (sentences → paragraphs → sections)

## Performance Characteristics

- **Time Complexity**: O(n) where n = total characters in all sections
- **Space Complexity**: O(c) where c = number of chunks (typically n / (chunk_size - overlap))
- **Determinism**: 100% - same input always produces identical output
- **Metadata overhead**: Minimal - each chunk has 6 fields regardless of text size

## Example: Before and After

### Before (Full Document)

```python
# AI gets entire document at once
chat_prompt = f"Given this document:\n\n{full_document_text}\n\nQuestion: {user_question}"
response = openai.ChatCompletion.create(prompt=chat_prompt)
```

### After (With RAG - Future)

```python
# 1. Extract and chunk
sections = extract_document_text(path)["_sections"]
chunks = Chunker().chunk(sections)

# 2. Embed and retrieve (when vector store is added)
chunk_embeddings = embed_chunks(chunks)
similar_chunks = retrieve_chunks(user_question, chunk_embeddings, k=5)

# 3. Augment prompt with relevant chunks only
relevant_text = "\n".join(c.text for c in similar_chunks)
rag_prompt = f"Context:\n{relevant_text}\n\nQuestion: {user_question}"
response = openai.ChatCompletion.create(prompt=rag_prompt)

# 4. Cite from selected chunks
citations = extract_citations_from_chunks(response, similar_chunks)
```

## References

- Input: `SourceSection` from `document_parser.py`
- Output: `DocumentChunk` (new dataclass)
- Configuration: `ChunkingConfig` (new class)
- Processor: `Chunker` (new class)
