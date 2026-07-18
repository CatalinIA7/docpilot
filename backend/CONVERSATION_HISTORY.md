# Conversation History

Persistent conversation history for document chat, enabling users to maintain conversational continuity across multiple messages while semantic retrieval continues on every request.

## Overview

**Purpose**: Allow users to have multiple persistent conversations per document, with full message history and citation preservation.

**Key Features**:
- Create and manage multiple conversations per document
- Persist user and assistant messages with citations
- Configurable context window (recent N messages)
- Full message history retrieval
- Automatic conversation timestamps
- Ownership verification on all operations
- Optional automatic title generation from first message

**Non-Goals**:
- Streaming responses
- Message editing or deletion
- Branching conversations
- Automatic summarization
- LLM-based title generation
- Multi-document conversations

## Data Model

### Conversation

Represents a user-document conversation.

**Table**: `conversations`

**Fields**:
- `id` (STRING, PK): UUID identifier
- `user_id` (INT, FK): User owning the conversation
- `document_id` (STRING, FK): Document being discussed
- `title` (STRING): Conversation title (auto-generated from first message if not provided)
- `created_at` (DATETIME): Creation timestamp (indexed)
- `updated_at` (DATETIME): Last update timestamp (indexed)

**Relationships**:
- `user` → User (many conversations per user)
- `document` → Document (many conversations per document)
- `messages` → Message[] (one conversation per message, cascade delete)

**Constraints**:
- Non-null user_id, document_id, title
- Created/updated timestamps in UTC

### Message

Represents a single message (user or assistant) in a conversation.

**Table**: `messages`

**Fields**:
- `id` (STRING, PK): UUID identifier
- `conversation_id` (STRING, FK): Conversation this message belongs to (indexed)
- `role` (STRING): Message role - `"user"` or `"assistant"`
- `content` (TEXT): Message body
- `citations` (JSON): Array of citation objects (persisted from assistant responses)
- `created_at` (DATETIME): Creation timestamp (indexed)

**Citation Object** (stored in JSON):
```json
{
  "source_id": 1,
  "page": 5,
  "paragraph": 3,
  "excerpt": "Text excerpt..."
}
```

**Constraints**:
- Non-null conversation_id, role, content
- Citations default to empty array []
- Role must be "user" or "assistant"

## Persistence Model

### User Message Persistence

**When**: Immediately before generation

**Workflow**:
1. User sends question
2. Validate ownership
3. **Persist user message** (immediately)
4. Retrieve chunks
5. Generate answer
6. Persist assistant message

**Rationale**: If generation fails, the user message is retained for debugging/replay

### Assistant Message Persistence

**When**: After successful generation

**Workflow**:
1. Receive answer from AI service
2. Process citations (validate source_ids)
3. **Persist assistant message** with citations
4. Return response to client

**Rationale**: Only persist if generation succeeded; preserve citation metadata

### Failure Handling

**Generation fails**:
- User message persisted ✓
- Assistant message NOT created
- Error response to client
- Observable in observability framework

**Retrieval fails**:
- User message NOT persisted (fails before persistence)
- Error response to client

## Configuration

**Environment Variable**: `DOCPILOT_CONVERSATION_MAX_MESSAGES`

**Type**: Positive integer

**Default**: `10`

**Purpose**: Maximum number of recent messages to include in chat context

**Validation**: Must be > 0

**Example**:
```bash
export DOCPILOT_CONVERSATION_MAX_MESSAGES=20
```

## API Endpoints

### Create Conversation

**Endpoint**: `POST /documents/{document_id}/conversations`

**Authentication**: Required (Bearer token)

**Request**:
```json
{
  "title": "Optional conversation title",
  "question": "Optional first question"
}
```

**Response** (201):
```json
{
  "id": "conv-uuid",
  "title": "Conversation title",
  "created_at": "2026-07-18T10:30:00",
  "updated_at": "2026-07-18T10:30:00",
  "message_count": 0,
  "last_message_at": null
}
```

**Errors**:
- 401: Not authenticated
- 404: Document not found
- 500: Creation failed

**Notes**:
- If title not provided, generated from document filename
- Document must be owned by authenticated user

### List Conversations

**Endpoint**: `GET /documents/{document_id}/conversations`

**Authentication**: Required

**Query Parameters**: None

**Response** (200):
```json
[
  {
    "id": "conv-uuid-1",
    "title": "First conversation",
    "created_at": "2026-07-18T10:00:00",
    "updated_at": "2026-07-18T10:30:00",
    "message_count": 5,
    "last_message_at": "2026-07-18T10:30:00"
  },
  {
    "id": "conv-uuid-2",
    "title": "Second conversation",
    "created_at": "2026-07-18T09:00:00",
    "updated_at": "2026-07-18T09:45:00",
    "message_count": 3,
    "last_message_at": "2026-07-18T09:45:00"
  }
]
```

**Ordering**: Newest updated first

**Errors**:
- 401: Not authenticated
- 404: Document not found

### Get Conversation Details

**Endpoint**: `GET /conversations/{conversation_id}`

