"""CityScraper Presentation Agents Package.

This package contains agents responsible for converting extraction results
into various output formats for display and export.

Agents:
- PR-1: Table Formatter - Converts extraction results to markdown tables
- PR-2: Excel Generator - Generates styled Excel workbooks
- PR-3: UI Data Packager - Packages data for UI display (future)
"""

from .table_formatter import TableFormatterAgent
from .excel_generator import ExcelGeneratorAgent

__all__ = ['TableFormatterAgent', 'ExcelGeneratorAgent']
