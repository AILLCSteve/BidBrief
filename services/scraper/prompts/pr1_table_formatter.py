"""
Table Formatter Agent (PR-1) Configuration

Converts extraction results to markdown tables following extractiondev.md schemas.

This agent does NOT use LLM prompts - it performs mechanical formatting.
This configuration file provides table header definitions and formatting options.

Version: 1.0.0
"""

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 1: MUNICIPAL SYSTEMS INFORMATION (15 columns per extractiondev.md)
# ═══════════════════════════════════════════════════════════════════════════

SYSTEMS_INFO_HEADERS = [
    "Municipality (City)",
    "State",
    "Relevant agency (name)",
    "1. Agency & scope of jurisdiction",
    "2. Sanitary sewer pipe total feet + pipe sizes + types",
    "3. Positive storm drain pipe total feet + pipe sizes + types",
    "4. Storm drain catch basins/asset counts + types",
    "5. System age + agency age/history of jurisdiction",
    "6. Owned equipment for cleaning/maintenance/CCTV",
    "7. Cleaning/televising/maintenance practices",
    "8. Sewage overflow/stoppage/pipe breaks/emergency incidents",
    "9. Storm drain overflow/flooding/clog incidents",
    "Source URL(s)",
    "Verbatim textual citations (direct quotes)",
    "Notes / reconciliation"
]

# ═══════════════════════════════════════════════════════════════════════════
# TABLE 2: MUNICIPAL PUBLIC BIDS (12 columns per extractiondev.md)
# ═══════════════════════════════════════════════════════════════════════════

PUBLIC_BIDS_HEADERS = [
    "Municipality (City)",
    "State",
    "1. Agency/agency(ies) + municipality represented",
    "Bid/contract title",
    "Sewer/storm keyword(s) explicitly present",
    "2. Scope (budget/award if available; type; length/amount/assets; methods)",
    "3. Timeline & requirements",
    "4. Contacts",
    "Status (open/closed/awarded) + key dates",
    "Source URL(s)",
    "Verbatim textual citations (direct quotes)",
    "Notes / reconciliation"
]

# ═══════════════════════════════════════════════════════════════════════════
# FORMATTING CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

FORMATTING_CONFIG = {
    # No truncation - show all data
    'truncate_cells': False,

    # Maximum cell width (for display purposes only, not enforced in output)
    'max_cell_display_width': None,

    # NOT FOUND placeholder
    'not_found_text': 'NOT FOUND',

    # Citation separator for multiple citations
    'citation_separator': ' | ',

    # URL separator for multiple sources
    'url_separator': '; ',

    # Key dates format in status column
    'dates_separator': '; ',

    # Keywords separator for sewer/storm keywords
    'keywords_separator': ', ',
}


def get_config():
    """Get table formatter configuration."""
    return {
        'systems_info_headers': SYSTEMS_INFO_HEADERS,
        'public_bids_headers': PUBLIC_BIDS_HEADERS,
        'systems_info_column_count': len(SYSTEMS_INFO_HEADERS),
        'public_bids_column_count': len(PUBLIC_BIDS_HEADERS),
        'formatting': FORMATTING_CONFIG,
    }


def get_systems_info_header_row() -> str:
    """Generate markdown header row for Municipal Systems Information table."""
    return "| " + " | ".join(SYSTEMS_INFO_HEADERS) + " |"


def get_systems_info_separator_row() -> str:
    """Generate markdown separator row for Municipal Systems Information table."""
    return "|" + "|".join(["---"] * len(SYSTEMS_INFO_HEADERS)) + "|"


def get_public_bids_header_row() -> str:
    """Generate markdown header row for Municipal Public Bids table."""
    return "| " + " | ".join(PUBLIC_BIDS_HEADERS) + " |"


def get_public_bids_separator_row() -> str:
    """Generate markdown separator row for Municipal Public Bids table."""
    return "|" + "|".join(["---"] * len(PUBLIC_BIDS_HEADERS)) + "|"
