# Smart Analysis Architecture Reference

## Overview

Smart Analysis is a multi-agent AI pipeline that performs executive-grade document analysis on bid and procurement documents. It runs after a user completes the standard Q&A extraction phase and explicitly triggers analysis via the Smart Analysis UI. The pipeline orchestrates five AI agents (plus one no-AI aggregation step) in a structured sequence: serial grounding, parallel analysis, and serial synthesis. Results are cached in-memory and served via a dedicated API surface. Exports to Excel and PDF are available post-analysis.

---

## Pipeline Diagram

```
POST /api/smart-analysis/<session_id>
           |
           v
  ┌─────────────────────┐
  │  ContextAggregator  │  (no AI — builds analysis_text, rich_analysis_text)
  └────────┬────────────┘
           |
           v
  ┌─────────────────────┐
  │  DocumentProfile    │  (serial — grounding pass, 1 AI call)
  │      Agent          │  max_tokens=4500, temp=0.15, timeout=90s
  └────────┬────────────┘
           |
     ┌─────┴─────────────────┐
     |           |           |
     v           v           v
  ┌──────┐  ┌────────┐  ┌──────────┐
  │SCOUT │  │MIRROR  │  │UserInput │  (parallel — asyncio.gather)
  │Agent │  │ Agent  │  │  Agent   │
  └──┬───┘  └───┬────┘  └────┬─────┘
     |           |            |
     └─────┬─────┴────────────┘
           |
           v
  ┌─────────────────────┐
  │   SynthesisAgent    │  (serial — final pass, 1 AI call)
  │                     │  max_tokens=8000, temp=0.2, timeout=180s
  └────────┬────────────┘
           |
           v
  ┌─────────────────────┐
  │  SmartAnalysisResult│  → cached in smart_analysis_results[session_id]
  └─────────────────────┘
           |
           v
  GET /api/smart-analysis/<session_id>
```

---

## Agent Reference Table

| Agent | File | AI Calls | max_tokens | Timeout | Temperature | Purpose |
|-------|------|----------|------------|---------|-------------|---------|
| ContextAggregator | `context_aggregator.py` | 0 | — | — | — | Aggregates Q&A + key_details_list + doc_context into structured context dicts; resolves legacy/modern field names |
| DocumentProfileAgent | `document_profile_agent.py` | 1 | 4500 | 90s | 0.15 | Pre-analysis grounding pass; establishes document understanding, expertise profile, and item presence/absence |
| ScoutAgent | `scout_agent.py` | 1 | 5000 | 120s | 0.3 | SCOUT framework analysis; identifies opportunities, uncertainties, gaps, and applied analytical lenses |
| MirrorAgent | `mirror_agent.py` | 1 | 5000 | 120s | 0.3 | MIRROR framework adversarial stress-test; identifies risks, missing elements, interpretation hazards, and failure scenarios |
| UserInputAgent | `user_input_agent.py` | 1 | 2500 | 90s | 0.2 | Answers user-provided questions against document context; skipped entirely if no user input present |
| SynthesisAgent | `synthesis_agent.py` | 1 | 8000 | 180s | 0.2 | Combines all upstream outputs into final executive analysis; enforces mandatory minimum output counts |

---

## Data Flow Between Agents

### Stage 1: ContextAggregator → DocumentProfileAgent

The aggregator produces two text representations:

- **`analysis_text`** — Standard representation. Used by SCOUT, MIRROR, UserInput, and Synthesis. Combines Q&A pairs and key details into a clean structured string.
- **`rich_analysis_text`** — High-fidelity representation. Used exclusively by DocumentProfileAgent. Preserves full answer text, page citations, and structured field values for maximum grounding accuracy.
- **`doc_context`** — Raw document context string (up to 10,000 characters), pre-extracted before the uploaded PDF is discarded. Passed to all agents.

### Stage 2: DocumentProfileAgent → Parallel Agents

DocumentProfileAgent outputs a `doc_profile` dict that all downstream agents consume:

```
doc_profile = {
  "confirmed_present": [...],           # item titles explicitly found
  "confirmed_absent":  [...],           # item titles confirmed missing
  "unverified":        [...],           # item titles with ambiguous evidence
  "expertise_profile": {
    "role":              str,
    "industry_context":  str,
    "key_benchmarks":    str,
    "typical_red_flags": str,
    "normal_expectations": str
  },
  "key_items": {
    "scope":       [...],
    "schedule":    [...],
    "commercial":  [...],
    "compliance":  [...],
    "risk_bearing":[...],
    "submission":  [...]
  },
  "document_understanding": {
    "document_title":         str,           # v3.3: AI-extracted formal document title
    "document_overview":      str,
    "major_workstreams":      [...],
    "key_obligations":        [...],
    "key_constraints":        [...],
    "structural_organization": str
  }
}
```

