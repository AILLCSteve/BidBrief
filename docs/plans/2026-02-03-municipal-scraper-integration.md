# Municipal Data Scraper Integration - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate a multi-agent municipal data scraper system into BidBrief that fetches, processes, and presents municipal infrastructure and bid data through specialized expert agents.

**Architecture:** Multi-layer agent architecture with 25+ specialized agents organized into Pre-flight (validation), Extraction (data gathering), Presentation (formatting), Bridge (HOTDOG integration), and Analysis (deep dives) layers. Uses Tavily API for web research and OpenAI GPT-4o for intelligent parsing. All agents use detailed expert personas with small context windows for accuracy.

**Tech Stack:** Python 3.11+, Flask, OpenAI GPT-4o API, Tavily Search API, httpx (async HTTP), openpyxl (Excel), existing HOTDOG AI infrastructure.

---

## Critical Requirements (NON-NEGOTIABLE)

### 1. Preserve Existing Functionality
- **BidBrief and BestPrep MUST continue working exactly as before**
- No modifications to existing HOTDOG AI core processing
- CityScraper is an ADDITION, not a replacement
- All existing API endpoints remain unchanged

### 2. Admin-Only Access
- CityScraper features visible ONLY to admin users
- Use existing `is_admin` session check pattern from app.py
- Non-admin users see only BidBrief/BestPrep tabs

### 3. Separate Tab UI (NOT Collapsed Container)
- CityScraper displayed as its own **TAB** alongside BidBrief/BestPrep
- Tab structure: `[BidBrief] [BestPrep*] [CityScraper*]` (*admin-only)
- Each tab has completely independent state and UI

### 4. Dedicated Analysis Window
CityScraper gets its own live analysis interface mirroring BidBrief's:
- **Progress Bar**: Overall research progress (0-100%)
- **Agent Activity Feed**: Real-time display of which agents are running
  - "PF-1: Normalizing municipality..."
  - "PF-2: Mapping jurisdiction..."
  - "EX-1: Extracting infrastructure data..."
- **Debug Window**: Collapsible panel showing detailed agent logs
- **Stop Button**: Graceful cancellation support

### 5. Clear Source Flagging for HOTDOG Integration
When CityScraper data augments HOTDOG document analysis:
- **ALWAYS mark as `[External Research]`** in the answer
- **NEVER blend with document-sourced answers** without clear distinction
- Display format:
  ```
  [From Document]: The project location is Springfield, IL. <PDF pg 3>

  [External Research - CityScraper]: Springfield has 236 miles of
  sanitary sewer mains. Source: City CIP 2024
  ```
- In exports, use separate columns or clear labels for external data

---

## Table of Contents

