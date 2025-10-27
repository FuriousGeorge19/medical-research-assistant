# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Retrieval-Augmented Generation (RAG) chatbot system for querying medical research literature. It uses ChromaDB for vector storage, Anthropic's Claude API with tool calling for response generation, and FastAPI for the backend API. The system provides evidence-based answers to medical research questions by searching through curated peer-reviewed medical papers.

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

# The database rebuilds automatically on server startup from medical_papers/ directory
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
   - Claude decides whether to use `search_medical_literature` tool
   - If tool use: executes search via `ToolManager`, then calls API again with results
   - Returns synthesized answer with medical disclaimers
5. **Tool Execution** (when Claude searches):
   - `MedicalLiteratureSearchTool` (`search_tools.py`) → Executes search via `VectorStore`
   - `VectorStore` (`vector_store.py`) → Performs semantic search in ChromaDB:
     - Builds metadata filters (topic, paper_type, year_range)
     - Searches `paper_content` collection with embeddings
     - Retrieves paper URLs from `paper_catalog` collection
   - Returns formatted results with source attribution (Title - Year - Journal)
6. **Response** → Backend returns `{answer, sources: [{text, url}], session_id}` to frontend

### Key Architectural Patterns

**Two-Collection ChromaDB Design:**
- `paper_catalog`: Stores paper metadata (title, authors, journal, year, topic, PMCID, DOI)
- `paper_content`: Stores chunked paper content with metadata for filtered retrieval

**Tool-Based Retrieval (Not Direct RAG):**
- Claude uses `search_medical_literature` tool to retrieve context
- Supports parameters: `query` (required), `topic` (optional), `paper_type` (optional), `min_year`/`max_year` (optional)
- More flexible than direct vector search - Claude controls retrieval strategy

**Session-Aware Conversations:**
- `SessionManager` maintains conversation history (default: last 2 exchanges)
- History passed to Claude as system context for follow-up questions
- Session IDs track conversations across multiple queries

**Section-Based Chunking with Overlap:**
- `DocumentProcessor` parses JATS XML and chunks by sections
- Abstract stored as single chunk
- Body sections chunked with 800 char limit, 100 char overlap
- Each chunk prefixed with "Paper: [title] | Section: [section_title]"

### Component Responsibilities

**`rag_system.py`** - Central orchestrator, owns all components, coordinates query flow
**`ai_generator.py`** - Anthropic API wrapper, handles tool execution loop, medical-focused system prompt
**`vector_store.py`** - ChromaDB wrapper, manages two collections, performs semantic search with filters
**`document_processor.py`** - Parses JATS XML medical papers, performs section-based chunking
**`search_tools.py`** - Defines `search_medical_literature` tool, formats results with citations
**`session_manager.py`** - Manages conversation state and history
**`app.py`** - FastAPI application, defines API endpoints, loads medical papers on startup
**`config.py`** - Centralized configuration loaded from `.env`

### Data Models (`models.py`)

**`Paper`** - Represents a medical research paper:
- `title`: Full paper title (unique identifier)
- `pmcid`: PubMed Central ID (for URL generation)
- `doi`: Digital Object Identifier (fallback URL)
- `journal`: Journal name
- `year`: Publication year
- `authors`: List of author names
- `paper_type`: Type (e.g., "Review", "Research Article")
- `topic`: Primary topic from pre-assigned metadata
- `keywords`: Keywords extracted from paper

**`PaperChunk`** - Text chunk for vector storage:
- `content`: The actual text content
- `paper_title`: Which paper this chunk belongs to
- `pmcid`, `doi`, `journal`, `year`, `topic`: Metadata for filtering
- `section_title`: Section name (e.g., "Abstract", "Results", "Discussion")
- `chunk_index`: Position in document

## Working with Medical Papers

### Expected Document Format

Medical papers must be in **JATS XML format** (Journal Article Tag Suite), which is the standard for PubMed Central articles. Key structure:
- `<front>`: Contains metadata (title, authors, journal, publication date, PMCID, DOI, keywords)
- `<body>`: Contains paper sections with `<sec>` tags
- `<back>`: Contains references

### Abstract-Only Papers

The system automatically detects and **skips abstract-only papers** that lack full text. Detection uses:
1. XML comment: `<!-- document supplied by publisher as abstract only -->`
2. Absence of `<body>` element

### Topic Assignment

Papers are assigned topics from pre-assigned metadata JSON files:
- `medical_papers_metadata.json`: Primary metadata file mapping paper titles to topics
- `replacement_papers_metadata.json`: Secondary metadata file for replacement papers
- Topics are loaded during document processing and stored in both collections

### Adding New Documents

