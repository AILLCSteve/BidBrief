"""
UI Data Packager Agent (PR-3) Configuration

Formats extraction results for the CityScraper frontend UI.

This agent does NOT use LLM - it performs mechanical data transformation.
This configuration file provides color mappings, display settings, and UI constants.

Version: 1.0.0
"""

# =============================================================================
# CONFIDENCE COLOR MAPPINGS (CSS colors for UI)
# =============================================================================

CONFIDENCE_COLORS = {
    'high': '#28a745',      # Green - reliable data
    'medium': '#ffc107',    # Yellow - needs verification
    'low': '#dc3545',       # Red - unreliable
    'not_found': '#6c757d', # Gray - missing data
}

# Additional UI colors for status indicators
STATUS_COLORS = {
    'completed': '#28a745',   # Green
    'partial': '#ffc107',     # Yellow
    'failed': '#dc3545',      # Red
    'running': '#17a2b8',     # Blue
    'pending': '#6c757d',     # Gray
}

# Agent status colors for activity feed
AGENT_STATUS_COLORS = {
    'starting': '#17a2b8',    # Blue
    'processing': '#007bff',  # Primary blue
    'searching': '#6f42c1',   # Purple
    'completed': '#28a745',   # Green
    'failed': '#dc3545',      # Red
}

# =============================================================================
# DATA TABLE HEADERS
# =============================================================================

SYSTEMS_INFO_TABLE_HEADERS = [
    'Municipality',
    'State',
    'Agency',
    'Scope',
    'Sewer Pipe',
    'Storm Pipe',
    'Storm Assets',
    'Age/History',
    'Equipment',
    'Maintenance',
    'Sewer Incidents',
    'Storm Incidents',
    'Sources',
    'Citations',
    'Notes',
]

PUBLIC_BIDS_TABLE_HEADERS = [
    'Municipality',
    'State',
    'Agency',
    'Bid Title',
    'Keywords',
    'Scope',
    'Timeline',
    'Contacts',
    'Status',
    'Sources',
    'Citations',
    'Notes',
]

# =============================================================================
# UI DISPLAY SETTINGS
# =============================================================================

# Maximum characters to show in table cells before truncating for display
MAX_CELL_DISPLAY_LENGTH = 200

# Truncation suffix when content exceeds display length
TRUNCATION_SUFFIX = '...'

# Default values for display
NOT_FOUND_DISPLAY = 'NOT FOUND'
NOT_AVAILABLE_DISPLAY = 'N/A'

# Date/time format for UI display
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
DATE_FORMAT = '%Y-%m-%d'

# =============================================================================
# EXPORT URL TEMPLATES
# =============================================================================

# API endpoint templates for exports
EXPORT_URL_TEMPLATES = {
    'excel': '/api/scraper/export/excel/{session_id}',
    'markdown': '/api/scraper/export/markdown/{session_id}',
    'json': '/api/scraper/export/json/{session_id}',
    'csv': '/api/scraper/export/csv/{session_id}',
}

# =============================================================================
# SOURCE TYPE DISPLAY NAMES
# =============================================================================

SOURCE_TYPE_DISPLAY = {
    'official': 'Official Website',
    'gis': 'GIS Portal',
    'cip': 'CIP Document',
    'cmom': 'CMOM Document',
    'bid_portal': 'Bid Portal',
    'news': 'News Article',
    'budget': 'Budget Document',
    'agenda': 'Meeting Agenda',
    'minutes': 'Meeting Minutes',
    'pdf': 'PDF Document',
    'report': 'Report',
    'unknown': 'Unknown Source',
}

# =============================================================================
# DOWNLOAD STATUS DISPLAY
# =============================================================================

DOWNLOAD_STATUS_DISPLAY = {
    'available': 'Available',
    'downloaded': 'Downloaded',
    'failed': 'Failed',
    'pending': 'Pending',
}

# =============================================================================
# CONFIGURATION FUNCTIONS
# =============================================================================


def get_config():
    """Get UI packager configuration."""
    return {
        'confidence_colors': CONFIDENCE_COLORS,
        'status_colors': STATUS_COLORS,
        'agent_status_colors': AGENT_STATUS_COLORS,
        'table_headers': {
            'systems_info': SYSTEMS_INFO_TABLE_HEADERS,
            'public_bids': PUBLIC_BIDS_TABLE_HEADERS,
        },
        'display': {
            'max_cell_length': MAX_CELL_DISPLAY_LENGTH,
            'truncation_suffix': TRUNCATION_SUFFIX,
            'not_found': NOT_FOUND_DISPLAY,
            'not_available': NOT_AVAILABLE_DISPLAY,
            'datetime_format': DATETIME_FORMAT,
            'date_format': DATE_FORMAT,
        },
        'export_urls': EXPORT_URL_TEMPLATES,
        'source_types': SOURCE_TYPE_DISPLAY,
        'download_statuses': DOWNLOAD_STATUS_DISPLAY,
    }


def get_confidence_color(confidence: str) -> str:
    """Get CSS color for a confidence level."""
    return CONFIDENCE_COLORS.get(confidence.lower(), CONFIDENCE_COLORS['not_found'])


def get_status_color(status: str) -> str:
    """Get CSS color for a session status."""
    return STATUS_COLORS.get(status.lower(), STATUS_COLORS['pending'])


def get_export_url(export_type: str, session_id: str) -> str:
    """Generate export URL for a given type and session."""
    template = EXPORT_URL_TEMPLATES.get(export_type, '')
    return template.format(session_id=session_id)
