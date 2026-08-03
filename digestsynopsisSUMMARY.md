# BidBrief Project Digest Synopsis

## 1. High-Level Summary (150-175 words)

BidBrief is a dual-mode AI document analysis platform powered by the HOTDOG (Hierarchical Orchestrated Thorough Document Oversight & Guidance) AI architecture. The system specializes in extracting structured information from bid specification documents, particularly for CIPP (Cured-In-Place Pipe) lining and municipal infrastructure projects.

The platform operates in two modes: **BID_SPEC** (traditional deduplication-based with Jaccard similarity merging) and **BESTPREP** (append-only exhaustive accumulation with Layer 7 synthesis). It features a 7-layer processing architecture: Document Ingestion (L0), Configuration Loading (L1), Expert Persona Generation (L2), Multi-Expert Processing (L3), Smart/Append Accumulation (L4), Token Budget Management (L5), Output Compilation (L6), and Synthesis (L7, BestPrep only).

The Flask-based backend uses threading for concurrent analysis with polling-based progress updates. Authentication is cookie-based with role support (admin/user). Export capabilities include professional 4-sheet Excel reports for Bid/Spec mode and 5-sheet comprehensive reports for BestPrep mode with fragments, footnotes, and page indexing.

---

## 2. Architecture & Major Components

### 2.1 System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Flask App (app.py)                        │
│  - Cookie-based auth, session management, SSE/polling progress  │
└─────────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────────┐
│                   HOTDOG Orchestrator                            │
│  - Dual-mode coordination (BID_SPEC / BESTPREP)                 │
│  - Window-based document processing (3-page sliding windows)    │
└─────────────────────────────────────────────────────────────────┘
                                │
     ┌──────────────────────────┴──────────────────────────┐
     │                                                      │
┌────┴────┐                                          ┌─────┴─────┐
│ Layer 0 │ Document Ingestion                       │  Layer 1  │
│  PyMuPDF/pdfplumber/PyPDF2                        │  Config   │
│  Multi-format extraction                           │  Loader   │
└─────────┘                                          └───────────┘
     │                                                      │
┌────┴────┐                                          ┌─────┴─────┐
│ Layer 2 │ Expert Persona Generation                │  Layer 3  │
│  AI-generated section specialists                  │  Multi-   │
│                                                    │  Expert   │
└─────────┘                                          │  Processor│
     │                                               └───────────┘
     │                          ┌────────────────────────┴────────┐
     │                          │                                  │
     │                   ┌──────┴──────┐                   ┌──────┴──────┐
     │                   │ BID_SPEC    │                   │ BESTPREP    │
     │                   │ Layer 4:    │                   │ Layer 4:    │
     │                   │ SmartAccum  │                   │ AppendAccum │
     │                   │ (dedupe)    │                   │ (never drop)│
     │                   └─────────────┘                   └─────────────┘
     │                          │                                  │
     │                          │                          ┌──────┴──────┐
     │                          │                          │ Layer 7:    │
     │                          │                          │ Synthesis   │
     │                          │                          │ Agent       │
     │                          │                          └─────────────┘
     │                          │                                  │
     └──────────────────────────┴──────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │      Layer 6:         │
                    │  Output Compilation   │
                    │  (Browser/Excel/PDF)  │
                    └───────────────────────┘
```

### 2.2 Core Python Modules

| Module | Location | Lines | Purpose |
|--------|----------|-------|---------|
| `app.py` | Root | ~1500 | Flask application, routes, auth, session management |
| `orchestrator.py` | services/hotdog/ | ~1027 | HOTDOG main coordinator |
| `models.py` | services/hotdog/ | ~350 | Data models (PageData, Question, Answer, ExpertPersona, etc.) |
| `layers.py` | services/hotdog/ | ~450 | L0 DocumentIngestion, L1 ConfigLoader, L2 ExpertGenerator, L5 TokenBudget |
| `smart_accumulator.py` | services/hotdog/ | ~300 | L4 Bid/Spec deduplication with Jaccard similarity |
| `append_accumulator.py` | services/hotdog/ | ~400 | L4 BestPrep append-only accumulator |
| `multi_expert_processor.py` | services/hotdog/ | ~400 | L3 parallel expert processing |
| `synthesis_agent.py` | services/hotdog/ | ~200 | L7 synthesis for BestPrep |
| `output_compiler.py` | services/hotdog/ | ~440 | L6 output formatting |
| `second_pass_processor.py` | services/hotdog/ | ~500 | Enhanced scrutiny for unanswered questions |
| `token_optimizer.py` | services/hotdog/ | ~240 | Token budget calculations |
| `key_requirements_extractor.py` | services/hotdog/ | ~230 | Always-run key requirement extraction |
| `mode_config.py` | services/hotdog/ | ~72 | Dual-mode configuration |
| `bestprep_excel.py` | services/ | ~456 | 5-sheet BestPrep Excel export |
| `excel_dashboard.py` | services/ | ~564 | 4-sheet Bid/Spec Excel export |
| `document_extractor.py` | services/ | ~425 | Multi-format document extraction |
| `pdf_extractor.py` | services/ | ~252 | PDF-specific extraction strategies |

### 2.3 Frontend Components

| File | Purpose |
|------|---------|
| `index.html` | Main analysis page with section selection, progress display, results modal |
| `login.html` | Authentication page with form-based login |
| `admin_sessions.html` | Admin panel for viewing all analyses, fragments, footnotes |

---

## 3. Data Models & Integrations

### 3.1 Core Data Models (services/hotdog/models.py)

```python
@dataclass
class PageData:
    page_num: int
    text: str
    char_count: int

@dataclass
class WindowContext:
    window_num: int
    pages: List[int]
    text: str
    page_range_str: str  # e.g., "1-3"

@dataclass
class Question:
    id: str
    text: str
    section_id: str

@dataclass
class Answer:
    question_id: str
    text: str
    pages: List[int]
    confidence: float  # 0.0 - 1.0
    expert: str
    window: int
    footnote: str = ""
    merge_count: int = 1
    windows: List[int] = field(default_factory=list)

    def get_confidence_level(self) -> ConfidenceLevel:
        """HIGH (>=0.75), MEDIUM (>=0.4), LOW (<0.4)"""

@dataclass
class ExpertPersona:
    name: str
    section_id: str
    system_prompt: str
    focus_areas: List[str]

@dataclass
class Section:
    id: str
    name: str
    description: str
    questions: List[Question]

@dataclass
class ParsedConfig:
    sections: List[Section]
    total_questions: int
    version: str

class AnswerAccumulation(TypedDict):
    # question_id -> List[Answer]
    pass

@dataclass
class AnalysisResult:
    document_name: str
    total_pages: int
    pages_analyzed: int
    questions: AnswerAccumulation
    footnotes: List[str]
    metadata: Dict[str, Any]
    started_at: datetime
    completed_at: datetime
    total_tokens: int
    estimated_cost: float
```

### 3.2 BestPrep-Specific Models (services/hotdog/append_accumulator.py)

```python
@dataclass
class AnswerFragment:
    """Individual answer fragment - NEVER deleted once added."""
    fragment_id: str      # "FRAG-0001"
    text: str
    pages: List[int]
    confidence: float
    window_index: int
    expert_name: str
    timestamp: str

