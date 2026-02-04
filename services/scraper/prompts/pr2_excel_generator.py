"""
Excel Generator Agent (PR-2) Configuration

Creates styled Excel workbooks from extraction results.

This agent does NOT use LLM - it performs mechanical Excel generation.
This configuration file provides sheet names, styling colors, and column widths.

Version: 1.0.0
"""

# =============================================================================
# SHEET NAMES
# =============================================================================

SYSTEMS_INFO_SHEET = "Municipal Systems Info"
PUBLIC_BIDS_SHEET = "Municipal Public Bids"
SOURCES_SHEET = "Sources"
SUMMARY_SHEET = "Summary"

# =============================================================================
# STYLING COLORS (hex without #)
# =============================================================================

# BidBrief brand colors
HEADER_BG_COLOR = "1F4E79"      # Dark blue
HEADER_TEXT_COLOR = "FFFFFF"   # White
ALT_ROW_COLOR = "D6EAF8"       # Light blue
BORDER_COLOR = "000000"        # Black

# Additional styling colors
SECTION_HEADER_BG = "5B9BD5"   # Medium blue
SECTION_HEADER_TEXT = "FFFFFF"  # White
SUBHEADER_BG = "BDD7EE"        # Light blue
SUBHEADER_TEXT = "1F4E79"      # Dark blue
LINK_COLOR = "0563C1"          # Standard link blue

# Status colors
STATUS_OPEN_BG = "C6EFCE"      # Light green
STATUS_CLOSED_BG = "FFC7CE"    # Light red
STATUS_AWARDED_BG = "FFEB9C"   # Light yellow

# =============================================================================
# COLUMN WIDTH LIMITS
# =============================================================================

MIN_COL_WIDTH = 10
MAX_COL_WIDTH = 50
DEFAULT_COL_WIDTH = 20

# Sheet-specific column widths
SYSTEMS_INFO_COLUMN_WIDTHS = {
    'municipality_city': 20,
    'state': 8,
    'relevant_agency': 25,
    'agency_scope': 40,
    'sanitary_sewer_pipe': 45,
    'storm_drain_pipe': 45,
    'storm_drain_assets': 40,
    'system_age_history': 40,
    'equipment_owned': 40,
    'maintenance_practices': 45,
    'sewage_incidents': 40,
    'storm_incidents': 40,
    'source_urls': 50,
    'verbatim_citations': 60,
    'notes_reconciliation': 40,
}

PUBLIC_BIDS_COLUMN_WIDTHS = {
    'municipality_city': 20,
    'state': 8,
    'agency_municipality': 25,
    'bid_contract_title': 40,
    'sewer_storm_keywords': 30,
    'scope': 50,
    'timeline_requirements': 40,
    'contacts': 35,
    'status_dates': 30,
    'source_urls': 50,
    'verbatim_citations': 60,
    'notes_reconciliation': 40,
}

SOURCES_COLUMN_WIDTHS = {
    'source_number': 8,
    'url': 60,
    'title': 40,
    'source_type': 15,
    'retrieved_at': 20,
    'relevance_score': 15,
}

SUMMARY_COLUMN_WIDTHS = {
    'label': 30,
    'value': 50,
}

# =============================================================================
# ROW HEIGHT SETTINGS
# =============================================================================

HEADER_ROW_HEIGHT = 30
DATA_ROW_HEIGHT = 40
TITLE_ROW_HEIGHT = 35

# =============================================================================
# CONFIGURATION FUNCTIONS
# =============================================================================


def get_config():
    """Get Excel generator configuration."""
    return {
        'sheet_names': {
            'systems_info': SYSTEMS_INFO_SHEET,
            'public_bids': PUBLIC_BIDS_SHEET,
            'sources': SOURCES_SHEET,
            'summary': SUMMARY_SHEET,
        },
        'colors': {
            'header_bg': HEADER_BG_COLOR,
            'header_text': HEADER_TEXT_COLOR,
            'alt_row': ALT_ROW_COLOR,
            'border': BORDER_COLOR,
            'section_header_bg': SECTION_HEADER_BG,
            'section_header_text': SECTION_HEADER_TEXT,
            'subheader_bg': SUBHEADER_BG,
            'subheader_text': SUBHEADER_TEXT,
            'link_color': LINK_COLOR,
            'status_open': STATUS_OPEN_BG,
            'status_closed': STATUS_CLOSED_BG,
            'status_awarded': STATUS_AWARDED_BG,
        },
        'column_widths': {
            'min': MIN_COL_WIDTH,
            'max': MAX_COL_WIDTH,
            'default': DEFAULT_COL_WIDTH,
            'systems_info': SYSTEMS_INFO_COLUMN_WIDTHS,
            'public_bids': PUBLIC_BIDS_COLUMN_WIDTHS,
            'sources': SOURCES_COLUMN_WIDTHS,
            'summary': SUMMARY_COLUMN_WIDTHS,
        },
        'row_heights': {
            'header': HEADER_ROW_HEIGHT,
            'data': DATA_ROW_HEIGHT,
            'title': TITLE_ROW_HEIGHT,
        }
    }


def get_sheet_names():
    """Get sheet name constants."""
    return {
        'systems_info': SYSTEMS_INFO_SHEET,
        'public_bids': PUBLIC_BIDS_SHEET,
        'sources': SOURCES_SHEET,
        'summary': SUMMARY_SHEET,
    }
