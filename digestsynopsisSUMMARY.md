# BidBrief — Project Digest Synopsis
> Generated: 2026-03-01 | Three-pass deep review optimized for refactoring
> **READ THIS FIRST before touching any code. This is the canonical map.**

---

## 1. High-Level Summary

BidBrief is a Flask-based SaaS document analysis tool for construction/engineering bid professionals. It hosts two major product features under one application:

**HOTDOG AI** (Hierarchical Orchestrated Thorough Document Oversight & Guidance) — The core product. Ingests uploaded bid documents (PDF, DOCX, etc.), runs a multi-layer OpenAI-powered extraction pipeline across configurable expert question sets, and delivers structured Excel/browser results. Supports two analysis modes: **BID_SPEC** (deduplication-focused, optional v2 pipeline with ComprehensiveProcessor + RAG) and **BESTPREP** (append-only accumulation with final synthesis). Uses SSE + polling for real-time progress, Fernet encryption for uploaded files, and session-locked in-memory state management.

**CityScraper** — An admin-only municipal intelligence feature. Given a city name, it dispatches a multi-agent AI pipeline (5 preflight agents + 4–6 extraction agents) powered by Tavily web search + OpenAI GPT-4o to extract sewer/stormwater infrastructure data or active public bids. Produces live-updating data tables, Excel exports, and supports on-demand analysis modes. Both features share the same Flask app, session state lock, and auth layer.

---

## 2. Architecture & Major Components

### 2.1 Application Entry Point

**File:** `app.py` (3,924 lines — the monolith)

Single Flask application. All HOTDOG business logic (L0–L7 classes) lives inline here; CityScraper delegates to `services/scraper/`. Key global state:

```python
active_analyses: Dict[str, dict]        # sessions in progress
completed_analyses: Dict[str, dict]     # finished sessions
partial_analyses: Dict[str, dict]       # stopped-early sessions
session_lock: threading.Lock            # guards ALL 3 dicts on EVERY write

# CityScraper session dicts (separate from HOTDOG)
scraper_sessions: Dict[str, dict]       # research sessions
enrichment_sessions: Dict[str, dict]    # document enrichment sessions
comparison_sessions: Dict[str, dict]    # municipality comparison sessions
```

**Session ID formats:**
- HOTDOG: `uuid.uuid4().hex` (32 hex chars)
- CityScraper research: `scraper_{token_hex(8)}`
- CityScraper enrichment: `enrich_{token_hex(8)}`
- CityScraper comparison: `compare_{token_hex(8)}`

### 2.2 HOTDOG AI Layer Stack (L0–L7)

```
L0   DocumentIngestionLayer      services/document_extractor.py, services/pdf_extractor.py
L1   ConfigurationLoader         config/cipp_questions_default.json → ParsedConfig
L2   ExpertPersonaGenerator      app.py (async, GPT-4o, SHA256 cache per question set)
L3   MultiExpertProcessor        app.py (async parallel per window, temp=0.3, JSON mode)
L3.5 SecondPassProcessor         app.py (re-process unanswered Qs, temp=0.7, confidence≥0.3)
L4   SmartAccumulator            app.py (BID_SPEC, Jaccard dedup at 0.75 threshold)
     AppendOnlyAccumulator       app.py (BESTPREP, append-only, no dedup)
L4.5 DeepRAGProcessor            app.py (TAVILY external search, optional, confidence=0.3)
L5   TokenBudgetManager          app.py (60% prompt / 40% completion split)
L6   OutputCompiler              app.py (compile_results, format_for_browser, format_for_excel)
L7   SynthesisAgent              app.py (BESTPREP only, max_concurrent=3, temp=0.3)
```

### 2.3 HOTDOG7ATE Pipeline v2 (BID_SPEC Only, Optional)

Additional pipeline components when `use_pipeline_v2=True`:

```
PipelineCoordinator        Orchestrates 4 stages; _raise_if_stopped() at every boundary
DocumentStructureAnalyzer  7-pass analysis (TOC, Index, Appendix, SectionHeaders,
                           RunningHeaders, SpecDivisions, TopicHotspots) → DocumentStructure
DocumentNavigator          Pre-scan; NavigationMap + ExpertAssignment (primary ± 3 pages context)
                           EXPERT_KEYWORD_TEMPLATES (14 categories), 20+ regex domain patterns
ComprehensiveProcessor     Stage 1 quick scan (confidence_threshold=0.90, max 5 pages/question)
KeyRequirementsExtractor   Always runs; 13 fields; first 20 + last 5 pages; temp=0.1
SecondPassProcessor        Stage 3; unanswered Qs
DeepRAGProcessor           Stage 4; TAVILY; ≤3 queries (owner/engineer/project_type/location)
```

### 2.4 CityScraper Agent Architecture