@dataclass
class Footnote:
    """Individual footnote citation."""
    footnote_id: str      # "FN-0001"
    text: str
    page: int
    quote: str            # Direct quote from document
    question_id: str
    fragment_id: str
    window_index: int
    timestamp: str

@dataclass
class CumulativeAnswer:
    """Accumulates all fragments/footnotes for one question."""
    question_id: str
    question_text: str
    fragments: List[AnswerFragment] = field(default_factory=list)
    footnotes: List[Footnote] = field(default_factory=list)
    synthesized_answer: Optional[str] = None

    @property
    def all_pages(self) -> List[int]:
        """Sorted unique pages from all fragments."""

    @property
    def highest_confidence(self) -> float:
        """Max confidence across all fragments."""
```

### 3.3 Mode Configuration (services/hotdog/mode_config.py)

```python
class AnalysisMode(Enum):
    BID_SPEC = "bid_spec"      # Deduplication, merge similar
    BESTPREP = "bestprep"      # Append-only, never discard

@dataclass
class ModeConfig:
    mode: AnalysisMode
    deduplicate: bool                  # True for BID_SPEC
    similarity_threshold: float        # 0.75 for BID_SPEC
    preserve_all_fragments: bool       # True for BESTPREP
    individual_footnote_tracking: bool # True for BESTPREP
    max_footnotes_per_answer: int      # 0 = unlimited
    enable_synthesis: bool             # True for BESTPREP
    synthesis_per_section: bool
    export_format: str                 # 'bid_spec' or 'bestprep'
```

### 3.4 External Integrations

| Integration | Purpose | Configuration |
|-------------|---------|---------------|
| OpenAI API | GPT-4o for expert processing & synthesis | `OPENAI_API_KEY` env var |
| PyMuPDF (fitz) | Primary PDF extraction | Auto-detected |
| pdfplumber | Fallback PDF extraction | Auto-detected |
| PyPDF2 | Second fallback PDF extraction | Auto-detected |
| openpyxl | Excel report generation | Required dependency |
| Gunicorn | Production WSGI server | `gunicorn_config.py` |

---

## 4. Critical Flows & Behaviors

### 4.1 Analysis Flow (Start to Completion)

```
1. POST /api/analyze
   ├── Validate mode (bid_spec/bestprep)
   ├── Create session_id
   ├── Register in active_analyses dict
   └── Start background thread: run_analysis_thread()

2. run_analysis_thread()
   ├── Initialize HotdogOrchestrator(mode=mode)
   ├── Extract pages: Layer 0 (PyMuPDF/pdfplumber/PyPDF2)
   ├── Load config: Layer 1 (JSON question set)
   ├── Generate experts: Layer 2 (AI creates personas)
   ├── Run key requirements extractor (always)
   ├── For each 3-page window:
   │   ├── Layer 3: Multi-expert processing (parallel API calls)
   │   └── Layer 4: Accumulate answers
   │       ├── BID_SPEC: SmartAccumulator (Jaccard dedup)
   │       └── BESTPREP: AppendOnlyAccumulator (keep all)
   ├── Second pass: Process unanswered questions
   ├── [BESTPREP only] Layer 7: Synthesis Agent
   ├── Layer 6: Compile output
   ├── Move to completed_analyses
   └── Emit 'done' event

3. GET /api/events/<session_id>?last_index=N
   └── Return new events since last_index (polling)

4. GET /api/results/<session_id>
   └── Return completed/partial/active analysis results
```

### 4.2 Answer Accumulation Logic

**BID_SPEC Mode (SmartAccumulator):**
```python
def add_answer(self, question_id, new_answer):
    existing_answers = self.answers.get(question_id, [])
    for existing in existing_answers:
        similarity = jaccard_similarity(existing.text, new_answer.text)
        if similarity >= 0.75:
            existing.merge_with(new_answer)  # Merge into existing
            return
    existing_answers.append(new_answer)  # Add as new
```

**BESTPREP Mode (AppendOnlyAccumulator):**
```python
def add_answer(self, question_id, answer_text, pages, confidence, window, expert):
    # NEVER check for duplicates - always append
    fragment = AnswerFragment(
        fragment_id=self._next_fragment_id(),
        text=answer_text,
        pages=pages,
        confidence=confidence,
        window_index=window,
        expert_name=expert,
        timestamp=datetime.now().isoformat()
    )
    self.cumulative_answers[question_id].add_fragment(fragment)
    # Extract and store footnotes from PDF citations
    self._extract_footnotes(fragment, question_id)
```

### 4.3 Synthesis Flow (BestPrep Only)

```
1. SynthesisAgent.synthesize_all(accumulator)
   └── For each question with fragments (not yet synthesized):
       ├── Build fragments_text from all AnswerFragment objects
       ├── Build footnotes_text from all Footnote objects
       ├── Format SYNTHESIS_USER_TEMPLATE prompt
       ├── Call OpenAI with SYNTHESIS_SYSTEM_PROMPT
       │   - "Produce NATURAL LANGUAGE answer"
       │   - "NEVER include page numbers in text"
       │   - "NO inline citations like 'According to page X'"
       └── Store synthesized answer in CumulativeAnswer
```

### 4.4 Excel Export Flow

**BID_SPEC Mode (ExcelDashboardGenerator):**
```
Sheet 1: Executive Summary
├── Analysis statistics (total, answered, rate, confidence)
└── Key project requirements (auto-extracted)

Sheet 2: Detailed Results
├── All questions with answers in table
└── Columns: #, Section, Question, Answer, PDF Pages, Footnote, Status

Sheet 3: By Section
└── Questions grouped by section with headers

Sheet 4: Footnotes
└── All collected footnotes with context
```

**BESTPREP Mode (BestPrepExcelGenerator):**
```
Sheet 1: Summary
├── Analysis statistics
└── Fragment/footnote counts

Sheet 2: Synthesized Answers
├── Final merged answers per question
└── Source pages, fragment count, footnote count

Sheet 3: All Fragments
├── Every individual fragment
└── Fragment ID, Window, Pages, Confidence, Expert, Text

Sheet 4: All Footnotes
├── Every individual footnote
└── Footnote ID, Page, Quote, Window, Fragment ID