1. Place JATS XML files (`.xml`) in `medical_papers/` directory
2. Ensure topic metadata is in JSON files at project root
3. Restart server - `app.py:98-122` automatically loads all papers on startup
4. Papers are processed, chunked, embedded, and stored in ChromaDB
5. Duplicates are skipped based on paper title
6. Abstract-only papers are automatically skipped with console message

### Document Processing Pipeline

1. **Parse XML** (`document_processor.py:97-259`): Parse JATS XML, extract metadata from `<front>`
2. **Check Full Text** (`document_processor.py:261-272`): Verify paper has full body content
3. **Load Topics** (`document_processor.py:274-290`): Map paper title to topic from JSON metadata
4. **Extract Content** (`document_processor.py:197-259`):
   - Abstract from `<abstract>` element (single chunk)
   - Body sections from `<sec>` elements with titles
5. **Chunk Sections** (`document_processor.py:25-91`): Sentence-based chunking with 800 char limit, 100 overlap
6. **Add Context** (`document_processor.py:181-183`): Prefix chunks with "Paper: [title] | Section: [section]"
7. **Store Metadata** (`vector_store.py:135-160`): Add paper metadata to `paper_catalog` collection
8. **Store Content** (`vector_store.py:162-180`): Add chunks to `paper_content` collection

### Citation Format

Sources are formatted as: **"Title - Year - Journal"**

Example: "Intermittent Fasting: Myths, Fakes and Truth - 2022 - Nutrients"

URLs are generated from PMCID (preferred) or DOI:
- PMCID: `https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12345678/`
- DOI: `https://doi.org/10.1234/example`

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
CATALOG_COLLECTION  # "paper_catalog"
CONTENT_COLLECTION  # "paper_content"
DOCS_PATH           # "../medical_papers"
METADATA_PATH       # ".."
```

## Important Implementation Details

### Tool Execution Loop (`ai_generator.py:89-161`)

When Claude returns `stop_reason: "tool_use"`:
1. Extract tool calls from response
2. Execute each tool via `ToolManager`
3. Build new message list: original query + assistant tool_use + user tool_results
4. Call API again WITHOUT tools to get final answer
5. Handle edge cases where API returns empty content (graceful error message)
6. Return synthesized response

**Known Issue:** Follow-up queries after tool use sometimes return empty content. This is handled gracefully with temporary error handling code marked with `# TEMPORARY` comments. The root cause is conversation history + tool results formatting. This is intentionally left as a debugging exercise for students.

### Medical Literature Search Tool (`search_tools.py:16-127`)

Tool definition supports optional filters:
- `query` (required): Search query text
- `topic` (optional): Filter by topic (e.g., "Type 2 Diabetes Management")
- `paper_type` (optional): Filter by paper type (e.g., "Review")
- `min_year`, `max_year` (optional): Filter by publication year range

Results are formatted with citation and paper URL:
```python
source = {
    "text": "Title - Year - Journal",
    "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12345678/"
}
```

### Filtered Search (`vector_store.py:84-132`)

ChromaDB metadata filters are built dynamically:
```python
filter_dict = {}
if topic:
    filter_dict["topic"] = topic
if paper_type:
    filter_dict["paper_type"] = paper_type
if year_range:
    filter_dict["year"] = {"$gte": min_year, "$lte": max_year}
```

Search returns `SearchResults` with:
- `texts`: List of chunk content strings
- `metadatas`: List of metadata dicts (paper_title, section_title, year, journal, etc.)

### Source Attribution (`search_tools.py:88-127`)

1. Tool executes search and gets results
2. For each unique paper in results:
   - Extract title, year, journal from metadata
   - Get URL via `vector_store.get_paper_url()` (prefers PMCID over DOI)
   - Format as `{"text": "Title - Year - Journal", "url": "..."}`
3. Store sources in `last_sources` list
4. `ToolManager` retrieves sources after AI generation completes
5. Frontend displays sources as **plain text badges** (no hyperlinks yet - student exercise)

### Frontend State Management (`script.js`)

- `currentSessionId` tracks active conversation
- First query: session_id is null, backend creates new session
- Subsequent queries: send session_id to maintain context
- Session ID returned in every response

**Sources Display** (`script.js:113-152`):
- Sources received as `[{text: "...", url: "..."}, ...]`
- Currently displayed as plain text badges (hyperlink functionality not implemented)
- Students will add clickable hyperlinks as an exercise
- Backend provides URL data in source objects, but frontend ignores it for now

## API Endpoints

### `POST /api/query`

Process user query with optional session context.

**Request:**
```json
{
  "query": "What lifestyle changes help manage hypertension?",
  "session_id": "session_123" // optional
}
```

