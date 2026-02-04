"""CityScraper Presentation Agents Package.

This package contains agents responsible for converting extraction results
into various output formats for display and export.

Agents:
- PR-1: Table Formatter - Converts extraction results to markdown tables
- PR-2: Excel Generator - Generates Excel spreadsheets (future)
- PR-3: UI Data Packager - Packages data for UI display (future)
"""

from .table_formatter import TableFormatterAgent

__all__ = ['TableFormatterAgent']