Sheet 5: Page Index
└── Which questions reference each page
```

---

## 5. Risks, Gaps, and Open Questions

### 5.1 Current Risks

| Risk | Severity | Description |
|------|----------|-------------|
| In-memory session storage | High | All analyses stored in Python dicts; lost on worker restart |
| Single worker constraint | Medium | `max_requests=0` to prevent session loss; limits scalability |
| No persistent storage | High | TODO mentions Neon DB migration but not implemented |
| Token budget edge cases | Medium | Large documents may hit API limits despite TokenOptimizer |
| No rate limiting | Medium | Multiple concurrent analyses could exhaust API quota |

### 5.2 Known Gaps

1. **No database persistence**: Sessions stored in `active_analyses`, `completed_analyses`, `partial_analyses` dicts
2. **No user management UI**: Users defined in code/env vars, not admin-editable
3. **No analysis history per user**: No way to view past analyses after session expires
4. **Limited file format support**: Primarily PDF; DOCX/RTF support exists but less tested
5. **No export to PDF**: Only Excel export implemented

### 5.3 Open Questions

1. Should synthesis results be cached to avoid re-running on result view?
2. How to handle documents with 500+ pages (token budget constraints)?
3. Should there be a max analysis time cutoff?
4. How to handle concurrent edits to same session from multiple tabs?

---

## 6. Edge Cases, Failure Modes, and Quality

### 6.1 Error Handling

| Layer | Error Handling |
|-------|----------------|
| L0 Document Ingestion | Fallback strategies: PyMuPDF -> pdfplumber -> PyPDF2 |
| L3 Expert Processing | Per-window try/catch, continues on failure |
| L7 Synthesis | Returns None on failure, original fragments preserved |
| Excel Export | `sanitize_for_excel()` removes illegal XML characters |
| API Calls | Logged errors, graceful degradation to partial results |

### 6.2 Edge Cases Handled

1. **Empty pages**: Filtered out (min_length=50 chars)
2. **Missing PDF citations**: Auto-added from window pages
3. **Illegal Excel characters**: Control chars (0x00-0x1F) stripped
4. **Duplicate answers in BID_SPEC**: Merged via Jaccard similarity
5. **Question not initialized**: Auto-created on first answer in BESTPREP
6. **No answer found**: Marked with confidence=0, displayed as "Not found in document"

### 6.3 Testing Coverage

```
tests/test_bestprep_mode.py:
├── TestModeConfig (4 tests)
│   ├── test_bid_spec_mode_defaults
│   ├── test_bestprep_mode_defaults
│   ├── test_unknown_mode_defaults_to_bid_spec
│   └── test_mode_config_export_format
├── TestAppendOnlyAccumulator (13 tests)
│   ├── test_initialization
│   ├── test_initialize_question
│   ├── test_never_rejects_fragments (100 identical fragments test)
│   ├── test_fragment_ids_are_unique
│   ├── test_footnote_extraction
│   ├── test_all_pages_aggregation
│   ├── test_highest_confidence
│   ├── test_statistics
│   ├── test_get_questions_for_synthesis
│   ├── test_auto_create_question_on_add
│   └── test_serialization
└── TestCumulativeAnswer (2 tests)
    ├── test_add_fragment
    └── test_add_footnote
```

---

## 7. Opportunities and Next Steps

### 7.1 Immediate Improvements

1. **Persistent Storage Migration**
   - Implement Neon DB (PostgreSQL) for sessions
   - Re-enable `max_requests` worker cycling
   - Add session recovery on worker restart

2. **Admin Panel Enhancements**
   - Add user management CRUD
   - Implement analysis deletion
   - Add export history

3. **Performance Optimizations**
   - Cache synthesis results
   - Implement chunked streaming for large exports
   - Add Redis for cross-worker session sharing

### 7.2 Feature Opportunities

1. **Comparison Mode**: Compare two documents side-by-side
2. **Custom Question Sets**: Allow users to upload/edit question configs
3. **PDF Export**: Generate printable PDF reports
4. **Batch Processing**: Upload multiple documents at once
5. **API Access**: REST API for programmatic analysis

### 7.3 Technical Debt

1. Remove `GEVENT_PATCHED` code (unused since polling migration)
2. Consolidate `pdf_extractor.py` and `document_extractor.py` (overlap)
3. Standardize response format transformation
4. Add comprehensive logging across all layers
5. Implement proper request validation with Pydantic/Marshmallow

---

## 8. Exhaustive Function Mapping

### 8.1 app.py (Flask Application)

| Function | Lines | Purpose |
|----------|-------|---------|
| `_transform_to_legacy_format(hotdog_output)` | 207-277 | Convert HOTDOG output to legacy frontend format |
| `_extract_bestprep_data(orchestrator)` | 867-911 | Extract BestPrep fragments/footnotes for API |
| `check_auth_cookie()` | 284-302 | Validate auth cookie, return session or None |
| `require_auth(f)` | 305-317 | Decorator requiring authentication |
| `require_admin(f)` | 320-335 | Decorator requiring admin role |
| `index()` | 342-345 | Serve index.html (requires auth) |
| `login_page()` | 348-354 | Serve login.html |
| `form_login()` | 357-400 | Handle form-based login POST |
| `logout()` | 403-413 | Clear session and redirect |
| `serve_shared_assets(filename)` | 416-419 | Serve /shared/* assets |
| `health()` | 421-427 | Health check endpoint |
| `authenticate()` | 439-481 | API-based authentication (JSON) |
| `verify_session()` | 483-496 | Verify session token validity |
| `get_api_key()` | 503-513 | Return masked OpenAI API key |
| `sse_health()` | 516-547 | SSE environment diagnostic |
| `upload_file()` | 554-578 | Handle PDF upload |
| `progress_stream(session_id)` | 585-647 | SSE progress endpoint |
| `get_events(session_id)` | 654-672 | Polling progress endpoint |
| `analyze_document()` | 679-770 | Start HOTDOG analysis |
| `run_analysis_thread(...)` | ~775-900 | Background analysis thread |
| `stop_analysis()` | ~910-940 | Stop running analysis |
| `get_results(session_id)` | ~950-1050 | Get analysis results |
| `export_excel(session_id)` | ~1060-1150 | Generate Excel export |
| `export_bestprep_excel(session_id)` | ~1160-1220 | BestPrep-specific export |
| `admin_sessions_page()` | ~1230-1250 | Serve admin page |
| `admin_get_sessions()` | ~1260-1350 | Get all sessions for admin |
| `cleanup_old_sessions()` | ~1360-1400 | Periodic session cleanup |

### 8.2 services/hotdog/orchestrator.py (HotdogOrchestrator)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__(api_key, model, mode, ...)` | ~50-120 | Initialize orchestrator with mode config |
| `analyze(pdf_path, enabled_sections, context_guardrails, progress_callback)` | ~130-280 | Main analysis entry point |
| `_extract_pages(pdf_path)` | ~290-340 | Layer 0: Extract pages from PDF |
| `_load_config(enabled_sections)` | ~350-400 | Layer 1: Load question configuration |
| `_generate_experts(config)` | ~410-470 | Layer 2: Generate expert personas |
| `_create_windows(pages, window_size)` | ~480-520 | Create 3-page sliding windows |
| `_process_windows(windows, config, experts, ...)` | ~530-650 | Layer 3: Process all windows |
| `_run_second_pass(windows, config, experts, ...)` | ~660-720 | Process unanswered questions |
| `_run_synthesis()` | ~730-780 | Layer 7: Run BestPrep synthesis |
| `_compile_results(config, started_at)` | ~790-850 | Layer 6: Compile final output |
| `get_accumulated_answers()` | ~860-880 | Get current answer state |
| `stop()` | ~890-910 | Stop analysis gracefully |

### 8.3 services/hotdog/layers.py

