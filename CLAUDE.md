# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Retrieval-Augmented Generation (RAG) chatbot system for querying course materials. It uses ChromaDB for vector storage, Anthropic's Claude API with tool calling for response generation, and FastAPI for the backend API.

## Development Commands

### Setup and Installation
```bash
# Install dependencies
uv sync

# Create environment file (required before first run)
cp .env.example .env
# Then edit .env to add your ANTHROPIC_API_KEY
```

### Running the Application
```bash
# Quick start with script
./run.sh

# Manual start (from backend directory)
cd backend
uv run uvicorn app:app --reload --port 8000

# Access points
# - Web UI: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

### Database Management
```bash
# Clear vector database (forces rebuild on next startup)
rm -rf backend/chroma_db

# The database rebuilds automatically on server startup from docs/ directory
```

## Architecture Overview

### RAG Pipeline Flow

The system uses a **tool-based RAG architecture** where Claude decides when and how to search:

1. **User Query** → Frontend (`script.js`) sends POST to `/api/query`
2. **API Endpoint** (`app.py`) → Creates/retrieves session, delegates to RAG system
3. **RAG Orchestration** (`rag_system.py`) → Coordinates all components:
   - Retrieves conversation history from `SessionManager`
   - Calls `AIGenerator` with query + conversation history + tool definitions
   - Collects sources from `ToolManager`
   - Saves exchange to session
4. **AI Generation** (`ai_generator.py`) → Calls Anthropic API:
   - Claude decides whether to use `search_course_content` tool
   - If tool use: executes search via `ToolManager`, then calls API again with results
   - Returns synthesized answer
5. **Tool Execution** (when Claude searches):
   - `CourseSearchTool` (`search_tools.py`) → Executes search via `VectorStore`
   - `VectorStore` (`vector_store.py`) → Performs semantic search in ChromaDB:
     - Resolves course name using semantic matching on `course_catalog` collection
     - Builds metadata filters (course + lesson)
     - Searches `course_content` collection with embeddings
   - Returns formatted results with source attribution
6. **Response** → Backend returns `{answer, sources, session_id}` to frontend

### Key Architectural Patterns

**Two-Collection ChromaDB Design:**
- `course_catalog`: Stores course metadata (title, instructor, lessons) for semantic course name resolution
- `course_content`: Stores chunked course content for retrieval

**Tool-Based Retrieval (Not Direct RAG):**
- Claude uses `search_course_content` tool to retrieve context
- Supports parameters: `query` (required), `course_name` (optional), `lesson_number` (optional)
- More flexible than direct vector search - Claude controls retrieval strategy

**Session-Aware Conversations:**
- `SessionManager` maintains conversation history (default: last 2 exchanges)
- History passed to Claude as system context for follow-up questions
- Session IDs track conversations across multiple queries

**Sentence-Based Chunking with Overlap:**
- `DocumentProcessor` splits on sentence boundaries (not fixed character count)
- Configurable overlap prevents context loss at chunk boundaries
- Default: 800 char chunks, 100 char overlap

### Component Responsibilities

**`rag_system.py`** - Central orchestrator, owns all components, coordinates query flow
**`ai_generator.py`** - Anthropic API wrapper, handles tool execution loop
**`vector_store.py`** - ChromaDB wrapper, manages two collections, performs semantic search
**`document_processor.py`** - Parses course documents, performs sentence-based chunking
**`search_tools.py`** - Defines `search_course_content` tool, formats results for Claude
**`session_manager.py`** - Manages conversation state and history
**`app.py`** - FastAPI application, defines API endpoints, loads documents on startup
**`config.py`** - Centralized configuration loaded from `.env`

### Data Models (`models.py`)

**`Course`** - Represents a course (title is unique identifier, contains list of Lessons)
**`Lesson`** - Lesson within a course (number, title, optional link)
**`CourseChunk`** - Text chunk for vector storage (content, course_title, lesson_number, chunk_index)

## Working with Course Documents

### Expected Document Format
```
Course Title: [title]
Course Link: [url]
Course Instructor: [name]

Lesson 0: [lesson title]
Lesson Link: [url]
[lesson content...]

