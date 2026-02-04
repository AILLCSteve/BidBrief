"""
Document Downloader Agent (EX-6) Configuration

This agent does NOT use LLM parsing - it directly downloads files.
This file exists for consistency with other EX-* agents and provides
configuration constants.

PROMPT DEVELOPMENT HISTORY:
- N/A - This agent does not use LLM prompts. It is a mechanical
  downloader that uses httpx to fetch files directly.

Version: 1.0.0
Last Updated: 2026-02-03
"""

# ═══════════════════════════════════════════════════════════════════════════
# SUPPORTED FILE TYPES
# ═══════════════════════════════════════════════════════════════════════════

SUPPORTED_FILE_TYPES = [
    'pdf',      # PDF documents (most common for bids)
    'doc',      # Microsoft Word (legacy)
    'docx',     # Microsoft Word (modern)
    'xls',      # Microsoft Excel (legacy)
    'xlsx',     # Microsoft Excel (modern)
    'csv',      # Comma-separated values
    'txt',      # Plain text
    'rtf',      # Rich Text Format
    'zip',      # Compressed archives
]

# ═══════════════════════════════════════════════════════════════════════════
# DEFAULT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# Maximum file size to download (in megabytes)
# Files larger than this will be skipped
DEFAULT_MAX_FILE_SIZE_MB = 50

# Timeout for each download request (in seconds)
# Includes connection time and download time
DEFAULT_TIMEOUT_SECONDS = 30

# Base directory for downloaded files
# Files are stored in: {download_dir}/{session_id}/{filename}
DEFAULT_DOWNLOAD_DIR = 'scraper_downloads'

# Delay between downloads to avoid rate limiting (in seconds)
DEFAULT_RATE_LIMIT_DELAY = 0.5

# ═══════════════════════════════════════════════════════════════════════════
# USER AGENT
# ═══════════════════════════════════════════════════════════════════════════

# User-agent string sent with download requests
# Identifies the tool for municipal servers
USER_AGENT = 'BidBrief CityScraper/1.0 (Municipal Research Tool)'

# ═══════════════════════════════════════════════════════════════════════════
# MIME TYPE MAPPINGS
# ═══════════════════════════════════════════════════════════════════════════

# Maps Content-Type headers to file extensions
MIME_TYPE_MAP = {
    'application/pdf': 'pdf',
    'application/msword': 'doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.ms-excel': 'xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'text/csv': 'csv',
    'text/plain': 'txt',
    'application/rtf': 'rtf',
    'text/rtf': 'rtf',
    'application/zip': 'zip',
    'application/x-zip-compressed': 'zip',
}


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def get_config() -> dict:
    """
    Get download configuration.

    Returns:
        Dictionary with all configuration values
    """
    return {
        'supported_types': SUPPORTED_FILE_TYPES,
        'max_file_size_mb': DEFAULT_MAX_FILE_SIZE_MB,
        'timeout_seconds': DEFAULT_TIMEOUT_SECONDS,
        'download_dir': DEFAULT_DOWNLOAD_DIR,
        'rate_limit_delay': DEFAULT_RATE_LIMIT_DELAY,
        'user_agent': USER_AGENT,
        'mime_type_map': MIME_TYPE_MAP,
    }


def is_supported_file_type(file_type: str) -> bool:
    """
    Check if a file type is supported for download.

    Args:
        file_type: File extension (with or without leading dot)

    Returns:
        True if the file type is supported
    """
    if not file_type:
        return False
    return file_type.lower().strip('.') in SUPPORTED_FILE_TYPES


def get_extension_from_mime(content_type: str) -> str:
    """
    Get file extension from Content-Type header.

    Args:
        content_type: Content-Type header value

    Returns:
        File extension (without dot) or empty string
    """
    if not content_type:
        return ''

    content_type = content_type.lower().split(';')[0].strip()
    return MIME_TYPE_MAP.get(content_type, '')
