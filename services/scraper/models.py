"""
Data models for Municipal Scraper system (CityScraper).

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


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class TableMode(Enum):
    """Which data table to produce."""
    MUNICIPAL_SYSTEMS_INFO = "Municipal Systems Information"
    MUNICIPAL_PUBLIC_BIDS = "Municipal Public Bids"


class PreflightStatus(Enum):
    """Pre-flight validation status."""
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class ConfidenceRating(Enum):
    """Confidence level for extracted data."""
    HIGH = "high"      # GIS/engineering report, exact count, <5 years old
    MEDIUM = "medium"  # CIP/budget doc, approximate, 5-10 years old
    LOW = "low"        # News/press release, vague, >10 years old


# ═══════════════════════════════════════════════════════════════════════════
# VALUE OBJECTS (Immutable)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Municipality:
    """Value Object representing a municipality."""
    city: str
    state: str
    county: Optional[str] = None
    region: Optional[str] = None

    def __post_init__(self):
        if not self.city or not self.state:
            raise ValueError("Municipality requires city and state")

    @property
    def full_name(self) -> str:
        return f"{self.city}, {self.state}"

    @property
    def search_key(self) -> str:
        return f"{self.city.lower().replace(' ', '_')}_{self.state.lower()}"


@dataclass(frozen=True)
class SourceURL:
    """Value Object for a data source with metadata."""
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
    """Value Object for verbatim textual citation."""
    text: str
    source_url: str
    source_title: str
    page_or_section: Optional[str] = None

    def __post_init__(self):
        if not self.text:
            raise ValueError("VerbatimCitation requires text")


# ═══════════════════════════════════════════════════════════════════════════
# ENTITIES (Mutable)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ExtractedDataPoint:
    """Entity for a single extracted data point."""
    field_name: str
    value: str  # Never blank - use "NOT FOUND"
    raw_source_value: Optional[str] = None
    conversion_applied: Optional[str] = None
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
# TABLE 1: MUNICIPAL SYSTEMS INFORMATION (15 columns per extractiondev.md)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MunicipalSystemsInfoRow:
    """One row in Municipal Systems Information table - 15 columns."""
    # Identification
    municipality_city: str
    state: str
    relevant_agency: str

    # Data columns (1-9)
    agency_scope: ExtractedDataPoint
    sanitary_sewer_pipe: ExtractedDataPoint
    storm_drain_pipe: ExtractedDataPoint
    storm_drain_assets: ExtractedDataPoint
    system_age_history: ExtractedDataPoint
    equipment_owned: ExtractedDataPoint
    maintenance_practices: ExtractedDataPoint
    sewage_incidents: ExtractedDataPoint  # PRIORITY
    storm_incidents: ExtractedDataPoint   # PRIORITY

    # Source tracking
    source_urls: List[SourceURL] = field(default_factory=list)
    verbatim_citations: List[VerbatimCitation] = field(default_factory=list)
    notes_reconciliation: str = ""

    # Metadata
    extracted_at: datetime = field(default_factory=datetime.now)
    extraction_session_id: Optional[str] = None

    def to_markdown_row(self) -> str:
        """Convert to markdown table row."""
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
# TABLE 2: MUNICIPAL PUBLIC BIDS (12 columns per extractiondev.md)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MunicipalPublicBidRow:
    """One row in Municipal Public Bids table - 12 columns."""
    municipality_city: str
    state: str
    agency_municipality: ExtractedDataPoint
    bid_contract_title: str
    sewer_storm_keywords: List[str]
    scope: ExtractedDataPoint
    timeline_requirements: ExtractedDataPoint  # PRIORITY
    contacts: ExtractedDataPoint
    status: str  # "open", "closed", "awarded"
    key_dates: Dict[str, str] = field(default_factory=dict)
    source_urls: List[SourceURL] = field(default_factory=list)
    verbatim_citations: List[VerbatimCitation] = field(default_factory=list)
    notes_reconciliation: str = ""
    downloadable_documents: List[Dict[str, str]] = field(default_factory=list)
    downloaded_files: List[str] = field(default_factory=list)
    extracted_at: datetime = field(default_factory=datetime.now)
    extraction_session_id: Optional[str] = None

    def to_markdown_row(self) -> str:
        """Convert to markdown table row."""
        def safe_val(dp: ExtractedDataPoint) -> str:
            return dp.value.replace("|", "\\|").replace("\n", " ")

        def safe_str(s: str) -> str:
            return s.replace("|", "\\|").replace("\n", " ")

        # Format keywords as comma-separated list
        keywords_str = ", ".join(self.sewer_storm_keywords) if self.sewer_storm_keywords else "N/A"

        # Format key dates as semi-colon separated
        dates_parts = []
        for date_type, date_val in self.key_dates.items():
            dates_parts.append(f"{date_type}: {date_val}")
        key_dates_str = "; ".join(dates_parts) if dates_parts else "N/A"

        # Format sources
        sources = "; ".join([s.url for s in self.source_urls])

        # Format citations (truncate each to 200 chars)
        citations = " | ".join([c.text[:200] for c in self.verbatim_citations])

        return (
            f"| {safe_str(self.municipality_city)} | {safe_str(self.state)} | "
            f"{safe_val(self.agency_municipality)} | {safe_str(self.bid_contract_title)} | "
            f"{safe_str(keywords_str)} | {safe_val(self.scope)} | "
            f"{safe_val(self.timeline_requirements)} | {safe_val(self.contacts)} | "
            f"{safe_str(self.status)} | {safe_str(key_dates_str)} | "
            f"{sources} | {citations} | {safe_str(self.notes_reconciliation)} |"
        )


# ═══════════════════════════════════════════════════════════════════════════
# PRE-FLIGHT MODELS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class JurisdictionInfo:
    """Jurisdiction determination result."""
    sanitary_sewer_owner: str
    sanitary_sewer_operator: str
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
    """Local terminology for a municipality."""
    sanitary_terms: List[str] = field(default_factory=list)
    storm_terms: List[str] = field(default_factory=list)
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
    systems_info_rows: List[MunicipalSystemsInfoRow] = field(default_factory=list)
    public_bid_rows: List[MunicipalPublicBidRow] = field(default_factory=list)
    total_sources_searched: int = 0
    total_data_points_extracted: int = 0
    data_gaps: List[str] = field(default_factory=list)
    conflicts_detected: List[Dict[str, Any]] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    downloaded_documents: List[Dict[str, str]] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# ANALYSIS MODELS (comms dev functionality - NOT email drafting)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SystemInfoSummary:
    """Summary from 4 perspectives (commsdev Task 2)."""
    perspective: str  # "municipal_owner", "citizen", "contractor", "competitor"
    key_facts: List[str]
    operational_implications: List[str]
    likely_priorities: List[str]
    missing_data: List[str]
    leverage_points: List[str]


@dataclass
class BrainstormOpportunity:
    """Single brainstormed opportunity (commsdev Task 3)."""
    title: str
    plausibility_reason: str
    value_to_municipality: str
    work_description: str
    confirmation_questions: List[str]
    proof_cue: str


@dataclass
class DeepResearchTrail:
    """Research trail for a data section (commsdev Task 4)."""
    section_name: str
    trail_levels: List[Dict[str, str]]
    overlaps: List[str]
    outliers: List[str]
    relationship_implications: List[str]


@dataclass
class BidAnalysis:
    """Detailed bid analysis (commsdev Mode B)."""
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
    priority: int = 5
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
    current_phase: str
    completed_agents: List[str] = field(default_factory=list)
    pending_agents: List[str] = field(default_factory=list)
    failed_agents: List[str] = field(default_factory=list)
    accumulated_data: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)


# ═══════════════════════════════════════════════════════════════════════════
# UI EVENT MODELS (for CityScraper tab agent activity feed)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AgentActivityEvent:
    """Event for agent activity feed in UI."""
    agent_id: str
    agent_name: str
    status: str  # "starting", "processing", "completed", "failed"
    message: str
    is_active: bool = True
    is_completed: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ScraperSessionProgress:
    """Progress tracking for CityScraper session."""
    session_id: str
    phase: str  # "preflight", "extraction", "presentation", "analysis"
    progress_percent: int
    current_agent: Optional[str] = None
    agent_events: List[AgentActivityEvent] = field(default_factory=list)
    debug_events: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "running"  # "running", "completed", "failed", "stopped"