```
services/scraper/
├── models.py                      All data models (Value Objects, Entities, UI Events)
├── config.py                      ScraperConfig singleton + SOURCE_HIERARCHY + keywords
├── agents/
│   ├── base.py                    BaseAgent (ABC) — shared Tavily rate-limiting (class-level)
│   ├── preflight/
│   │   ├── municipality_normalizer.py    PF-1 (required)
│   │   ├── jurisdiction_mapper.py        PF-2 (required)
│   │   ├── source_discovery.py           PF-3 (required)
│   │   ├── terminology_extractor.py      PF-4 (optional — required=False)
│   │   └── readiness_validator.py        PF-5 (required)
│   ├── extraction/
│   │   ├── infrastructure_extractor.py   EX-1 (required)
│   │   ├── equipment_extractor.py        EX-2 (optional)
│   │   ├── maintenance_extractor.py      EX-3 (optional)
│   │   ├── incident_extractor.py         EX-4 (required)
│   │   ├── bid_extractor.py              EX-5 (required for bids mode)
│   │   └── document_downloader.py        EX-6 (optional, depends on EX-5)
│   ├── analysis/
│   │   ├── summary_generator.py          AN-1 (on-demand)
│   │   ├── brainstormer.py               AN-2 (on-demand)
│   │   ├── deep_researcher.py            AN-3 (on-demand)
│   │   └── bid_analyzer.py              AN-4 (on-demand)
│   ├── bridge/
│   │   ├── municipality_detector.py      BR-1 (used by enrichment)
│   │   ├── gap_analyzer.py               BR-2 (used by enrichment)
│   │   ├── data_merger.py                BR-3 (used by enrichment)
│   │   └── scraper_dispatcher.py         BR-4 (used by enrichment)
│   └── presentation/
│       ├── table_formatter.py            PR-1 (markdown export)
│       ├── excel_generator.py            PR-2 (Excel export)
│       └── ui_data_packager.py           PR-3 (end of research pipeline)
├── orchestrators/
│   ├── standalone_research.py            UC-2 — master research orchestrator
│   ├── preflight.py                      PF-O — runs PF-1 to PF-5
│   ├── extraction.py                     EX-O — runs EX-1 to EX-6
│   ├── comparative_intelligence.py       Compare 2+ municipalities
│   ├── document_enrichment.py            Enrich HOTDOG session with municipal data
│   └── bid_download.py                   Bid document download pipeline
└── prompts/                              Full LLM system prompts per agent
    ├── pf1.py ... pf5.py
    ├── ex1.py ... ex6.py
    ├── an1.py ... an4.py
    ├── br1.py ... br4.py
    └── pr1.py ... pr3.py
```

### 2.5 Service Layer (Non-CityScraper)

```
services/
├── document_extractor.py    Multi-format Strategy Pattern: PyMuPDF → PDFPlumber → PyPDF2
├── pdf_extractor.py         PDF-only Strategy Pattern:    PyPDF2  → PDFPlumber → pdfminer
├── excel_dashboard.py       ExcelDashboardGenerator (BID_SPEC, 4 + V2 sheets)
└── bestprep_excel.py        BestPrepExcelGenerator (BESTPREP, 5 sheets)
```

### 2.6 Auth & Security

- SHA256 hashed passwords, env-var users (`BIDBRIEF_USER_*`)
- httponly cookie `bidbrief_auth`, 24-hour expiry
- `@require_auth` decorator on all `/api/*` routes
- `@require_admin` decorator on CityScraper endpoints (admin cookie OR Bearer token)
- Fernet symmetric encryption for in-transit uploaded file storage
- CityScraper polling endpoints: session_id as auth token (low entropy — 8 hex bytes)

---

## 3. Data Models & Integrations

### 3.1 HOTDOG Session Dict Schema

```python
{
  'session_id': str,
  'status': 'running' | 'completed' | 'failed' | 'stopped',
  'mode': 'BID_SPEC' | 'BESTPREP',
  'use_pipeline_v2': bool,
  'filename': str,
  'events': List[dict],          # progress events polled by /api/events/<id>
  'result': dict | None,         # final compiled result
  'orchestrator': object,        # live ref to running orchestrator (has stop_requested attr)
  'started_at': datetime,
  'completed_at': datetime | None,
  'detected_municipality': str,  # set during analysis; consumed by CityScraper enrichment
}
```

### 3.2 CityScraper Core Data Models (`services/scraper/models.py`)

**Enums:**
- `TableMode`: `MUNICIPAL_SYSTEMS_INFO` | `MUNICIPAL_PUBLIC_BIDS`
- `PreflightStatus`: `PASS` | `PARTIAL` | `FAIL`
- `ConfidenceRating`: `HIGH` | `MEDIUM` | `LOW` (with documented criteria per field)

**Value Objects (frozen dataclasses):**
- `Municipality(city, state, county?, region?)` — `full_name` property, `search_key` property
- `SourceURL(url, title, source_type, retrieved_at, relevance_score)`
- `VerbatimCitation(text, source_url, source_title, page_or_section?)`

**Entities:**
- `ExtractedDataPoint(field_name, value, raw_source_value?, conversion_applied?, source_url, verbatim_quote, confidence, confidence_rationale, notes?, conflicts: List[Dict])` — **value NEVER blank; defaults to "NOT FOUND" in `__post_init__`**
- `MunicipalSystemsInfoRow` — 15 columns; `to_markdown_row()` pipe-escaped
- `MunicipalPublicBidRow` — 12 columns; `to_markdown_row()` pipe-escaped

**Preflight models:** `JurisdictionInfo`, `SourceMap`, `TerminologyMap`, `PreflightResult`

**Top-level extraction:** `ExtractionResult(municipality, table_mode, preflight, systems_info_rows, public_bid_rows, total_sources_searched, data_gaps, conflicts_detected, downloaded_documents)`

**Analysis models:** `SystemInfoSummary`, `BrainstormOpportunity`, `DeepResearchTrail`, `BidAnalysis`

**Agent communication:** `AgentRequest(agent_id, task, input_data, context, priority, timeout_seconds)`, `AgentResponse(agent_id, task, success, output_data, errors, tokens_used, processing_time_seconds)`

**UI event models:**
- `AgentActivityEvent(agent_id, agent_name, status, message, is_active, is_completed, timestamp, data_update: Optional[Dict])` — **`data_update` drives live table rows in UI**
- `ScraperSessionProgress(session_id, phase, progress_percent, current_agent, agent_events, debug_events, status)`

### 3.3 ScraperConfig Values