Lesson 1: [next lesson title]
[content...]
```

### Adding New Documents
1. Place `.txt`, `.pdf`, or `.docx` files in `docs/` directory
2. Restart server - `app.py:88-98` automatically loads all documents on startup
3. Documents are processed, chunked, embedded, and stored in ChromaDB
4. Duplicates are skipped based on course title

### Document Processing Pipeline
1. **Parse** (`document_processor.py:97-259`): Extract metadata, split by lesson markers
2. **Chunk** (`document_processor.py:25-91`): Sentence-based chunking with overlap
3. **Add Context** (`document_processor.py:186-188`): Prefix chunks with "Course X Lesson Y content:"
4. **Store Metadata** (`vector_store.py:135-160`): Add to `course_catalog` collection
5. **Store Content** (`vector_store.py:162-180`): Add chunks to `course_content` collection

## Key Configuration

All configuration in `backend/config.py` with `.env` overrides:

```python
ANTHROPIC_API_KEY    # Required - from .env
ANTHROPIC_MODEL      # "claude-sonnet-4-20250514"
EMBEDDING_MODEL      # "all-MiniLM-L6-v2" (sentence-transformers)
CHUNK_SIZE          # 800 characters
CHUNK_OVERLAP       # 100 characters
MAX_RESULTS         # 5 search results
MAX_HISTORY         # 2 conversation exchanges
CHROMA_PATH         # "./chroma_db" (relative to backend/)
```

## Important Implementation Details

### Tool Execution Loop (`ai_generator.py:89-135`)
When Claude returns `stop_reason: "tool_use"`:
1. Extract tool calls from response
2. Execute each tool via `ToolManager`
3. Build new message list: original query + assistant tool_use + user tool_results
4. Call API again WITHOUT tools to get final answer
5. Return synthesized response

### Course Name Resolution (`vector_store.py:102-116`)
Uses semantic search on `course_catalog` to handle:
- Partial matches (e.g., "Python" matches "Introduction to Python")
- Fuzzy matching (e.g., "MCP" matches "Model Context Protocol")
- Returns exact course title for filtering content search

### Source Attribution (`search_tools.py:88-114`)
- Tool formats results as: `[Course Title - Lesson X]\ncontent`
- Stores sources in `last_sources` list: `["Course - Lesson X", ...]`
- `ToolManager` retrieves sources after AI generation completes
- Frontend displays sources in collapsible section

### Frontend State Management (`script.js`)
- `currentSessionId` tracks active conversation
- First query: session_id is null, backend creates new session
- Subsequent queries: send session_id to maintain context
- Session ID returned in every response

## API Endpoints

### `POST /api/query`
Process user query with optional session context.

**Request:** `{query: string, session_id?: string}`
**Response:** `{answer: string, sources: string[], session_id: string}`

### `GET /api/courses`
Get course catalog statistics.

**Response:** `{total_courses: int, course_titles: string[]}`

## Testing the System

### Manual Testing via Web UI
1. Start server with `./run.sh`
2. Open `http://localhost:8000`
3. Try suggested questions or custom queries
4. Verify sources are displayed
5. Test follow-up questions to check session context

### Testing via API Documentation
1. Navigate to `http://localhost:8000/docs`
2. Expand `/api/query` endpoint
3. Click "Try it out"
4. Enter query and optional session_id
5. Execute and verify response structure

### Testing Course Name Matching
Try variations like:
- "What is covered in the Python course?" (tests fuzzy matching)
- "Tell me about lesson 2 in Python" (tests lesson filtering)
- "Search for arrays" (tests content search without filters)

## Modifying System Behavior

### Changing Claude's Behavior
Edit system prompt in `ai_generator.py:8-30` to adjust:
- Search tool usage rules
- Response format and style
- When to search vs use general knowledge

### Adjusting Search Results
- Modify `MAX_RESULTS` in `config.py` to return more/fewer chunks
- Change `VectorStore.search()` limit parameter for specific queries
- Adjust `CHUNK_SIZE` and `CHUNK_OVERLAP` to change granularity

### Adding New Tools
1. Create tool class implementing `Tool` interface in `search_tools.py`
2. Define `get_tool_definition()` with Anthropic tool schema
3. Implement `execute(**kwargs)` method
4. Register with `ToolManager` in `rag_system.py:22-25`

### Modifying Conversation History
- Change `MAX_HISTORY` in `config.py` to remember more/fewer exchanges
- Edit `SessionManager.get_conversation_history()` to change formatting
- Modify `ai_generator.py:61-65` to adjust how history is passed to Claude

## Common Issues and Solutions

**ChromaDB persistence:** Collections persist to disk at `backend/chroma_db/`. Delete this directory to force rebuild.

**Embedding model caching:** First run downloads `all-MiniLM-L6-v2` (~90MB) to `~/.cache/huggingface/`.

**Course not found:** Course name resolution is semantic, but may fail if query is too different from actual title. Check exact titles via `/api/courses` endpoint.

**Empty search results:** Can occur if:
- No documents match query semantically
- Course/lesson filter too restrictive
- Documents not loaded properly (check startup logs)

**Session context not working:** Ensure same `session_id` is sent with each query in a conversation thread.