**Authentication**: Required

**Response** (200):
```json
{
  "id": "conv-uuid",
  "title": "Conversation title",
  "created_at": "2026-07-18T10:00:00",
  "updated_at": "2026-07-18T10:30:00",
  "message_count": 2,
  "last_message_at": "2026-07-18T10:30:00",
  "messages": [
    {
      "id": "msg-1",
      "role": "user",
      "content": "What is this about?",
      "citations": [],
      "created_at": "2026-07-18T10:15:00"
    },
    {
      "id": "msg-2",
      "role": "assistant",
      "content": "This document discusses...",
      "citations": [
        {
          "source_id": 1,
          "page": 5,
          "paragraph": 2,
          "excerpt": "..."
        }
      ],
      "created_at": "2026-07-18T10:16:00"
    }
  ]
}
```

**Message Ordering**: Chronological (oldest first)

**Errors**:
- 401: Not authenticated
- 404: Conversation not found

### Continue Conversation (Chat)

**Endpoint**: `POST /documents/{document_id}/chat`

**Authentication**: Required

**Request**:
```json
{
  "question": "Follow-up question",
  "conversation_id": "conv-uuid"  # Optional
}
```

**Response** (200):
```json
{
  "answer": "Assistant response...",
  "citations": [
    {
      "source_id": 1,
      "page": 5,
      "paragraph": 2,
      "excerpt": "..."
    }
  ]
}
```

**Behavior**:
- If `conversation_id` provided:
  - Verify ownership
  - Load recent messages
  - Persist user message
  - Generate answer
  - Persist assistant message
  - Return response
- If `conversation_id` not provided:
  - Single-turn chat (no persistence)
  - Retrieve chunks
  - Generate answer
  - Return response

**Errors**:
- 400: Document has no content or embeddings, no relevant chunks found
- 401: Not authenticated
- 404: Document or conversation not found
- 502: AI or retrieval service unavailable
- 503: Services not configured

### Delete Conversation

**Endpoint**: `DELETE /conversations/{conversation_id}`

**Authentication**: Required

**Response**: 204 No Content

**Behavior**:
- Delete conversation
- Delete all messages (cascaded)
- Do NOT delete document

**Errors**:
- 401: Not authenticated
- 404: Conversation not found

## Context Window

### Purpose

Limit conversation history sent to LLM to control costs and focus on recent context.

### Implementation

**Configuration**: `CONVERSATION_MAX_MESSAGES` (default: 10)

**Behavior**:
1. User sends message + conversation_id
2. Load most recent N messages from conversation
3. Messages ordered chronologically
4. Include in chat context (not shown to LLM directly in current implementation)
5. Retrieve chunks on every request (unchanged RAG behavior)
6. Generate answer (may reference recent messages in follow-up context)

**Example** (MAX_MESSAGES=10):
- Conversation has 25 messages
- Load messages [16, 17, ..., 25] (most recent 10)
- User message is message #26 (persisted immediately)
- Generation happens with up to 10 previous messages in context

### Notes

- Context window complements semantic retrieval, doesn't replace it
- Every request performs fresh retrieval on current question
- No conversation summarization or compression
- Recent messages provide continuity, retrieval provides relevance

## Ownership Verification

**All operations verify**:
- Authenticated user exists
- User owns the document
- User owns the conversation (if applicable)

**Implementation**:
- Document ownership checked via `Document.user_id == current_user.id`
- Conversation ownership checked via `Conversation.user_id == current_user.id`
- Returns 404 (not 403) to avoid confirming resource existence for other users

**Denied Operations**:
- Creating conversation for document user doesn't own
- Accessing another user's conversation
- Deleting another user's conversation

## Integration with Existing Systems

### Unchanged

- **Retrieval Service**: Continues to retrieve chunks independently on every request
- **AI Service**: Receives retrieved chunks, generates answers as before
- **Authentication**: Uses existing JWT auth
- **Documents/Uploads**: Unaffected
- **Evaluation Framework**: Operates independently (no conversation context by default)

### New Integration Points

- **Chat Endpoint**: Now accepts optional `conversation_id` parameter
- **Database**: Two new tables (Conversation, Message)
- **Models**: Two new models with relationships

### Backward Compatibility

- Chat endpoint works without `conversation_id` (single-turn chat)
- Existing tests unchanged
- Existing API responses unchanged
- No changes to document endpoints

## Citation Persistence

### Workflow

1. AI service returns `(answer, citations)` with source_ids
2. Citations validated against retrieved chunk range
3. Invalid citations skipped with warning
4. Remaining citations converted to database format:
   ```python
   {
       "source_id": int,
       "page": int,
       "paragraph": int,
       "excerpt": str,
   }
   ```
5. Persisted with assistant message as JSON array

### Non-Regeneration

- Citations retrieved from database, not regenerated
- Preserves exact AI service output
- No re-validation on retrieval (assumes source metadata is stable)

## Title Generation

### Automatic Generation

If conversation created without title:
```python
title = f"Conversation with {document.filename}"
```