```python
TavilyConfig:
  api_key: env TAVILY_API_KEY (None if missing → graceful degradation)
  search_depth: "advanced"
  max_results_per_query: 20  # NOTE: env var SCRAPER_MAX_RESULTS defaults to 10, not 20
  include_raw_content: True
  timeout_seconds: 60
  requests_per_minute: 30
  circuit_breaker_threshold: 5   # consecutive failures to open circuit
  circuit_breaker_cooldown: 60.0  # seconds

OpenAIConfig:
  api_key: env OPENAI_API_KEY
  model: "gpt-4o"
  temperature: 0.1
  max_tokens: 16384

AgentConfig:
  max_context_tokens: 32000
  max_retries: 3
  retry_delay_seconds: 2.0
  require_citations: True

ScraperConfig.is_ready: tavily AND openai both non-None
```

**SOURCE_HIERARCHY** (11-level, index 0 = most authoritative):
`gis_export → asset_management_db → engineering_report → regulatory_filing → capital_improvement_plan → cmom_sso_report → ms4_permit → comprehensive_plan → budget_document → news_article → press_release`

Used by `get_source_authority(source_type) → int` (unknown type → len(HIERARCHY) = lowest auth).

### 3.4 External Integrations

| Integration | Where | Key Config |
|-------------|-------|-----------|
| OpenAI API | HOTDOG (L2–L7) + CityScraper (all agents) | `OPENAI_API_KEY`, model gpt-4o |
| Tavily Search | HOTDOG DeepRAGProcessor + CityScraper BaseAgent | `TAVILY_API_KEY` |
| Fernet | Upload encryption | `FERNET_KEY` env |
| Flask sessions | Cookie auth | `SECRET_KEY` env |
| Gunicorn | Production | 1 worker, 10 threads, 900s timeout |

---

## 4. Critical Flows & Behaviors

### 4.1 HOTDOG Classic Pipeline Flow (BID_SPEC)

```
POST /api/analyze
  → @require_auth, validate form (file, mode, config_id)
  → DocumentIngestionLayer.ingest() → List[(page_num, text)]
  → ConfigurationLoader.load(config_id) → ParsedConfig
  → session_lock: create entry in active_analyses
  → spawn daemon thread → run_analysis_async(session_id, ...)

run_analysis_async():
  → L2: ExpertPersonaGenerator.generate() [async, SHA256 cached]
  → L5: TokenBudgetManager.calculate_budget()
  → SLIDING WINDOW LOOP (3 pages, non-overlapping):
      → L3: MultiExpertProcessor.process_window(pages, experts) [asyncio.gather]
      → L4: SmartAccumulator.accumulate(window_results)  [Jaccard 0.75]
  → L3.5: SecondPassProcessor.process_unanswered()
  → (if Tavily available) L4.5: DeepRAGProcessor.search_tavily()
  → L6: OutputCompiler.compile_results() + format_for_browser()
  → session_lock: move active_analyses → completed_analyses
  → append 'completed' event to events list
```

### 4.2 HOTDOG v2 Pipeline Flow (BID_SPEC, use_pipeline_v2=True)

```
POST /api/analyze
  → DocumentIngestionLayer.ingest()
  → PipelineCoordinator.__init__()
  → Stage 0a: DocumentStructureAnalyzer.analyze() [7 passes]
  → Stage 0b: DocumentNavigator.pre_scan() → NavigationMap
  → Stage 1a: ComprehensiveProcessor.quick_scan() [confidence_threshold=0.90]
  → Stage 1b: KeyRequirementsExtractor.extract() [always, 13 fields]
  → _raise_if_stopped()
  → Stage 2:  MultiExpertProcessor (targeted pages from NavigationMap)
  → _raise_if_stopped()
  → Stage 3:  SecondPassProcessor (unanswered Qs)
  → _raise_if_stopped()
  → Stage 4:  DeepRAGProcessor (TAVILY, ≤3 queries)
  → OutputCompiler → completed
```

### 4.3 HOTDOG BESTPREP Flow

```
Same as classic BUT:
  L4: AppendOnlyAccumulator (no dedup, all fragments kept)
  L7: SynthesisAgent runs AFTER all windows (max_concurrent=3, temp=0.3)
  Excel: BestPrepExcelGenerator (5 sheets: Summary, Synthesized Answers,
         All Fragments, All Footnotes, Page Index)
```

### 4.4 HOTDOG Stop Flow

```
POST /api/stop/<session_id>
  → orchestrator.stop_requested = True
  → poll up to 10s (0.5s intervals) watching for session_id in partial_analyses
  → return 200 with partial results OR 202 if still running after 10s
```

### 4.5 CityScraper Research Flow (UC-2)

```
POST /api/scraper/research
  → @require_admin
  → scraper_sessions[session_id] = {status: 'running', events: [], ...}
  → spawn daemon thread → run_scraper_research_sync(session_id, ...)

run_scraper_research_sync():
  → asyncio.new_event_loop().run_until_complete(orchestrator.run())

StandaloneResearchOrchestrator.run():
  → _validate_inputs(municipality_input, table_mode)   [len≥3, valid mode string]
  → _run_preflight() → PreflightOrchestrator.run():
      PF-1 (required) → normalize city/state
      check _cancelled
      PF-2 (required) → jurisdiction mapping
      check _cancelled
      PF-3 (required) → source discovery
      check _cancelled
      PF-4 (optional) → terminology extraction (failure non-fatal)
      check _cancelled
      PF-5 (required) → readiness validation → to_preflight_result()
      → returns PreflightResult
  → check _cancelled
  → _run_extraction() → ExtractionOrchestrator.run():
      if MUNICIPAL_SYSTEMS_INFO:
        asyncio.gather(EX-1, EX-2, EX-3, EX-4)    ← PARALLEL
      if MUNICIPAL_PUBLIC_BIDS:
        EX-5 sequential → EX-6 (only if EX-5 has docs)  ← SEQUENTIAL
      → returns ExtractionResult
  → check _cancelled
  → _run_presentation():
      UIDataPackagerAgent.process() → packaged UI data
      (failure non-fatal; raw extraction data returned instead)
  → _calculate_statistics()
  → scraper_sessions[session_id] = {status: 'completed', result: ...}
```

