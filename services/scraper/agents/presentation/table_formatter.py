"""
Table Formatter Agent (PR-1)

Converts ExtractionResult to markdown tables matching extractiondev.md schemas exactly.

Key Responsibilities:
- Convert MunicipalSystemsInfoRow to markdown table row
- Convert MunicipalPublicBidRow to markdown table row
- Generate complete markdown tables with headers
- NO truncation - show all data
- NO placeholders - use "NOT FOUND" for missing data
- Preserve all verbatim citations
- Handle pipe characters in data (escape with \\|)

Version: 1.0.0
"""

import logging
import time
from typing import Dict, Any, List, Optional

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    ExtractionResult,
    MunicipalSystemsInfoRow,
    MunicipalPublicBidRow,
    ExtractedDataPoint,
    TableMode,
)
from services.scraper.prompts.pr1_table_formatter import (
    get_config,
    SYSTEMS_INFO_HEADERS,
    PUBLIC_BIDS_HEADERS,
    FORMATTING_CONFIG,
)

logger = logging.getLogger(__name__)


class TableFormatterAgent(BaseAgent):
    """
    PR-1: Table Formatter Agent

    Converts extraction results to markdown tables following exact schemas
    from extractiondev.md.

    This agent performs mechanical formatting - no LLM calls needed for
    standard formatting. LLM may be used for intelligent formatting decisions
    if edge cases arise.

    Table Schemas:
    - Municipal Systems Information: 15 columns
    - Municipal Public Bids: 12 columns
    """

    AGENT_ID = "pr-1"
    AGENT_NAME = "Table Formatter"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "1.0.0"  # Config version, not LLM prompt
    PROMPT_LAST_REFINED = "2026-02-04"

    def __init__(self, *args, **kwargs):
        """Initialize the Table Formatter Agent."""
        super().__init__(*args, **kwargs)
        self._config = get_config()

    def get_system_prompt(self) -> str:
        """
        Get system prompt for edge case handling.

        The Table Formatter mostly does mechanical formatting, but may use
        LLM for intelligent formatting decisions in complex edge cases.
        """
        return """You are a Table Formatter specialist for municipal data.

Your task is to help format complex data into clean markdown table cells when
mechanical formatting is insufficient.

Rules:
1. Never truncate data - show everything
2. Escape pipe characters with \\|
3. Replace newlines with spaces
4. Use "NOT FOUND" for missing data
5. Preserve verbatim citations exactly as provided
6. Separate multiple values with semicolons or as specified

When asked to format a specific value, return ONLY the formatted string
suitable for a markdown table cell."""

    def _escape_pipe(self, text: str) -> str:
        """Escape pipe characters and newlines for markdown tables."""
        if not text:
            return ""
        # Escape pipe characters
        escaped = text.replace("|", "\\|")
        # Replace newlines with spaces
        escaped = escaped.replace("\n", " ").replace("\r", " ")
        # Collapse multiple spaces
        while "  " in escaped:
            escaped = escaped.replace("  ", " ")
        return escaped.strip()

    def _safe_value(self, value: Any) -> str:
        """
        Safely convert any value to a table cell string.

        Args:
            value: The value to convert (str, ExtractedDataPoint, list, dict, etc.)

        Returns:
            Escaped string suitable for markdown table cell
        """
        if value is None:
            return FORMATTING_CONFIG['not_found_text']

        if isinstance(value, ExtractedDataPoint):
            return self._escape_pipe(value.value or FORMATTING_CONFIG['not_found_text'])

        if isinstance(value, list):
            if not value:
                return FORMATTING_CONFIG['not_found_text']
            # Join list items
            items = [str(item) for item in value if item]
            return self._escape_pipe(FORMATTING_CONFIG['keywords_separator'].join(items))

        if isinstance(value, dict):
            if not value:
                return FORMATTING_CONFIG['not_found_text']
            # Format dict as key: value pairs
            parts = [f"{k}: {v}" for k, v in value.items() if v]
            return self._escape_pipe(FORMATTING_CONFIG['dates_separator'].join(parts))

        # String or other type
        text = str(value).strip()
        if not text:
            return FORMATTING_CONFIG['not_found_text']
        return self._escape_pipe(text)

    def _format_sources(self, source_urls: List[Any]) -> str:
        """Format source URLs for table cell."""
        if not source_urls:
            return FORMATTING_CONFIG['not_found_text']

        urls = []
        for source in source_urls:
            if hasattr(source, 'url'):
                urls.append(source.url)
            elif isinstance(source, dict) and 'url' in source:
                urls.append(source['url'])
            elif isinstance(source, str):
                urls.append(source)

        if not urls:
            return FORMATTING_CONFIG['not_found_text']

        return self._escape_pipe(FORMATTING_CONFIG['url_separator'].join(urls))

    def _format_citations(self, verbatim_citations: List[Any]) -> str:
        """
        Format verbatim citations for table cell.

        NO TRUNCATION - preserve full citations as required by extractiondev.md.
        """
        if not verbatim_citations:
            return FORMATTING_CONFIG['not_found_text']

        texts = []
        for citation in verbatim_citations:
            if hasattr(citation, 'text'):
                texts.append(citation.text)
            elif isinstance(citation, dict) and 'text' in citation:
                texts.append(citation['text'])
            elif isinstance(citation, str):
                texts.append(citation)

        if not texts:
            return FORMATTING_CONFIG['not_found_text']

        # Join with citation separator - NO TRUNCATION
        return self._escape_pipe(FORMATTING_CONFIG['citation_separator'].join(texts))

    def _format_systems_info_row(self, row: MunicipalSystemsInfoRow) -> str:
        """
        Format a single Municipal Systems Information row as markdown.

        Args:
            row: MunicipalSystemsInfoRow object

        Returns:
            Markdown table row string (starts and ends with |)
        """
        cells = [
            # Identification columns
            self._safe_value(row.municipality_city),
            self._safe_value(row.state),
            self._safe_value(row.relevant_agency),

            # Data columns 1-9
            self._safe_value(row.agency_scope),
            self._safe_value(row.sanitary_sewer_pipe),
            self._safe_value(row.storm_drain_pipe),
            self._safe_value(row.storm_drain_assets),
            self._safe_value(row.system_age_history),
            self._safe_value(row.equipment_owned),
            self._safe_value(row.maintenance_practices),
            self._safe_value(row.sewage_incidents),
            self._safe_value(row.storm_incidents),

            # Source tracking
            self._format_sources(row.source_urls),
            self._format_citations(row.verbatim_citations),
            self._safe_value(row.notes_reconciliation),
        ]

        return "| " + " | ".join(cells) + " |"

    def _format_public_bid_row(self, row: MunicipalPublicBidRow) -> str:
        """
        Format a single Municipal Public Bids row as markdown.

        Args:
            row: MunicipalPublicBidRow object

        Returns:
            Markdown table row string (starts and ends with |)
        """
        # Format status with key dates
        status_parts = [row.status or "NOT FOUND"]
        if row.key_dates:
            date_parts = [f"{k}: {v}" for k, v in row.key_dates.items() if v]
            if date_parts:
                status_parts.append(FORMATTING_CONFIG['dates_separator'].join(date_parts))
        status_with_dates = " | ".join(status_parts)

        cells = [
            # Identification
            self._safe_value(row.municipality_city),
            self._safe_value(row.state),
            self._safe_value(row.agency_municipality),
            self._safe_value(row.bid_contract_title),

            # Keywords
            self._safe_value(row.sewer_storm_keywords),

            # Data columns
            self._safe_value(row.scope),
            self._safe_value(row.timeline_requirements),
            self._safe_value(row.contacts),
            self._escape_pipe(status_with_dates),

            # Source tracking
            self._format_sources(row.source_urls),
            self._format_citations(row.verbatim_citations),
            self._safe_value(row.notes_reconciliation),
        ]

        return "| " + " | ".join(cells) + " |"

    def format_systems_info_table(
        self,
        rows: List[MunicipalSystemsInfoRow]
    ) -> str:
        """
        Generate complete markdown table for Municipal Systems Information.

        Args:
            rows: List of MunicipalSystemsInfoRow objects

        Returns:
            Complete markdown table string with headers and all rows
        """
        # Header row
        header = "| " + " | ".join(SYSTEMS_INFO_HEADERS) + " |"

        # Separator row
        separator = "|" + "|".join(["---"] * len(SYSTEMS_INFO_HEADERS)) + "|"

        # Body rows
        body_rows = [self._format_systems_info_row(row) for row in rows]

        # Combine
        return "\n".join([header, separator] + body_rows)

    def format_public_bids_table(
        self,
        rows: List[MunicipalPublicBidRow]
    ) -> str:
        """
        Generate complete markdown table for Municipal Public Bids.

        Args:
            rows: List of MunicipalPublicBidRow objects

        Returns:
            Complete markdown table string with headers and all rows
        """
        # Header row
        header = "| " + " | ".join(PUBLIC_BIDS_HEADERS) + " |"

        # Separator row
        separator = "|" + "|".join(["---"] * len(PUBLIC_BIDS_HEADERS)) + "|"

        # Body rows
        body_rows = [self._format_public_bid_row(row) for row in rows]

        # Combine
        return "\n".join([header, separator] + body_rows)

    def _check_citations_complete(
        self,
        rows: List[Any],
        table_mode: TableMode
    ) -> bool:
        """Check if all rows have citations."""
        for row in rows:
            if not row.verbatim_citations:
                return False
        return True

    def _collect_warnings(
        self,
        rows: List[Any],
        table_mode: TableMode
    ) -> List[str]:
        """Collect formatting warnings for the result."""
        warnings = []

        for i, row in enumerate(rows, 1):
            # Check for missing citations
            if not row.verbatim_citations:
                if table_mode == TableMode.MUNICIPAL_SYSTEMS_INFO:
                    warnings.append(f"Row {i}: Missing verbatim citations")
                else:
                    warnings.append(f"Row {i}: Missing verbatim citations for bid")

            # Check for missing sources
            if not row.source_urls:
                warnings.append(f"Row {i}: Missing source URLs")

            # Check for NOT FOUND in critical fields
            if table_mode == TableMode.MUNICIPAL_SYSTEMS_INFO:
                row_typed: MunicipalSystemsInfoRow = row
                if row_typed.agency_scope and row_typed.agency_scope.value == "NOT FOUND":
                    warnings.append(f"Row {i}: Agency scope NOT FOUND")
            else:
                row_typed_bid: MunicipalPublicBidRow = row
                if row_typed_bid.scope and row_typed_bid.scope.value == "NOT FOUND":
                    warnings.append(f"Row {i}: Bid scope NOT FOUND")

        return warnings

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process table formatting request.

        Expected input_data:
        - extraction_result: ExtractionResult object (or dict representation)
        - table_mode: TableMode enum or string

        Returns AgentResponse with:
        - markdown_table: Complete markdown table string
        - row_count: Number of data rows
        - column_count: Number of columns
        - has_all_citations: Whether all rows have citations
        - warnings: List of formatting warnings
        """
        start_time = time.time()

        try:
            self.emit_event("processing", "Formatting extraction results to markdown table")

            # Extract inputs
            extraction_result = request.input_data.get('extraction_result')
            table_mode = request.input_data.get('table_mode')

            # Validate extraction_result
            if extraction_result is None:
                return AgentResponse(
                    agent_id=self.AGENT_ID,
                    task=request.task,
                    success=False,
                    output_data={},
                    errors=["extraction_result is required"],
                    processing_time_seconds=time.time() - start_time
                )

            # Handle table_mode as string or enum
            if isinstance(table_mode, str):
                try:
                    table_mode = TableMode(table_mode)
                except ValueError:
                    # Try matching by name
                    if table_mode.upper() == 'MUNICIPAL_SYSTEMS_INFO':
                        table_mode = TableMode.MUNICIPAL_SYSTEMS_INFO
                    elif table_mode.upper() == 'MUNICIPAL_PUBLIC_BIDS':
                        table_mode = TableMode.MUNICIPAL_PUBLIC_BIDS
                    else:
                        return AgentResponse(
                            agent_id=self.AGENT_ID,
                            task=request.task,
                            success=False,
                            output_data={},
                            errors=[f"Invalid table_mode: {table_mode}"],
                            processing_time_seconds=time.time() - start_time
                        )
            elif table_mode is None:
                # Try to get from extraction_result
                if hasattr(extraction_result, 'table_mode'):
                    table_mode = extraction_result.table_mode
                elif isinstance(extraction_result, dict) and 'table_mode' in extraction_result:
                    mode_val = extraction_result['table_mode']
                    if isinstance(mode_val, TableMode):
                        table_mode = mode_val
                    elif isinstance(mode_val, str):
                        try:
                            table_mode = TableMode(mode_val)
                        except ValueError:
                            pass

            if table_mode is None:
                return AgentResponse(
                    agent_id=self.AGENT_ID,
                    task=request.task,
                    success=False,
                    output_data={},
                    errors=["table_mode is required and could not be determined"],
                    processing_time_seconds=time.time() - start_time
                )

            # Get rows from extraction result
            if isinstance(extraction_result, ExtractionResult):
                systems_rows = extraction_result.systems_info_rows
                bid_rows = extraction_result.public_bid_rows
            elif isinstance(extraction_result, dict):
                systems_rows = extraction_result.get('systems_info_rows', [])
                bid_rows = extraction_result.get('public_bid_rows', [])
            else:
                return AgentResponse(
                    agent_id=self.AGENT_ID,
                    task=request.task,
                    success=False,
                    output_data={},
                    errors=[f"extraction_result must be ExtractionResult or dict, got {type(extraction_result).__name__}"],
                    processing_time_seconds=time.time() - start_time
                )

            # Format based on table mode
            if table_mode == TableMode.MUNICIPAL_SYSTEMS_INFO:
                self.emit_event("processing", f"Formatting {len(systems_rows)} systems info rows")

                if not systems_rows:
                    return AgentResponse(
                        agent_id=self.AGENT_ID,
                        task=request.task,
                        success=True,
                        output_data={
                            'markdown_table': self.format_systems_info_table([]),
                            'row_count': 0,
                            'column_count': len(SYSTEMS_INFO_HEADERS),
                            'has_all_citations': True,
                            'warnings': ["No data rows to format"],
                        },
                        processing_time_seconds=time.time() - start_time
                    )

                markdown_table = self.format_systems_info_table(systems_rows)
                row_count = len(systems_rows)
                column_count = len(SYSTEMS_INFO_HEADERS)
                has_all_citations = self._check_citations_complete(systems_rows, table_mode)
                warnings = self._collect_warnings(systems_rows, table_mode)

            else:  # MUNICIPAL_PUBLIC_BIDS
                self.emit_event("processing", f"Formatting {len(bid_rows)} public bid rows")

                if not bid_rows:
                    return AgentResponse(
                        agent_id=self.AGENT_ID,
                        task=request.task,
                        success=True,
                        output_data={
                            'markdown_table': self.format_public_bids_table([]),
                            'row_count': 0,
                            'column_count': len(PUBLIC_BIDS_HEADERS),
                            'has_all_citations': True,
                            'warnings': ["No data rows to format"],
                        },
                        processing_time_seconds=time.time() - start_time
                    )

                markdown_table = self.format_public_bids_table(bid_rows)
                row_count = len(bid_rows)
                column_count = len(PUBLIC_BIDS_HEADERS)
                has_all_citations = self._check_citations_complete(bid_rows, table_mode)
                warnings = self._collect_warnings(bid_rows, table_mode)

            elapsed = time.time() - start_time

            self.emit_event(
                "completed",
                f"Formatted {row_count} rows into {column_count}-column markdown table",
                is_completed=True
            )

            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=True,
                output_data={
                    'markdown_table': markdown_table,
                    'row_count': row_count,
                    'column_count': column_count,
                    'has_all_citations': has_all_citations,
                    'warnings': warnings,
                },
                processing_time_seconds=elapsed
            )

        except Exception as e:
            logger.exception(f"PR-1 unexpected error: {e}")
            self.emit_event("failed", f"Formatting error: {str(e)[:100]}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:200]}"],
                processing_time_seconds=time.time() - start_time
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate table formatter output."""
        errors = []

        # Check required fields
        if 'markdown_table' not in output:
            errors.append("Missing 'markdown_table' in output")

        if 'row_count' not in output:
            errors.append("Missing 'row_count' in output")

        if 'column_count' not in output:
            errors.append("Missing 'column_count' in output")

        # Validate markdown_table is a string
        if 'markdown_table' in output and not isinstance(output['markdown_table'], str):
            errors.append("'markdown_table' must be a string")

        # Validate row_count is an int
        if 'row_count' in output and not isinstance(output['row_count'], int):
            errors.append("'row_count' must be an integer")

        # Validate column_count is an int
        if 'column_count' in output and not isinstance(output['column_count'], int):
            errors.append("'column_count' must be an integer")

        return errors
