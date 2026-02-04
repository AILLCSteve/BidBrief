"""
BR-4 Scraper Dispatcher Configuration

Mechanical orchestration agent - no LLM prompts.
Dispatches to PF-O (Pre-flight Orchestrator) and EX-O (Extraction Orchestrator).

This agent coordinates the CityScraper pipeline execution from HOTDOG bridge requests.
It is purely mechanical - no LLM calls are needed.

Version: 1.0.0
"""

# =============================================================================
# STATUS VALUES
# =============================================================================

STATUS_DISPATCHED = "dispatched"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# All valid status values
VALID_STATUSES = (STATUS_DISPATCHED, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED)

# =============================================================================
# TABLE MODE VALUES
# =============================================================================

TABLE_MODE_SYSTEMS_INFO = "systems_info"
TABLE_MODE_PUBLIC_BIDS = "public_bids"
TABLE_MODE_BOTH = "both"

VALID_TABLE_MODES = (TABLE_MODE_SYSTEMS_INFO, TABLE_MODE_PUBLIC_BIDS, TABLE_MODE_BOTH)

# =============================================================================
# DEFAULT CONFIGURATION
# =============================================================================

DEFAULT_CONFIG = {
    "async_mode": True,
    "timeout_seconds": 300,  # 5 minute timeout
    "retry_preflight": False,
    "retry_extraction": True,
    "max_retries": 1,
}

# =============================================================================
# ERROR MESSAGES
# =============================================================================

ERROR_MESSAGES = {
    "missing_municipality": "Municipality input is required",
    "invalid_municipality": "Municipality must be a dict with 'city' and 'state' keys",
    "invalid_table_mode": "table_mode must be one of: systems_info, public_bids, both",
    "preflight_failed": "Pre-flight validation failed",
    "extraction_failed": "Extraction pipeline failed",
    "packaging_failed": "Result packaging failed",
    "timeout": "Pipeline timed out after {timeout} seconds",
}

# =============================================================================
# CONFIGURATION FUNCTIONS
# =============================================================================


def get_config() -> dict:
    """Return default dispatch configuration."""
    return DEFAULT_CONFIG.copy()


def get_status_values() -> tuple:
    """Return valid status values."""
    return VALID_STATUSES


def get_table_modes() -> tuple:
    """Return valid table mode values."""
    return VALID_TABLE_MODES


def get_error_message(error_key: str, **kwargs) -> str:
    """Get formatted error message."""
    template = ERROR_MESSAGES.get(error_key, f"Unknown error: {error_key}")
    return template.format(**kwargs)