### 4.6 CityScraper Extraction Parallelism Detail

```python
# ExtractionOrchestrator._run_systems_info_extraction()
tasks = [(stage.agent_id, _run_stage(stage, input_data)) for stage in SYSTEMS_INFO_STAGES]
stage_results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
# Exceptions caught per-task and wrapped as PipelineResult(success=False)
# EX-1 (Infrastructure): required=True   → failure → aggregation marks as gap
# EX-2 (Equipment):      required=False  → failure → silently continues
# EX-3 (Maintenance):    required=False  → failure → silently continues
# EX-4 (Incident):       required=True   → failure → aggregation marks as gap

# ExtractionOrchestrator._run_bid_extraction()
# EX-5 runs first → extracts bids + downloadable_documents
# EX-6 runs only if EX-5 success AND downloadable_documents non-empty
# EX-6 max file size: 50MB, timeout: 30s, session_id passed for file naming
```

### 4.7 BaseAgent Tavily Rate Limiting (Class-Level, All Instances Share)

```python
BaseAgent._tavily_last_call_time: float = 0.0       # shared
BaseAgent._tavily_consecutive_failures: int = 0       # shared
BaseAgent._tavily_circuit_open_until: float = 0.0    # shared
BaseAgent._tavily_min_interval: float = 2.0          # 2s between calls minimum

Circuit breaker:
  5 consecutive failures → open circuit (raise immediately, no retries)
  Auto-close after 60s cooldown

Retry per query: max 3 attempts (from AgentConfig.max_retries)
Backoff: min(initial_backoff * 2**attempt, max_backoff) — NO JITTER

Tavily response:
  Returns List[{title, url, content, raw_content, score, query}]
  PLUS: if answer field present → append as extra item with score=1.0
```

### 4.8 CityScraper Event System (Live UI Updates)

```python
# Two event types:
emit_event(message)           → AgentActivityEvent(data_update=None)   [status only]
emit_data_event(data, msg)    → AgentActivityEvent(data_update=dict)    [live table row]

# Polling endpoint:
GET /api/scraper/events/<id>?since=N
  → returns events[N:] + current status + error if any
```

### 4.9 CityScraper Analysis Agents (Synchronous On-Demand)

```python
POST /api/scraper/analyze/{summary|brainstorm|research|bid}
  → @require_admin
  → asyncio.new_event_loop().run_until_complete(agent.process(request))
  # Each creates a fresh event loop — no shared async state
```

### 4.10 Session Lifecycle (HOTDOG)

```
upload + POST /analyze → active_analyses
  ↓ (orchestrator.stop_requested = True via /api/stop)
partial_analyses  (partial results)
  ↓ (complete / fail)
completed_analyses

cleanup_expired_sessions():
  - Runs at module load (threading daemon)
  - Repeats every 15 minutes
  - Moves completed sessions older than SESSION_EXPIRY_HOURS (default 24h) to cleanup
```

### 4.11 Progress Delivery

```
Primary:   GET /api/events/<id>?since=N     → polls events list, returns new events after index N
Secondary: GET /api/progress/<id>           → SSE stream via EventSource
```

---

## 5. EXHAUSTIVE FUNCTION & MODULE MAP

### 5.1 `app.py` — All Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/` | cookie | Main SPA |
| POST | `/api/analyze` | cookie | Start HOTDOG analysis |
| GET | `/api/status/<id>` | cookie | Poll session status |
| GET | `/api/progress/<id>` | cookie | SSE progress stream |
| GET | `/api/events/<id>` | cookie | Poll events array (primary) |
| POST | `/api/stop/<id>` | cookie | Stop; polls 10s for partial result |
| GET | `/api/result/<id>` | cookie | Get final result JSON |
| GET | `/api/download/<id>` | cookie | BID_SPEC Excel download |
| GET | `/api/download/bestprep/<id>` | cookie | BESTPREP Excel download |
| POST | `/api/login` | none | Password auth |
| POST | `/api/logout` | cookie | Clear cookie |
| GET | `/api/config` | cookie | Get current question config |
| POST | `/api/config` | admin | Save custom config |
| DELETE | `/api/config` | admin | Reset to default |
| GET | `/api/config/default` | cookie | Get default config |
| GET | `/api/sessions` | admin | List all HOTDOG sessions |
| DELETE | `/api/sessions/<id>` | admin | Delete session |
| POST | `/api/openai/chat` | cookie | OpenAI proxy (server-side key) |
| POST | `/api/scraper/research` | admin | Start CityScraper research |
| GET | `/api/scraper/research/<id>` | session_id | Research status + result |
| GET | `/api/scraper/events/<id>` | session_id | Poll scraper events |
| POST | `/api/scraper/stop/<id>` | session_id | Cancel scraper |
| POST | `/api/scraper/enrich/<hotdog_id>` | admin | Enrich via HOTDOG session data |
| POST | `/api/scraper/compare` | admin | Compare ≥2 municipalities |
| POST | `/api/scraper/analyze/summary` | admin | AN-1 (sync) |
| POST | `/api/scraper/analyze/brainstorm` | admin | AN-2 (sync) |
| POST | `/api/scraper/analyze/research` | admin | AN-3 (sync) |
| POST | `/api/scraper/analyze/bid` | admin | AN-4 (sync) |
| GET | `/api/scraper/sessions` | admin | List all scraper sessions |
| DELETE | `/api/scraper/sessions/<id>` | admin | Cancel + delete |
| GET | `/api/scraper/export/excel/<id>` | session_id | PR-2 Excel via send_file |
| GET | `/api/scraper/export/markdown/<id>` | session_id | PR-1 Markdown attachment |
| GET | `/health` | none | Status + active/completed counts |