| Class/Method | Lines | Purpose |
|--------------|-------|---------|
| `DocumentIngestionLayer.__init__()` | ~30-50 | Init with PDFExtractorService |
| `DocumentIngestionLayer.extract_pages(pdf_path)` | ~55-90 | Extract pages, return List[PageData] |
| `ConfigurationLoader.__init__()` | ~100-120 | Load default config path |
| `ConfigurationLoader.load_config(enabled_sections)` | ~125-180 | Parse JSON, filter sections |
| `ExpertPersonaGenerator.__init__(api_key, model)` | ~190-210 | Init with OpenAI client |
| `ExpertPersonaGenerator.generate_experts(config)` | ~215-300 | AI-generate expert personas |
| `TokenBudgetManager.__init__(model)` | ~310-340 | Detect model limits |
| `TokenBudgetManager.calculate_budget(num_questions)` | ~345-380 | Calculate optimal token budgets |

### 8.4 services/hotdog/smart_accumulator.py (SmartAccumulator)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__(similarity_threshold)` | ~30-45 | Init with 0.75 threshold |
| `add_answer(question_id, answer)` | ~50-90 | Add/merge answer with Jaccard check |
| `_jaccard_similarity(a, b)` | ~95-110 | Calculate Jaccard coefficient |
| `_merge_answers(existing, new)` | ~115-140 | Merge two similar answers |
| `get_best_answer(question_id)` | ~145-160 | Return highest confidence answer |
| `get_all_answers(question_id)` | ~165-175 | Return all answers for question |
| `get_statistics()` | ~180-210 | Return accumulation stats |

### 8.5 services/hotdog/append_accumulator.py (AppendOnlyAccumulator)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__()` | ~100-115 | Init empty cumulative_answers dict |
| `initialize_question(question_id, question_text)` | ~120-135 | Create CumulativeAnswer entry |
| `add_answer(question_id, answer_text, pages, ...)` | ~140-200 | Append AnswerFragment, extract footnotes |
| `_extract_footnotes(fragment, question_id)` | ~205-250 | Parse <PDF pg X> citations |
| `_next_fragment_id()` | ~255-265 | Generate "FRAG-0001" style ID |
| `_next_footnote_id()` | ~270-280 | Generate "FN-0001" style ID |
| `get_cumulative_answer(question_id)` | ~285-295 | Return CumulativeAnswer |
| `get_questions_for_synthesis()` | ~300-320 | Return questions needing synthesis |
| `set_synthesized_answer(question_id, text)` | ~325-335 | Store synthesis result |
| `mark_window_processed(window_index)` | ~340-350 | Track processed windows |
| `get_statistics()` | ~355-400 | Return comprehensive stats |
| `to_dict()` | ~405-450 | Serialize to dict for JSON/storage |

### 8.6 services/hotdog/multi_expert_processor.py (MultiExpertProcessor)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__(openai_client, max_parallel, ...)` | ~40-70 | Init with concurrency limit |
| `process_window(window, questions, experts)` | ~80-150 | Process window with all experts |
| `_query_expert(window, questions, expert)` | ~160-250 | Single expert API call |
| `_build_system_prompt(expert)` | ~260-300 | Construct expert system prompt |
| `_build_user_prompt(window, questions)` | ~310-360 | Construct analysis prompt |
| `_parse_expert_response(response, questions, expert, window)` | ~370-450 | Extract answers from JSON |

### 8.7 services/hotdog/synthesis_agent.py (SynthesisAgent)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__(api_key, model)` | ~69-76 | Init with OpenAI client |
| `synthesize_question(cumulative_answer)` | ~78-146 | Synthesize one question's fragments |
| `synthesize_all(accumulator, section_ids, max_concurrent)` | ~148-191 | Synthesize all questions in parallel |
| `get_statistics()` | ~193-196 | Return synthesis stats |

### 8.8 services/hotdog/output_compiler.py (OutputCompiler)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__()` | ~44-47 | Init footnotes list |
| `compile_results(accumulation, config, metadata, ...)` | ~49-98 | Create AnalysisResult |
| `_compile_footnotes(accumulation)` | ~100-137 | Extract all unique footnotes |
| `_extract_citations(text)` | ~139-163 | Parse <PDF pg X> patterns |
| `format_for_browser(result, config)` | ~165-227 | Create frontend JSON structure |
| `_format_answer_for_browser(answer)` | ~229-259 | Format single answer with badges |
| `format_for_excel(result, config)` | ~261-367 | Create Excel sheet data structures |
| `generate_text_report(result, config)` | ~369-427 | Create ASCII text report |

### 8.9 services/hotdog/second_pass_processor.py (SecondPassProcessor)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__(openai_client, max_parallel, ...)` | ~51-86 | Init with enhanced settings |
| `process_unanswered_questions(windows, questions, experts)` | ~87-143 | Process all windows for unanswered |
| `_process_window_enhanced(window, questions, experts)` | ~145-225 | Enhanced scrutiny per window |
| `_query_expert_enhanced(window, questions, expert)` | ~227-288 | API call with creative prompts |
| `_build_enhanced_system_prompt(expert)` | ~290-340 | Add "SECOND PASS" instructions |
| `_build_enhanced_user_prompt(window, questions)` | ~342-382 | Add inference permission |
| `_parse_expert_response_enhanced(response, questions, ...)` | ~384-476 | Parse with reasoning field |
| `get_statistics()` | ~478-493 | Return second pass stats |

### 8.10 services/hotdog/token_optimizer.py (TokenOptimizer)

| Method | Lines | Purpose |
|--------|-------|---------|
| `detect_model_limits(model_name)` | ~106-146 | Return ModelLimits for model |
| `calculate_optimal_window_size(model_name, ...)` | ~148-185 | Calculate pages per window |
| `get_enhanced_prompt_budget(model_name)` | ~187-215 | Return token budget allocation |
| `estimate_completion_tokens(model_name, num_questions)` | ~217-239 | Estimate needed completion tokens |

### 8.11 services/hotdog/key_requirements_extractor.py (KeyRequirementsExtractor)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__(api_key, model)` | ~91-94 | Init with OpenAI client |
| `extract_from_document(pages_text, sample_pages)` | ~96-189 | Extract key requirements |
| `get_requirements_dict()` | ~191-202 | Return requirements as dict |
| `get_summary_data()` | ~204-229 | Return display-name mapped values |

### 8.12 services/bestprep_excel.py (BestPrepExcelGenerator)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__(analysis_result, accumulator_data)` | ~46-59 | Init with data and styles |
| `generate()` | ~61-75 | Generate 5-sheet workbook |
| `_create_summary_sheet()` | ~77-167 | Sheet 1: Statistics |
| `_create_answers_sheet()` | ~169-255 | Sheet 2: Synthesized answers |
| `_create_fragments_sheet()` | ~257-332 | Sheet 3: All fragments |
| `_create_footnotes_sheet()` | ~334-396 | Sheet 4: All footnotes |
| `_create_sources_sheet()` | ~398-455 | Sheet 5: Page index |

### 8.13 services/excel_dashboard.py (ExcelDashboardGenerator)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__(analysis_result, is_partial)` | ~102-107 | Init with result data |
| `generate()` | ~109-122 | Generate 4-sheet workbook |
| `_collect_footnotes()` | ~124-140 | Gather all footnotes |
| `_extract_key_requirements()` | ~142-170 | Pattern-match key requirements |
| `_calculate_statistics()` | ~172-199 | Compute answer rate, confidence |
| `_create_executive_summary()` | ~201-318 | Sheet 1: Summary |
| `_create_detailed_results()` | ~320-409 | Sheet 2: All Q&A |
| `_create_by_section()` | ~411-498 | Sheet 3: Grouped by section |
| `_create_footnotes_sheet()` | ~500-559 | Sheet 4: Footnotes |
| `_get_timestamp()` | ~561-563 | Format current date |