The `document_understanding` sub-dict is surfaced directly in the final `SmartAnalysisResult` and rendered in the frontend Document Overview section. The `document_title` field is additionally used by `pdf_generator._clean_display_title()` as the primary cover page title for PDF exports.

### Stage 3: Parallel Agents → SynthesisAgent

SynthesisAgent receives a combined findings dict:

```
{
  "analysis_text":       str,           # from ContextAggregator
  "doc_context":         str,           # raw document context
  "doc_profile":         dict,          # full DocumentProfileAgent output
  "scout_findings":      dict,          # full ScoutAgent output
  "mirror_findings":     dict,          # full MirrorAgent output
  "user_responses":      dict | None    # UserInputAgent output, or None if skipped
}
```

### Stage 4: Orchestrator → SmartAnalysisResult

`orchestrator.py` calls `_build_result()` which assembles the final `SmartAnalysisResult` dataclass from SynthesisAgent output plus `document_understanding` extracted from `doc_profile`.

---

## SmartAnalysisResult Schema

```python
@dataclass
class SmartAnalysisResult:
    session_id:             str
    document_name:          str
    document_type:          str
    document_type_label:    str
    analysis_completeness:  float           # 0.0–1.0
    generated_at:           str             # ISO 8601 timestamp
    executive_summary:      str
    key_insights:           List[SmartAnalysisItem]   # minimum 5
    risks:                  List[SmartAnalysisItem]   # minimum 5
    opportunities:          List[SmartAnalysisItem]   # minimum 5
    ambiguities:            List[SmartAnalysisItem]   # minimum 5
    contradictions:         List[SmartAnalysisItem]
    assessments:            List[ProfessionalAssessment]  # minimum 6, unique categories
    follow_up_questions:    List[str]                 # minimum 6
    strategic_recommendations: List[str]             # minimum 5
    user_question_responses:   List[dict]
    evidence_classification:   Dict[str, Any]        # includes minimum_count_notes
    document_understanding:    Dict[str, Any]        # from doc_profile
```

---

## SmartAnalysisItem Schema

```python
@dataclass
class SmartAnalysisItem:
    title:              str
    description:        str
    severity:           str             # e.g. "HIGH", "MEDIUM", "LOW", "INFO"
    evidence:           List[str]
    page_refs:          List[str]
    follow_up_direction: Dict[str, str]
```

### follow_up_direction Schema (v3, 5-field)

Applied to `risks`, `opportunities`, and `ambiguities` items:

```python
{
    "why_unclear":        str,   # why this item requires further investigation
    "verification_step":  str,   # the immediate next action to take
    "what_to_ask":        str,   # the specific question to pose
    "who_to_ask":         str,   # the party to direct the question to
    "where_to_look":      str    # the document section or source to examine
}
```

The frontend also handles the v2 3-field format (`action`, `target`, `specific_question`) for backward compatibility with previously cached analyses.

---

## ProfessionalAssessment Schema

```python
@dataclass
class ProfessionalAssessment:
    category:   str    # uniquely derived per run — never hardcoded
    rating:     str    # e.g. "STRONG", "ACCEPTABLE", "WEAK", "CRITICAL"
    rationale:  str
    confidence: str    # e.g. "HIGH", "MEDIUM", "LOW"
```

---

## Key Design Principles

### LENS GENERATION RULE (ScoutAgent, MirrorAgent)
Lenses must be derived from the specific document's content before being applied — never selected from a static list. The agent must first identify what dimensions of analysis are actually relevant to this document, then apply those lenses. Generic lenses (e.g. "Financial Risk", "Legal Risk") that could apply to any document are prohibited.

### EXPERTISE UNIQUENESS RULE (DocumentProfileAgent)
The expertise profile must contain document-specific benchmarks, red flags, and normal expectations — not generic industry boilerplate. Benchmarks must name actual figures, timeframes, or standards that are specific to the document type, sector, and scope identified.

### 4-Tier Language Discipline (SynthesisAgent)
All analysis claims must be labeled with one of four evidence tiers:
- `CONFIRMED PRESENT` — explicitly stated in document
- `CONFIRMED ABSENT` — explicitly stated as not required/not included
- `NOT SURFACED` — not mentioned; absence is informative but not definitive
- `PRESENT BUT UNRESOLVED` — found but ambiguous, incomplete, or contradictory

