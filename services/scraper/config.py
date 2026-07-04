"""
Configuration for Municipal Scraper (CityScraper) system.

Environment variables:
- TAVILY_API_KEY: Required for web search
- OPENAI_API_KEY: Required for AI parsing
- SCRAPER_SEARCH_DEPTH: "basic" or "advanced" (default: advanced)
- SCRAPER_MAX_RESULTS: Max results per query (default: 10)
- SCRAPER_OPENAI_MODEL: Model to use (default: gpt-4o)
- SCRAPER_DOWNLOADS_DIR: Where to store downloaded docs
- SCRAPER_CACHE_DIR: Where to cache research data
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
    search_depth: str = "advanced"
    max_results_per_query: int = 20  # Increased from 10 for more comprehensive results
    include_raw_content: bool = True
    include_answer: bool = True
    timeout_seconds: int = 60  # Increased from 30 for larger result sets
    preferred_domains: List[str] = field(default_factory=list)  # No domain restriction — municipal data lives everywhere
    requests_per_minute: int = 30  # Increased from 20
    max_retries_per_query: int = 3
    initial_backoff_seconds: float = 2.0
    max_backoff_seconds: float = 30.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown: float = 60.0

    @classmethod
    def from_env(cls) -> Optional['TavilyConfig']:
        api_key = os.environ.get('TAVILY_API_KEY')
        if not api_key:
            logger.warning("TAVILY_API_KEY not set - web search disabled")
            return None
        return cls(
            api_key=api_key,
            search_depth=os.environ.get('SCRAPER_SEARCH_DEPTH', 'advanced'),
            max_results_per_query=int(os.environ.get('SCRAPER_MAX_RESULTS', '10'))
        )


@dataclass
class OpenAIConfig:
    """OpenAI API configuration. Model defaults to the central standard tier."""
    api_key: str
    model: str = ""  # resolved in __post_init__ so env changes apply per-instantiation
    temperature: float = 0.1  # Low for accuracy (legacy models only; reasoning models ignore it)
    max_tokens: int = 16384  # Desired visible output; adapter adds reasoning headroom

    def __post_init__(self):
        if not self.model:
            from services.ai_models import standard_model
            self.model = standard_model()

    @classmethod
    def from_env(cls) -> Optional['OpenAIConfig']:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            logger.error("OPENAI_API_KEY not set - agents disabled")
            return None
        return cls(
            api_key=api_key,
            model=os.environ.get('SCRAPER_OPENAI_MODEL', '')
        )


@dataclass
class AgentConfig:
    """Configuration for individual agents."""
    max_context_tokens: int = 32000  # Increased from 4000 for gpt-4o's full context
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    require_citations: bool = True
    require_source_urls: bool = True
    prompt_version: str = "1.0.0"


# Research focus menu. Default is a general full-system sweep; the others narrow
# the lens. The directive is appended to every agent's system prompt so the whole
# pipeline (preflight, extraction, presentation) leans into the chosen focus.
RESEARCH_FOCUS_PRESETS = {
    'full_system': {
        'label': 'Full System (default)',
        'directive': (
            'RESEARCH FOCUS — FULL SYSTEM: perform general full-system research across the '
            'entire municipal organization: all utilities (water, sanitary sewer, storm, reclaimed), '
            'public works, streets/ROW, facilities, org and governance structure, budgets/CIP, and '
            'procurement practices. Do NOT privilege sewer/wastewater unless the data itself is '
            'sewer-dominant; report what the municipality actually operates.'
        ),
    },
    'sewer_wastewater': {
        'label': 'Sewer / Wastewater',
        'directive': (
            'RESEARCH FOCUS — SEWER/WASTEWATER: sanitary sewer and wastewater systems are the '
            'primary focus (collection, gravity mains, force mains, lift/pump stations, treatment, '
            'CMOM/SSO history, I&I). Include other systems only where they materially affect '
            'sewer operations.'
        ),
    },
    'stormwater': {
        'label': 'Stormwater',
        'directive': (
            'RESEARCH FOCUS — STORMWATER: storm drainage systems are the primary focus (storm '
            'mains, culverts, detention/retention, outfalls, MS4 permit status, flooding history, '
            'drainage utility fees). Include sanitary only where combined or materially related.'
        ),
    },
    'water_distribution': {
        'label': 'Water Distribution',
        'directive': (
            'RESEARCH FOCUS — WATER DISTRIBUTION: potable water systems are the primary focus '
            '(source/supply, treatment, storage, distribution mains, pump stations, pressure zones, '
            'lead service line inventories, CCR data). Include other utilities only where shared '
            'infrastructure or governance applies.'
        ),
    },
    'streets_row': {
        'label': 'Streets / Public Works',
        'directive': (
            'RESEARCH FOCUS — STREETS & PUBLIC WORKS: streets, right-of-way, paving programs, '
            'sidewalks, bridges, fleet, and general public-works operations are the primary focus. '
            'Utilities matter mainly where they drive street cuts, moratoriums, or joint projects.'
        ),
    },
}

DEFAULT_RESEARCH_FOCUS = 'full_system'


def focus_directive(focus: str) -> str:
    """Directive text for a focus id (falls back to full_system)."""
    preset = RESEARCH_FOCUS_PRESETS.get(focus) or RESEARCH_FOCUS_PRESETS[DEFAULT_RESEARCH_FOCUS]
    return preset['directive']


@dataclass
class ScraperConfig:
    """Master configuration for CityScraper."""
    tavily: Optional[TavilyConfig]
    openai: Optional[OpenAIConfig]
    agents: AgentConfig = field(default_factory=AgentConfig)
    research_focus: str = DEFAULT_RESEARCH_FOCUS  # key into RESEARCH_FOCUS_PRESETS
    downloads_dir: str = "scraper_downloads"
    cache_dir: str = "scraper_cache"
    session_timeout_minutes: int = 60
    max_concurrent_sessions: int = 5
    enable_document_download: bool = True
    enable_comparative_mode: bool = True
    enable_analysis_features: bool = True

    @classmethod
    def from_env(cls) -> 'ScraperConfig':
        return cls(
            tavily=TavilyConfig.from_env(),
            openai=OpenAIConfig.from_env(),
            downloads_dir=os.environ.get('SCRAPER_DOWNLOADS_DIR', 'scraper_downloads'),
            cache_dir=os.environ.get('SCRAPER_CACHE_DIR', 'scraper_cache')
        )

    @property
    def is_ready(self) -> bool:
        return self.tavily is not None and self.openai is not None


# Singleton
_config: Optional[ScraperConfig] = None


def get_config() -> ScraperConfig:
    """Get the singleton configuration instance."""
    global _config
    if _config is None:
        _config = ScraperConfig.from_env()
        if _config.is_ready:
            logger.info("CityScraper config loaded successfully")
        else:
            logger.warning("CityScraper config incomplete")
    return _config


def reset_config():
    """Reset configuration singleton (for testing)."""
    global _config
    _config = None


def get_config_for_tier(high_power: bool = False, research_focus: str = None) -> ScraperConfig:
    """
    Config resolved for a model tier + research focus. Always returns a copy when
    anything differs from the singleton so concurrent sessions never share mutations.
    """
    from dataclasses import replace
    base = get_config()
    focus = research_focus if research_focus in RESEARCH_FOCUS_PRESETS else DEFAULT_RESEARCH_FOCUS
    needs_model_swap = high_power and base.openai is not None
    if not needs_model_swap and focus == base.research_focus:
        return base
    openai_cfg = base.openai
    if needs_model_swap:
        from services.ai_models import high_power_model
        openai_cfg = replace(base.openai, model=high_power_model())
    return replace(base, openai=openai_cfg, research_focus=focus)


# Source hierarchy (lower index = more authoritative)
SOURCE_HIERARCHY = [
    "gis_export",
    "asset_management_db",
    "engineering_report",
    "regulatory_filing",
    "capital_improvement_plan",
    "cmom_sso_report",
    "ms4_permit",
    "comprehensive_plan",
    "budget_document",
    "news_article",
    "press_release"
]


def get_source_authority(source_type: str) -> int:
    """
    Get the authority ranking for a source type.

    Lower values indicate higher authority (more trustworthy).
    Unknown source types return the lowest authority (highest value).

    Args:
        source_type: The type of source to rank

    Returns:
        Integer ranking (0 = most authoritative)
    """
    try:
        return SOURCE_HIERARCHY.index(source_type)
    except ValueError:
        return len(SOURCE_HIERARCHY)


# Keywords for sewer/storm bid inclusion filter
SEWER_STORM_KEYWORDS = [
    "sewer", "sanitary sewer", "storm sewer", "storm drain",
    "wastewater", "stormwater", "lift station", "pump station",
    "manhole", "catch basin", "CCTV inspection", "pipe lining",
    "CIPP", "sewer rehabilitation", "sewer cleaning", "jetting",
    "hydro cleaning", "root foaming", "smoke testing"
]