### 8.14 services/document_extractor.py (DocumentExtractorService)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__()` | ~219-220 | Init all strategies |
| `_initialize_strategies()` | ~222-280 | Detect available libraries |
| `get_file_type(filename)` | ~282-293 | Determine format from extension |
| `is_supported(filename)` | ~295-300 | Check if format supported |
| `extract_text_with_pages(file_path, min_length)` | ~302-349 | Extract with fallback |
| `extract_text_combined(file_path, min_length)` | ~351-376 | Extract with page markers |
| `_clean_text(text)` | ~378-403 | Normalize whitespace |
| `get_available_libraries()` | ~405-410 | Return available extractors |
| `get_supported_extensions()` | ~412-424 | Return ['.pdf', '.txt', ...] |

### 8.15 services/pdf_extractor.py (PDFExtractorService)

| Method | Lines | Purpose |
|--------|-------|---------|
| `__init__()` | ~125-126 | Init strategies |
| `_initialize_strategies()` | ~128-158 | Detect pdfplumber/PyPDF2/pdfminer |
| `extract_text_with_pages(pdf_path, min_length)` | ~160-198 | Extract with fallback |
| `extract_text_combined(pdf_path, min_length)` | ~200-220 | Combine with <PDF pg X> markers |
| `_clean_text(text)` | ~222-247 | Clean extracted text |
| `get_available_libraries()` | ~249-251 | Return strategy names |

---

## 9. Configuration Files

### 9.1 gunicorn_config.py

```python
bind = "0.0.0.0:{PORT}"
workers = 1              # Single worker for session consistency
worker_class = 'sync'    # Sync with threading
threads = 10             # 10 concurrent threads
timeout = 900            # 15 minutes for long analyses
max_requests = 0         # Disabled to preserve sessions
```

### 9.2 Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API authentication | Required |
| `PORT` | Server port | 5000 |
| `LOG_LEVEL` | Logging verbosity | INFO |
| `FLASK_ENV` | Environment mode | development |
| `DEBUG` | Enable debug mode | false |
| `AUTH_USER_*` | User credentials (hash-based) | None |

### 9.3 Question Configuration (services/hotdog/config/questions.json)

Default 100-question set covering:
- General Project Information (Q1-Q10)
- Televising Requirements (Q11-Q21)
- Access to Easement (Q21-Q30)
- Safety & Environmental (Q41-Q50)
- Equipment & Resources (Q51-Q60)
- Warranty & Closeout (Q61-Q70)
- Special Conditions (Q71-Q80)
- Pricing Structure (Q81-Q90)
- Experience & Qualifications (Q91-Q100+)

---

## 10. API Endpoints Reference

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/` | Required | Main analysis page |
| GET | `/login` | None | Login page |
| POST | `/auth/login` | None | Form login |
| GET | `/auth/logout` | None | Clear session |
| POST | `/api/authenticate` | None | JSON login |
| POST | `/api/verify-session` | None | Validate token |
| GET | `/api/config/apikey` | None | Get masked API key |
| POST | `/api/upload` | Required | Upload PDF |
| POST | `/api/analyze` | Required | Start analysis |
| GET | `/api/events/<session_id>` | Required | Poll progress |
| GET | `/api/progress/<session_id>` | Required | SSE progress (legacy) |
| POST | `/api/stop/<session_id>` | Required | Stop analysis |
| GET | `/api/results/<session_id>` | Required | Get results |
| GET | `/api/export/<session_id>` | Required | Export Excel |
| GET | `/admin` | Admin | Admin panel |
| GET | `/api/admin/sessions` | Admin | Get all sessions |
| GET | `/health` | None | Health check |

---

---

## 11. Smart Analysis — Multi-Agent Executive Analysis Layer

> **Added:** commit d65a75d (v1) → e4cf7ca (v2) → 887e82a (v3, current)
> **Full architecture reference:** `docs/smart_analysis/SMART_ANALYSIS_ARCHITECTURE.md`
> **Refactoring guide:** `docs/smart_analysis/SMART_ANALYSIS_REFACTORING_GUIDE.md`
> **v3 refactor analysis:** `docs/smart_analysis/V3_REFACTOR_ANALYSIS.md`

### 11.1 Overview

Smart Analysis is a post-extraction executive analysis feature. It runs after HOTDOG completes Q&A extraction and the user explicitly triggers it. It consumes the extraction results and produces a decision-oriented executive report with risks, opportunities, ambiguities, assessments, and strategic recommendations.

**Pipeline (5 AI calls, mixed serial/parallel):**
```
ContextAggregator (no AI)
  → DocumentProfileAgent (serial, 1 AI call)
  → gather(SCOUTAgent, MIRRORAgent, UserInputAgent) (parallel, up to 3 AI calls)
  → SynthesisAgent (serial, 1 AI call)
  → SmartAnalysisResult
```

### 11.2 Agent Reference

| Agent | File | Tokens | Timeout | Role |
|-------|------|--------|---------|------|
| ContextAggregator | context_aggregator.py | No AI | — | Builds analysis_text + rich_analysis_text from Q&A results; handles both legacy and modern result field names via `_resolve_question_fields()` |
| DocumentProfileAgent | document_profile_agent.py | 4500 | 90s | Evidence grounding: confirmed_present/absent/unverified, expertise_profile (document-specific), key_items, document_understanding |
| SCOUTAgent | scout_agent.py | 5000 | 120s | SCOUT framework: lens_selection_reasoning, sanity_flags, criteria_gaps, opportunities, uncertainties (5-field follow_up), assumptions (5-field follow_up) |
| MIRRORAgent | mirror_agent.py | 5000 | 120s | MIRROR framework: lens_selection_reasoning, missing_elements (5-field follow_up), interpretation_risks, risks (5-field follow_up), stakeholder_perspectives, failure_scenarios |
| UserInputAgent | user_input_agent.py | 2500 | 90s | Answers user-provided questions; skipped if no user_input; 3-field follow_up_direction |
| SynthesisAgent | synthesis_agent.py | 8000 | 180s | Final synthesis: mandatory minimums (≥5 risks, ≥5 opps, ≥5 ambiguities, ≥6 assessments, ≥6 follow_up_questions, ≥5 recommendations), unique assessment categories, 5-field follow_up_direction |

### 11.3 Key Design Principles (v3)

1. **EXPERTISE UNIQUENESS RULE** (DocProfile): Benchmarks derived from THIS document's specifics — not generic examples. Prevents cross-run repetition.
2. **LENS GENERATION RULE** (SCOUT + MIRROR): Each agent must justify 5-7 document-specific analytical dimensions before applying them. `lens_selection_reasoning` is a required output field.
3. **4-Tier Language Discipline** (all agents): CONFIRMED PRESENT / CONFIRMED ABSENT / NOT SURFACED BY ANALYSIS / PRESENT BUT UNRESOLVED — never conflated.
4. **Mandatory Minimum Outputs** (Synthesis): ≥5/6 per output category. If minimum can't be reached, a justification item is required.
5. **Multi-Step Follow-Up Direction** (v3): All risk/opportunity/ambiguity items carry a 5-field sequence: why_unclear, verification_step, what_to_ask, who_to_ask, where_to_look.
6. **Document Understanding Layer** (v3): DocProfile outputs a `document_understanding` block with `document_title`, `document_overview`, `major_workstreams`, `key_obligations`, `key_constraints`, and `structural_organization`. Consumed by all downstream agents and rendered in UI. `document_title` is the AI-extracted formal document name; it is used as the primary title on PDF export cover pages.

### 11.4 Smart Analysis Data Models

```python
@dataclass
class SmartAnalysisItem:
    title: str
    description: str
    severity: str           # 'critical' | 'high' | 'medium' | 'low'
    evidence: List[str]
    page_refs: List[int]
    follow_up_direction: Dict[str, str]  # v3: 5-field; v2: 3-field (backward compat)

