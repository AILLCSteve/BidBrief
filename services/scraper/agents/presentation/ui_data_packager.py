"""
UI Data Packager Agent (PR-3)

Formats extraction results as JSON for the CityScraper tab in the frontend.

Key Responsibilities:
- Convert ExtractionResult to frontend-friendly JSON
- Include metadata for display (confidence colors, source links)
- Structure data for the agent activity feed
- Format data for the results tabs (Data Table, Sources, Analysis, Downloads)
- Include export URLs
- Support partial and failed status reporting

This agent does NOT need LLM - it performs mechanical data transformation.

Version: 1.0.0
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    ExtractionResult,
    MunicipalSystemsInfoRow,
    MunicipalPublicBidRow,
    ExtractedDataPoint,
    SourceURL,
    VerbatimCitation,
    TableMode,
    ConfidenceRating,
    AgentActivityEvent,
    Municipality,
    PreflightResult,
    PreflightStatus,
)
from services.scraper.prompts.pr3_ui_packager import (
    get_config,
    get_confidence_color,
    get_export_url,
    CONFIDENCE_COLORS,
    SYSTEMS_INFO_TABLE_HEADERS,
    PUBLIC_BIDS_TABLE_HEADERS,
    SOURCE_TYPE_DISPLAY,
    DOWNLOAD_STATUS_DISPLAY,
)

logger = logging.getLogger(__name__)


class UIDataPackagerAgent(BaseAgent):
    """
    PR-3: UI Data Packager Agent

    Transforms extraction results into frontend-friendly JSON structures
    for the CityScraper tab display.

    Output includes:
    - Session metadata
    - Summary statistics
    - Data table with confidence indicators
    - Sources list
    - Downloads list
    - Agent activity feed
    - Export URLs
    - Data gaps and warnings

    This agent does NOT need LLM - it performs mechanical data transformation.
    """

    AGENT_ID = "pr-3"
    AGENT_NAME = "UI Data Packager"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "1.0.0"  # Config version, not LLM prompt
    PROMPT_LAST_REFINED = "2026-02-04"

    def __init__(self, *args, **kwargs):
        """Initialize the UI Data Packager Agent."""
        super().__init__(*args, **kwargs)
        self._config = get_config()

    def get_system_prompt(self) -> str:
        """
        Get system prompt - not used for this mechanical agent.

        The UI Data Packager does purely mechanical data transformation,
        so no LLM calls are needed for standard operation.
        """
        return """You are a UI Data Packager specialist for municipal data.

