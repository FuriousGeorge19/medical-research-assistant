# Handoff Instructions: Medical Research RAG Assistant

## Context for New Claude Code Instance

You're being brought into a project to convert a **course materials RAG chatbot** into a **medical research assistant RAG chatbot**. The original repo (https://github.com/FuriousGeorge19/starting-ragchatbot-codebase) is designed for querying course materials. We need to adapt it for medical research papers.

---

## What Has Already Been Done

### 1. Medical Papers Dataset (COMPLETED ✅)

**Location:** `medical_papers/` directory

**Contents:**
- **45 high-quality medical research papers** (37 full-text, 8 abstract-only)
- All papers are open-access, highly-cited reviews/meta-analyses
- Published 2020-2025
- Structured XML format (better for RAG than PDFs)

**Topic Distribution:**
- Type 2 Diabetes Management: 7 papers
- Mental Health (Digital Interventions): 6 papers
- Cardiovascular Health (Hypertension): 7 papers
- Sleep Medicine: 4 papers
- Nutrition & Metabolism (Intermittent Fasting, Obesity): 7 papers
- Cancer Prevention & Screening: 5 papers
- Infectious Diseases (COVID-19, Long COVID): 9 papers

**Metadata Files:**
- `medical_papers_metadata.json` - Original 35 papers
- `replacement_papers_metadata.json` - 20 replacement papers
- `download_medical_papers.py` - Script to download papers from PMC

### 2. Planning & Design Discussions (COMPLETED ✅)

**See:** `conversation_log.md` for full context

**Key Decisions Made:**
- Target audience: Medical students, researchers, healthcare providers, patients
- Use cases: Evidence-based practice queries, treatment comparisons, risk factors, clinical guidelines
- UI enhancements needed: Medical disclaimers, citation export, source quality indicators
- Paper selection criteria: Highly cited, open access, systematic reviews/meta-analyses

**Example UI Queries Designed:**
- "What are the most effective treatments for Type 2 diabetes based on recent studies?"
- "Compare the efficacy of medication vs. cognitive behavioral therapy for depression"
- "What are the current screening recommendations for breast cancer?"
- "What are the long-term effects of COVID-19?"

---

## What Needs to Be Done

### Phase 1: Document Processing Adaptation

**Current State:**
- `backend/document_processor.py` expects course materials format:
  ```
  Course Title: [title]
  Lesson 0: [lesson title]
  [content...]
  ```

**Needed:**
- Adapt parser to handle **medical research papers in XML format**
- Extract key sections: Title, Authors, Abstract, Methods, Results, Discussion, References
- Create chunks that preserve paper structure
- Map to new data model (replacing Course/Lesson with Paper/Section)

**Files to Modify:**
- `backend/document_processor.py` - Core parsing logic
- `backend/models.py` - Data models (Paper, Section instead of Course, Lesson)

### Phase 2: Vector Store & Collections Modification

**Current State:**
- Two ChromaDB collections:
  - `course_catalog` - Stores course metadata
  - `course_content` - Stores chunked course content

**Needed:**
- Rename/redesign collections:
  - `paper_catalog` - Store paper metadata (title, authors, journal, year, PMC ID, topic)
  - `paper_content` - Store chunked paper sections with metadata
- Update semantic search to handle paper queries instead of course queries

**Files to Modify:**
- `backend/vector_store.py` - Collection names and schema
- `backend/config.py` - Collection name constants

### Phase 3: Tool & RAG System Updates

**Current State:**
- Tool: `search_course_content(query, course_name, lesson_number)`
- System prompt: Course assistant focused

**Needed:**
- Update tool: `search_medical_literature(query, topic, paper_type, year_range)`
- New system prompt: Medical research assistant with disclaimers
- Response formatting: Include paper citations, journal names, publication years

**Files to Modify:**
- `backend/search_tools.py` - Tool definitions and execution
- `backend/ai_generator.py` - System prompt
- `backend/rag_system.py` - Orchestration (minimal changes)

### Phase 4: Frontend UI Modifications

**Current State:**
- Course materials theme
- Example questions about courses

**Needed:**
- Medical research theme
- Medical disclaimer: "For educational purposes only. Consult healthcare provider."
- Example questions from conversation_log.md
- Source display with: Journal name, year, paper type (Review/Meta-analysis)
- Optional: Citation export button

**Files to Modify:**
- `frontend/index.html` - UI structure and styling
- `frontend/script.js` - Example questions, disclaimer display

### Phase 5: Testing & Validation