@dataclass
class ProfessionalAssessment:
    category: str           # Unique per run — derived from document
    rating: str
    rationale: str
    confidence: str         # 'high' | 'medium' | 'low'

@dataclass
class SmartAnalysisResult:
    session_id: str
    document_name: str
    document_type: str
    document_type_label: str
    analysis_completeness: str          # 'full' | 'partial'
    generated_at: str                   # ISO timestamp
    executive_summary: str
    key_insights: List[str]
    risks: List[SmartAnalysisItem]
    opportunities: List[SmartAnalysisItem]
    ambiguities: List[SmartAnalysisItem]
    contradictions: List[SmartAnalysisItem]
    assessments: List[ProfessionalAssessment]
    follow_up_questions: List[str]
    strategic_recommendations: List[str]
    user_question_responses: List[Dict[str, Any]]
    evidence_classification: Dict[str, Any]  # v2
    document_understanding: Dict[str, Any]   # v3
```

### 11.5 Smart Analysis API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/smart-analysis/<session_id>` | Run analysis (cached on first call) |
| GET | `/api/smart-analysis/<session_id>` | Retrieve cached result |
| GET | `/api/smart-analysis/<session_id>/export/excel` | Export to Excel |
| GET | `/api/smart-analysis/<session_id>/export/pdf` | Export to PDF |

### 11.6 app.py Smart Analysis Functions

| Function | Purpose |
|----------|---------|
| `_build_smart_analysis_data(session_id)` | Assembles analysis_data dict from HOTDOG results; includes key_details_list from KeyDocumentDetailsExtractor |
| `_extract_doc_context(pdf_path, max_chars)` | Extracts up to 10K chars of document context from PDF; called at analysis start before PDF cleanup |
| `run_smart_analysis(session_id)` | POST handler; checks cache, builds data, runs orchestrator, caches result |
| `get_smart_analysis(session_id)` | GET handler; returns cached result |
| `export_smart_analysis_excel(session_id)` | Excel export via SmartAnalysisExcelGenerator |
| `export_smart_analysis_pdf(session_id)` | PDF export via SmartAnalysisPDFGenerator |

### 11.7 Critical Implementation Notes

- **asyncio pattern**: `asyncio.new_event_loop()` + `loop.run_until_complete()` — required for async agents in sync Gunicorn workers
- **doc_context persistence**: PDF is deleted after analysis. doc_context (10K chars) is pre-extracted at analysis start and stored in `active_analyses[session_id]['doc_context']`. All three session transitions (completed/stopped/error) must preserve it.
- **legacy field compat**: HOTDOG result format uses `question`/`answer`/`page_citations`. `_resolve_question_fields()` handles both this and the modern `question_text`/`primary_answer` format. This was the v2 critical bug — wrong field names made all Q&A invisible to agents.
- **smart_analysis_results cache**: `smart_analysis_results` dict caches results by session_id. POST accepts `force_refresh=true` to bypass cache.
- **key_details_list**: `_build_smart_analysis_data()` uses `get_details_list()` (not `get_summary_data()`) to include PDF quotes and page references in addition to name→value pairs.

### 11.8 Version History

| Version | Commit | Key Changes |
|---------|--------|-------------|
| v1 | d65a75d | Initial build: 10 service files, 4 API routes, SCOUT/MIRROR/UserInput/Synthesis agents, UI integration |
| v2 | e4cf7ca | Critical fix: context_aggregator field name bug. Added DocumentProfileAgent, 4-tier language discipline, evidence grounding, follow_up_direction (3-field: action/target/specific_question), rich_analysis_text |
| v3 | 887e82a | Depth refactor: document_understanding layer, EXPERTISE UNIQUENESS RULE, LENS GENERATION RULE, mandatory minimum output counts (≥5/6 per category), 5-field follow_up_direction, unique assessment categories, token increases (DocProfile 3000→4500, SCOUT 3500→5000, MIRROR 3500→5000, Synthesis 5000→8000), UI rendering updates |
| v3.1 | 41f562c | Admin panel: 🧠 Smart button per session row, Smart Analysis tab in session modal, run + Excel/PDF export from admin |
| v3.2 | d7977ed | Question hub uniformity: removed admin bypass (all users see AI gen + CIPP Sample Set + Manage); CIPP button relabeled; "AI is generating" → "BidBrief is generating"; AI question section hard cap ≤10 Qs (ceil formula), max_tokens 4000→6000, timeout 60→90s |
| v3.3 | 91eac96 | PDF cover page title fix: DocumentProfileAgent extracts `document_title` into `document_understanding`; pdf_generator `_clean_display_title()` uses AI title first, falls back to cleaned filename (strips .tmp paths, UUID prefixes, percent-encoding); PDF metadata `title=` also updated |

---

## 12. Delta Since Last Full Digest (post-2026-01-31)

The following changes were made after the digest was originally generated. The function mapping in §8 does not yet reflect these:

1. **KeyRequirementsExtractor replaced**: `key_requirements_extractor.py` superseded by `key_document_details_extractor.py` (KeyDocumentDetailsExtractor). New version includes `get_details_list()` returning items with PDF quotes and page references, not just name→value pairs.

2. **Smart Analysis service module**: New `services/smart_analysis/` package with 11 files (see §11). Not in §2.2 module table.

3. **app.py Smart Analysis routes**: 4 new routes + 2 helper functions (see §11.5, §11.6). Not in §8.1 function table.

4. **app.py doc_context persistence**: doc_context pre-extraction and preservation through session transitions added. Not in §8.1.

5. **PDF export**: `services/smart_analysis/pdf_generator.py` adds PDF export for Smart Analysis results. Cover page uses `_clean_display_title()` — AI-extracted `document_title` first, cleaned filename fallback. Not in §7.2 gaps list.

6. **New API endpoints** (see §10): `/api/smart-analysis/*` routes not in §10 table.

7. **Admin Smart Analysis panel** (commit 41f562c): `admin_sessions.html` — 🧠 Smart button per session row, Smart Analysis tab in session modal with `runAdminSmartAnalysis()`, `renderSmartAnalysisTab()`, `exportAdminSmartExcel()`, `exportAdminSmartPDF()`.