### Manual Title

Explicitly provided in conversation creation:
```python
title = "My custom title"
```

### Implementation

No LLM invocation - simple string truncation.

```python
def _generate_title_from_question(question: str, max_length: int = 50) -> str:
    """Truncate at word boundary with ellipsis."""
    title = question.strip()
    if len(title) > max_length:
        truncated = title[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > 20:
            title = truncated[:last_space] + "..."
        else:
            title = truncated + "..."
    return title
```

## Observability

### Integration Points

Current implementation focuses on core functionality. Observability integration points for future enhancement:

- Conversation creation tracked (logging)
- Message persistence tracked (logging)
- Deletion tracked (logging)
- Errors in persistence logged (no-block-on-failure pattern)

### Future Enhancements

- Metrics: conversation count, average message count, context usage
- Tracing: message persistence latency
- Events: conversation lifecycle, message patterns

## Testing

### Test Coverage

**17 tests** organized in 5 test classes:

1. **TestConversationCreation** (4 tests):
   - Create with title
   - Create without title (auto-generated)
   - Reject nonexistent document
   - Reject wrong owner

2. **TestMessagePersistence** (4 tests):
   - Add user message
   - Add assistant message with citations
   - Message ordering (chronological)
   - Citation persistence

3. **TestConversationRetrieval** (4 tests):
   - Get conversation by ID
   - Reject wrong user
   - List conversations
   - Filter by document

4. **TestConversationDeletion** (2 tests):
   - Delete conversation and messages
   - Reject wrong user

5. **TestTitleGeneration** (3 tests):
   - Short titles unchanged
   - Long titles truncated
   - Truncation respects word boundaries

### Mocking

- Database fixtures use test database
- Registered user fixtures for authentication tests
- Uploaded document fixtures for document ownership tests

### Running Tests

```bash
pytest tests/test_conversations.py -v
```

All 17 tests pass.

## Example Workflows

### Workflow 1: Create Conversation and Ask Questions

```bash
# 1. Create conversation
POST /documents/doc-123/conversations
{
  "title": "Understanding Chapter 3"
}
→ Response: { "id": "conv-456", ... }

# 2. First message
POST /documents/doc-123/chat
{
  "question": "What is the main topic?",
  "conversation_id": "conv-456"
}
→ User message persisted
→ Chunks retrieved
→ Answer generated
→ Assistant message persisted

# 3. Follow-up question
POST /documents/doc-123/chat
{
  "question": "Can you elaborate on that?",
  "conversation_id": "conv-456"
}
→ Recent messages loaded (~10)
→ User message persisted
→ Chunks retrieved (fresh)
→ Answer generated (may reference previous context)
→ Assistant message persisted

# 4. View conversation history
GET /conversations/conv-456
→ All messages with citations, chronological order

# 5. Delete conversation
DELETE /conversations/conv-456
→ Conversation and all messages deleted
```

### Workflow 2: Single-Turn Chat (No Persistence)

```bash
# No conversation_id = single-turn chat
POST /documents/doc-123/chat
{
  "question": "Quick question?",
  "conversation_id": null
}
→ No message persistence
→ Chunks retrieved
→ Answer generated
→ Response returned
```

### Workflow 3: Multiple Conversations per Document

```bash
# Create two conversations for same document
POST /documents/doc-123/conversations { "title": "Conv 1" } → conv-1
POST /documents/doc-123/conversations { "title": "Conv 2" } → conv-2

# List conversations for document
GET /documents/doc-123/conversations
→ [conv-1, conv-2, ...]

# Each maintains independent history
POST /documents/doc-123/chat {"question": "Q1", "conversation_id": "conv-1"}
POST /documents/doc-123/chat {"question": "Q2", "conversation_id": "conv-2"}
```

## Database Schema

```sql
CREATE TABLE conversations (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    document_id VARCHAR(36) NOT NULL REFERENCES documents(id),
    title VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_document_id (document_id),
    INDEX idx_created_at (created_at),
    INDEX idx_updated_at (updated_at)
);

CREATE TABLE messages (
    id VARCHAR(36) PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL REFERENCES conversations(id),
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    citations JSON NOT NULL DEFAULT '[]',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_created_at (created_at)
);
```

## Key Files

- `backend/models.py`: Added Conversation, Message models
- `backend/config.py`: Added CONVERSATION_MAX_MESSAGES
- `backend/schemas.py`: Added conversation request/response schemas
- `backend/conversation_service.py`: Business logic service
- `backend/routers/conversations.py`: REST endpoints
- `backend/routers/chat.py`: Retrieval-backed chat with optional `conversation_id`
- `backend/main.py`: Conversation router registration
- `backend/tests/test_conversations.py`: Focused conversation tests

## Summary

Conversation history provides persistent, user-friendly continuity for document chat while preserving the core RAG pipeline. Users can create, continue, retrieve, and delete conversations with full message and citation persistence, automatic timestamp tracking, and flexible title management.

Implementation remains backward-compatible (single-turn chat still works),
ownership-verified, and covered by the full backend test suite.