**Response:**
```json
{
  "answer": "Evidence-based answer with medical disclaimers...",
  "sources": [
    {
      "text": "Updates in the management of hypertension - 2023 - Journal of Hypertension",
      "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12345678/"
    }
  ],
  "session_id": "session_123"
}
```

### `GET /api/papers`

Get paper catalog statistics.

**Response:**
```json
{
  "total_papers": 34,
  "topics": [
    "Cancer Prevention & Screening",
    "Cardiovascular Health",
    "Infectious Diseases",
    "Mental Health",
    "Nutrition & Metabolism",
    "Sleep Medicine",
    "Type 2 Diabetes Management"
  ]
}
```

## Testing the System

### Manual Testing via Web UI

1. Start server with `./run.sh`
2. Open `http://localhost:8000`
3. Try suggested questions or custom medical queries
4. Verify sources are displayed (as plain text badges)
5. Test follow-up questions to check session context

Example queries:
- "What are the current treatments for type 2 diabetes?"
- "What does research show about the effectiveness of digital mental health apps?"
- "What are the guidelines for managing hypertension?"
- "What are the health effects of intermittent fasting?"

### Testing via API Documentation

1. Navigate to `http://localhost:8000/docs`
2. Expand `/api/query` endpoint
3. Click "Try it out"
4. Enter query and optional session_id
5. Execute and verify response structure

### Testing Topic Filtering

Try queries that should trigger topic filters:
- "What papers do you have on diabetes?" (should search within Type 2 Diabetes Management topic)
- "Show me recent research on mental health apps" (should filter by Mental Health topic and recent years)
- "What are the latest hypertension guidelines?" (should search Cardiovascular Health topic)

## Modifying System Behavior

### Changing Claude's Behavior

Edit system prompt in `ai_generator.py:8-39` to adjust:
- Medical disclaimers and safety reminders
- Search tool usage rules (currently: "One search per query maximum")
- Response format and style (evidence-based, accessible, balanced)
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
- Modify `ai_generator.py:69-74` to adjust how history is passed to Claude

## Common Issues and Solutions

**ChromaDB persistence:** Collections persist to disk at `backend/chroma_db/`. Delete this directory to force rebuild.

**Embedding model caching:** First run downloads `all-MiniLM-L6-v2` (~90MB) to `~/.cache/huggingface/`.

**Paper not found:** Ensure XML files are in `medical_papers/` directory and topics are in metadata JSON files at project root.

**Abstract-only papers loaded:** The system should automatically skip these. Check console logs for "Skipping abstract-only paper" messages.

**Empty search results:** Can occur if:
- No papers match query semantically
- Topic/paper_type/year_range filter too restrictive
- Papers not loaded properly (check startup logs for "Loaded X papers with Y chunks")

**Session context not working:** Ensure same `session_id` is sent with each query in a conversation thread.

**Follow-up query errors:** Known issue where follow-up queries after tool use may return empty content. System handles this gracefully with error message. Root cause is conversation history + tool results formatting. Temporary error handling code is marked with `# TEMPORARY` comments in `ai_generator.py` and `app.py`.

## Student Exercises

This repository includes intentional gaps for educational purposes:

1. **Add Hyperlink Functionality to Sources** (`frontend/script.js:125-134`):
   - Backend provides URL data in source objects: `{text: "...", url: "..."}`
   - Frontend currently displays sources as plain text badges only
   - Exercise: Modify `addMessage()` function to render sources as clickable hyperlinks when URL is available
   - Expected output: `<a href="..." target="_blank" rel="noopener noreferrer">...</a>`

2. **Debug Follow-up Query Issue** (`ai_generator.py:145-161`):
   - Known bug: Follow-up queries after tool use sometimes return empty content
   - Temporary error handling prevents crashes but doesn't solve root cause
   - Debug logging in place showing `stop_reason` and `content length`
   - Root cause: Conversation history + tool results formatting issue
   - Exercise: Investigate message formatting in `_handle_tool_execution()`, fix the bug, remove temporary error handling

3. **Add Comprehensive Testing**:
   - No test suite included (intentional)
   - Exercise: Use Claude Code to create pytest tests covering:
     - XML parsing (full-text vs abstract-only)
     - Topic assignment from metadata
     - Source formatting (citation + URL)
     - API endpoints (query, papers)
     - Session management
     - Tool execution loop

## Temporary Code to Remove

Before deploying for student use, remove these temporary debugging artifacts:

**`backend/app.py`:**
- Line 11: `import traceback` comment
- Lines 75-83: Detailed error logging in `/api/query` endpoint

**`backend/ai_generator.py`:**
- Lines 145-161: Temporary edge case handling and debug logging in `_handle_tool_execution()`

These are marked with `# TEMPORARY` comments for easy identification.