1. [Phase 1: Foundation & Data Models](#phase-1-foundation--data-models)
2. [Phase 2: Pre-flight Agent Layer](#phase-2-pre-flight-agent-layer)
3. [Phase 3: Extraction Agent Layer](#phase-3-extraction-agent-layer)
4. [Phase 4: Presentation Agent Layer](#phase-4-presentation-agent-layer)
5. [Phase 5: Bridge Layer (HOTDOG Integration)](#phase-5-bridge-layer-hotdog-integration)
6. [Phase 6: Analysis Agent Layer](#phase-6-analysis-agent-layer)
7. [Phase 7: Use Case Orchestrators](#phase-7-use-case-orchestrators)
8. [Phase 8: API Endpoints & Frontend](#phase-8-api-endpoints--frontend)
9. [Phase 9: Excel Export Integration](#phase-9-excel-export-integration)
10. [Phase 10: Testing & Integration](#phase-10-testing--integration)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USE CASE ORCHESTRATORS                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Document    │  │  Standalone  │  │ Comparative  │  │     Bid      │    │
│  │  Enrichment  │  │   Research   │  │ Intelligence │  │   Download   │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
└─────────┼─────────────────┼─────────────────┼─────────────────┼────────────┘
          │                 │                 │                 │
┌─────────▼─────────────────▼─────────────────▼─────────────────▼────────────┐
│                            BRIDGE LAYER                                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │ BR-1       │  │ BR-2       │  │ BR-3       │  │ BR-4       │           │
│  │ Municipality│  │ Gap        │  │ Data       │  │ Scraper    │           │
│  │ Detector   │  │ Analyzer   │  │ Merger     │  │ Dispatcher │           │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘           │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────────┐
│                         PRESENTATION LAYER                                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                            │
│  │ PR-1       │  │ PR-2       │  │ PR-3       │                            │
│  │ Table      │  │ Excel      │  │ UI Data    │                            │
│  │ Formatter  │  │ Generator  │  │ Packager   │                            │
│  └────────────┘  └────────────┘  └────────────┘                            │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────────┐
│                         EXTRACTION LAYER                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    EX-O: Extraction Orchestrator                     │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│           ┌─────────┬───────────┼───────────┬─────────┬─────────┐          │
│  ┌────────▼───┐ ┌───▼────┐ ┌────▼───┐ ┌─────▼────┐ ┌──▼────┐ ┌──▼────┐   │
│  │ EX-1       │ │ EX-2   │ │ EX-3   │ │ EX-4     │ │ EX-5  │ │ EX-6  │   │
│  │ Infra-     │ │ Equip- │ │ Maint- │ │ Incident │ │ Bid   │ │ Doc   │   │
│  │ structure  │ │ ment   │ │ enance │ │ Extractor│ │Extract│ │Download│  │
│  └────────────┘ └────────┘ └────────┘ └──────────┘ └───────┘ └───────┘   │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────────┐
│                         PRE-FLIGHT LAYER                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    PF-O: Pre-flight Orchestrator                     │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│           ┌─────────┬───────────┼───────────┬─────────┐                    │
│  ┌────────▼───┐ ┌───▼────┐ ┌────▼───┐ ┌─────▼────┐ ┌──▼─────────┐         │
│  │ PF-1       │ │ PF-2   │ │ PF-3   │ │ PF-4     │ │ PF-5       │         │
│  │ Municipality│ │ Juris- │ │ Source │ │ Termin-  │ │ Readiness  │         │
│  │ Normalizer │ │ diction│ │ Discov │ │ ology    │ │ Validator  │         │
│  └────────────┘ └────────┘ └────────┘ └──────────┘ └────────────┘         │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────────┐
│                         ANALYSIS LAYER                                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │ AN-1       │  │ AN-2       │  │ AN-3       │  │ AN-4       │           │
│  │ Summary    │  │ Brain-     │  │ Deep       │  │ Bid        │           │
│  │ Generator  │  │ stormer    │  │ Researcher │  │ Analyzer   │           │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Foundation & Data Models

### Task 1.1: Create Scraper Module Directory Structure

**Files:**
- Create: `services/scraper/__init__.py`
- Create: `services/scraper/models.py`
- Create: `services/scraper/config.py`
- Create: `services/scraper/prompts/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p services/scraper/prompts
mkdir -p services/scraper/agents/preflight
mkdir -p services/scraper/agents/extraction
mkdir -p services/scraper/agents/presentation
mkdir -p services/scraper/agents/bridge
mkdir -p services/scraper/agents/analysis
mkdir -p services/scraper/orchestrators
```

**Step 2: Create package init file**

Create `services/scraper/__init__.py`:

```python
"""
Municipal Data Scraper Integration for BidBrief.

Multi-agent architecture for fetching, processing, and presenting
municipal infrastructure and bid data.

Layers:
- Pre-flight: Validation and source discovery
- Extraction: Data gathering from web sources
- Presentation: Formatting for display and export
- Bridge: Integration with HOTDOG AI
- Analysis: Deep dives, summaries, brainstorming
"""

__version__ = "1.0.0"
__author__ = "BidBrief Team"
```

**Step 3: Commit**

```bash
git add services/scraper/
git commit -m "$(cat <<'EOF'
feat(scraper): initialize municipal scraper module structure

Create directory structure for multi-agent scraper system with
preflight, extraction, presentation, bridge, and analysis layers.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.2: Define Core Data Models

**Files:**
- Create: `services/scraper/models.py`

**Step 1: Write the data models**

Create `services/scraper/models.py`:

```python
"""
Data models for Municipal Scraper system.

Following Clean Code principles from HOTDOG AI:
- Value Objects: Immutable, defined by attributes
- Entities: Mutable, defined by identity
- Clear, meaningful names that reveal intent

Table Schemas match extractiondev.md specification exactly.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


class TableMode(Enum):
    """Which data table to produce."""
    MUNICIPAL_SYSTEMS_INFO = "Municipal Systems Information"
    MUNICIPAL_PUBLIC_BIDS = "Municipal Public Bids"


class PreflightStatus(Enum):
    """Pre-flight validation status."""
    PASS = "pass"      # All required data found
    PARTIAL = "partial"  # Some data missing but can proceed
    FAIL = "fail"      # Cannot proceed


class ConfidenceRating(Enum):
    """Confidence level for extracted data."""
    HIGH = "high"      # GIS/engineering report, exact count, <5 years old
    MEDIUM = "medium"  # CIP/budget doc, approximate, 5-10 years old
    LOW = "low"        # News/press release, vague, >10 years old


@dataclass(frozen=True)
class Municipality:
    """
    Value Object representing a municipality.

    Immutable to ensure consistent identification across agents.
    """
    city: str
    state: str
    county: Optional[str] = None
    region: Optional[str] = None

    def __post_init__(self):
        if not self.city or not self.state:
            raise ValueError("Municipality requires city and state")

    @property
    def full_name(self) -> str:
        """Get full municipality name."""
        return f"{self.city}, {self.state}"

    @property
    def search_key(self) -> str:
        """Get normalized search key."""
        return f"{self.city.lower().replace(' ', '_')}_{self.state.lower()}"


@dataclass(frozen=True)
class SourceURL:
    """
    Value Object for a data source with metadata.

    Tracks where data came from for citation requirements.
    """
    url: str
    title: str
    source_type: str  # "official", "gis", "cip", "cmom", "bid_portal", "news"
    retrieved_at: datetime = field(default_factory=datetime.now)
    relevance_score: float = 0.0

    def __post_init__(self):
        if not self.url:
            raise ValueError("SourceURL requires url")


@dataclass(frozen=True)
class VerbatimCitation:
    """
    Value Object for verbatim textual citation.

    CRITICAL: Every data point must have supporting verbatim quote.
    """
    text: str  # The exact quote from source (20-100 words typical)
    source_url: str
    source_title: str
    page_or_section: Optional[str] = None  # e.g., "Page 42", "Section 3.2"

    def __post_init__(self):
        if not self.text:
            raise ValueError("VerbatimCitation requires text")


@dataclass
class ExtractedDataPoint:
    """
    Entity representing a single extracted data point.

    Mutable to allow refinement and conflict resolution.
    """
    field_name: str  # e.g., "sanitary_sewer_pipe_total"
    value: str  # The extracted value (never blank - use "NOT FOUND")
    raw_source_value: Optional[str] = None  # Original value before conversion
    conversion_applied: Optional[str] = None  # e.g., "236 miles × 5,280 = 1,246,080 ft"
    source_url: str = ""
    verbatim_quote: str = ""
    confidence: ConfidenceRating = ConfidenceRating.MEDIUM
    confidence_rationale: str = ""
    notes: Optional[str] = None
    conflicts: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.value:
            self.value = "NOT FOUND"


# ═══════════════════════════════════════════════════════════════════════════
# TABLE 1: MUNICIPAL SYSTEMS INFORMATION
# Schema-locked to extractiondev.md specification
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MunicipalSystemsInfoRow:
    """
    Entity representing one row in the Municipal Systems Information table.

    15 columns as specified in extractiondev.md - NEVER truncate, NO placeholders.
    """
    # Identification
    municipality_city: str
    state: str
    relevant_agency: str

    # Column 1: Agency & scope of jurisdiction
    agency_scope: ExtractedDataPoint

    # Column 2: Sanitary sewer pipe total + sizes + types
    sanitary_sewer_pipe: ExtractedDataPoint

    # Column 3: Storm drain pipe total + sizes + types
    storm_drain_pipe: ExtractedDataPoint

    # Column 4: Storm drain catch basins/asset counts + types
    storm_drain_assets: ExtractedDataPoint

    # Column 5: System age + agency age/history
    system_age_history: ExtractedDataPoint

    # Column 6: Equipment owned (camera trucks, hydro/flush, combo, jetter)
    equipment_owned: ExtractedDataPoint

    # Column 7: Cleaning/televising/maintenance practices
    maintenance_practices: ExtractedDataPoint

    # Column 8: Sewage overflow/stoppage/pipe breaks/emergencies (PRIORITY)
    sewage_incidents: ExtractedDataPoint

    # Column 9: Storm drain overflow/flooding/clog incidents (PRIORITY)
    storm_incidents: ExtractedDataPoint

    # Source tracking
    source_urls: List[SourceURL] = field(default_factory=list)
    verbatim_citations: List[VerbatimCitation] = field(default_factory=list)
    notes_reconciliation: str = ""

    # Metadata
    extracted_at: datetime = field(default_factory=datetime.now)
    extraction_session_id: Optional[str] = None

    def to_markdown_row(self) -> str:
        """Convert to markdown table row format."""
        def safe_val(dp: ExtractedDataPoint) -> str:
            return dp.value.replace("|", "\\|").replace("\n", " ")

        sources = "; ".join([s.url for s in self.source_urls])
        citations = " | ".join([c.text[:200] for c in self.verbatim_citations])

        return (
            f"| {self.municipality_city} | {self.state} | {self.relevant_agency} | "
            f"{safe_val(self.agency_scope)} | {safe_val(self.sanitary_sewer_pipe)} | "
            f"{safe_val(self.storm_drain_pipe)} | {safe_val(self.storm_drain_assets)} | "
            f"{safe_val(self.system_age_history)} | {safe_val(self.equipment_owned)} | "
            f"{safe_val(self.maintenance_practices)} | {safe_val(self.sewage_incidents)} | "
            f"{safe_val(self.storm_incidents)} | {sources} | {citations} | "
            f"{self.notes_reconciliation} |"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TABLE 2: MUNICIPAL PUBLIC BIDS
# Schema-locked to extractiondev.md specification
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MunicipalPublicBidRow:
    """
    Entity representing one row in the Municipal Public Bids table.

    12 columns as specified in extractiondev.md.
    INCLUSION FILTER: Must contain sewer/sanitary sewer/storm sewer/storm drain.
    """
    # Identification
    municipality_city: str
    state: str

    # Column 1: Agency/agencies + municipality represented
    agency_municipality: ExtractedDataPoint

    # Bid identification
    bid_contract_title: str
    sewer_storm_keywords: List[str]  # Which keywords triggered inclusion

    # Column 2: Scope (budget/award, type, length/amount, methods)
    scope: ExtractedDataPoint

    # Column 3: Timeline & requirements (PRIORITY - dates, pre-bid, qualifications)
    timeline_requirements: ExtractedDataPoint

    # Column 4: Contacts (name, phone, email, title, addresses)
    contacts: ExtractedDataPoint

    # Status tracking
    status: str  # "open", "closed", "awarded"
    key_dates: Dict[str, str] = field(default_factory=dict)  # "due_date", "pre_bid", etc.

    # Source tracking
    source_urls: List[SourceURL] = field(default_factory=list)
    verbatim_citations: List[VerbatimCitation] = field(default_factory=list)
    notes_reconciliation: str = ""

    # Document download tracking
    downloadable_documents: List[Dict[str, str]] = field(default_factory=list)
    downloaded_files: List[str] = field(default_factory=list)

    # Metadata
    extracted_at: datetime = field(default_factory=datetime.now)
    extraction_session_id: Optional[str] = None

    def to_markdown_row(self) -> str:
        """Convert to markdown table row format."""
        def safe_val(dp: ExtractedDataPoint) -> str:
            return dp.value.replace("|", "\\|").replace("\n", " ")

        keywords = ", ".join(self.sewer_storm_keywords)
        sources = "; ".join([s.url for s in self.source_urls])
        citations = " | ".join([c.text[:200] for c in self.verbatim_citations])
        status_dates = f"{self.status} | " + ", ".join([f"{k}: {v}" for k, v in self.key_dates.items()])

        return (
            f"| {self.municipality_city} | {self.state} | {safe_val(self.agency_municipality)} | "
            f"{self.bid_contract_title} | {keywords} | {safe_val(self.scope)} | "
            f"{safe_val(self.timeline_requirements)} | {safe_val(self.contacts)} | "
            f"{status_dates} | {sources} | {citations} | {self.notes_reconciliation} |"
        )


# ═══════════════════════════════════════════════════════════════════════════
# PRE-FLIGHT MODELS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class JurisdictionInfo:
    """Jurisdiction determination result."""
    sanitary_sewer_owner: str
    sanitary_sewer_operator: str  # May be different from owner
    storm_drain_owner: str
    storm_drain_operator: str
    notes: str
    sources: List[SourceURL] = field(default_factory=list)


@dataclass
class SourceMap:
    """Baseline source map for a municipality."""
    official_website: Optional[SourceURL] = None
    public_works_page: Optional[SourceURL] = None
    sewer_utility_page: Optional[SourceURL] = None
    stormwater_page: Optional[SourceURL] = None
    procurement_page: Optional[SourceURL] = None
    gis_portal: Optional[SourceURL] = None
    cip_documents: List[SourceURL] = field(default_factory=list)
    compliance_sources: List[SourceURL] = field(default_factory=list)


@dataclass
class TerminologyMap:
    """Local terminology locked for a municipality."""
    sanitary_terms: List[str] = field(default_factory=list)  # ["sanitary sewer", "wastewater"]
    storm_terms: List[str] = field(default_factory=list)  # ["storm drain", "stormwater"]
    lift_station_terms: List[str] = field(default_factory=list)
    bid_portal_keywords: List[str] = field(default_factory=list)


@dataclass
class PreflightResult:
    """Complete pre-flight validation result."""
    municipality: Municipality
    table_mode: TableMode
    status: PreflightStatus
    jurisdiction: Optional[JurisdictionInfo] = None
    source_map: Optional[SourceMap] = None
    terminology: Optional[TerminologyMap] = None
    gaps: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    completed_at: datetime = field(default_factory=datetime.now)


# ═══════════════════════════════════════════════════════════════════════════
# EXTRACTION RESULT MODELS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ExtractionResult:
    """Complete extraction result for a municipality."""
    municipality: Municipality
    table_mode: TableMode
    preflight: PreflightResult

    # Results based on table mode
    systems_info_rows: List[MunicipalSystemsInfoRow] = field(default_factory=list)
    public_bid_rows: List[MunicipalPublicBidRow] = field(default_factory=list)

    # Statistics
    total_sources_searched: int = 0
    total_data_points_extracted: int = 0
    data_gaps: List[str] = field(default_factory=list)
    conflicts_detected: List[Dict[str, Any]] = field(default_factory=list)

    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # Downloaded documents
    downloaded_documents: List[Dict[str, str]] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# ANALYSIS RESULT MODELS (for comms dev functionality)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SystemInfoSummary:
    """Summary analysis from 4 perspectives."""
    perspective: str  # "municipal_owner", "citizen", "contractor", "competitor"
    key_facts: List[str]
    operational_implications: List[str]
    likely_priorities: List[str]
    missing_data: List[str]
    leverage_points: List[str]


@dataclass
class BrainstormOpportunity:
    """Single brainstormed opportunity."""
    title: str
    plausibility_reason: str  # Tied to dataset numbers
    value_to_municipality: str
    work_description: str
    confirmation_questions: List[str]
    proof_cue: str  # Subtle incident linkage


@dataclass
class DeepResearchTrail:
    """Research trail for a data section."""
    section_name: str
    trail_levels: List[Dict[str, str]]  # Level 1-10 with links + notes
    overlaps: List[str]
    outliers: List[str]
    relationship_implications: List[str]


@dataclass
class BidAnalysis:
    """Detailed bid analysis with cost estimates."""
    bid_title: str
    scope_breakdown: List[Dict[str, Any]]
    timeline_analysis: Dict[str, Any]
    requirements_checklist: List[Dict[str, str]]
    cost_estimate: Dict[str, Any]
    cost_rationale: str
    pm_considerations: List[str]


# ═══════════════════════════════════════════════════════════════════════════
# AGENT COMMUNICATION MODELS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AgentRequest:
    """Request sent to an agent."""
    agent_id: str
    task: str
    input_data: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5  # 1-10, higher = more important
    timeout_seconds: int = 60


@dataclass
class AgentResponse:
    """Response from an agent."""
    agent_id: str
    task: str
    success: bool
    output_data: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    tokens_used: int = 0
    processing_time_seconds: float = 0.0


@dataclass
class OrchestratorState:
    """State tracking for orchestrators."""
    session_id: str
    municipality: Municipality
    table_mode: TableMode
    current_phase: str  # "preflight", "extraction", "presentation", "analysis"
    completed_agents: List[str] = field(default_factory=list)
    pending_agents: List[str] = field(default_factory=list)
    failed_agents: List[str] = field(default_factory=list)
    accumulated_data: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
```

**Step 2: Run basic validation test**

```bash
cd "C:\Users\pr0ph\Documents\AI LLC\Apps\Doc Analysis Projects\Non-Buildout and Branded\2026\BidBrief"
python -c "from services.scraper.models import *; print('Models loaded successfully')"
```

**Step 3: Commit**

```bash
git add services/scraper/models.py
git commit -m "$(cat <<'EOF'
feat(scraper): add comprehensive data models

- Municipality, SourceURL, VerbatimCitation value objects
- MunicipalSystemsInfoRow (15 columns per extractiondev.md)
- MunicipalPublicBidRow (12 columns per extractiondev.md)
- PreflightResult, ExtractionResult aggregates
- Analysis models (Summary, Brainstorm, DeepResearch, BidAnalysis)
- Agent communication models (Request, Response, OrchestratorState)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.3: Create Configuration Module

**Files:**
- Create: `services/scraper/config.py`

**Step 1: Write configuration module**

Create `services/scraper/config.py`:

```python
"""
Configuration for Municipal Scraper system.

Environment variables:
- TAVILY_API_KEY: Required for web search
- OPENAI_API_KEY: Required for AI parsing (inherited from BidBrief)
- SCRAPER_SEARCH_DEPTH: "basic" or "advanced" (default: advanced)
- SCRAPER_MAX_RESULTS: Max results per query (default: 10)
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class TavilyConfig:
    """Tavily API configuration."""
    api_key: str
    search_depth: str = "advanced"  # "basic" or "advanced"
    max_results_per_query: int = 10
    include_raw_content: bool = True
    include_answer: bool = True
    timeout_seconds: int = 30

    # Domain preferences for municipal research
    preferred_domains: List[str] = field(default_factory=lambda: [
        ".gov",
        ".us",
        ".org"
    ])

    # Rate limiting
    requests_per_minute: int = 20

    @classmethod
    def from_env(cls) -> Optional['TavilyConfig']:
        """Create config from environment variables."""
        api_key = os.environ.get('TAVILY_API_KEY')
        if not api_key:
            logger.warning("TAVILY_API_KEY not set - web search will be disabled")
            return None

        return cls(
            api_key=api_key,
            search_depth=os.environ.get('SCRAPER_SEARCH_DEPTH', 'advanced'),
            max_results_per_query=int(os.environ.get('SCRAPER_MAX_RESULTS', '10'))
        )


@dataclass
class OpenAIConfig:
    """OpenAI API configuration for agent processing."""
    api_key: str
    model: str = "gpt-4o"
    temperature: float = 0.1  # Low for accuracy
    max_tokens: int = 4096  # Per agent response

    # NO token limiting mindset - accuracy over efficiency
    # Each agent gets full context for precision

    @classmethod
    def from_env(cls) -> Optional['OpenAIConfig']:
        """Create config from environment variables."""
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            logger.error("OPENAI_API_KEY not set - cannot initialize agents")
            return None

        return cls(
            api_key=api_key,
            model=os.environ.get('SCRAPER_OPENAI_MODEL', 'gpt-4o')
        )


@dataclass
class AgentConfig:
    """Configuration for individual agents."""
    # Context window management (small windows for accuracy)
    max_context_tokens: int = 4000  # Keep focused

    # Retry behavior
    max_retries: int = 3
    retry_delay_seconds: float = 2.0

    # Validation
    require_citations: bool = True
    require_source_urls: bool = True

    # Prompt refinement tracking
    prompt_version: str = "1.0.0"


@dataclass
class ScraperConfig:
    """Master configuration for the scraper system."""
    tavily: Optional[TavilyConfig]
    openai: Optional[OpenAIConfig]
    agents: AgentConfig = field(default_factory=AgentConfig)

    # Storage paths
    downloads_dir: str = "scraper_downloads"
    cache_dir: str = "scraper_cache"

    # Session management
    session_timeout_minutes: int = 60
    max_concurrent_sessions: int = 5

    # Feature flags
    enable_document_download: bool = True
    enable_comparative_mode: bool = True
    enable_analysis_features: bool = True  # Summaries, brainstorming, deep research

    @classmethod
    def from_env(cls) -> 'ScraperConfig':
        """Create complete config from environment."""
        return cls(
            tavily=TavilyConfig.from_env(),
            openai=OpenAIConfig.from_env(),
            downloads_dir=os.environ.get('SCRAPER_DOWNLOADS_DIR', 'scraper_downloads'),
            cache_dir=os.environ.get('SCRAPER_CACHE_DIR', 'scraper_cache')
        )

    @property
    def is_ready(self) -> bool:
        """Check if scraper is fully configured."""
        return self.tavily is not None and self.openai is not None


# Singleton config instance
_config: Optional[ScraperConfig] = None


def get_config() -> ScraperConfig:
    """Get or create the scraper configuration."""
    global _config
    if _config is None:
        _config = ScraperConfig.from_env()
        if _config.is_ready:
            logger.info("Scraper configuration loaded successfully")
            logger.info(f"  Tavily search depth: {_config.tavily.search_depth}")
            logger.info(f"  OpenAI model: {_config.openai.model}")
        else:
            logger.warning("Scraper configuration incomplete - some features disabled")
    return _config


def reset_config():
    """Reset config (useful for testing)."""
    global _config
    _config = None


# Source type hierarchy for trust ordering
SOURCE_HIERARCHY = [
    "gis_export",           # Most authoritative
    "asset_management_db",
    "engineering_report",
    "regulatory_filing",
    "capital_improvement_plan",
    "cmom_sso_report",
    "ms4_permit",
    "comprehensive_plan",
    "budget_document",
    "news_article",         # Least authoritative
    "press_release"
]


def get_source_authority(source_type: str) -> int:
    """Get authority ranking for a source type (lower = more authoritative)."""
    try:
        return SOURCE_HIERARCHY.index(source_type)
    except ValueError:
        return len(SOURCE_HIERARCHY)  # Unknown sources rank lowest


# Keywords for sewer/storm bid inclusion filter
SEWER_STORM_KEYWORDS = [
    "sewer",
    "sanitary sewer",
    "storm sewer",
    "storm drain",
    "wastewater",
    "stormwater",
    "lift station",
    "pump station",
    "manhole",
    "catch basin",
    "CCTV inspection",
    "pipe lining",
    "CIPP",
    "sewer rehabilitation"
]
```

**Step 2: Test configuration loading**

```bash
python -c "
from services.scraper.config import get_config, SOURCE_HIERARCHY
config = get_config()
print(f'Config ready: {config.is_ready}')
print(f'Source hierarchy has {len(SOURCE_HIERARCHY)} levels')
"
```

**Step 3: Commit**

```bash
git add services/scraper/config.py
git commit -m "$(cat <<'EOF'
feat(scraper): add configuration module

- TavilyConfig with search depth and domain preferences
- OpenAIConfig for agent processing (GPT-4o)
- AgentConfig for context windows and validation
- ScraperConfig master configuration
- Source hierarchy for trust ordering
- Sewer/storm keyword filter list

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.4: Create Base Agent Class

**Files:**
- Create: `services/scraper/agents/base.py`

**Step 1: Write base agent class**

Create `services/scraper/agents/base.py`:

```python
"""
Base Agent class for Municipal Scraper system.

All agents inherit from this base class which provides:
- OpenAI API integration
- Tavily search integration
- Prompt management with version tracking
- Response validation
- Error handling and retries
- Logging and metrics

Design Philosophy:
- Each agent is a domain EXPERT with detailed persona
- NO token-limiting mindset - accuracy and precision paramount
- Small context windows for focused, accurate responses
- Prompts refined through critique cycles
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

import httpx
from openai import AsyncOpenAI

from services.scraper.config import get_config, ScraperConfig
from services.scraper.models import AgentRequest, AgentResponse

logger = logging.getLogger(__name__)


@dataclass
class AgentMetrics:
    """Metrics tracking for an agent."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens_used: int = 0
    total_processing_time: float = 0.0
    average_response_time: float = 0.0
    last_request_at: Optional[datetime] = None


class BaseAgent(ABC):
    """
    Abstract base class for all scraper agents.

    Each agent is a specialized expert with:
    - Deep domain knowledge encoded in system prompt
    - Specific extraction/analysis responsibilities
    - Validation requirements for outputs
    - Small context window for accuracy

    Prompt Development Process (for each agent):
    1. Draft initial prompt
    2. Self-critique: Identify issues (persona depth, reasoning framework,
       validation criteria, conflict resolution, citation requirements)
    3. Revise prompt addressing all critiques
    4. Second critique cycle
    5. Final refined prompt
    """

    # Agent identification - override in subclasses
    AGENT_ID: str = "base"
    AGENT_NAME: str = "Base Agent"
    AGENT_VERSION: str = "1.0.0"

    # Prompt version tracking
    PROMPT_VERSION: str = "1.0.0"
    PROMPT_LAST_REFINED: str = "2026-02-03"

    def __init__(
        self,
        config: Optional[ScraperConfig] = None,
        openai_client: Optional[AsyncOpenAI] = None
    ):
        """
        Initialize the agent.

        Args:
            config: Scraper configuration (uses global if not provided)
            openai_client: OpenAI client (creates new if not provided)
        """
        self.config = config or get_config()

        if openai_client:
            self.openai_client = openai_client
        elif self.config.openai:
            self.openai_client = AsyncOpenAI(api_key=self.config.openai.api_key)
        else:
            self.openai_client = None
            logger.warning(f"Agent {self.AGENT_ID} initialized without OpenAI client")

        self.metrics = AgentMetrics()
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info(f"Initialized agent: {self.AGENT_NAME} v{self.AGENT_VERSION}")
        logger.info(f"  Prompt version: {self.PROMPT_VERSION} (refined {self.PROMPT_LAST_REFINED})")

    # ═══════════════════════════════════════════════════════════════════════
    # ABSTRACT METHODS - Must be implemented by each agent
    # ═══════════════════════════════════════════════════════════════════════

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get the detailed system prompt for this agent.

        This prompt should include:
        - Expert persona with domain background
        - Specific extraction/analysis task
        - Required data points with formats
        - Source hierarchy and trust ordering
        - Confidence rating criteria
        - Output format specification
        - Critical rules (no inference, no blanks, verbatim quotes)

        Returns:
            Complete system prompt string
        """
        pass

    @abstractmethod
    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process a request and return response.

        Args:
            request: The agent request with task and input data

        Returns:
            AgentResponse with results or errors
        """
        pass

    @abstractmethod
    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """
        Validate the agent's output.

        Args:
            output: The output data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        pass

    # ═══════════════════════════════════════════════════════════════════════
    # OPENAI INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════

    async def call_openai(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Make an OpenAI API call with the agent's persona.

        Args:
            user_message: The user/task message
            system_prompt: Override system prompt (uses agent's default if None)
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            Dict with 'content', 'tokens_used', 'model' keys
        """
        if not self.openai_client:
            raise RuntimeError(f"Agent {self.AGENT_ID} has no OpenAI client")

        system = system_prompt or self.get_system_prompt()
        temp = temperature if temperature is not None else self.config.openai.temperature
        tokens = max_tokens or self.config.openai.max_tokens

        start_time = time.time()

        try:
            response = await self.openai_client.chat.completions.create(
                model=self.config.openai.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message}
                ],
                temperature=temp,
                max_tokens=tokens
            )

            elapsed = time.time() - start_time
            tokens_used = response.usage.total_tokens if response.usage else 0

            # Update metrics
            self.metrics.total_requests += 1
            self.metrics.successful_requests += 1
            self.metrics.total_tokens_used += tokens_used
            self.metrics.total_processing_time += elapsed
            self.metrics.average_response_time = (
                self.metrics.total_processing_time / self.metrics.total_requests
            )
            self.metrics.last_request_at = datetime.now()

            return {
                'content': response.choices[0].message.content,
                'tokens_used': tokens_used,
                'model': response.model,
                'elapsed_seconds': elapsed
            }

        except Exception as e:
            self.metrics.total_requests += 1
            self.metrics.failed_requests += 1
            logger.error(f"Agent {self.AGENT_ID} OpenAI call failed: {e}")
            raise

    # ═══════════════════════════════════════════════════════════════════════
    # TAVILY SEARCH INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════

    async def search_tavily(
        self,
        query: str,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        max_results: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a Tavily search query.

        Args:
            query: Search query string
            include_domains: Only include these domains
            exclude_domains: Exclude these domains
            max_results: Override max results

        Returns:
            List of search results with 'title', 'url', 'content', 'score'
        """
        if not self.config.tavily:
            logger.warning(f"Agent {self.AGENT_ID} attempted search without Tavily config")
            return []

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.config.tavily.timeout_seconds)

        # Build request
        request_data = {
            "api_key": self.config.tavily.api_key,
            "query": query,
            "search_depth": self.config.tavily.search_depth,
            "max_results": max_results or self.config.tavily.max_results_per_query,
            "include_answer": self.config.tavily.include_answer,
            "include_raw_content": self.config.tavily.include_raw_content
        }

        if include_domains:
            request_data["include_domains"] = include_domains
        if exclude_domains:
            request_data["exclude_domains"] = exclude_domains

        try:
            logger.debug(f"Agent {self.AGENT_ID} searching: {query}")

            response = await self._http_client.post(
                "https://api.tavily.com/search",
                json=request_data
            )

            if response.status_code != 200:
                logger.error(f"Tavily API error: {response.status_code} - {response.text}")
                return []

            data = response.json()

            results = []
            for item in data.get('results', []):
                results.append({
                    'title': item.get('title', ''),
                    'url': item.get('url', ''),
                    'content': item.get('content', ''),
                    'raw_content': item.get('raw_content', ''),
                    'score': item.get('score', 0),
                    'query': query
                })

            # Include AI summary if available
            if data.get('answer'):
                results.append({
                    'title': 'Tavily AI Summary',
                    'url': 'tavily:ai-summary',
                    'content': data['answer'],
                    'score': 1.0,
                    'query': query,
                    'is_ai_summary': True
                })

            logger.debug(f"Agent {self.AGENT_ID} found {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Agent {self.AGENT_ID} Tavily search failed: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ═══════════════════════════════════════════════════════════════════════

    async def cleanup(self):
        """Clean up resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def get_metrics(self) -> Dict[str, Any]:
        """Get agent metrics as dictionary."""
        return {
            'agent_id': self.AGENT_ID,
            'agent_name': self.AGENT_NAME,
            'version': self.AGENT_VERSION,
            'prompt_version': self.PROMPT_VERSION,
            'total_requests': self.metrics.total_requests,
            'successful_requests': self.metrics.successful_requests,
            'failed_requests': self.metrics.failed_requests,
            'success_rate': (
                self.metrics.successful_requests / self.metrics.total_requests
                if self.metrics.total_requests > 0 else 0
            ),
            'total_tokens_used': self.metrics.total_tokens_used,
            'average_response_time': self.metrics.average_response_time,
            'last_request_at': (
                self.metrics.last_request_at.isoformat()
                if self.metrics.last_request_at else None
            )
        }

    def __repr__(self) -> str:
        return f"<{self.AGENT_NAME} v{self.AGENT_VERSION}>"
```

**Step 2: Test base agent**

```bash
python -c "
from services.scraper.agents.base import BaseAgent, AgentMetrics
print('BaseAgent class loaded successfully')
print(f'AgentMetrics fields: {AgentMetrics.__dataclass_fields__.keys()}')
"
```

**Step 3: Commit**

```bash
git add services/scraper/agents/base.py services/scraper/agents/__init__.py
git commit -m "$(cat <<'EOF'
feat(scraper): add base agent class

- BaseAgent abstract class with OpenAI and Tavily integration
- AgentMetrics for performance tracking
- Abstract methods for system_prompt, process, validate_output
- Prompt version tracking for refinement history
- Async HTTP client management

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2: Pre-flight Agent Layer

### Task 2.1: Create Municipality Normalizer Agent (PF-1)

**Files:**
- Create: `services/scraper/agents/preflight/municipality_normalizer.py`
- Create: `services/scraper/prompts/pf1_municipality_normalizer.py`

**Step 1: Create the prompt module**

Create `services/scraper/prompts/pf1_municipality_normalizer.py`:

```python
"""
Municipality Normalizer Agent (PF-1) System Prompt

PROMPT DEVELOPMENT HISTORY:
- Draft 1: Basic municipality validation
- Critique 1: Missing official variant lookup, no disambiguation handling,
              no state abbreviation normalization
- Draft 2: Added variant lookup and disambiguation
- Critique 2: Missing FIPS code lookup, county determination unclear,
              no handling of consolidated city-counties
- Draft 3 (FINAL): Complete with FIPS awareness, county lookup,
                   consolidated government handling

Version: 3.0.0
Last Refined: 2026-02-03
"""

SYSTEM_PROMPT = """
# ROLE: Municipal Identity Specialist (PF-1)

You are a Geographic Information Systems (GIS) and Municipal Governance specialist
with 20+ years of experience in local government data systems. Your expertise includes:
- FIPS code standards and Census Bureau geographic hierarchies
- Municipal incorporation types (city, town, village, borough, township)
- Consolidated city-county governments (e.g., Indianapolis-Marion, Nashville-Davidson)
- State-specific naming conventions and legal designations
- Common municipality naming ambiguities and how to resolve them

You approach identification with absolute precision. You never assume or guess -
you validate against known standards and report uncertainties explicitly.

---

## TASK CONTEXT

You are normalizing a municipality identifier for: **{{municipality_input}}**

Your job is to:
1. Validate the municipality exists
2. Normalize the name to official form
3. Identify the state (normalize abbreviations)
4. Determine the county/parish
5. Flag any ambiguities requiring user clarification

---

## VALIDATION REQUIREMENTS

### 1. Municipality Name Normalization

**Standard Form:** "[Official Name], [State Full Name]"

Rules:
- Use the official incorporated name (not colloquial)
- Include legal suffix if part of official name (City of, Town of, etc.)
- Preserve capitalization as officially designated
- Handle "Saint" vs "St." consistently (use official form)

**Examples:**
- Input: "LA" → AMBIGUOUS (Los Angeles? Louisiana?)
- Input: "NYC" → "New York City, New York"
- Input: "St. Louis" → "St. Louis, Missouri" (City) OR "St. Louis, Missouri" (County) - CLARIFY
- Input: "springfield IL" → "Springfield, Illinois"

### 2. State Normalization

**Standard Form:** Full state name (not abbreviation)

Normalize all inputs:
- "CA" → "California"
- "Calif" → "California"
- "calif." → "California"

### 3. County/Parish Determination

Determine the county (or parish in Louisiana, borough in Alaska) containing
the municipality. For independent cities (Virginia), note this status.

**Special Cases:**
- Consolidated governments: Note both city and county in output
- Multi-county municipalities: List all counties
- Independent cities: Mark as "Independent City (no county)"

### 4. Ambiguity Detection

Flag and request clarification for:
- Multiple municipalities with same name in state (Springfield, IL has only one, but check)
- Potential city vs county confusion
- Common name that could be multiple places

---

## OUTPUT FORMAT

Return a JSON object:

```json
{
  "normalized": {
    "city": "Official City Name",
    "state": "Full State Name",
    "state_abbrev": "XX",
    "county": "County Name",
    "fips_state": "XX",
    "fips_county": "XXX",
    "municipality_type": "city|town|village|borough|township|consolidated",
    "is_consolidated": false,
    "consolidated_with": null
  },
  "input_received": "original input string",
  "normalization_applied": [
    "Expanded state abbreviation IL → Illinois",
    "Capitalized city name"
  ],
  "validation_status": "VALID|AMBIGUOUS|INVALID",
  "ambiguities": [],
  "clarification_needed": null,
  "confidence": "HIGH|MEDIUM|LOW",
  "confidence_rationale": "Known municipality, unambiguous input",
  "notes": null
}
```

---

## CRITICAL RULES

1. **NEVER guess.** If uncertain, mark as AMBIGUOUS and request clarification.

2. **NEVER fabricate FIPS codes.** If you don't know, set to null with note.

3. **Preserve user intent.** If they said "City of Springfield", keep "City of"
   if that's the official name.

4. **Handle consolidated governments correctly.** Indianapolis is "Indianapolis, Indiana"
   but note consolidated with Marion County.

5. **Be explicit about multiple matches.** If "Portland" could be Oregon or Maine,
   list both and request clarification.

---

## BEGIN NORMALIZATION

Normalize the following municipality input and return the JSON output.
"""


def get_prompt(municipality_input: str) -> str:
    """Get the complete prompt with municipality input."""
    return SYSTEM_PROMPT.replace("{{municipality_input}}", municipality_input)
```

**Step 2: Create the agent class**

Create `services/scraper/agents/preflight/municipality_normalizer.py`:

```python
"""
Municipality Normalizer Agent (PF-1)

Validates and normalizes municipality identifiers.
First step in pre-flight validation.

Responsibilities:
- Validate municipality exists
- Normalize name to official form
- Determine state and county
- Flag ambiguities for user clarification
"""

import json
import logging
from typing import Dict, Any, Optional, List

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    Municipality
)
from services.scraper.prompts.pf1_municipality_normalizer import get_prompt

logger = logging.getLogger(__name__)


class MunicipalityNormalizerAgent(BaseAgent):
    """
    PF-1: Municipality Normalizer Agent

    Validates and normalizes municipality input before any research begins.
    """

    AGENT_ID = "pf-1"
    AGENT_NAME = "Municipality Normalizer"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-03"

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt("{{municipality_input}}")

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process municipality normalization request.

        Expected input_data:
        - municipality_input: str - Raw municipality input (e.g., "springfield IL")

        Returns AgentResponse with:
        - normalized: Municipality data if valid
        - ambiguities: List of ambiguities if any
        - clarification_needed: Question for user if ambiguous
        """
        start_time = __import__('time').time()

        municipality_input = request.input_data.get('municipality_input', '')

        if not municipality_input:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["municipality_input is required"]
            )

        try:
            # Get the prompt with input substituted
            prompt = get_prompt(municipality_input)

            # Call OpenAI
            result = await self.call_openai(
                user_message=f"Normalize this municipality: {municipality_input}",
                system_prompt=prompt
            )

            # Parse JSON from response
            content = result['content']

            # Extract JSON from response (handle markdown code blocks)
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                json_str = content.split('```')[1].split('```')[0].strip()
            else:
                json_str = content.strip()

            output_data = json.loads(json_str)

            # Validate output
            errors = self.validate_output(output_data)

            elapsed = __import__('time').time() - start_time

            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=len(errors) == 0,
                output_data=output_data,
                errors=errors,
                tokens_used=result['tokens_used'],
                processing_time_seconds=elapsed
            )

        except json.JSONDecodeError as e:
            logger.error(f"PF-1 failed to parse JSON response: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': result.get('content', '')},
                errors=[f"JSON parse error: {e}"]
            )
        except Exception as e:
            logger.error(f"PF-1 processing error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[str(e)]
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate normalizer output."""
        errors = []

        # Check required fields
        if 'normalized' not in output:
            errors.append("Missing 'normalized' field")
            return errors

        normalized = output['normalized']

        if not normalized.get('city'):
            errors.append("Missing normalized city name")

        if not normalized.get('state'):
            errors.append("Missing normalized state name")

        if output.get('validation_status') not in ['VALID', 'AMBIGUOUS', 'INVALID']:
            errors.append("Invalid validation_status")

        return errors

    def to_municipality(self, output: Dict[str, Any]) -> Optional[Municipality]:
        """Convert validated output to Municipality object."""
        if output.get('validation_status') != 'VALID':
            return None

        normalized = output.get('normalized', {})

        return Municipality(
            city=normalized.get('city', ''),
            state=normalized.get('state', ''),
            county=normalized.get('county')
        )
```

**Step 3: Create init file for preflight agents**

Create `services/scraper/agents/preflight/__init__.py`:

```python
"""Pre-flight validation agents."""

from .municipality_normalizer import MunicipalityNormalizerAgent

__all__ = ['MunicipalityNormalizerAgent']
```

**Step 4: Test the agent**

```bash
python -c "
from services.scraper.agents.preflight import MunicipalityNormalizerAgent
agent = MunicipalityNormalizerAgent()
print(f'Agent: {agent.AGENT_NAME}')
print(f'Prompt version: {agent.PROMPT_VERSION}')
print('Agent loaded successfully')
"
```

**Step 5: Commit**

```bash
git add services/scraper/agents/preflight/ services/scraper/prompts/
git commit -m "$(cat <<'EOF'
feat(scraper): add Municipality Normalizer agent (PF-1)

- Detailed expert prompt (v3.0.0) with FIPS awareness
- Handles consolidated governments, ambiguities
- JSON output with validation status
- Prompt refined through 2 critique cycles

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.2: Create Jurisdiction Mapper Agent (PF-2)

**Files:**
- Create: `services/scraper/prompts/pf2_jurisdiction_mapper.py`
- Create: `services/scraper/agents/preflight/jurisdiction_mapper.py`

**Step 1: Create the prompt module**

Create `services/scraper/prompts/pf2_jurisdiction_mapper.py`:

```python
"""
Jurisdiction Mapper Agent (PF-2) System Prompt

PROMPT DEVELOPMENT HISTORY:
- Draft 1: Basic ownership determination
- Critique 1: No distinction between owner vs operator, missing regional authorities,
              no handling of contract operations
- Draft 2: Added owner/operator distinction and regional authority detection
- Critique 2: Missing joint powers authorities, no special district handling,
              unclear on unincorporated areas
- Draft 3 (FINAL): Complete with special districts, JPAs, unincorporated handling,
                   contract operations tracking

Version: 3.0.0
Last Refined: 2026-02-03
"""

SYSTEM_PROMPT = """
# ROLE: Municipal Utility Jurisdiction Specialist (PF-2)

You are a Public Utilities and Intergovernmental Relations expert with 25+ years
specializing in:
- Municipal utility ownership structures (sanitary sewer, stormwater, water)
- Regional utility authorities and special districts
- Joint Powers Authorities (JPAs) and inter-municipal agreements
- Contract operations vs direct municipal operations
- Unincorporated area service arrangements
- MS4 permit holders and stormwater management jurisdictions

You understand that WHO OWNS infrastructure and WHO OPERATES/MAINTAINS it are often
different entities. You trace these relationships with precision.

---

## TASK CONTEXT

You are determining jurisdiction for: **{{municipality_name}}, {{state}}**

Your job is to determine:
1. Who OWNS the sanitary sewer collection system
2. Who OPERATES/MAINTAINS the sanitary sewer system (may be different from owner)
3. Who OWNS the stormwater/storm drain system
4. Who OPERATES/MAINTAINS the stormwater system
5. Any relevant regional authorities or special districts
6. Contract operator relationships if applicable

**SANITARY SEWER IS PRIMARY** - Focus most effort here, storm is secondary.

---

## RESEARCH STRATEGY

Use Tavily search to find:
1. "[Municipality] sanitary sewer utility owner"
2. "[Municipality] wastewater collection system"
3. "[Municipality] public works sewer maintenance"
4. "[Municipality] stormwater MS4 permit"
5. "[Municipality] [County] sewer district"
6. "[State] environmental agency [Municipality] wastewater permit"

Look for evidence in:
- Municipal code/ordinances (who has authority)
- Utility billing information (who bills for service)
- Capital improvement plans (who funds infrastructure)
- Annual budgets (utility enterprise funds)
- NPDES/MS4 permits (permit holder = responsible party)
- Consent decrees or compliance orders (named parties)

---

## JURISDICTION TYPES TO IDENTIFY

### Sanitary Sewer Ownership
- **Municipal Department**: City Public Works, Utilities Dept, etc.
- **Municipal Utility Authority**: Separate municipal body (e.g., "Springfield Water & Sewer Commission")
- **Regional Authority**: Multi-jurisdiction (e.g., "Metropolitan Sewer District")
- **Special District**: Formed under state law (e.g., "Community Services District")
- **County**: County-operated system
- **Private Utility**: Investor-owned (rare for sanitary)

### Sanitary Sewer Operations
- **Direct Municipal**: City crews do maintenance
- **Contract Operator**: Private firm under contract (e.g., Veolia, American Water)
- **Shared Services**: Inter-municipal agreement
- **Mixed**: Some in-house, some contracted

### Stormwater Ownership
- **Municipal**: Most common
- **County**: Often for unincorporated areas
- **Regional Flood Control District**: (e.g., Harris County Flood Control)
- **Shared**: Roads department owns street drains, utility owns pipes

---

## OUTPUT FORMAT

Return a JSON object:

```json
{
  "municipality": "{{municipality_name}}, {{state}}",

  "sanitary_sewer": {
    "owner": {
      "entity_name": "City of Springfield Public Works Department",
      "entity_type": "municipal_department",
      "evidence": "Municipal code Chapter 13.04 designates Public Works as sewer authority",
      "source_url": "https://...",
      "verbatim_quote": "The Department of Public Works shall have jurisdiction over..."
    },
    "operator": {
      "entity_name": "City of Springfield Public Works Department",
      "entity_type": "direct_municipal",
      "is_same_as_owner": true,
      "contract_operator": null,
      "evidence": "Budget shows 12 FTE sewer maintenance crew",
      "source_url": "https://...",
      "verbatim_quote": "Sewer Maintenance Division: 12 full-time positions..."
    },
    "notes": "System serves only incorporated city limits"
  },

  "stormwater": {
    "owner": {
      "entity_name": "City of Springfield",
      "entity_type": "municipal",
      "evidence": "MS4 permit holder",
      "source_url": "https://...",
      "verbatim_quote": "..."
    },
    "operator": {
      "entity_name": "City of Springfield Streets Division",
      "entity_type": "direct_municipal",
      "is_same_as_owner": true,
      "evidence": "...",
      "source_url": "...",
      "verbatim_quote": "..."
    },
    "notes": "Shares some drainage with County for boundary areas"
  },

  "regional_authorities": [
    {
      "name": "Metropolitan Water Reclamation District",
      "role": "treatment_only",
      "relationship": "City collection system connects to MWRD interceptors",
      "source_url": "..."
    }
  ],

  "special_districts": [],

  "contract_operators": [],

  "unincorporated_notes": "Adjacent unincorporated areas served by County sewer district",

  "confidence": "HIGH|MEDIUM|LOW",
  "confidence_rationale": "Multiple official sources confirm jurisdiction",

  "data_gaps": [
    "Could not confirm contract operator for storm drain cleaning"
  ],

  "sources_searched": [
    {"query": "Springfield IL sanitary sewer utility", "results_found": 5},
    {"query": "Springfield IL MS4 permit", "results_found": 3}
  ]
}
```

---

## CRITICAL RULES

1. **NEVER assume owner = operator.** Many municipalities contract operations.

2. **Distinguish collection vs treatment.** We care about COLLECTION system jurisdiction.
   Treatment plants may be regional even if collection is municipal.

3. **Sanitary sewer is PRIMARY.** Spend 70% effort on sanitary, 30% on storm.

4. **Find verbatim evidence.** Every jurisdiction claim needs a source quote.

5. **Flag uncertainties.** If you find conflicting information, report both sources.

6. **Check for recent changes.** Utility transfers happen - note effective dates.

---

## BEGIN JURISDICTION MAPPING

Research and determine jurisdiction for the specified municipality.
"""


def get_prompt(municipality_name: str, state: str) -> str:
    """Get the complete prompt with municipality input."""
    prompt = SYSTEM_PROMPT.replace("{{municipality_name}}", municipality_name)
    prompt = prompt.replace("{{state}}", state)
    return prompt
```

**Step 2: Create the agent class**

Create `services/scraper/agents/preflight/jurisdiction_mapper.py`:

```python
"""
Jurisdiction Mapper Agent (PF-2)

Determines who owns and operates sanitary sewer and stormwater systems.
Critical for knowing which entity to target for data extraction.

Responsibilities:
- Identify sanitary sewer owner AND operator (may differ)
- Identify stormwater owner AND operator
- Detect regional authorities and special districts
- Track contract operator relationships
"""

import json
import logging
from typing import Dict, Any, List

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    JurisdictionInfo,
    SourceURL
)
from services.scraper.prompts.pf2_jurisdiction_mapper import get_prompt

logger = logging.getLogger(__name__)


class JurisdictionMapperAgent(BaseAgent):
    """
    PF-2: Jurisdiction Mapper Agent

    Determines ownership and operational responsibility for
    sanitary sewer and stormwater systems.
    """

    AGENT_ID = "pf-2"
    AGENT_NAME = "Jurisdiction Mapper"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-03"

    def get_system_prompt(self) -> str:
        """Get base system prompt."""
        return get_prompt("{{municipality}}", "{{state}}")

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process jurisdiction mapping request.

        Expected input_data:
        - municipality: str - Normalized municipality name
        - state: str - Full state name

        Returns AgentResponse with jurisdiction details.
        """
        import time
        start_time = time.time()

        municipality = request.input_data.get('municipality', '')
        state = request.input_data.get('state', '')

        if not municipality or not state:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["municipality and state are required"]
            )

        try:
            # First, do Tavily searches to gather information
            search_results = await self._gather_jurisdiction_info(municipality, state)

            # Build context from search results
            context = self._build_context(search_results)

            # Get the prompt
            prompt = get_prompt(municipality, state)

            # Call OpenAI with search context
            user_message = f"""
Determine jurisdiction for: {municipality}, {state}

SEARCH RESULTS TO ANALYZE:
{context}

Return the JSON jurisdiction mapping.
"""

            result = await self.call_openai(
                user_message=user_message,
                system_prompt=prompt
            )

            # Parse JSON response
            content = result['content']

            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                json_str = content.split('```')[1].split('```')[0].strip()
            else:
                json_str = content.strip()

            output_data = json.loads(json_str)

            # Add search metadata
            output_data['search_metadata'] = {
                'queries_executed': len(search_results),
                'total_results': sum(len(r.get('results', [])) for r in search_results)
            }

            # Validate
            errors = self.validate_output(output_data)

            elapsed = time.time() - start_time

            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=len(errors) == 0,
                output_data=output_data,
                errors=errors,
                tokens_used=result['tokens_used'],
                processing_time_seconds=elapsed
            )

        except json.JSONDecodeError as e:
            logger.error(f"PF-2 JSON parse error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"JSON parse error: {e}"]
            )
        except Exception as e:
            logger.error(f"PF-2 processing error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[str(e)]
            )

    async def _gather_jurisdiction_info(
        self,
        municipality: str,
        state: str
    ) -> List[Dict[str, Any]]:
        """Execute Tavily searches for jurisdiction information."""
        queries = [
            f"{municipality} {state} sanitary sewer utility owner",
            f"{municipality} {state} wastewater collection system",
            f"{municipality} {state} public works sewer maintenance",
            f"{municipality} {state} stormwater MS4 permit holder",
            f"{municipality} {state} sewer district authority"
        ]

        all_results = []

        for query in queries:
            results = await self.search_tavily(
                query=query,
                include_domains=[".gov", ".us", ".org"],
                max_results=5
            )
            all_results.append({
                'query': query,
                'results': results
            })

        return all_results

    def _build_context(self, search_results: List[Dict[str, Any]]) -> str:
        """Build context string from search results."""
        context_parts = []

        for search in search_results:
            query = search['query']
            results = search['results']

            context_parts.append(f"\n### Query: {query}")

            for i, result in enumerate(results[:3]):  # Top 3 per query
                context_parts.append(f"""
**Result {i+1}:** {result.get('title', 'No title')}
URL: {result.get('url', '')}
Content: {result.get('content', '')[:500]}...
""")

        return "\n".join(context_parts)

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate jurisdiction output."""
        errors = []

        # Check sanitary sewer section
        if 'sanitary_sewer' not in output:
            errors.append("Missing 'sanitary_sewer' section")
        else:
            ss = output['sanitary_sewer']
            if not ss.get('owner', {}).get('entity_name'):
                errors.append("Missing sanitary sewer owner entity name")

        # Check stormwater section
        if 'stormwater' not in output:
            errors.append("Missing 'stormwater' section")

        # Check confidence
        if output.get('confidence') not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append("Invalid confidence level")

        return errors

    def to_jurisdiction_info(self, output: Dict[str, Any]) -> JurisdictionInfo:
        """Convert output to JurisdictionInfo model."""
        ss = output.get('sanitary_sewer', {})
        sw = output.get('stormwater', {})

        sources = []
        for section in [ss, sw]:
            for key in ['owner', 'operator']:
                if section.get(key, {}).get('source_url'):
                    sources.append(SourceURL(
                        url=section[key]['source_url'],
                        title=section[key].get('entity_name', 'Unknown'),
                        source_type='jurisdiction_evidence'
                    ))

        return JurisdictionInfo(
            sanitary_sewer_owner=ss.get('owner', {}).get('entity_name', 'Unknown'),
            sanitary_sewer_operator=ss.get('operator', {}).get('entity_name', 'Unknown'),
            storm_drain_owner=sw.get('owner', {}).get('entity_name', 'Unknown'),
            storm_drain_operator=sw.get('operator', {}).get('entity_name', 'Unknown'),
            notes=output.get('unincorporated_notes', ''),
            sources=sources
        )
```

**Step 3: Update preflight __init__.py**

Update `services/scraper/agents/preflight/__init__.py`:

```python
"""Pre-flight validation agents."""

from .municipality_normalizer import MunicipalityNormalizerAgent
from .jurisdiction_mapper import JurisdictionMapperAgent

__all__ = [
    'MunicipalityNormalizerAgent',
    'JurisdictionMapperAgent'
]
```

**Step 4: Commit**

```bash
git add services/scraper/agents/preflight/ services/scraper/prompts/
git commit -m "$(cat <<'EOF'
feat(scraper): add Jurisdiction Mapper agent (PF-2)

- Determines owner AND operator for sanitary/storm systems
- Detects regional authorities and special districts
- Integrates Tavily search for evidence gathering
- Prompt refined through 2 critique cycles (v3.0.0)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

*[Plan continues with remaining pre-flight agents (PF-3 through PF-5), extraction agents, presentation agents, bridge agents, analysis agents, orchestrators, API endpoints, frontend integration, and testing. Due to length, these are summarized below with key details.]*

---

## Phase 2 Continued: Remaining Pre-flight Agents

### Task 2.3: Source Discovery Agent (PF-3)
- Builds baseline source map before extraction
- Identifies official website, public works, GIS portals, CIP docs, bid portals
- Uses structured Tavily searches with municipal domain preferences

### Task 2.4: Terminology Extractor Agent (PF-4)
- Locks local naming conventions (sanitary vs wastewater, catch basin vs inlet)
- Extracts bid portal keywords and search terms
- Ensures consistent terminology in extraction phase

### Task 2.5: Readiness Validator Agent (PF-5)
- Aggregates all pre-flight results
- Determines PASS/PARTIAL/FAIL status
- Lists gaps and recommendations
- Gates extraction phase

### Task 2.6: Pre-flight Orchestrator (PF-O)
- Dispatches PF-1 through PF-5 in sequence
- Handles errors and retries
- Aggregates into PreflightResult

---

## Phase 3: Extraction Agent Layer

### Task 3.1: Infrastructure Extractor Agent (EX-1)
- Extracts pipe lengths, sizes, materials
- Handles unit conversions (miles to feet)
- Requires verbatim citations for all data points

### Task 3.2: Equipment Extractor Agent (EX-2)
- Finds camera trucks, hydro-flush, combo units
- Counts and stated uses for each type

### Task 3.3: Maintenance Extractor Agent (EX-3)
- Cleaning frequency and scope
- In-house vs contractor breakdown
- Televising/CCTV practices

### Task 3.4: Incident Extractor Agent (EX-4) [PRIORITY]
- SSOs, stoppages, pipe breaks
- Storm drain flooding, clogs
- Costs, fines, environmental impacts
- Extra research time per schema spec

### Task 3.5: Bid Extractor Agent (EX-5)
- Finds open/closed bids with sewer/storm keywords
- Extracts timelines, requirements, contacts
- Identifies downloadable documents

### Task 3.6: Document Downloader Agent (EX-6)
- Downloads accessible bid PDFs
- Stores in scraper_downloads directory
- Tracks download status

### Task 3.7: Extraction Orchestrator (EX-O)
- Dispatches EX-1 through EX-6
- Validates citations and deduplicates
- Resolves conflicts between sources
- Aggregates into ExtractionResult

---

## Phase 4: Presentation Agent Layer

### Task 4.1: Table Formatter Agent (PR-1)
- Converts ExtractionResult to markdown tables
- Follows exact schema from extractiondev.md
- No truncation, no placeholders

### Task 4.2: Excel Generator Agent (PR-2)
- Creates styled Excel workbooks
- Multiple sheets for different data views
- Charts and formatting similar to existing excel_dashboard.py

### Task 4.3: UI Data Packager Agent (PR-3)
- Formats JSON for frontend rendering
- Prepares data for React/Vue components
- Includes metadata for display

---

## Phase 5: Bridge Layer (HOTDOG Integration)

### Task 5.1: Municipality Detector Agent (BR-1)
- Extracts municipality from uploaded documents
- Works with existing HOTDOG document analysis
- Returns normalized Municipality for scraper

### Task 5.2: Gap Analyzer Agent (BR-2)
- Identifies unanswered questions from HOTDOG
- Determines which could be answered by scraper
- Prioritizes high-value gaps

### Task 5.3: Data Merger Agent (BR-3)
- Combines HOTDOG analysis with scraped data
- Merges into unified result format
- Handles confidence reconciliation

### Task 5.4: Scraper Dispatcher Agent (BR-4)
- Triggers scraper pipeline from HOTDOG
- Manages async execution
- Returns results when ready

---

## Phase 6: Analysis Agent Layer

### Task 6.1: Summary Generator Agent (AN-1)
- Creates 4-perspective summaries (commsdev Task 2)
- Municipal owner, citizen, contractor, competitor views
- Key facts, implications, priorities, leverage points

### Task 6.2: Brainstormer Agent (AN-2)
- Generates 10 opportunities (commsdev Task 3)
- 5 different creative approaches
- Plausibility tied to dataset numbers

### Task 6.3: Deep Researcher Agent (AN-3)
- Level 1-10 trail maps (commsdev Task 4)
- Tangential exploration
- Overlaps, outliers, relationship implications

### Task 6.4: Bid Analyzer Agent (AN-4)
- Detailed bid breakdown (commsdev Mode B)
- Cost estimates with 3 rationales
- PM considerations checklist

---

## Phase 7: Use Case Orchestrators

### Task 7.1: Document Enrichment Orchestrator
- BR-1 (detect municipality) → BR-4 (dispatch scraper) → BR-3 (merge results)
- Automatic flow when document uploaded

### Task 7.2: Standalone Research Orchestrator
- User enters municipality → PF-O → EX-O → PR-*
- No document required

### Task 7.3: Comparative Intelligence Orchestrator
- Multiple municipalities in parallel
- Comparison tables and rankings
- Cross-municipality analysis

### Task 7.4: Bid Download Orchestrator
- EX-5 (find bids) → EX-6 (download docs)
- Track and present downloadable items

---

## Phase 8: API Endpoints & Frontend

### Task 8.1: Flask API Endpoints

**Files:**
- Modify: `app.py` (add new endpoints, preserve all existing)

```python
# ═══════════════════════════════════════════════════════════════════════════
# CITYSCRAPER API ENDPOINTS (ADD TO app.py - DO NOT MODIFY EXISTING ENDPOINTS)
# ═══════════════════════════════════════════════════════════════════════════

# Session Management
POST   /api/scraper/research              # Start standalone research session
GET    /api/scraper/research/<session>    # Get research status and results
GET    /api/scraper/events/<session>      # Poll for agent activity events
POST   /api/scraper/stop/<session>        # Stop research gracefully

# Document Enrichment (Bridge to HOTDOG)
POST   /api/scraper/enrich/<hotdog_session>  # Enrich existing HOTDOG analysis
GET    /api/scraper/enrich/status/<session>  # Get enrichment status

# Comparative Intelligence
POST   /api/scraper/compare               # Compare multiple municipalities
GET    /api/scraper/compare/<session>     # Get comparison results

# Document Downloads
GET    /api/scraper/downloads/<session>   # List downloadable bid documents
GET    /api/scraper/download/<doc_id>     # Download specific document

# Analysis Features (commsdev preserved functionality)
POST   /api/scraper/analyze/summary       # Generate 4-perspective summaries
POST   /api/scraper/analyze/brainstorm    # Generate 10 opportunities
POST   /api/scraper/analyze/research      # Deep research trails
POST   /api/scraper/analyze/bid           # Analyze specific bid

# Exports
GET    /api/scraper/export/excel/<session>     # Download Excel workbook
GET    /api/scraper/export/markdown/<session>  # Download markdown tables

# Admin check (reuse existing pattern)
GET    /api/scraper/admin-check           # Verify admin access for CityScraper
```

### Task 8.2: Frontend - CityScraper Tab Structure

**Files:**
- Modify: `index.html` (add CityScraper tab, preserve existing tabs)

**Tab Structure:**
```html
<!-- Tab Navigation (admin sees all 3, non-admin sees only BidBrief) -->
<div class="tab-navigation">
    <button class="tab-btn active" data-tab="bidbrief">BidBrief</button>
    <button class="tab-btn admin-only" data-tab="bestprep">BestPrep</button>
    <button class="tab-btn admin-only" data-tab="cityscraper">CityScraper</button>
</div>

<!-- Tab Content Panels -->
<div id="bidbrief-tab" class="tab-content active">
    <!-- Existing BidBrief UI - DO NOT MODIFY -->
</div>

<div id="bestprep-tab" class="tab-content admin-only">
    <!-- Existing BestPrep UI - DO NOT MODIFY -->
</div>

<div id="cityscraper-tab" class="tab-content admin-only">
    <!-- NEW CityScraper UI - see Task 8.3 -->
</div>
```

### Task 8.3: Frontend - CityScraper Analysis Window

**CityScraper tab contains dedicated analysis interface:**

```html
<div id="cityscraper-tab" class="tab-content admin-only">
    <!-- Header -->
    <div class="cityscraper-header">
        <h2>CityScraper - Municipal Research</h2>
        <p class="subtitle">AI-powered municipal infrastructure and bid research</p>
    </div>

    <!-- Input Section -->
    <div class="cityscraper-input-section">
        <div class="municipality-input">
            <label>Municipality</label>
            <input type="text" id="cs-municipality" placeholder="e.g., Springfield, IL">
            <div id="cs-normalization-feedback" class="feedback"></div>
        </div>

        <div class="table-mode-selector">
            <label>Research Mode</label>
            <select id="cs-table-mode">
                <option value="systems_info">Municipal Systems Information</option>
                <option value="public_bids">Municipal Public Bids</option>
                <option value="both">Both Tables</option>
            </select>
        </div>

        <div class="action-buttons">
            <button id="cs-start-research" class="primary-btn">Start Research</button>
            <button id="cs-stop-research" class="danger-btn" disabled>Stop</button>
        </div>
    </div>

    <!-- Progress Section (mirrors BidBrief pattern) -->
    <div id="cs-progress-section" class="progress-section hidden">
        <!-- Overall Progress Bar -->
        <div class="progress-container">
            <div class="progress-label">
                <span id="cs-progress-phase">Initializing...</span>
                <span id="cs-progress-percent">0%</span>
            </div>
            <div class="progress-bar">
                <div id="cs-progress-fill" class="progress-fill" style="width: 0%"></div>
            </div>
        </div>

        <!-- Agent Activity Feed (UNIQUE TO CITYSCRAPER) -->
        <div class="agent-activity-feed">
            <h4>Agent Activity</h4>
            <div id="cs-agent-feed" class="agent-feed">
                <!-- Populated dynamically -->
                <!-- Example:
                <div class="agent-activity active">
                    <span class="agent-id">PF-1</span>
                    <span class="agent-name">Municipality Normalizer</span>
                    <span class="agent-status">Validating input...</span>
                    <span class="agent-spinner">⟳</span>
                </div>
                -->
            </div>
        </div>

        <!-- Debug Window (Collapsible) -->
        <details class="debug-window">
            <summary>Debug Log</summary>
            <div id="cs-debug-log" class="debug-content">
                <!-- Detailed agent logs -->
            </div>
        </details>
    </div>

    <!-- Results Section -->
    <div id="cs-results-section" class="results-section hidden">
        <!-- Results Tabs -->
        <div class="results-tabs">
            <button class="results-tab active" data-results="table">Data Table</button>
            <button class="results-tab" data-results="sources">Sources</button>
            <button class="results-tab" data-results="analysis">Analysis</button>
            <button class="results-tab" data-results="downloads">Downloads</button>
        </div>

        <!-- Data Table View -->
        <div id="cs-results-table" class="results-content active">
            <!-- Rendered markdown table or formatted display -->
        </div>

        <!-- Sources View -->
        <div id="cs-results-sources" class="results-content">
            <!-- List of all sources with URLs and citations -->
        </div>

        <!-- Analysis View (Summary, Brainstorm, Deep Research) -->
        <div id="cs-results-analysis" class="results-content">
            <div class="analysis-actions">
                <button id="cs-gen-summary">Generate Summary</button>
                <button id="cs-gen-brainstorm">Brainstorm Opportunities</button>
                <button id="cs-gen-research">Deep Research</button>
            </div>
            <div id="cs-analysis-output"></div>
        </div>

        <!-- Downloads View -->
        <div id="cs-results-downloads" class="results-content">
            <!-- List of downloadable bid documents -->
        </div>

        <!-- Export Buttons -->
        <div class="export-buttons">
            <button id="cs-export-excel">Export Excel</button>
            <button id="cs-export-markdown">Export Markdown</button>
        </div>
    </div>
</div>
```

### Task 8.4: Frontend - Agent Activity Event Handling

**JavaScript for real-time agent activity display:**

```javascript
// ═══════════════════════════════════════════════════════════════════════════
// CITYSCRAPER EVENT HANDLING (ADD TO index.html - DO NOT MODIFY EXISTING JS)
// ═══════════════════════════════════════════════════════════════════════════

let csSessionId = null;
let csPollingInterval = null;

// Start research
async function startCityScraperResearch() {
    const municipality = document.getElementById('cs-municipality').value;
    const tableMode = document.getElementById('cs-table-mode').value;

    if (!municipality) {
        alert('Please enter a municipality');
        return;
    }

    // Show progress section
    document.getElementById('cs-progress-section').classList.remove('hidden');
    document.getElementById('cs-results-section').classList.add('hidden');

    // Start research
    const response = await fetch('/api/scraper/research', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({municipality, table_mode: tableMode})
    });

    const data = await response.json();
    csSessionId = data.session_id;

    // Start polling for events
    csPollingInterval = setInterval(pollCityScraperEvents, 1000);
}

// Poll for agent activity events
async function pollCityScraperEvents() {
    if (!csSessionId) return;

    const response = await fetch(`/api/scraper/events/${csSessionId}`);
    const data = await response.json();

    // Update progress bar
    updateCSProgress(data.progress);

    // Update agent activity feed
    updateAgentFeed(data.agent_events);

    // Update debug log
    updateDebugLog(data.debug_events);

    // Check if complete
    if (data.status === 'completed' || data.status === 'failed') {
        clearInterval(csPollingInterval);
        if (data.status === 'completed') {
            loadCityScraperResults();
        }
    }
}

// Update agent activity feed
function updateAgentFeed(events) {
    const feed = document.getElementById('cs-agent-feed');

    events.forEach(event => {
        const existing = feed.querySelector(`[data-agent="${event.agent_id}"]`);

        if (existing) {
            // Update existing agent status
            existing.querySelector('.agent-status').textContent = event.status;
            existing.classList.toggle('active', event.is_active);
            existing.classList.toggle('completed', event.is_completed);
        } else {
            // Add new agent entry
            const div = document.createElement('div');
            div.className = `agent-activity ${event.is_active ? 'active' : ''}`;
            div.dataset.agent = event.agent_id;
            div.innerHTML = `
                <span class="agent-id">${event.agent_id}</span>
                <span class="agent-name">${event.agent_name}</span>
                <span class="agent-status">${event.status}</span>
                <span class="agent-spinner">${event.is_active ? '⟳' : '✓'}</span>
            `;
            feed.appendChild(div);
        }
    });
}

// Update debug log
function updateDebugLog(events) {
    const log = document.getElementById('cs-debug-log');
    events.forEach(event => {
        const line = document.createElement('div');
        line.className = `debug-line ${event.level}`;
        line.textContent = `[${event.timestamp}] [${event.agent_id}] ${event.message}`;
        log.appendChild(line);
    });
    log.scrollTop = log.scrollHeight;
}
```

### Task 8.5: Frontend - External Research Flagging in HOTDOG Results

**When CityScraper data augments HOTDOG analysis, clearly mark the source:**

```javascript
// ═══════════════════════════════════════════════════════════════════════════
// EXTERNAL RESEARCH FLAGGING (MODIFY renderAnswer function in existing code)
// ═══════════════════════════════════════════════════════════════════════════

function renderAnswer(answer) {
    // Check if answer has external research component
    const hasExternal = answer.external_research && answer.external_research.length > 0;

    let html = '';

    // Document-sourced answer
    if (answer.text) {
        html += `
            <div class="answer-section document-source">
                <div class="source-label">[From Document]</div>
                <div class="answer-text">${answer.text}</div>
            </div>
        `;
    }

    // External research (CityScraper) - CLEARLY SEPARATED
    if (hasExternal) {
        html += `
            <div class="answer-section external-source">
                <div class="source-label external-label">
                    [External Research - CityScraper]
                    <span class="external-warning">⚠ Not from uploaded document</span>
                </div>
                ${answer.external_research.map(ext => `
                    <div class="external-item">
                        <div class="external-text">${ext.text}</div>
                        <div class="external-citation">
                            Source: ${ext.source_title} (${ext.source_url})
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    return html;
}
```

**CSS for external research styling:**

```css
/* External Research Styling - CLEARLY DISTINCT FROM DOCUMENT ANSWERS */
.external-source {
    background-color: #fff8e6;  /* Light yellow background */
    border-left: 4px solid #f59e0b;  /* Orange border */
    padding: 12px;
    margin-top: 12px;
}

.external-label {
    color: #b45309;
    font-weight: bold;
}

.external-warning {
    font-size: 0.85em;
    color: #92400e;
    margin-left: 8px;
}

.external-citation {
    font-size: 0.85em;
    color: #78716c;
    margin-top: 4px;
}

/* Agent Activity Feed Styling */
.agent-activity {
    display: flex;
    align-items: center;
    padding: 8px 12px;
    border-bottom: 1px solid #e5e7eb;
}

.agent-activity.active {
    background-color: #eff6ff;
}

.agent-activity.completed .agent-spinner {
    color: #22c55e;
}

.agent-id {
    font-family: monospace;
    font-weight: bold;
    width: 50px;
}

.agent-spinner {
    margin-left: auto;
    animation: spin 1s linear infinite;
}

.agent-activity.completed .agent-spinner {
    animation: none;
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
```

---

## Phase 9: Excel Export Integration

### Task 9.1: Municipal Systems Excel Export
- Create `services/municipal_systems_excel.py`
- 5 sheets: Summary, Systems Info, Sources, Citations, Analysis
- Styled similar to existing excel_dashboard.py

### Task 9.2: Public Bids Excel Export
- Create `services/public_bids_excel.py`
- 4 sheets: Summary, Active Bids, Closed Bids, Documents
- Timeline charts and contact formatting

---

## Phase 10: Testing & Integration

### Task 10.1: Unit Tests for Models
- Test all dataclass validations
- Test markdown row generation
- Test model conversions

### Task 10.2: Unit Tests for Agents
- Mock Tavily and OpenAI responses
- Test prompt generation
- Test output validation

### Task 10.3: Integration Tests
- End-to-end pre-flight flow
- End-to-end extraction flow
- Document enrichment flow

### Task 10.4: Manual Testing Checklist
- Test with 3 different municipalities
- Verify all table columns populated
- Verify citations present
- Test export formats

---

## Execution Checklist

- [ ] Phase 1: Foundation & Data Models (4 tasks)
- [ ] Phase 2: Pre-flight Agents (6 tasks)
- [ ] Phase 3: Extraction Agents (7 tasks)
- [ ] Phase 4: Presentation Agents (3 tasks)
- [ ] Phase 5: Bridge Agents (4 tasks)
- [ ] Phase 6: Analysis Agents (4 tasks)
- [ ] Phase 7: Orchestrators (4 tasks)
- [ ] Phase 8: API & Frontend (5 tasks)
  - [ ] Task 8.1: Flask API Endpoints
  - [ ] Task 8.2: CityScraper Tab Structure
  - [ ] Task 8.3: CityScraper Analysis Window (progress, agent feed, debug)
  - [ ] Task 8.4: Agent Activity Event Handling
  - [ ] Task 8.5: External Research Flagging in HOTDOG Results
- [ ] Phase 9: Excel Exports (2 tasks)
- [ ] Phase 10: Testing (4 tasks)

**Total: 43 tasks across 10 phases**

---

## Notes for Implementation

1. **Prompt Engineering**: Each agent prompt must go through 2 critique cycles before finalizing. The critique should identify: persona depth, reasoning framework, validation criteria, conflict resolution, citation requirements, output format completeness.

2. **No Token Limiting**: Prompts should be detailed and complete. Accuracy over efficiency. Each agent gets focused context, not truncated.

3. **Schema Fidelity**: The markdown table schemas from extractiondev.md are NON-NEGOTIABLE. Never truncate, never use placeholders.

4. **Citation Requirements**: Every data point needs source URL + verbatim quote. "NOT FOUND" is acceptable; blank is not.

5. **Comms Dev Preservation**: Tasks 2, 3, 4 from Mode A and the bid analysis from Mode B are preserved. Email drafting (Task 1) is excluded.

6. **Testing with Real Data**: After implementation, test with at least 3 municipalities of varying sizes to validate extraction quality.