This agent performs mechanical data transformation and does not typically
require LLM assistance. If invoked, help with formatting decisions."""

    # =========================================================================
    # VALUE EXTRACTION HELPERS
    # =========================================================================

    def _get_value(self, data: Any) -> str:
        """Extract string value from various data types."""
        if data is None:
            return "NOT FOUND"

        if isinstance(data, ExtractedDataPoint):
            return data.value or "NOT FOUND"

        if isinstance(data, list):
            if not data:
                return "NOT FOUND"
            items = [str(item) for item in data if item]
            return ", ".join(items) if items else "NOT FOUND"

        if isinstance(data, dict):
            if not data:
                return "NOT FOUND"
            parts = [f"{k}: {v}" for k, v in data.items() if v]
            return "; ".join(parts) if parts else "NOT FOUND"

        text = str(data).strip()
        return text if text else "NOT FOUND"

    def _get_confidence(self, data: Any) -> str:
        """Extract confidence level from data."""
        if isinstance(data, ExtractedDataPoint):
            if data.confidence:
                if isinstance(data.confidence, ConfidenceRating):
                    return data.confidence.value
                return str(data.confidence).lower()
            return "medium"

        if data is None or (isinstance(data, str) and data == "NOT FOUND"):
            return "not_found"

        return "medium"

    def _format_datetime(self, dt: Optional[datetime]) -> str:
        """Format datetime for UI display."""
        if dt is None:
            return ""
        return dt.strftime(self._config['display']['datetime_format'])

    def _truncate_for_display(self, text: str) -> str:
        """Truncate text for table cell display."""
        max_len = self._config['display']['max_cell_length']
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + self._config['display']['truncation_suffix']

    # =========================================================================
    # SUMMARY GENERATION
    # =========================================================================

    def _generate_summary(
        self,
        result: ExtractionResult,
        table_mode: TableMode
    ) -> Dict[str, Any]:
        """Generate summary statistics for the extraction."""
        high_count = 0
        medium_count = 0
        low_count = 0
        not_found_count = 0
        total_data_points = 0

        # Collect all data points for confidence counting
        data_points: List[ExtractedDataPoint] = []

        if table_mode == TableMode.MUNICIPAL_SYSTEMS_INFO:
            for row in result.systems_info_rows:
                data_points.extend([
                    row.agency_scope,
                    row.sanitary_sewer_pipe,
                    row.storm_drain_pipe,
                    row.storm_drain_assets,
                    row.system_age_history,
                    row.equipment_owned,
                    row.maintenance_practices,
                    row.sewage_incidents,
                    row.storm_incidents,
                ])
        else:  # MUNICIPAL_PUBLIC_BIDS
            for row in result.public_bid_rows:
                data_points.extend([
                    row.agency_municipality,
                    row.scope,
                    row.timeline_requirements,
                    row.contacts,
                ])

        # Count confidences
        for dp in data_points:
            if dp is None:
                not_found_count += 1
                continue

            total_data_points += 1
            value = self._get_value(dp)
            confidence = self._get_confidence(dp)

            if value == "NOT FOUND":
                not_found_count += 1
            elif confidence == "high":
                high_count += 1
            elif confidence == "low":
                low_count += 1
            else:
                medium_count += 1

        # Count unique sources
        source_urls = set()
        for row in result.systems_info_rows:
            for source in row.source_urls:
                if isinstance(source, SourceURL):
                    source_urls.add(source.url)
                elif isinstance(source, dict):
                    source_urls.add(source.get('url', ''))
                elif isinstance(source, str):
                    source_urls.add(source)

        for row in result.public_bid_rows:
            for source in row.source_urls:
                if isinstance(source, SourceURL):
                    source_urls.add(source.url)
                elif isinstance(source, dict):
                    source_urls.add(source.get('url', ''))
                elif isinstance(source, str):
                    source_urls.add(source)

        return {
            'total_data_points': total_data_points,
            'high_confidence_count': high_count,
            'medium_confidence_count': medium_count,
            'low_confidence_count': low_count,
            'not_found_count': not_found_count,
            'sources_count': len(source_urls),
        }

    # =========================================================================
    # DATA TABLE GENERATION
    # =========================================================================

    def _create_cell(
        self,
        value: str,
        confidence: str,
        source_url: str = "",
        has_citation: bool = False
    ) -> Dict[str, Any]:
        """Create a table cell with metadata."""
        return {
            'value': value,
            'confidence': confidence,
            'confidence_color': get_confidence_color(confidence),
            'has_citation': has_citation,
            'source_url': source_url,
        }

    def _format_systems_info_row(
        self,
        row: MunicipalSystemsInfoRow,
        row_id: str
    ) -> Dict[str, Any]:
        """Format a Municipal Systems Information row for the data table."""
        # Get primary source URL if available
        primary_source = ""
        if row.source_urls:
            first_source = row.source_urls[0]
            if isinstance(first_source, SourceURL):
                primary_source = first_source.url
            elif isinstance(first_source, dict):
                primary_source = first_source.get('url', '')
            elif isinstance(first_source, str):
                primary_source = first_source

        has_citations = len(row.verbatim_citations) > 0

        cells = [
            self._create_cell(row.municipality_city, "high"),
            self._create_cell(row.state, "high"),
            self._create_cell(row.relevant_agency, "high"),
            self._create_cell(
                self._get_value(row.agency_scope),
                self._get_confidence(row.agency_scope),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._get_value(row.sanitary_sewer_pipe),
                self._get_confidence(row.sanitary_sewer_pipe),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._get_value(row.storm_drain_pipe),
                self._get_confidence(row.storm_drain_pipe),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._get_value(row.storm_drain_assets),
                self._get_confidence(row.storm_drain_assets),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._get_value(row.system_age_history),
                self._get_confidence(row.system_age_history),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._get_value(row.equipment_owned),
                self._get_confidence(row.equipment_owned),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._get_value(row.maintenance_practices),
                self._get_confidence(row.maintenance_practices),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._get_value(row.sewage_incidents),
                self._get_confidence(row.sewage_incidents),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._get_value(row.storm_incidents),
                self._get_confidence(row.storm_incidents),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._format_sources_cell(row.source_urls),
                "high"
            ),
            self._create_cell(
                self._format_citations_cell(row.verbatim_citations),
                "high" if has_citations else "not_found"
            ),
            self._create_cell(row.notes_reconciliation or "N/A", "medium"),
        ]

        return {
            'id': row_id,
            'cells': cells,
        }

    def _format_public_bid_row(
        self,
        row: MunicipalPublicBidRow,
        row_id: str
    ) -> Dict[str, Any]:
        """Format a Municipal Public Bids row for the data table."""
        # Get primary source URL if available
        primary_source = ""
        if row.source_urls:
            first_source = row.source_urls[0]
            if isinstance(first_source, SourceURL):
                primary_source = first_source.url
            elif isinstance(first_source, dict):
                primary_source = first_source.get('url', '')
            elif isinstance(first_source, str):
                primary_source = first_source

        has_citations = len(row.verbatim_citations) > 0

        # Format keywords
        keywords = ", ".join(row.sewer_storm_keywords) if row.sewer_storm_keywords else "NOT FOUND"

        # Format status with key dates
        status_parts = [row.status or "NOT FOUND"]
        if row.key_dates:
            date_parts = [f"{k}: {v}" for k, v in row.key_dates.items() if v]
            if date_parts:
                status_parts.append("; ".join(date_parts))
        status_display = " | ".join(status_parts)

        cells = [
            self._create_cell(row.municipality_city, "high"),
            self._create_cell(row.state, "high"),
            self._create_cell(
                self._get_value(row.agency_municipality),
                self._get_confidence(row.agency_municipality),
                primary_source,
                has_citations
            ),
            self._create_cell(row.bid_contract_title or "NOT FOUND", "high"),
            self._create_cell(keywords, "high" if row.sewer_storm_keywords else "not_found"),
            self._create_cell(
                self._get_value(row.scope),
                self._get_confidence(row.scope),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._get_value(row.timeline_requirements),
                self._get_confidence(row.timeline_requirements),
                primary_source,
                has_citations
            ),
            self._create_cell(
                self._get_value(row.contacts),
                self._get_confidence(row.contacts),
                primary_source,
                has_citations
            ),
            self._create_cell(status_display, "high"),
            self._create_cell(
                self._format_sources_cell(row.source_urls),
                "high"
            ),
            self._create_cell(
                self._format_citations_cell(row.verbatim_citations),
                "high" if has_citations else "not_found"
            ),
            self._create_cell(row.notes_reconciliation or "N/A", "medium"),
        ]

        return {
            'id': row_id,
            'cells': cells,
        }

    def _format_sources_cell(self, sources: List[Any]) -> str:
        """Format source URLs for table cell display."""
        if not sources:
            return "NOT FOUND"

        urls = []
        for source in sources[:10]:  # Increased from 3 for more comprehensive display
            if isinstance(source, SourceURL):
                urls.append(source.url)
            elif isinstance(source, dict):
                urls.append(source.get('url', ''))
            elif isinstance(source, str):
                urls.append(source)

        result = "; ".join(urls)
        if len(sources) > 3:
            result += f" (+{len(sources) - 3} more)"

        return result

    def _format_citations_cell(self, citations: List[Any]) -> str:
        """Format citations for table cell display."""
        if not citations:
            return "NOT FOUND"

        texts = []
        for citation in citations[:10]:  # Increased from 2 for more comprehensive display
            if isinstance(citation, VerbatimCitation):
                texts.append(self._truncate_for_display(citation.text))
            elif isinstance(citation, dict):
                texts.append(self._truncate_for_display(citation.get('text', '')))
            elif isinstance(citation, str):
                texts.append(self._truncate_for_display(citation))

        result = " | ".join(texts)
        if len(citations) > 2:
            result += f" (+{len(citations) - 2} more)"

        return result

    def _generate_data_table(
        self,
        result: ExtractionResult,
        table_mode: TableMode
    ) -> Dict[str, Any]:
        """Generate the data table structure for UI."""
        if table_mode == TableMode.MUNICIPAL_SYSTEMS_INFO:
            headers = SYSTEMS_INFO_TABLE_HEADERS
            rows = [
                self._format_systems_info_row(row, f"row-{i}")
                for i, row in enumerate(result.systems_info_rows, 1)
            ]
        else:
            headers = PUBLIC_BIDS_TABLE_HEADERS
            rows = [
                self._format_public_bid_row(row, f"row-{i}")
                for i, row in enumerate(result.public_bid_rows, 1)
            ]

        return {
            'headers': headers,
            'rows': rows,
        }

    # =========================================================================
    # SOURCES LIST GENERATION
    # =========================================================================

    def _generate_sources_list(self, result: ExtractionResult) -> List[Dict[str, Any]]:
        """Generate the sources list for UI."""
        sources_map: Dict[str, Dict[str, Any]] = {}

        # Collect from systems info rows
        for row in result.systems_info_rows:
            for source in row.source_urls:
                source_data = self._extract_source_data(source)
                url = source_data['url']
                if url and url not in sources_map:
                    sources_map[url] = source_data
                    sources_map[url]['citations_count'] = 0

            # Count citations per source
            for citation in row.verbatim_citations:
                source_url = ""
                if isinstance(citation, VerbatimCitation):
                    source_url = citation.source_url
                elif isinstance(citation, dict):
                    source_url = citation.get('source_url', '')

                if source_url and source_url in sources_map:
                    sources_map[source_url]['citations_count'] += 1
                elif source_url:
                    # Citation references a source not in our map - add it
                    sources_map[source_url] = {
                        'url': source_url,
                        'title': 'Untitled',
                        'type': 'Unknown',
                        'citations_count': 1,
                    }

        # Collect from public bid rows
        for row in result.public_bid_rows:
            for source in row.source_urls:
                source_data = self._extract_source_data(source)
                url = source_data['url']
                if url and url not in sources_map:
                    sources_map[url] = source_data
                    sources_map[url]['citations_count'] = 0

            # Count citations per source
            for citation in row.verbatim_citations:
                source_url = ""
                if isinstance(citation, VerbatimCitation):
                    source_url = citation.source_url
                elif isinstance(citation, dict):
                    source_url = citation.get('source_url', '')

                if source_url and source_url in sources_map:
                    sources_map[source_url]['citations_count'] += 1
                elif source_url:
                    # Citation references a source not in our map - add it
                    sources_map[source_url] = {
                        'url': source_url,
                        'title': 'Untitled',
                        'type': 'Unknown',
                        'citations_count': 1,
                    }

        return list(sources_map.values())

    def _extract_source_data(self, source: Any) -> Dict[str, Any]:
        """Extract source data from various source types."""
        if isinstance(source, SourceURL):
            return {
                'url': source.url,
                'title': source.title or 'Untitled',
                'type': SOURCE_TYPE_DISPLAY.get(source.source_type, 'Unknown'),
                'citations_count': 0,
            }
        elif isinstance(source, dict):
            source_type = source.get('source_type', 'unknown')
            return {
                'url': source.get('url', ''),
                'title': source.get('title', 'Untitled'),
                'type': SOURCE_TYPE_DISPLAY.get(source_type, 'Unknown'),
                'citations_count': 0,
            }
        elif isinstance(source, str):
            return {
                'url': source,
                'title': 'Untitled',
                'type': 'Unknown',
                'citations_count': 0,
            }
        return {
            'url': '',
            'title': 'Unknown',
            'type': 'Unknown',
            'citations_count': 0,
        }

    # =========================================================================
    # DOWNLOADS LIST GENERATION
    # =========================================================================

    def _generate_downloads_list(self, result: ExtractionResult) -> List[Dict[str, Any]]:
        """Generate the downloads list for UI."""
        downloads = []

        # From downloaded_documents in ExtractionResult
        for doc in result.downloaded_documents:
            if isinstance(doc, dict):
                status = doc.get('status', 'available')
                downloads.append({
                    'title': doc.get('title', 'Untitled Document'),
                    'url': doc.get('url', ''),
                    'file_type': doc.get('file_type', 'pdf'),
                    'status': DOWNLOAD_STATUS_DISPLAY.get(status, 'Available'),
                    'local_path': doc.get('local_path', ''),
                })

        # From public bid rows downloadable documents
        for row in result.public_bid_rows:
            if not hasattr(row, 'downloadable_documents') or not row.downloadable_documents:
                continue
            for doc in row.downloadable_documents:
                if isinstance(doc, dict):
                    status = doc.get('status', 'available')
                    downloads.append({
                        'title': doc.get('title', 'Untitled Document'),
                        'url': doc.get('url', ''),
                        'file_type': doc.get('file_type', 'pdf'),
                        'status': DOWNLOAD_STATUS_DISPLAY.get(status, 'Available'),
                        'local_path': doc.get('local_path', ''),
                    })

        # Remove duplicates by URL
        seen_urls = set()
        unique_downloads = []
        for dl in downloads:
            if dl['url'] not in seen_urls:
                seen_urls.add(dl['url'])
                unique_downloads.append(dl)

        return unique_downloads

    # =========================================================================
    # AGENT ACTIVITY FEED GENERATION
    # =========================================================================

    def _format_agent_activity(
        self,
        events: List[AgentActivityEvent]
    ) -> List[Dict[str, Any]]:
        """Format agent activity events for UI."""
        return [
            {
                'agent_id': event.agent_id,
                'agent_name': event.agent_name,
                'status': event.status,
                'message': event.message,
                'timestamp': self._format_datetime(event.timestamp),
            }
            for event in events
        ]

    # =========================================================================
    # STATUS DETERMINATION
    # =========================================================================

    def _determine_status(self, result: ExtractionResult) -> str:
        """Determine overall session status."""
        # Check if we have any data
        has_data = bool(result.systems_info_rows or result.public_bid_rows)

        if not has_data:
            return "failed"

        # Check for data gaps
        if result.data_gaps and len(result.data_gaps) > 3:
            return "partial"

        # Check for conflicts
        if result.conflicts_detected and len(result.conflicts_detected) > 2:
            return "partial"

        return "completed"

    # =========================================================================
    # MAIN PROCESS METHOD
    # =========================================================================

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process UI data packaging request.

        Expected input_data:
        - extraction_result: ExtractionResult object (or dict representation)
        - session_id: str
        - include_raw_data: bool (optional, default False)
        - agent_events: List[AgentActivityEvent] (optional)

        Returns AgentResponse with packaged UI data.
        """
        start_time = time.time()

        try:
            self.emit_event("processing", "Packaging data for UI display")

            # Extract inputs
            extraction_result = request.input_data.get('extraction_result')
            session_id = request.input_data.get('session_id', 'unknown')
            include_raw_data = request.input_data.get('include_raw_data', False)
            agent_events = request.input_data.get('agent_events', [])

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

            # Convert if dict
            if isinstance(extraction_result, dict):
                extraction_result = self._dict_to_extraction_result(extraction_result)
            elif not isinstance(extraction_result, ExtractionResult):
                return AgentResponse(
                    agent_id=self.AGENT_ID,
                    task=request.task,
                    success=False,
                    output_data={},
                    errors=[f"extraction_result must be ExtractionResult or dict, got {type(extraction_result).__name__}"],
                    processing_time_seconds=time.time() - start_time
                )

            table_mode = extraction_result.table_mode
            municipality = extraction_result.municipality
            status = self._determine_status(extraction_result)

            self.emit_event("processing", "Generating session metadata")

            # Build session info
            session_info = {
                'id': session_id,
                'municipality': municipality.city,
                'state': municipality.state,
                'table_mode': table_mode.value,
                'status': status,
                'started_at': self._format_datetime(extraction_result.started_at),
                'completed_at': self._format_datetime(extraction_result.completed_at),
            }

            self.emit_event("processing", "Generating summary statistics")

            # Generate summary
            summary = self._generate_summary(extraction_result, table_mode)

            self.emit_event("processing", "Formatting data table")

            # Generate data table
            data_table = self._generate_data_table(extraction_result, table_mode)

            self.emit_event("processing", "Collecting sources")

            # Generate sources list
            sources = self._generate_sources_list(extraction_result)

            self.emit_event("processing", "Collecting downloads")

            # Generate downloads list
            downloads = self._generate_downloads_list(extraction_result)

            # Format agent activity
            agent_activity = self._format_agent_activity(agent_events)

            # Generate export URLs
            export_urls = {
                'excel': get_export_url('excel', session_id),
                'markdown': get_export_url('markdown', session_id),
            }

            # Build final output
            output = {
                'session': session_info,
                'summary': summary,
                'data_table': data_table,
                'sources': sources,
                'downloads': downloads,
                'agent_activity': agent_activity,
                'export_urls': export_urls,
                'data_gaps': self._serialize_data_gaps(extraction_result.data_gaps),
                'warnings': self._serialize_conflicts(extraction_result.conflicts_detected),
            }

            # Include raw data if requested
            if include_raw_data:
                output['raw_extraction_result'] = self._serialize_extraction_result(
                    extraction_result
                )

            elapsed = time.time() - start_time

            self.emit_event(
                "completed",
                f"Packaged {len(data_table['rows'])} rows for UI display",
                is_completed=True
            )

            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=True,
                output_data=output,
                processing_time_seconds=elapsed
            )

        except Exception as e:
            logger.exception(f"PR-3 unexpected error: {e}")
            self.emit_event("failed", f"Packaging error: {str(e)[:100]}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:200]}"],
                processing_time_seconds=time.time() - start_time
            )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _dict_to_extraction_result(self, data: dict) -> ExtractionResult:
        """Convert a dict representation to ExtractionResult."""
        # Get municipality
        muni_data = data.get('municipality', {})
        if isinstance(muni_data, Municipality):
            municipality = muni_data
        else:
            municipality = Municipality(
                city=muni_data.get('city', 'Unknown'),
                state=muni_data.get('state', 'Unknown'),
                county=muni_data.get('county'),
                region=muni_data.get('region'),
            )

        # Get table mode
        mode_val = data.get('table_mode', TableMode.MUNICIPAL_SYSTEMS_INFO)
        if isinstance(mode_val, str):
            try:
                table_mode = TableMode(mode_val)
            except ValueError:
                table_mode = TableMode.MUNICIPAL_SYSTEMS_INFO
        elif isinstance(mode_val, TableMode):
            table_mode = mode_val
        else:
            table_mode = TableMode.MUNICIPAL_SYSTEMS_INFO

        # Get preflight
        preflight_data = data.get('preflight', {})
        if isinstance(preflight_data, PreflightResult):
            preflight = preflight_data
        else:
            preflight = PreflightResult(
                municipality=municipality,
                table_mode=table_mode,
                status=PreflightStatus.PASS,
            )

        # Build result
        result = ExtractionResult(
            municipality=municipality,
            table_mode=table_mode,
            preflight=preflight,
            systems_info_rows=data.get('systems_info_rows', []),
            public_bid_rows=data.get('public_bid_rows', []),
            total_sources_searched=data.get('total_sources_searched', 0),
            total_data_points_extracted=data.get('total_data_points_extracted', 0),
            data_gaps=data.get('data_gaps', []),
            conflicts_detected=data.get('conflicts_detected', []),
            downloaded_documents=data.get('downloaded_documents', []),
        )

        if data.get('started_at'):
            result.started_at = data['started_at']
        if data.get('completed_at'):
            result.completed_at = data['completed_at']

        return result

    def _serialize_extraction_result(self, result: ExtractionResult) -> Dict[str, Any]:
        """Serialize ExtractionResult to dict for raw data output."""
        return {
            'municipality': {
                'city': result.municipality.city,
                'state': result.municipality.state,
                'county': result.municipality.county,
                'region': result.municipality.region,
            },
            'table_mode': result.table_mode.value,
            'total_sources_searched': result.total_sources_searched,
            'total_data_points_extracted': result.total_data_points_extracted,
            'data_gaps': result.data_gaps,
            'conflicts_detected': result.conflicts_detected,
            'systems_info_rows_count': len(result.systems_info_rows),
            'public_bid_rows_count': len(result.public_bid_rows),
            'downloaded_documents_count': len(result.downloaded_documents),
            'started_at': self._format_datetime(result.started_at),
            'completed_at': self._format_datetime(result.completed_at),
        }

    def _serialize_data_gaps(self, data_gaps: Optional[List[Any]]) -> List[str]:
        """Safely serialize data_gaps to JSON-compatible list of strings.

        Args:
            data_gaps: List of data gaps which may contain various types

        Returns:
            List of string representations safe for JSON serialization
        """
        if not data_gaps:
            return []

        result = []
        for gap in data_gaps:
            if gap is None:
                continue
            elif isinstance(gap, str):
                result.append(gap)
            elif isinstance(gap, dict):
                # Convert dict to readable string
                field = gap.get('field', 'unknown')
                reason = gap.get('reason', gap.get('message', 'Not found'))
                result.append(f"{field}: {reason}")
            else:
                # Fallback: convert to string
                try:
                    result.append(str(gap))
                except (ValueError, TypeError):
                    result.append("Unknown data gap")
        return result

    def _serialize_conflicts(self, conflicts: Optional[List[Any]]) -> List[str]:
        """Safely serialize conflicts to JSON-compatible list of warning strings.

        Args:
            conflicts: List of conflict dictionaries or objects

        Returns:
            List of warning strings safe for JSON serialization
        """
        if not conflicts:
            return []

        result = []
        for conflict in conflicts:
            if conflict is None:
                continue
            elif isinstance(conflict, str):
                result.append(f"Conflict detected: {conflict}")
            elif isinstance(conflict, dict):
                field = conflict.get('field', 'unknown')
                result.append(f"Conflict detected: {field}")
            else:
                # Fallback: convert to string
                try:
                    result.append(f"Conflict detected: {str(conflict)}")
                except (ValueError, TypeError):
                    result.append("Conflict detected: Unknown")
        return result

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate UI packager output."""
        errors = []

        # Check required top-level fields
        required_fields = [
            'session', 'summary', 'data_table', 'sources',
            'downloads', 'agent_activity', 'export_urls',
            'data_gaps', 'warnings'
        ]

        for field in required_fields:
            if field not in output:
                errors.append(f"Missing '{field}' in output")

        # Validate session structure
        if 'session' in output:
            session = output['session']
            session_fields = ['id', 'municipality', 'state', 'table_mode', 'status']
            for f in session_fields:
                if f not in session:
                    errors.append(f"Missing '{f}' in session")

        # Validate summary structure
        if 'summary' in output:
            summary = output['summary']
            summary_fields = [
                'total_data_points', 'high_confidence_count',
                'medium_confidence_count', 'low_confidence_count',
                'not_found_count', 'sources_count'
            ]
            for f in summary_fields:
                if f not in summary:
                    errors.append(f"Missing '{f}' in summary")

        # Validate data_table structure
        if 'data_table' in output:
            data_table = output['data_table']
            if 'headers' not in data_table:
                errors.append("Missing 'headers' in data_table")
            if 'rows' not in data_table:
                errors.append("Missing 'rows' in data_table")

        # Validate export_urls
        if 'export_urls' in output:
            export_urls = output['export_urls']
            if 'excel' not in export_urls:
                errors.append("Missing 'excel' in export_urls")
            if 'markdown' not in export_urls:
                errors.append("Missing 'markdown' in export_urls")

        return errors