### Mandatory Minimum Output Counts (SynthesisAgent)
SynthesisAgent enforces hard minimums to prevent thin analysis:
- key_insights: ≥ 5
- risks: ≥ 5
- opportunities: ≥ 5
- ambiguities: ≥ 5
- assessments: ≥ 6 (with unique category names per run)
- follow_up_questions: ≥ 6
- strategic_recommendations: ≥ 5

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/smart-analysis/<session_id>` | Trigger full Smart Analysis pipeline for a session |
| GET | `/api/smart-analysis/<session_id>` | Retrieve cached SmartAnalysisResult |
| GET | `/api/smart-analysis/<session_id>/export/excel` | Export result as Excel file |
| GET | `/api/smart-analysis/<session_id>/export/pdf` | Export result as PDF file |

---

## Token Budget Summary

| Agent | max_tokens | Position | Notes |
|-------|------------|----------|-------|
| DocumentProfileAgent | 4,500 | Serial (first) | Low temp (0.15) for grounding accuracy |
| ScoutAgent | 5,000 | Parallel | Higher temp (0.3) for analytical breadth |
| MirrorAgent | 5,000 | Parallel | Higher temp (0.3) for adversarial breadth |
| UserInputAgent | 2,500 | Parallel | Skipped entirely if no user questions |
| SynthesisAgent | 8,000 | Serial (last) | Largest budget; combines all inputs |
| **Total** | **~25,000** | | Actual spend varies by document length and user input presence |

---

## Known Constraints and Architectural Notes

### asyncio.new_event_loop() Pattern
The Flask app runs under Gunicorn with 1 worker and 10 threads. Because Gunicorn does not run an asyncio event loop by default, `orchestrator.py` calls `asyncio.new_event_loop()` to create and manage its own loop per request. This is the correct pattern for sync Gunicorn compatibility but means the pipeline is blocking for the duration of one request thread.

### In-Memory Cache
All analysis results are stored in `smart_analysis_results` — a plain Python dict in application memory. Results do not survive a server restart. There is no persistence layer. This also means the in-memory dicts (`active_analyses`, `completed_analyses`, `partial_analyses`, `smart_analysis_results`) are not shared across workers. With 1 Gunicorn worker this is not a problem; scaling to multiple workers would require a shared store (Redis or similar).

### doc_context Pre-Extraction
The raw document context string (up to 10,000 characters) is extracted and stored in session state before the uploaded PDF is cleaned up from the filesystem. This is a deliberate architectural choice: agents receive pre-extracted text rather than re-reading files, and the pipeline does not depend on file persistence.

### Field Name Compatibility
`context_aggregator.py` handles both legacy Q&A field names (`question`, `answer`, `page_citations`) and the modern names (`question_text`, `primary_answer`). The `_resolve_question_fields()` function centralizes this resolution. Both formats produce identical `analysis_text` output — downstream agents are unaware of which format was stored.

### Parallel Agent Skipping
UserInputAgent is unconditionally skipped (not instantiated) when no user questions are present in the session. SCOUT and MIRROR always run. The `asyncio.gather()` call in the orchestrator handles the conditional inclusion of UserInputAgent transparently.

---

## File Locations

```
services/smart_analysis/
├── context_aggregator.py
├── document_profile_agent.py
├── scout_agent.py
├── mirror_agent.py
├── user_input_agent.py
├── synthesis_agent.py
├── orchestrator.py
├── models.py
├── excel_generator.py
└── pdf_generator.py
```

---

## PDF Export Cover Page — Title Resolution

`pdf_generator._clean_display_title(result)` determines the cover page document title:

1. **Primary**: `result.document_understanding.get('document_title')` — AI-extracted formal title from DocumentProfileAgent
2. **Fallback**: cleaned `result.document_name` — strips directory path, `tmp...`/UUID prefixes, percent-encoding, file extension; converts underscores/hyphens to spaces

Both the `SimpleDocTemplate(title=)` PDF metadata and the cover page heading `Paragraph` use this function. The raw `document_name` (which is typically a `.tmp` path) is never shown to end users.

---

## Version History

| Version | Commit | Key Changes |
|---------|--------|-------------|
| v1 | d65a75d | Initial build: 10 service files, 4 API routes, SCOUT/MIRROR/UserInput/Synthesis |
| v2 | e4cf7ca | DocumentProfileAgent added; context_aggregator field name bug fixed; 4-tier language discipline; 3-field follow_up_direction |
| v3 | 887e82a | document_understanding layer; EXPERTISE UNIQUENESS RULE; LENS GENERATION RULE; mandatory minimums (≥5/6); 5-field follow_up_direction; token increases across all agents |
| v3.1 | 41f562c | Admin panel: 🧠 Smart button + SA tab in session modal + admin export (Excel/PDF) |
| v3.2 | d7977ed | Question hub uniform for all users; AI question section hard cap ≤10 Qs; max_tokens 4000→6000 |
| v3.3 | 91eac96 | document_title added to document_understanding; PDF cover page uses _clean_display_title() |

---