**Error handlers:** 404 → JSON, 500 → JSON + logging, global Exception → JSON

**Boot:** `cleanup_expired_sessions()` at module level. `if __name__ == '__main__'`: port from `PORT` env, debug from `DEBUG` env, `app.run(host='0.0.0.0', threaded=True)`.

### 5.2 `app.py` — Key Inline Classes & Functions

| Name | Type | Location / Purpose |
|------|------|-------------------|
| `require_auth` | decorator | Check `bidbrief_auth` cookie; 401 JSON on failure |
| `require_admin` | decorator | Admin cookie OR Bearer token; 403 JSON on failure |
| `cleanup_expired_sessions()` | fn | Thread daemon; runs every 15min from startup |
| `run_analysis_async(session_id, ...)` | fn | Main HOTDOG runner in daemon thread |
| `run_scraper_research_sync(...)` | fn | Sync wrapper for CityScraper asyncio |
| `ExpertPersonaGenerator` | class | L2: generate experts from question config (SHA256 cache) |
| `MultiExpertProcessor` | class | L3: asyncio.gather per window; temp=0.3; JSON format |
| `SecondPassProcessor` | class | L3.5: re-process unanswered; temp=0.7; confidence≥0.3 |
| `SmartAccumulator` | class | L4 BID_SPEC: Jaccard dedup at 0.75 |
| `AppendOnlyAccumulator` | class | L4 BESTPREP: append all fragments |
| `DeepRAGProcessor` | class | L4.5: Tavily external search; confidence always 0.3 |
| `TokenBudgetManager` | class | L5: 60/40 prompt/completion split |
| `OutputCompiler` | class | L6: compile_results(), format_for_browser(), format_for_excel() |
| `SynthesisAgent` | class | L7 BESTPREP: max_concurrent=3; temp=0.3 |
| `PipelineCoordinator` | class | v2: orchestrates 4 stages; _raise_if_stopped() |
| `DocumentStructureAnalyzer` | class | v2: 7-pass analysis → DocumentStructure |
| `DocumentNavigator` | class | v2: pre-scan → NavigationMap + ExpertAssignment |
| `ComprehensiveProcessor` | class | v2 Stage 1: quick scan; confidence_threshold=0.90 |
| `KeyRequirementsExtractor` | class | v2: 13-field extraction; first 20 + last 5 pages; temp=0.1 |
| `TokenOptimizer` | class | ModelLimits + MODEL_CONFIGS for 5 GPT-4 variants |
| `MODULE_LOAD_ID` | const | Admin diagnostic: worker restart detection |
| `MODULE_LOAD_TIME` | const | Admin diagnostic: worker start time |

### 5.3 `services/scraper/agents/base.py` — BaseAgent (Abstract)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `__init__` | `(config, openai_client?, event_callback?)` | Init; creates httpx.AsyncClient |
| `get_system_prompt` | `() → str` | **Abstract** — each agent implements |
| `process` | `(request: AgentRequest) → AgentResponse` | **Abstract** — main agent execution |
| `validate_output` | `(output: dict) → bool` | **Abstract** — validates LLM response |
| `emit_event` | `(agent_id, name, status, message, data_update?)` | Creates + fires AgentActivityEvent |
| `call_openai` | `(messages, temperature?, max_tokens?) → str` | GPT-4o call; updates AgentMetrics |
| `search_tavily` | `(query, max_results?) → List[dict]` | Rate-limited Tavily; circuit breaker + backoff |
| `cleanup` | `() → None` | **ALWAYS call in finally** — closes httpx.AsyncClient |
| `get_metrics` | `() → dict` | Returns AgentMetrics as dict |

**Class-level rate limiting (ALL instances share):**
`_tavily_last_call_time`, `_tavily_consecutive_failures`, `_tavily_circuit_open_until`, `_tavily_min_interval=2.0`

### 5.4 `services/scraper/orchestrators/standalone_research.py` — StandaloneResearchOrchestrator

| Method | Purpose |
|--------|---------|
| `__init__(config, event_callback)` | Init state |
| `run(municipality_input, table_mode)` | Top-level pipeline; called from asyncio loop |
| `cancel()` | Sets `_cancelled = True`; checked between stages |
| `emit_event(message, agent_id?, status?)` | Status event |
| `emit_data_event(data, message?)` | Live table row event (data_update dict) |
| `_validate_inputs(municipality_input, table_mode)` | len≥3; valid mode string |
| `_create_event_collector()` | Returns callback storing + forwarding events |
| `_run_preflight(municipality_input, table_mode)` | Instantiates + runs PreflightOrchestrator |
| `_run_extraction(municipality, table_mode, preflight)` | Instantiates + runs ExtractionOrchestrator |
| `_run_presentation(extraction_result)` | PR-3 UIDataPackager; non-fatal failure |
| `_calculate_statistics(stages)` | Aggregates from stage_results list |
| `_serialize_preflight_result(result)` | PreflightResult → dict |
| `_serialize_extraction_result(result)` | ExtractionResult → dict |
| `_create_error_result(error, stage_results?)` | Partial result on error |
| `_create_cancelled_result(stage_results?)` | Partial result on cancel |
| `get_statistics()` | Orchestrator-level stats |

### 5.5 `services/scraper/orchestrators/preflight.py` — PreflightOrchestrator

| Method | Purpose |
|--------|---------|
| `__init__(config, event_callback)` | Init; defines PIPELINE_STAGES PF-1..PF-5 |
| `run(municipality_input, table_mode)` | Sequential: PF-1→PF-2→PF-3→PF-4→PF-5 |
| `cancel()` | Sets `_cancelled = True` |
| `emit_event(message, stage_id?)` | Progress event |
| `_resolve_table_mode(table_mode_input)` | String → TableMode enum |
| `_run_stage(stage, input_data)` | Execute + retry (max_retries=2 per stage) |
| `_create_failed_result(municipality, table_mode, error, state)` | FAIL PreflightResult |
| `_create_cancelled_result(municipality, state, table_mode)` | FAIL PreflightResult |
| `_aggregate_results(...)` | Fallback when PF-5 fails to produce result |
| `get_statistics()` | Execution stats dict |