8. **Question hub uniformity** (commit d7977ed): `index.html` — removed admin bypass in `openQuestionSetHub()`; all users see AI gen + CIPP Sample Set + Manage tabs. CIPP button relabeled. "AI is generating" → "BidBrief is generating". `app.py` `generate_question_set()` section hard cap ≤10 Qs (ceil formula), max_tokens 4000→6000, timeout 60→90s.

9. **PDF cover title fix** (commit 91eac96): `document_profile_agent.py` adds `document_title` to `document_understanding` schema. `pdf_generator.py` `_clean_display_title()` resolves best cover title; both `SimpleDocTemplate(title=)` and cover page `Paragraph` updated.

---

10. **GPT-5 tier upgrade + High Power + Bonus Features + Dynamic Intelligence (commit cb6e4ba, 2026-07-04):**
   - `services/ai_models.py` — central model registry: standard `gpt-5.4`, high-power `gpt-5.5`
     (env: `BIDBRIEF_MODEL_STANDARD` / `BIDBRIEF_MODEL_HIGH_POWER`). `completion_params()` adapter is
     MANDATORY for all OpenAI calls: GPT-5.x rejects `max_tokens`/`temperature`; needs
     `max_completion_tokens` (+reasoning headroom) and `reasoning_effort`. All 15 call sites converted.
   - `high_power: true` accepted by /api/analyze, question generate(+additional), smart-analysis POST,
     scraper preflight/extract/comms/research. 403 unless admin or bonus (`_resolve_high_power_request`).
   - Bonus Features: `bonus_feature_users` set (in-memory), GET/POST `/api/admin/bonus-features`
     (strict admin), `/api/user/info` gains `bonus_features` + `premium`. `_check_scraper_admin` now
     admin-OR-bonus; scraper session list/delete own-only for bonus. `/api/admin/sessions` stays strict-admin.
   - `services/dynamic_intelligence.py` — shared document-sensing table engine (strings-only contract:
     table_id/title/why_relevant/columns/rows/insights, caps 6×10×25). Integrated: Smart Analysis
     (parallel gather; result.dynamic_tables + intelligence_focus; Excel sheet + PDF section), HOTDOG
     completion (results payload + completed_analyses keys + excel_dashboard Document Intelligence sheet),
     CityScraper extraction (results dict + markdown export appendix).
   - CityScraper `research_focus` menu (config.RESEARCH_FOCUS_PRESETS): full_system (DEFAULT — changed
     from sewer-primary), sewer_wastewater, stormwater, water_distribution, streets_row. Directive
     appended to every agent system prompt in `agents/base.call_openai`; comms engine focus-aware
     (`_SCRAPER_COMMS_FOCUS_LINES`).
   - tests: test_ai_models.py, test_bonus_features.py, test_dynamic_intelligence.py (57 total pass).

11. **Question generation: always high-power + questions-source ingestion (commit 3239772, 2026-07-05):**
   - `/api/config/questions/generate` and `/api/config/questions/generate-additional` now force
     `high_power_model()` UNCONDITIONALLY — no entitlement gate, no 403. These two routes are the
     documented EXCEPTION to §12.10's "403 unless admin or bonus" rule (`_resolve_high_power_request`
     is bypassed for question gen). The request `high_power` field is ignored (kept for telemetry only).
     Rationale: question gen is a light, cheap call; every user gets flagship quality. The iOS client
     correspondingly stopped sending `high_power` for Q-gen.
   - `generate` accepts a `source_kind` form field: `context` (default — extract title/TOC/glossary/
     appendix, do NOT ask about structure) vs `questions_source` (frame the upload as material to
     DERIVE questions FROM — email/notes/standard/syllabus/plain list; intelligently infer type). A
     non-PDF upload is now read as UTF-8 text (`raw.decode('utf-8', errors='ignore')[:6000]`) instead
     of being forced through the PDF path.
   - tests: test_bonus_features.py updated — `test_question_gen_always_high_power_for_plain_user`
     (was the old 403 test) + `test_generate_questions_source_frames_derivation`. **61 total pass.**

---

*Generated by /digest skill - Last updated: 2026-01-31*
*Δ Updated: 2026-03-25 — Smart Analysis v3 added (§11), delta summary added (§12)*
*Δ Updated: 2026-03-25 (session 2) — v3.1–v3.3: admin SA panel, question hub uniformity, AI question section cap, PDF cover title fix (§12.7–12.9, §11.8)*
*Δ Updated: 2026-07-04 — GPT-5 tiers, High Power, Bonus Features, Dynamic Intelligence engine, scraper research focus (§12.10)*
*Δ Updated: 2026-07-05 — question gen always high-power (no gate) + questions-source ingestion / source_kind (§12.11)*

---

## Δ 2026-07-06 — L6.5 Answer Summarizer, fail-fast section filter, persona-architect Q-gen (commits bb55fd9..fdde163)

1. **Layer 6.5 — AnswerSummarizer** (`services/hotdog/answer_summarizer.py`): between L4 accumulation
   and L6 compilation (BID_SPEC classic + v2; BestPrep skips — L7 synthesis is its equivalent), the
   section's L2 expert persona distills each answered question's appended quote pile into a 1-3 sentence
   `Answer.summary`. One JSON call per section; non-fatal per section; `only_question_ids` re-runs it for
   second-pass answers. Events: `layer_6_5_start/complete/failed`, `summary_section_start/complete/failed`.
   Surfaces: legacy payload `answer_summary` (between `answer` and `page_citations`), OutputCompiler
   browser/Excel formats, excel_dashboard Detailed Results + By Section ("Answer Summary" column after
   Answer), index.html unitary table/modals/CSV/HTML report.
2. **enabled_sections filter** extracted to module-level `apply_enabled_sections(config, enabled_sections)`
   in `orchestrator.py` — raises ValueError on empty/unknown-only selections, emits `sections_filtered`
   event {requested, matched, dropped}. Tests: `tests/test_section_filter.py`.