**Test Cases:**
- Parse and load all 45 medical papers into ChromaDB
- Verify semantic search returns relevant papers
- Test example queries from conversation_log.md
- Validate citations and source attribution
- Check medical disclaimer appears

---

## Transferred Files Reference

### Primary Data
- **medical_papers/** - 45 medical research papers (XML and PDF)
- **medical_papers_metadata.json** - Metadata for original 35 papers
- **replacement_papers_metadata.json** - Metadata for 20 replacement papers

### Supporting Files
- **download_medical_papers.py** - Script to download papers from PMC
- **conversation_log.md** - Complete planning discussion and decisions
- **HANDOFF_TO_NEW_CLAUDE.md** - This file

---

## Architecture Overview (From CLAUDE.md)

### RAG Pipeline Flow
1. User Query → Frontend → POST `/api/query`
2. API → Creates/retrieves session → Delegates to RAG system
3. RAG System → Retrieves conversation history → Calls AI Generator
4. AI Generator → Claude decides whether to use search tool
5. Tool (if used) → Executes search → Returns formatted results
6. AI Generator → Synthesizes answer with sources
7. Response → Returns {answer, sources, session_id} to frontend

### Key Components
- **`rag_system.py`** - Central orchestrator
- **`ai_generator.py`** - Anthropic API wrapper, handles tool execution
- **`vector_store.py`** - ChromaDB wrapper, semantic search
- **`document_processor.py`** - Parse & chunk documents
- **`search_tools.py`** - Define search tool for Claude
- **`session_manager.py`** - Conversation history
- **`app.py`** - FastAPI application

---

## Development Setup

### Prerequisites
```bash
# The repo uses uv for dependency management
uv sync

# Set up environment
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

### Running the App
```bash
./run.sh
# Or manually:
cd backend && uv run uvicorn app:app --reload --port 8000
```

### Code Quality
```bash
./format_code.sh  # Auto-format code
./check_quality.sh # Run all quality checks
```

---

## Key Configuration Changes Needed

**`backend/config.py`** - Update these constants:
```python
# Collections (change from course to paper)
CATALOG_COLLECTION = "paper_catalog"  # was: course_catalog
CONTENT_COLLECTION = "paper_content"  # was: course_content

# Paths
DOCS_PATH = "./medical_papers"  # was: ../docs
```

---

## Important Notes

### XML File Format
- Medical papers are in **JATS XML format** (Journal Article Tag Suite)
- Structure: `<article>` → `<front>` (metadata) → `<body>` (content) → `<back>` (references)
- Key tags: `<title>`, `<abstract>`, `<sec>` (sections), `<p>` (paragraphs)

### 8 Papers Have Restricted Full Text
Some XML files contain:
```xml
<!--The publisher does not allow downloading of the full text in XML form.-->
```
These only have abstract + metadata. **This is OK** - still valuable for context.

### Chunking Strategy
- Current: Sentence-based chunking with overlap (800 chars, 100 overlap)
- Recommendation for medical papers: **Section-based chunking**
  - Keep abstract as one chunk
  - Chunk methods, results, discussion separately
  - Preserves scientific structure

---

## Suggested Implementation Order

1. **Start Small:** Parse 1-2 medical papers manually to understand XML structure
2. **Update Models:** Modify `models.py` for Paper/Section data model
3. **Update Parser:** Adapt `document_processor.py` for XML parsing
4. **Test Loading:** Load papers into ChromaDB, verify collections
5. **Update Tools:** Modify `search_tools.py` and system prompt
6. **Update Frontend:** Change UI theme and example questions
7. **End-to-End Test:** Full query cycle with medical papers

---

## Success Criteria

✅ All 37 full-text papers successfully loaded into ChromaDB
✅ Medical research queries return relevant papers
✅ Sources properly attributed (journal, year, paper type)
✅ Medical disclaimer visible in UI
✅ System prompt appropriate for medical context
✅ Example queries from conversation_log.md work correctly

---

## Reference Documents

- **Original Repo:** https://github.com/FuriousGeorge19/starting-ragchatbot-codebase
- **Conversation Log:** `conversation_log.md` - Complete planning discussion
- **CLAUDE.md:** Architecture documentation in original repo
- **PMC XML Format:** https://jats.nlm.nih.gov/ (JATS standard)

---

## Questions to Ask the User Before Starting

1. Do you want to preserve the course materials assistant, or fully convert to medical only?
2. Should we support both PDF and XML papers, or XML only?
3. Any specific medical disclaimer text you want?
4. Should citations be formatted in a specific style (AMA, APA, etc.)?

---

**Good luck! The medical papers dataset is excellent and ready to go. Focus on adapting the document processor first - that's the biggest change.**