**Important details:**
- Each stage: new agent instance per run. Cleanup via `await agent.cleanup()` in `finally`.
- PF-5: `ReadinessValidatorAgent.to_preflight_result()` called on a SECOND new instance — known code smell.
- `_cancelled` checked after each stage completion.

### 5.6 `services/scraper/orchestrators/extraction.py` — ExtractionOrchestrator

| Method | Purpose |
|--------|---------|
| `__init__(config, event_callback)` | Init; SYSTEMS_INFO_STAGES + BID_STAGES |
| `run(municipality, table_mode, preflight_result)` | Routes to systems/bids/both |
| `cancel()` | Sets `_cancelled = True` |
| `emit_event(message, stage_id?)` | Progress event |
| `_run_systems_info_extraction(municipality, preflight)` | **asyncio.gather(EX-1,EX-2,EX-3,EX-4) PARALLEL** |
| `_run_bid_extraction(municipality, preflight)` | EX-5 → EX-6 SEQUENTIAL |
| `_run_stage(stage, input_data)` | Execute + retry (same pattern as PF-O) |
| `_extract_source_map(preflight_result)` | preflight.source_map → dict |
| `_extract_terminology(preflight_result)` | preflight.terminology → dict |
| `_extract_downloadable_documents(ex5_output)` | Flatten bids → docs with URLs |
| `_aggregate_results(...)` | ExtractionResult from all stage outputs |
| `_create_failed_result(...)` | Error ExtractionResult |
| `_create_cancelled_result(...)` | Cancelled ExtractionResult |
| `get_statistics()` | Execution stats |

### 5.7 CityScraper Agent Summary (All Groups)

**Preflight (PF-1 to PF-5) — sequential, each depends on prior:**

| ID | Class | Input Keys | Key Output Keys |
|----|-------|-----------|----------------|
| PF-1 | `MunicipalityNormalizerAgent` | `municipality_input` | `normalized.{city,state,county,region}` |
| PF-2 | `JurisdictionMapperAgent` | `municipality_name, state` | `jurisdiction.{sewer_owner,storm_owner,...}` |
| PF-3 | `SourceDiscoveryAgent` | `municipality_name, state` | `source_map.{official_website,public_works,...}` |
| PF-4 | `TerminologyExtractorAgent` (opt) | `municipality_name, state` | `terminology.{sanitary_terms,storm_terms,...}` |
| PF-5 | `ReadinessValidatorAgent` | `all PF results + table_mode` | `PreflightResult` via `to_preflight_result()` |

**Extraction (EX-1 to EX-6):**

| ID | Class | Mode | Required | Key Output |
|----|-------|------|---------|-----------|
| EX-1 | `InfrastructureExtractorAgent` | Systems | **Yes** | pipe miles, system age, agency scope |
| EX-2 | `EquipmentExtractorAgent` | Systems | No | equipment owned fields |
| EX-3 | `MaintenanceExtractorAgent` | Systems | No | maintenance practices fields |
| EX-4 | `IncidentExtractorAgent` | Systems | **Yes** | sewage/storm incidents (PRIORITY) |
| EX-5 | `BidExtractorAgent` | Bids | **Yes** | `bids[{bid_title,downloadable_documents,...}]` |
| EX-6 | `DocumentDownloaderAgent` | Bids | No | downloaded files; 50MB limit, 30s timeout |

**Analysis (AN-1 to AN-4) — on-demand, sync via new event loop:**

| ID | Class | Endpoint | Output Model |
|----|-------|---------|-------------|
| AN-1 | `SummaryGeneratorAgent` | `/analyze/summary` | `SystemInfoSummary` (4 perspectives) |
| AN-2 | `BrainstormerAgent` | `/analyze/brainstorm` | `List[BrainstormOpportunity]` |
| AN-3 | `DeepResearcherAgent` | `/analyze/research` | `DeepResearchTrail` |
| AN-4 | `BidAnalyzerAgent` | `/analyze/bid` | `BidAnalysis` (scope, timeline, cost) |

**Bridge (BR-1 to BR-4) — used by DocumentEnrichmentOrchestrator:**

| ID | Class | Purpose |
|----|-------|---------|
| BR-1 | `MunicipalityDetectorAgent` | Auto-detect municipality from HOTDOG doc text |
| BR-2 | `GapAnalyzerAgent` | Find data gaps between HOTDOG and CityScraper |
| BR-3 | `DataMergerAgent` | Merge HOTDOG data with CityScraper data |
| BR-4 | `ScraperDispatcherAgent` | Trigger targeted CityScraper for gaps |

**Presentation (PR-1 to PR-3):**

| ID | Class | Triggered By | Output |
|----|-------|-------------|--------|
| PR-1 | `TableFormatterAgent` | `/export/markdown/<id>` | Markdown table text/markdown |
| PR-2 | `ExcelGeneratorAgent` | `/export/excel/<id>` | Excel file (send_file) |
| PR-3 | `UIDataPackagerAgent` | End of StandaloneResearchOrchestrator | JSON for live UI rendering |

### 5.8 `services/document_extractor.py` — Multi-Format Extraction

| Class/Method | Purpose |
|--------------|---------|
| `DocumentExtractionStrategy` (ABC) | `extract_text_with_pages(path)`, `supports_file(path)`, `name` |
| `PyMuPDFStrategy` | Primary: `fitz.open()`, `page.get_text()` |
| `PDFPlumberStrategy` | PDF fallback |
| `PyPDF2Strategy` | PDF fallback 2 |
| `DocumentExtractorService` | Strategy chain; `extract_text_with_pages()`, `extract_text_combined()` |

