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
    max_results_per_query: int = 10
    include_raw_content: bool = True
    include_answer: bool = True
    timeout_seconds: int = 30
    preferred_domains: List[str] = field(default_factory=lambda: [".gov", ".us", ".org"])
    requests_per_minute: int = 20

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
    """OpenAI API configuration."""
    api_key: str
    model: str = "gpt-4o"
    temperature: float = 0.1  # Low for accuracy
    max_tokens: int = 4096

    @classmethod
    def from_env(cls) -> Optional['OpenAIConfig']:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            logger.error("OPENAI_API_KEY not set - agents disabled")
            return None
        return cls(
            api_key=api_key,
            model=os.environ.get('SCRAPER_OPENAI_MODEL', 'gpt-4o')
        )


@dataclass
class AgentConfig:
    """Configuration for individual agents."""
    max_context_tokens: int = 4000
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    require_citations: bool = True
    require_source_urls: bool = True
    prompt_version: str = "1.0.0"


@dataclass
class ScraperConfig:
    """Master configuration for CityScraper."""
    tavily: Optional[TavilyConfig]
    openai: Optional[OpenAIConfig]
    agents: AgentConfig = field(default_factory=AgentConfig)
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