3. **Q-gen is two-stage** (`/api/config/questions/generate` + `/generate-additional`): Stage 1
   `_build_persona_panel()` (Persona Architect) derives a bespoke 3-6 expert panel from the uploaded
   material + `source_intent` (new optional field: user's one-line intent for the attachment); Stage 2
   generates with the panel embedded and REQUIRES per-section `section_summary` rationale. Response adds
   `generation_personas` + `document_reading`. Architect failure → single-stage fallback, never 500.

---

## Δ 2026-07-26 — Web front-end rebuilt to iOS parity (2.2.0)

The web client (`index.html`, `login.html`) was rebuilt so its visual language and information
architecture match the BidBrief iOS app 2.1.3. **No backend behaviour changed** — the only `app.py`
edit is the `/health` version string (`2.0.0` → `2.2.0`). Full map: `docs/WEB_FRONTEND.md`.

1. **Structure.** The 5,514-line single-file app is gone. `index.html` is now a ~55-line shell (orb
   layer, four page containers, tab bar, banner + modal hosts) and all CSS/JS lives under
   `shared/assets/` served by the existing `/shared/<path:filename>` route. No bundler, no framework,
   and the dead `cdn.sheetjs.com` script was removed (every Excel export is server-side).
2. **Design system** (`css/bb-theme.css`, `css/bb-orb.css`): the iOS `BBTheme` palette verbatim, glass
   cards, glow/ghost/hub buttons, stage headers, eyebrows, back chips, segmented controls, iOS-style
   switches, and the suspended planet with per-tab parallax drift and a deterministic starfield. All
   animation is disabled under `prefers-reduced-motion`.
3. **Information architecture**: a floating capsule bottom tab bar — Analyze / Questions /
   Admin·Bonus / Settings — replacing the old two-tab navbar. `BB.state` (`js/bb-state.js`) mirrors the
   iOS `AppModels`, including the confirmed-question-set gate and the 2.1.3 cue rules (a fresh upload
   cues Questions; confirming a set clears `needsQuestionChoice` so the cue advances to Analyze).
4. **Analyze**: upload orb → configure (question-choice card, guardrails, **Start Analysis directly
   below the guardrails and above the sections**, disabled until a set is confirmed) → progress →
   results. Section toggles are WYSIWYG: the explicit checked list is always sent.
5. **Progress**: `js/bb-status.js` is a transcription of iOS `AnalysisPhase`/`AnalysisStatus` — the
   12%→90% window band, key-details staying under it, `analysis_complete` not terminal. Rendered as a
   progress orb ring + five-step phase track, with a Live Activity popup (friendly narration for
   everyone, raw event stream for admins only).
6. **Results**: staged overview → sections → key details → document intelligence → improve
   (second-pass / deep-RAG multi-select) → exports → table view. `answer_summary` renders between the
   answer and the page citations everywhere, including CSV and the HTML report.
7. **Question Hub** reaches full 2.1.x parity: Create/Add first and glowing, Libraries (localStorage
   snapshots + a one-time Starter Set seed from the iOS `DefaultQuestionSet.json`), and a Current
   Question Set disclosure that reads "No set currently loaded" until the user chooses. The Create
   screen gained the **Questions Source** slot, an inline `source_intent` field (replacing
   `window.prompt`), Replace/Merge with an automatic library snapshot, the expert-panel card, and
   per-section rationale on suggestions. Generation now sends the analyzer document ALWAYS — as `file`
   with `source_kind=context`, or as `context_file` beside a PDF questions-source (the 2.1.1/2.1.2
   contract the web client never implemented).
8. **Testing**: `tests/test_web_ui.py` (30 served-structure/invariant tests, incl. a PNG-alpha check so
   a white-backed logo cannot ship again) and `tests/js/*.test.js` (85 dependency-free `node --test`
   unit tests over the pure logic). Suite: **106 passed**. A Playwright walkthrough of login → upload →
   hub → results → admin → settings at 1280px and 390px reports no console errors.

---

## Δ 2026-07-27 — Free Beta Testing + an /api/analyze auth fix (2.3.0)

A one-click free trial on the web sign-in page, an admin panel to run it, and a per-tester
document quota. **iOS untouched.** Full detail: `HANDOFF.md` § 2.3.0, `docs/WEB_FRONTEND.md`
(invariants 9–12).

1. **`services/beta_access.py` (NEW)** — owns the free-beta switch and the ephemeral tester
   registry. In-memory, lock-guarded (analyses run on background threads), hands out dict copies.
   Boot state from `BETA_LOGIN_ENABLED`, quota from `BETA_DOC_LIMIT` (default 5).
2. **Ephemeral identities, never a shared account.** Each `/auth/beta-login` mints `beta-<hex>`.
   Analyses are owner-scoped by username (`_is_authorized_for_session`), so one shared beta
   account would make every tester's results readable by every other tester.
3. **New routes**: `GET /api/beta/status` (public), `POST /auth/beta-login`,
   `GET|POST /api/admin/beta`, `POST|DELETE /api/admin/beta/testers/<username>`.
   `/api/user/info` gained `is_beta` + a live `beta` quota block.
4. **Quota** is enforced in `/api/analyze` — pre-checked for a clean 402 paywall, then claimed
   atomically at session pre-registration so invalid requests cost nothing.
5. **SECURITY: `/api/analyze` gained `@require_auth`.** It had none. Anonymous callers created
   analyses with `owner=None` — bypassing the quota and producing unowned sessions readable by
   anyone. A wider audit found 44 unguarded `/api/*` routes; most rely on per-session ownership
   checks, but the question-config group (already noted as a backend gap) remains genuinely open.
6. **Refactors**: `_issue_session` + `_set_auth_cookie` unify session creation across form/API/beta
   login; `format_session_info` + `_snapshot_sessions_by_bucket` lifted to module scope so the beta
   dashboard and `/api/admin/sessions` serve identical session rows (the shape iOS decodes).
7. `/health` → **2.3.0**. Suite: **130 passed** (was 106); JS: **97 passed** (was 85).

---

## Δ 2026-08-02 — Visual Intelligence, results-as-workbook, in-app admin dashboard (2.4.0)

Web app only; iOS untouched and unaffected (it never sends the new flag; its results decode
ignores unknown keys). Full detail: `HANDOFF.md` § 2.4.0, `docs/WEB_FRONTEND.md` invariants 13–15.

1. **Layer 0.5 — Visual Intelligence** (`services/hotdog/visual_intelligence.py`, NEW; opt-in via
   `enable_visual_analysis` on `/api/analyze`). Heuristic page selection (raster coverage + vector
   path density + text sparsity; pure `score_page` fn; cap `BIDBRIEF_VISUAL_MAX_PAGES`=25) →
   pages rendered ≤1568px → vision call through `completion_params` (`BIDBRIEF_MODEL_VISION`
   overrides the model) → each finding appends a `[VISUAL CONTENT]` block to the page text
   BEFORE `create_windows`, so experts cite drawing/map/photo content as normal `<PDF pg X>`
   answers. **ADDITIVE ONLY + failure-safe**: flag off ⇒ byte-identical pipeline; any error ⇒
   `visual_scan_failed` event, analysis continues. Findings list `visual_findings`
   {page, kind, title, description, extracted_text, key_facts, confidence} rides
   `get_browser_output`/`_build_partial_browser_output` → legacy payload → `/api/results` +
   `results_ready` + Excel export. Events: `visual_scan_start/visual_page_complete/
   visual_scan_complete/visual_scan_failed`.
2. **excel_dashboard.py** gains a **Visual Intelligence** sheet (after Document Intelligence,
   only when findings exist). The web HTML report gains the same table.
3. **Web results screen = the Excel workbook** (`bb-results.js` rebuilt): glass sheet tabs —
   Executive Summary / Detailed Results / By Section / Document Intelligence / Visual
   Intelligence / Footnotes (`sheetList()` gates the conditional two). Improve + Exports/Smart
   Analysis remain separate layers; `BB.results` helper API unchanged (bb-admin depends on it).
4. **Admin Session Dashboard in-app** (`bb-admin.js`): renders `/api/admin/sessions` on the
   design system (buckets, View results modal, **mode-aware per-session Excel export restored**,
   Stop for active). Legacy `/admin/sessions` page unlinked but still served.
5. `/health` → **2.4.0**. Suite: **149 passed** (was 130); JS: **110 passed** (was 97).
   Chromium walkthrough green, zero console errors, 1280px + 390px.