Output format: `List[Tuple[int, str]]` (page_num, page_text)

### 5.9 `services/pdf_extractor.py` — PDF-Only Extraction

| Class/Method | Purpose |
|--------------|---------|
| `PyPDF2Strategy` | Primary |
| `PDFPlumberStrategy` | Fallback 1 |
| `PDFMinerStrategy` | Fallback 2; handles `--- PAGE N ---` markers |
| `PDFExtractorService` | `extract_text_with_pages()`, `extract_text_combined()`, `_clean_text()` |

`extract_text_combined()` joins pages with `\n\n<PDF pg {N}>\n{text}` markers.

**Note:** Two separate extraction services exist. Unclear which HOTDOG uses. `document_extractor.py` handles multi-format; `pdf_extractor.py` is PDF-only. This is a DRY/clarity issue.

### 5.10 `services/excel_dashboard.py` — BID_SPEC Excel

| Method | Purpose |
|--------|---------|
| `__init__(analysis_result, is_partial, api_key_requirements, optimized_scan_data, unanswered_pass_data, rag_data)` | Init with all V2 pipeline data |
| `generate()` | 4 standard sheets + V2-specific sheets |
| `sanitize_for_excel(text)` | Strip control chars 0x00–0x1F (except 0x09, 0x0A, 0x0D) |
| `KEY_REQUIREMENT_PATTERNS` | 13 regex categories for key requirement extraction |

**Sheets:** Executive Summary, Detailed Results, By Section, Footnotes (+ V2: Key Requirements, etc.)
**Color scheme:** BidBrief Navy/Blue constants defined at module level.

### 5.11 `services/bestprep_excel.py` — BESTPREP Excel

| Method | Purpose |
|--------|---------|
| `__init__(analysis_result, accumulator_data)` | Init |
| `generate()` | 5 sheets |
| `sanitize_for_excel(text)` | **Duplicate of excel_dashboard.py version (DRY violation)** |

**Sheets:** Summary, Synthesized Answers, All Fragments, All Footnotes, Page Index

---

## 6. Risks, Gaps, and Open Questions

### 6.1 Confirmed Technical Risks

**Architecture:**
- `app.py` is 3,924 lines — all HOTDOG layers (L0–L7), pipeline classes, session management, routing, and auth in one file. Largest single refactoring debt.
- No test files observed in codebase. Verification relies entirely on runtime behavior.
- Two PDF extraction services (`document_extractor.py` vs `pdf_extractor.py`) with no clear documentation of which HOTDOG uses.

**State Management:**
- All 6 session dicts share one `session_lock` — single-threaded bottleneck under concurrency.
- No disk persistence: app restart = all session data lost.
- CityScraper session tokens: `token_hex(8)` = only 32-bit entropy (4 billion combinations).

**CityScraper:**
- `ReadinessValidatorAgent.to_preflight_result()` invoked on a throwaway second agent instance (preflight.py:272). Wasteful; suggests method should be `@staticmethod`.
- BaseAgent class-level Tavily state has no explicit threading lock — relies on Python GIL.
- No jitter in exponential backoff → thundering herd risk after circuit breaker reopens.
- `SCRAPER_MAX_RESULTS` env var defaults to 10 in `from_env()` but dataclass default is 20. Inconsistency.

**HOTDOG:**
- Jaccard threshold (0.75) hardcoded — no per-upload configuration.
- Cost calculation: `total_tokens * 0.00003` is GPT-4 rate, not gpt-4o rate.
- `detected_municipality` in HOTDOG session dict populated during analysis but integration with CityScraper enrichment flow is lightly documented.

**Security:**
- No visible CSRF protection on state-changing POST endpoints.
- `sanitize_for_excel()` duplicated in two files — a change to one silently diverges from the other.

### 6.2 Open Questions

1. Does HOTDOG L0 use `document_extractor.py` or `pdf_extractor.py`?
2. Are Bridge agents (BR-1 to BR-4) fully integrated and tested in `DocumentEnrichmentOrchestrator`?
3. What happens to EX-6 downloaded files after session expiry?
4. Does "both" TableMode (checked by string) work end-to-end? The enum has only two values.
5. Is `DeepRAGProcessor` in HOTDOG using the same Tavily key as CityScraper? Rate limits could interact.
6. Which `prompts/` files have been verified against actual agent behavior?

---

## 7. Edge Cases & Failure Modes

| Scenario | Behavior |
|----------|----------|
| Tavily API key missing | CityScraper degrades to OpenAI-only; HOTDOG RAG skipped |
| OpenAI API key missing | `ScraperConfig.is_ready = False`; agents all fail |
| EX-5 fails | EX-6 skipped: `PipelineResult(success=False, error="Skipped - EX-5 failed")` |
| PF-4 fails | Pipeline continues (required=False) |
| PR-3 (UIDataPackager) fails | `_run_presentation()` catches exception; raw extraction data returned |
| All PDF libs unavailable | `PDFExtractorService` raises "All PDF extraction methods failed" |
| Circuit breaker open | `search_tavily()` raises immediately; no retries during cooldown (60s) |
| Session not found on GET | 404 JSON `{"error": "Session not found"}` |
| Stop on completed session | Returns completed result without error |
| Presentation agent cleanup | `agent.cleanup()` in `finally` — always called even on failure |
| EX-1/EX-4 fail (parallel) | `asyncio.gather(return_exceptions=True)` catches; wrapped as PipelineResult(success=False) |
| PF-5 fails to produce result | `_aggregate_results()` fallback: PASS if PF-1+2+3+5 succeed, PARTIAL if 1+2 succeed |
| EX-6 no documents | Skipped with explicit success PipelineResult (empty downloads list) |

---

## 8. Opportunities & Recommended Next Steps

### 8.1 High-Impact Refactoring (Priority Order)

1. **Extract HOTDOG pipeline from app.py** → `services/hotdog/` mirroring CityScraper structure:
   - `services/hotdog/layers/` (L0–L7 as separate classes)
   - `services/hotdog/pipeline/` (PipelineCoordinator + v2 components)
   - `services/hotdog/orchestrator.py` (session management)

2. **Unify PDF extraction** — Choose `document_extractor.py` (more complete), deprecate `pdf_extractor.py`, update all callers.

3. **Deduplicate `sanitize_for_excel()`** → `services/excel_utils.py`.

4. **Fix `ReadinessValidatorAgent.to_preflight_result()`** → Make `@staticmethod` or module-level function; eliminate throwaway instance.

5. **Strengthen CityScraper tokens** → `token_hex(16)` (128-bit).

### 8.2 Quick Wins

- Add `asyncio.Semaphore` to BaseAgent Tavily calls for explicit thread safety.
- Add jitter to backoff: `backoff * (1 + random.uniform(0, 0.3))`.
- Fix `SCRAPER_MAX_RESULTS` inconsistency: align env default with dataclass default.
- Update token cost constant to gpt-4o pricing.

### 8.3 Feature Validation

- Validate Bridge agents (BR-1 to BR-4) integration in `DocumentEnrichmentOrchestrator`.
- Surface HOTDOG → CityScraper enrichment flow in UI (the `enrich_from_hotdog` endpoint exists but UI integration is unclear).
- Add session persistence (Redis or SQLite) to survive restarts.

---

## 9. Configuration Reference

### 9.1 Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENAI_API_KEY` | Yes | — | All AI features |
| `TAVILY_API_KEY` | No | — | RAG + CityScraper web search |
| `FERNET_KEY` | Yes | — | File upload encryption |
| `SECRET_KEY` | Yes | — | Flask session signing |
| `BIDBRIEF_USER_*` | Yes (≥1) | — | User auth |
| `BIDBRIEF_ADMIN_*` | Yes (CityScraper) | — | Admin auth |
| `ADMIN_BEARER_TOKEN` | No | — | API bearer token alternative |
| `PORT` | No | 5000 | Dev server port |
| `DEBUG` | No | false | Flask debug mode |
| `SCRAPER_SEARCH_DEPTH` | No | advanced | Tavily depth |
| `SCRAPER_MAX_RESULTS` | No | 10 (env) / 20 (dataclass) | Results per query |
| `SCRAPER_OPENAI_MODEL` | No | gpt-4o | CityScraper model |
| `SCRAPER_DOWNLOADS_DIR` | No | scraper_downloads | EX-6 download dir |
| `SCRAPER_CACHE_DIR` | No | scraper_cache | Cache dir |
| `SESSION_EXPIRY_HOURS` | No | 24 | Session cleanup |

### 9.2 Key Files Quick Reference

| File | Purpose |
|------|---------|
| `app.py` | ALL HOTDOG logic + ALL routing + session management |
| `services/scraper/models.py` | All CityScraper data models |
| `services/scraper/config.py` | ScraperConfig singleton |
| `services/scraper/agents/base.py` | BaseAgent + Tavily rate limiting |
| `services/scraper/orchestrators/standalone_research.py` | CityScraper main entry point |
| `services/scraper/orchestrators/preflight.py` | PF-O (PF-1 to PF-5) |
| `services/scraper/orchestrators/extraction.py` | EX-O (EX-1 to EX-6) |
| `services/document_extractor.py` | Multi-format PDF/DOCX extraction |
| `services/pdf_extractor.py` | PDF-only extraction (parallel impl) |
| `services/excel_dashboard.py` | BID_SPEC Excel output |
| `services/bestprep_excel.py` | BESTPREP Excel output |
| `config/cipp_questions_default.json` | 100 questions, 9 sections |

---

## 10. Refactoring Conventions & Rules

> These must be respected in every code change.

1. **Session lock discipline** — ALL reads/writes to `active_analyses`, `completed_analyses`, `partial_analyses`, `scraper_sessions`, `enrichment_sessions`, `comparison_sessions` inside `with session_lock:`.

2. **Agent cleanup** — ALWAYS call `await agent.cleanup()` in `finally` blocks. HTTP clients are not garbage collected automatically.

3. **`ExtractedDataPoint.value`** — NEVER set to empty string. "NOT FOUND" is enforced in `__post_init__`, but constructors with explicit `value=""` bypass it.

4. **`<PDF pg X>` citation format** — Mandatory in all HOTDOG LLM responses. Regex: `r'<PDF pg ([0-9, ]+)>'`. Do not change format.

5. **Tavily in CityScraper** — Route all Tavily calls through `BaseAgent.search_tavily()`. Never bypass the rate limiter.

6. **Cancellation checks** — Check `self._cancelled` between EVERY major stage in orchestrators, not inside agent loops.

7. **PF-4 is optional** — Never assert `preflight_result.terminology is not None`.

8. **EX-2, EX-3 are optional** — Never assert equipment or maintenance data present in aggregated results.

9. **TableMode "both"** — Detected by string check `"both" in str(table_mode.value).lower()`. The enum has only two values. Adding a BOTH variant requires updating all downstream conditional logic.

10. **New CityScraper agents** — Must extend `BaseAgent`, implement all 3 abstract methods, and be registered in the corresponding orchestrator's `PIPELINE_STAGES` list.

11. **No inline session management in routes** — Session dict manipulation belongs in orchestrators, not Flask route handlers.

12. **Cost calculation** — Token cost at `total_tokens * 0.00003` is WRONG for gpt-4o. Do not add new cost calculations using this constant without fixing it first.
