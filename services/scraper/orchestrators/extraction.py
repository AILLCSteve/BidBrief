"""
Extraction Orchestrator (EX-O)

Orchestrates the complete extraction pipeline by dispatching
EX-1 through EX-6 agents based on table mode and aggregating results.

Pipeline Logic:
- Municipal Systems Info mode: Run EX-1, EX-2, EX-3, EX-4 (can run in parallel)
- Municipal Public Bids mode: Run EX-5 first, then EX-6 with EX-5's documents
- Both mode: Run all agents

Responsibilities:
- Dispatch agents based on table mode
- Handle parallel execution for systems info agents
- Sequential execution for bid pipeline (EX-5 -> EX-6)
- Error handling and retry logic for transient failures
- Progress tracking and event emission
- Aggregation of all results into ExtractionResult
- Citation validation across all data points
- Conflict detection and documentation
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional, Callable, Type, List
from dataclasses import dataclass, field
from datetime import datetime

from services.scraper.config import get_config, ScraperConfig
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    ExtractionResult,
    PreflightResult,
    Municipality,
    TableMode,
    MunicipalSystemsInfoRow,
    MunicipalPublicBidRow,
    ExtractedDataPoint,
    SourceURL,
    VerbatimCitation,
    ConfidenceRating,
    AgentActivityEvent
)
from services.scraper.agents.base import BaseAgent
from services.scraper.agents.extraction import (
    InfrastructureExtractorAgent,
    EquipmentExtractorAgent,
    MaintenanceExtractorAgent,
    IncidentExtractorAgent,
    BidExtractorAgent,
    DocumentDownloaderAgent
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineStage:
    """Configuration for a pipeline stage."""
    agent_id: str
    agent_name: str
    agent_class: Type[BaseAgent]
    max_retries: int = 2
    retry_delay: float = 2.0
    required: bool = True


@dataclass
class PipelineResult:
    """Result of a single pipeline stage."""
    stage_id: str
    success: bool
    response: Optional[AgentResponse] = None
    error: Optional[str] = None
    retries_used: int = 0
    duration_seconds: float = 0.0


class ExtractionOrchestrator:
    """
    Orchestrates the extraction pipeline.

    Dispatches EX-1 through EX-6 based on table mode, handles parallel
    and sequential execution, and aggregates results into ExtractionResult.
    """

    ORCHESTRATOR_ID = "ex-o"
    ORCHESTRATOR_NAME = "Extraction Orchestrator"
    ORCHESTRATOR_VERSION = "1.0.0"

    # Systems Info stages (EX-1 through EX-4)
    SYSTEMS_INFO_STAGES = [
        PipelineStage("ex-1", "Infrastructure Extractor", InfrastructureExtractorAgent, required=True),
        PipelineStage("ex-2", "Equipment Extractor", EquipmentExtractorAgent, required=False),
        PipelineStage("ex-3", "Maintenance Extractor", MaintenanceExtractorAgent, required=False),
        PipelineStage("ex-4", "Incident Extractor", IncidentExtractorAgent, required=True),
    ]

    # Bid stages (EX-5 and EX-6)
    BID_STAGES = [
        PipelineStage("ex-5", "Bid Extractor", BidExtractorAgent, required=True),
        PipelineStage("ex-6", "Document Downloader", DocumentDownloaderAgent, required=False),
    ]

    def __init__(
        self,
        config: Optional[ScraperConfig] = None,
        event_callback: Optional[Callable[[AgentActivityEvent], None]] = None
    ):
        """
        Initialize the Extraction Orchestrator.

        Args:
            config: Optional scraper configuration
            event_callback: Optional callback for progress events
        """
        self.config = config or get_config()
        self.event_callback = event_callback

        # Track pipeline state
        self.results: Dict[str, PipelineResult] = {}
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self._cancelled = False
        self._session_id: Optional[str] = None

    def emit_event(self, message: str, stage_id: Optional[str] = None):
        """Emit a progress event."""
        if self.event_callback:
            event = AgentActivityEvent(
                agent_id=stage_id or self.ORCHESTRATOR_ID,
                agent_name=self.ORCHESTRATOR_NAME,
                status=message,
                message=message,
                timestamp=datetime.now()
            )
            self.event_callback(event)
        logger.info(f"EX-O: {message}")

    def cancel(self):
        """Request cancellation of the pipeline."""
        self._cancelled = True
        logger.info("EX-O: Cancellation requested")

    async def run(
        self,
        municipality: Municipality,
        table_mode: TableMode,
        preflight_result: PreflightResult
    ) -> ExtractionResult:
        """
        Run the extraction pipeline based on table mode.

        Args:
            municipality: Municipality from PF-1
            table_mode: Target table type
            preflight_result: Results from PF-O

        Returns:
            ExtractionResult with aggregated extraction data
        """
        self.started_at = datetime.now()
        self._cancelled = False
        self.results = {}
        self._session_id = f"ex-{uuid.uuid4().hex[:8]}"

        self.emit_event(f"Starting extraction for: {municipality.full_name}")

        try:
            # Initialize result tracking
            systems_info_results: Dict[str, PipelineResult] = {}
            bid_results: Dict[str, PipelineResult] = {}

            # Determine which pipelines to run based on table mode
            # NOTE: TableMode enum has MUNICIPAL_SYSTEMS_INFO and MUNICIPAL_PUBLIC_BIDS
            # "Both" mode can be requested via string value containing "both"
            table_mode_str = str(table_mode.value).lower()

            if "both" in table_mode_str:
                # Explicit "both" mode - run all agents
                run_systems_info = True
                run_bids = True
            elif table_mode == TableMode.MUNICIPAL_SYSTEMS_INFO:
                run_systems_info = True
                run_bids = False
            elif table_mode == TableMode.MUNICIPAL_PUBLIC_BIDS:
                run_systems_info = False
                run_bids = True
            else:
                # Unknown mode - default to systems info
                logger.warning(f"Unknown table mode {table_mode}, defaulting to systems info")
                run_systems_info = True
                run_bids = False

            # Run Systems Info extraction (EX-1 through EX-4) - can run in parallel
            if run_systems_info:
                if self._cancelled:
                    return self._create_cancelled_result(municipality, table_mode, preflight_result)

                self.emit_event("Running Systems Info extraction (EX-1 through EX-4)...")
                systems_info_results = await self._run_systems_info_extraction(
                    municipality=municipality,
                    preflight_result=preflight_result
                )
                self.results.update(systems_info_results)

            # Run Bid extraction (EX-5 and EX-6) - sequential (EX-6 depends on EX-5)
            if run_bids:
                if self._cancelled:
                    return self._create_cancelled_result(municipality, table_mode, preflight_result)

                self.emit_event("Running Bid extraction (EX-5 and EX-6)...")
                bid_results = await self._run_bid_extraction(
                    municipality=municipality,
                    preflight_result=preflight_result
                )
                self.results.update(bid_results)

            self.completed_at = datetime.now()

            # Aggregate results
            return self._aggregate_results(
                municipality=municipality,
                table_mode=table_mode,
                preflight_result=preflight_result,
                systems_info_results=systems_info_results,
                bid_results=bid_results
            )

        except Exception as e:
            logger.exception(f"EX-O pipeline error: {e}")
            self.completed_at = datetime.now()
            return self._create_failed_result(
                municipality=municipality,
                table_mode=table_mode,
                preflight_result=preflight_result,
                error=f"Pipeline error: {str(e)}"
            )

    async def _run_systems_info_extraction(
        self,
        municipality: Municipality,
        preflight_result: PreflightResult
    ) -> Dict[str, PipelineResult]:
        """
        Run EX-1 through EX-4 for systems info extraction.

        These agents can run in parallel since they extract independent data.

        Args:
            municipality: Target municipality
            preflight_result: Pre-flight results with source map and terminology

        Returns:
            Dict mapping agent IDs to PipelineResults
        """
        results: Dict[str, PipelineResult] = {}

        # Prepare input data for all agents
        input_data = {
            'municipality_name': municipality.city,
            'state': municipality.state,
            'source_map': self._extract_source_map(preflight_result),
            'terminology': self._extract_terminology(preflight_result)
        }

        # Create tasks for parallel execution
        tasks = []
        for stage in self.SYSTEMS_INFO_STAGES:
            if self._cancelled:
                break
            task = self._run_stage(stage=stage, input_data=input_data)
            tasks.append((stage.agent_id, task))

        # Run all stages in parallel
        self.emit_event("Executing EX-1, EX-2, EX-3, EX-4 in parallel...")

        # Gather results
        if tasks:
            stage_results = await asyncio.gather(
                *[task for _, task in tasks],
                return_exceptions=True
            )

            for i, (agent_id, _) in enumerate(tasks):
                result = stage_results[i]
                if isinstance(result, Exception):
                    results[agent_id] = PipelineResult(
                        stage_id=agent_id,
                        success=False,
                        error=str(result)
                    )
                elif isinstance(result, PipelineResult):
                    results[agent_id] = result
                else:
                    # Unexpected return type - wrap in failure result
                    results[agent_id] = PipelineResult(
                        stage_id=agent_id,
                        success=False,
                        error=f"Unexpected return type: {type(result).__name__}"
                    )

        return results

    async def _run_bid_extraction(
        self,
        municipality: Municipality,
        preflight_result: PreflightResult
    ) -> Dict[str, PipelineResult]:
        """
        Run EX-5 and EX-6 for bid data extraction.

        EX-6 depends on EX-5's results, so they must run sequentially.

        Args:
            municipality: Target municipality
            preflight_result: Pre-flight results with source map and terminology

        Returns:
            Dict mapping agent IDs to PipelineResults
        """
        results: Dict[str, PipelineResult] = {}

        # Prepare input data for EX-5
        input_data = {
            'municipality_name': municipality.city,
            'state': municipality.state,
            'source_map': self._extract_source_map(preflight_result),
            'terminology': self._extract_terminology(preflight_result)
        }

        # Run EX-5 (Bid Extractor) first
        ex5_stage = self.BID_STAGES[0]
        self.emit_event(f"Running {ex5_stage.agent_name}...", ex5_stage.agent_id)

        ex5_result = await self._run_stage(stage=ex5_stage, input_data=input_data)
        results[ex5_stage.agent_id] = ex5_result

        if self._cancelled:
            return results

        # Run EX-6 (Document Downloader) with EX-5's documents
        if ex5_result.success and ex5_result.response:
            ex6_stage = self.BID_STAGES[1]

            # Extract downloadable documents from EX-5
            downloadable_documents = self._extract_downloadable_documents(
                ex5_result.response.output_data
            )

            if downloadable_documents:
                self.emit_event(
                    f"Running {ex6_stage.agent_name} for {len(downloadable_documents)} documents...",
                    ex6_stage.agent_id
                )

                ex6_input = {
                    'session_id': self._session_id,
                    'documents': downloadable_documents,
                    'max_file_size_mb': 50,
                    'timeout_seconds': 30
                }

                ex6_result = await self._run_stage(stage=ex6_stage, input_data=ex6_input)
                results[ex6_stage.agent_id] = ex6_result
            else:
                self.emit_event("No downloadable documents found - skipping EX-6", ex6_stage.agent_id)
                results[ex6_stage.agent_id] = PipelineResult(
                    stage_id=ex6_stage.agent_id,
                    success=True,
                    response=AgentResponse(
                        agent_id=ex6_stage.agent_id,
                        task="skip",
                        success=True,
                        output_data={
                            'downloads': [],
                            'summary': {
                                'total_documents': 0,
                                'successful': 0,
                                'failed': 0,
                                'skipped': 0,
                                'total_size_bytes': 0
                            },
                            'download_directory': ''
                        }
                    ),
                    error=None
                )
        else:
            # EX-5 failed, skip EX-6
            ex6_stage = self.BID_STAGES[1]
            results[ex6_stage.agent_id] = PipelineResult(
                stage_id=ex6_stage.agent_id,
                success=False,
                error="Skipped - EX-5 (Bid Extractor) failed"
            )

        return results

    async def _run_stage(
        self,
        stage: PipelineStage,
        input_data: Dict[str, Any]
    ) -> PipelineResult:
        """
        Run a single pipeline stage with retry logic.
        """
        start_time = time.time()
        retries = 0
        last_error = None

        self.emit_event(f"Running {stage.agent_name}...", stage.agent_id)

        while retries <= stage.max_retries:
            agent = None
            try:
                # Create agent instance
                agent = stage.agent_class(
                    config=self.config,
                    event_callback=self.event_callback
                )

                # Create request
                request = AgentRequest(
                    agent_id=stage.agent_id,
                    task=f"{stage.agent_id}-{datetime.now().isoformat()}",
                    input_data=input_data
                )

                # Run agent
                response = await agent.process(request)

                duration = time.time() - start_time

                if response.success:
                    self.emit_event(f"{stage.agent_name} completed successfully", stage.agent_id)
                    result = PipelineResult(
                        stage_id=stage.agent_id,
                        success=True,
                        response=response,
                        retries_used=retries,
                        duration_seconds=duration
                    )
                    return result
                else:
                    last_error = "; ".join(response.errors) if response.errors else "Unknown error"
                    logger.warning(f"{stage.agent_id} failed: {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.error(f"{stage.agent_id} exception: {e}")
            finally:
                # CRITICAL: Always cleanup agent resources to prevent leaks
                if agent:
                    try:
                        await agent.cleanup()
                    except Exception as cleanup_error:
                        logger.error(f"Cleanup error in {stage.agent_id}: {cleanup_error}")

            # Retry logic
            retries += 1
            if retries <= stage.max_retries:
                self.emit_event(f"{stage.agent_name} retry {retries}/{stage.max_retries}...", stage.agent_id)
                await asyncio.sleep(stage.retry_delay)

        # All retries exhausted
        duration = time.time() - start_time
        self.emit_event(f"{stage.agent_name} failed after {retries} retries", stage.agent_id)

        result = PipelineResult(
            stage_id=stage.agent_id,
            success=False,
            error=last_error,
            retries_used=retries,
            duration_seconds=duration
        )
        return result

    def _extract_source_map(self, preflight_result: PreflightResult) -> Optional[Dict[str, Any]]:
        """Extract source map dict from preflight result."""
        if not preflight_result.source_map:
            return None

        source_map = preflight_result.source_map

        def source_to_dict(source: Optional[SourceURL]) -> Optional[Dict[str, Any]]:
            if not source:
                return None
            return {
                'url': source.url,
                'title': source.title,
                'source_type': source.source_type
            }

        return {
            'official_website': source_to_dict(source_map.official_website),
            'public_works_page': source_to_dict(source_map.public_works_page),
            'sewer_utility_page': source_to_dict(source_map.sewer_utility_page),
            'stormwater_page': source_to_dict(source_map.stormwater_page),
            'procurement_page': source_to_dict(source_map.procurement_page),
            'gis_portal': source_to_dict(source_map.gis_portal),
            'cip_documents': [source_to_dict(s) for s in source_map.cip_documents],
            'compliance_sources': [source_to_dict(s) for s in source_map.compliance_sources]
        }

    def _extract_terminology(self, preflight_result: PreflightResult) -> Optional[Dict[str, Any]]:
        """Extract terminology dict from preflight result."""
        if not preflight_result.terminology:
            return None

        terminology = preflight_result.terminology
        return {
            'sanitary_terms': terminology.sanitary_terms,
            'storm_terms': terminology.storm_terms,
            'lift_station_terms': terminology.lift_station_terms,
            'bid_portal_keywords': terminology.bid_portal_keywords
        }

    def _extract_downloadable_documents(self, ex5_output: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract downloadable documents from EX-5 output."""
        documents = []

        bids = ex5_output.get('bids', [])
        for bid in bids:
            bid_title = bid.get('bid_title', 'Unknown')
            docs = bid.get('downloadable_documents', [])

            if isinstance(docs, list):
                for doc in docs:
                    if isinstance(doc, dict) and doc.get('url'):
                        documents.append({
                            'title': doc.get('title', 'Unknown Document'),
                            'url': doc.get('url'),
                            'file_type': doc.get('file_type', 'Unknown'),
                            'bid_title': bid_title
                        })

        return documents

    def _aggregate_results(
        self,
        municipality: Municipality,
        table_mode: TableMode,
        preflight_result: PreflightResult,
        systems_info_results: Dict[str, PipelineResult],
        bid_results: Dict[str, PipelineResult]
    ) -> ExtractionResult:
        """Aggregate all extraction results into ExtractionResult."""

        # Aggregate systems info rows
        systems_info_rows = []
        if systems_info_results:
            rows = self._aggregate_systems_info(municipality, systems_info_results)
            systems_info_rows.extend(rows)

        # Aggregate bid rows
        public_bid_rows = []
        downloaded_documents = []
        if bid_results:
            rows, docs = self._aggregate_bids(municipality, bid_results)
            public_bid_rows.extend(rows)
            downloaded_documents.extend(docs)

        # Calculate statistics
        total_sources_searched = 0
        total_data_points_extracted = 0

        for result in list(systems_info_results.values()) + list(bid_results.values()):
            if result.success and result.response:
                output = result.response.output_data
                sources = output.get('sources_checked', [])
                if isinstance(sources, list):
                    total_sources_searched += len(sources)

        # Count data points from rows
        for row in systems_info_rows:
            for attr_name in ['agency_scope', 'sanitary_sewer_pipe', 'storm_drain_pipe',
                              'storm_drain_assets', 'system_age_history', 'equipment_owned',
                              'maintenance_practices', 'sewage_incidents', 'storm_incidents']:
                dp = getattr(row, attr_name, None)
                if dp and isinstance(dp, ExtractedDataPoint) and dp.value != 'NOT FOUND':
                    total_data_points_extracted += 1

        for row in public_bid_rows:
            # Count non-empty fields
            total_data_points_extracted += 1  # Each bid row counts as a data point

        # Validate citations and detect conflicts
        data_gaps = self._validate_citations(systems_info_results, bid_results)
        conflicts_detected = self._resolve_conflicts(systems_info_results, bid_results)

        self.emit_event(
            f"Extraction complete: {len(systems_info_rows)} system rows, "
            f"{len(public_bid_rows)} bid rows, {total_data_points_extracted} data points"
        )

        return ExtractionResult(
            municipality=municipality,
            table_mode=table_mode,
            preflight=preflight_result,
            systems_info_rows=systems_info_rows,
            public_bid_rows=public_bid_rows,
            total_sources_searched=total_sources_searched,
            total_data_points_extracted=total_data_points_extracted,
            data_gaps=data_gaps,
            conflicts_detected=conflicts_detected,
            started_at=self.started_at or datetime.now(),
            completed_at=self.completed_at or datetime.now(),
            downloaded_documents=downloaded_documents
        )

    def _aggregate_systems_info(
        self,
        municipality: Municipality,
        results: Dict[str, PipelineResult]
    ) -> List[MunicipalSystemsInfoRow]:
        """
        Aggregate extraction results from EX-1 through EX-4 into MunicipalSystemsInfoRow.

        Column mapping:
        - EX-1: columns 2 (sanitary_sewer_pipe), 3 (storm_drain_pipe)
        - EX-2: column 6 (equipment_owned)
        - EX-3: column 7 (maintenance_practices)
        - EX-4: columns 8 (sewage_incidents), 9 (storm_incidents)
        """
        source_urls: List[SourceURL] = []
        verbatim_citations: List[VerbatimCitation] = []

        # Extract data from each agent's output
        def get_data_point(
            output: Optional[Dict[str, Any]],
            key: str,
            field_name: str
        ) -> ExtractedDataPoint:
            """Create ExtractedDataPoint from agent output."""
            if not output:
                return ExtractedDataPoint(
                    field_name=field_name,
                    value='NOT FOUND'
                )

            data = output.get(key, {})
            if not isinstance(data, dict):
                return ExtractedDataPoint(
                    field_name=field_name,
                    value=str(data) if data else 'NOT FOUND'
                )

            # Handle nested structure (e.g., sanitary_sewer_pipe with total_feet, etc.)
            value_parts = []
            if data.get('total_feet') and data.get('total_feet') != 'NOT FOUND':
                value_parts.append(f"Total: {data['total_feet']} ft")
            if data.get('pipe_sizes') and data.get('pipe_sizes') != 'NOT FOUND':
                value_parts.append(f"Sizes: {data['pipe_sizes']}")
            if data.get('pipe_types') and data.get('pipe_types') != 'NOT FOUND':
                value_parts.append(f"Types: {data['pipe_types']}")

            # Handle flat value or description
            if not value_parts:
                if data.get('value'):
                    value_parts.append(str(data['value']))
                elif data.get('description'):
                    value_parts.append(str(data['description']))
                elif data.get('summary'):
                    value_parts.append(str(data['summary']))

            value = "; ".join(value_parts) if value_parts else 'NOT FOUND'

            # Map confidence string to enum
            conf_str = data.get('confidence', 'MEDIUM')
            confidence_map = {
                'HIGH': ConfidenceRating.HIGH,
                'MEDIUM': ConfidenceRating.MEDIUM,
                'LOW': ConfidenceRating.LOW
            }
            confidence = confidence_map.get(conf_str, ConfidenceRating.MEDIUM)

            return ExtractedDataPoint(
                field_name=field_name,
                value=value,
                raw_source_value=data.get('raw_data_found'),
                conversion_applied=data.get('conversion_applied'),
                source_url=data.get('source_url', ''),
                verbatim_quote=data.get('verbatim_citation', ''),
                confidence=confidence,
                confidence_rationale=data.get('confidence_rationale', '')
            )

        # Get outputs from each agent
        ex1_output = results.get('ex-1', PipelineResult(stage_id='ex-1', success=False))
        ex2_output = results.get('ex-2', PipelineResult(stage_id='ex-2', success=False))
        ex3_output = results.get('ex-3', PipelineResult(stage_id='ex-3', success=False))
        ex4_output = results.get('ex-4', PipelineResult(stage_id='ex-4', success=False))

        ex1_data = ex1_output.response.output_data if ex1_output.success and ex1_output.response else {}
        ex2_data = ex2_output.response.output_data if ex2_output.success and ex2_output.response else {}
        ex3_data = ex3_output.response.output_data if ex3_output.success and ex3_output.response else {}
        ex4_data = ex4_output.response.output_data if ex4_output.success and ex4_output.response else {}

        # Collect source URLs and citations from all agents
        for data in [ex1_data, ex2_data, ex3_data, ex4_data]:
            sources = data.get('sources_checked', [])
            if isinstance(sources, list):
                for source in sources:
                    if isinstance(source, dict) and source.get('url'):
                        try:
                            source_urls.append(SourceURL(
                                url=source.get('url', ''),
                                title=source.get('title', 'Unknown'),
                                source_type=source.get('source_type', 'web')
                            ))
                        except ValueError:
                            pass  # Skip invalid sources

        # Build the row
        # Determine relevant agency from preflight jurisdiction info
        relevant_agency = "City"  # Default
        if hasattr(self, 'preflight_result') and self.preflight_result:
            jurisdiction = getattr(self.preflight_result, 'jurisdiction', None)
            if jurisdiction:
                relevant_agency = getattr(jurisdiction, 'sanitary_sewer_owner', 'City')

        row = MunicipalSystemsInfoRow(
            municipality_city=municipality.city,
            state=municipality.state,
            relevant_agency=relevant_agency,
            # Column 1: agency_scope - would come from pre-flight data
            agency_scope=ExtractedDataPoint(
                field_name='agency_scope',
                value='Municipal sewer and storm drain systems'
            ),
            # EX-1: columns 2, 3
            sanitary_sewer_pipe=get_data_point(ex1_data, 'sanitary_sewer_pipe', 'sanitary_sewer_pipe'),
            storm_drain_pipe=get_data_point(ex1_data, 'storm_drain_pipe', 'storm_drain_pipe'),
            # Column 4: storm_drain_assets - from EX-1 if available
            storm_drain_assets=get_data_point(ex1_data, 'storm_drain_assets', 'storm_drain_assets'),
            # Column 5: system_age_history - from EX-1 if available
            system_age_history=get_data_point(ex1_data, 'system_age_history', 'system_age_history'),
            # EX-2: column 6
            equipment_owned=get_data_point(ex2_data, 'equipment_owned', 'equipment_owned'),
            # EX-3: column 7
            maintenance_practices=get_data_point(ex3_data, 'maintenance_practices', 'maintenance_practices'),
            # EX-4: columns 8, 9 (PRIORITY)
            sewage_incidents=get_data_point(ex4_data, 'sewage_incidents', 'sewage_incidents'),
            storm_incidents=get_data_point(ex4_data, 'storm_incidents', 'storm_incidents'),
            # Source tracking
            source_urls=source_urls,
            verbatim_citations=verbatim_citations,
            notes_reconciliation=self._generate_reconciliation_notes(results),
            extracted_at=datetime.now(),
            extraction_session_id=self._session_id
        )

        return [row]

    def _aggregate_bids(
        self,
        municipality: Municipality,
        results: Dict[str, PipelineResult]
    ) -> tuple:
        """
        Aggregate bid extraction results from EX-5 and EX-6 into MunicipalPublicBidRow objects.

        Returns:
            Tuple of (List[MunicipalPublicBidRow], List[Dict] downloaded_documents)
        """
        rows: List[MunicipalPublicBidRow] = []
        downloaded_documents: List[Dict[str, str]] = []

        ex5_result = results.get('ex-5')
        ex6_result = results.get('ex-6')

        if not ex5_result or not ex5_result.success or not ex5_result.response:
            return rows, downloaded_documents

        ex5_data = ex5_result.response.output_data
        bids = ex5_data.get('bids', [])

        # Get download info from EX-6
        ex6_downloads = {}
        if ex6_result and ex6_result.success and ex6_result.response:
            ex6_data = ex6_result.response.output_data
            downloads = ex6_data.get('downloads', [])
            for dl in downloads:
                if dl.get('status') == 'success':
                    downloaded_documents.append({
                        'local_path': dl.get('local_path', ''),
                        'title': dl.get('title', ''),
                        'bid_title': dl.get('bid_title', ''),
                        'file_type': dl.get('file_type', ''),
                        'original_url': dl.get('original_url', '')
                    })
                    # Index by URL for matching
                    ex6_downloads[dl.get('original_url', '')] = dl.get('local_path', '')

        # Convert each bid to a row
        for bid in bids:
            if not isinstance(bid, dict):
                continue

            # Extract scope data point
            scope_data = bid.get('scope', {})
            scope_dp = ExtractedDataPoint(
                field_name='scope',
                value=self._format_scope(scope_data),
                source_url=scope_data.get('source_url', '') if isinstance(scope_data, dict) else '',
                verbatim_quote=scope_data.get('verbatim_citation', '') if isinstance(scope_data, dict) else ''
            )

            # Extract timeline data point
            timeline_data = bid.get('timeline', {})
            timeline_dp = ExtractedDataPoint(
                field_name='timeline_requirements',
                value=self._format_timeline(timeline_data),
                source_url=timeline_data.get('source_url', '') if isinstance(timeline_data, dict) else '',
                verbatim_quote=timeline_data.get('verbatim_citation', '') if isinstance(timeline_data, dict) else ''
            )

            # Extract contacts data point
            contacts_data = bid.get('contacts', {})
            contacts_dp = ExtractedDataPoint(
                field_name='contacts',
                value=self._format_contacts(contacts_data),
                source_url=contacts_data.get('source_url', '') if isinstance(contacts_data, dict) else '',
                verbatim_quote=contacts_data.get('verbatim_citation', '') if isinstance(contacts_data, dict) else ''
            )

            # Extract agency
            agency_dp = ExtractedDataPoint(
                field_name='agency_municipality',
                value=bid.get('agency', municipality.city)
            )

            # Build source URLs
            source_urls = []
            for section_key in ['scope', 'timeline', 'requirements', 'contacts']:
                section = bid.get(section_key, {})
                if isinstance(section, dict) and section.get('source_url'):
                    try:
                        source_urls.append(SourceURL(
                            url=section['source_url'],
                            title=bid.get('bid_title', 'Unknown'),
                            source_type='bid_portal'
                        ))
                    except ValueError:
                        pass

            # Build downloadable documents list
            downloadable_docs = bid.get('downloadable_documents', [])
            if not isinstance(downloadable_docs, list):
                downloadable_docs = []

            # Match with downloaded files
            downloaded_files = []
            for doc in downloadable_docs:
                if isinstance(doc, dict):
                    url = doc.get('url', '')
                    if url in ex6_downloads:
                        downloaded_files.append(ex6_downloads[url])

            # Extract key dates
            key_dates = {}
            if isinstance(timeline_data, dict):
                if timeline_data.get('bid_due_date'):
                    key_dates['due_date'] = str(timeline_data['bid_due_date'])
                if timeline_data.get('pre_bid_meeting'):
                    key_dates['pre_bid_meeting'] = str(timeline_data['pre_bid_meeting'])
                if timeline_data.get('questions_deadline'):
                    key_dates['questions_deadline'] = str(timeline_data['questions_deadline'])

            row = MunicipalPublicBidRow(
                municipality_city=municipality.city,
                state=municipality.state,
                agency_municipality=agency_dp,
                bid_contract_title=bid.get('bid_title', 'Unknown'),
                sewer_storm_keywords=bid.get('sewer_storm_keywords', []),
                scope=scope_dp,
                timeline_requirements=timeline_dp,
                contacts=contacts_dp,
                status=bid.get('status', 'unknown'),
                key_dates=key_dates,
                source_urls=source_urls,
                verbatim_citations=[],  # Would need to collect from all sections
                notes_reconciliation='',
                downloadable_documents=downloadable_docs,
                downloaded_files=downloaded_files,
                extracted_at=datetime.now(),
                extraction_session_id=self._session_id
            )
            rows.append(row)

        return rows, downloaded_documents

    def _format_scope(self, scope: Any) -> str:
        """Format scope data into string."""
        if not scope or not isinstance(scope, dict):
            return 'NOT FOUND'

        parts = []
        if scope.get('description'):
            parts.append(str(scope['description']))
        if scope.get('work_type'):
            parts.append(f"Work type: {scope['work_type']}")
        if scope.get('budget_amount'):
            parts.append(f"Budget: {scope['budget_amount']}")

        return "; ".join(parts) if parts else 'NOT FOUND'

    def _format_timeline(self, timeline: Any) -> str:
        """Format timeline data into string."""
        if not timeline or not isinstance(timeline, dict):
            return 'NOT FOUND'

        parts = []
        if timeline.get('bid_due_date'):
            parts.append(f"Due: {timeline['bid_due_date']}")
        if timeline.get('pre_bid_meeting'):
            parts.append(f"Pre-bid: {timeline['pre_bid_meeting']}")
        if timeline.get('questions_deadline'):
            parts.append(f"Questions by: {timeline['questions_deadline']}")

        return "; ".join(parts) if parts else 'NOT FOUND'

    def _format_contacts(self, contacts: Any) -> str:
        """Format contacts data into string."""
        if not contacts or not isinstance(contacts, dict):
            return 'NOT FOUND'

        parts = []
        if contacts.get('name'):
            parts.append(str(contacts['name']))
        if contacts.get('title'):
            parts.append(f"({contacts['title']})")
        if contacts.get('email'):
            parts.append(str(contacts['email']))
        if contacts.get('phone'):
            parts.append(str(contacts['phone']))

        return " ".join(parts) if parts else 'NOT FOUND'

    def _generate_reconciliation_notes(self, results: Dict[str, PipelineResult]) -> str:
        """Generate reconciliation notes from extraction results."""
        notes = []

        for agent_id, result in results.items():
            if not result.success:
                notes.append(f"{agent_id}: {result.error or 'Failed'}")
            elif result.response:
                data_gaps = result.response.output_data.get('data_gaps', [])
                if data_gaps:
                    notes.append(f"{agent_id} gaps: {', '.join(data_gaps[:3])}")

        return "; ".join(notes) if notes else ""

    def _validate_citations(
        self,
        systems_info_results: Dict[str, PipelineResult],
        bid_results: Dict[str, PipelineResult]
    ) -> List[str]:
        """
        Validate that all extracted data points have citations.

        Returns:
            List of validation gap messages
        """
        gaps = []

        # Check systems info results
        for agent_id, result in systems_info_results.items():
            if result.success and result.response:
                output = result.response.output_data
                agent_gaps = output.get('data_gaps', [])
                if isinstance(agent_gaps, list):
                    for gap in agent_gaps:
                        gaps.append(f"{agent_id}: {gap}")

        # Check bid results
        for agent_id, result in bid_results.items():
            if result.success and result.response:
                output = result.response.output_data
                agent_gaps = output.get('data_gaps', [])
                if isinstance(agent_gaps, list):
                    for gap in agent_gaps:
                        gaps.append(f"{agent_id}: {gap}")

        return gaps

    def _resolve_conflicts(
        self,
        systems_info_results: Dict[str, PipelineResult],
        bid_results: Dict[str, PipelineResult]
    ) -> List[Dict[str, Any]]:
        """
        Detect and document data conflicts across extraction results.

        Returns:
            List of conflict dictionaries
        """
        conflicts = []

        # Collect all data points by field name for conflict detection
        data_by_field: Dict[str, List[Dict[str, Any]]] = {}

        for agent_id, result in list(systems_info_results.items()) + list(bid_results.items()):
            if not result.success or not result.response:
                continue

            output = result.response.output_data

            # Look for conflicts in individual data points
            for key, value in output.items():
                if isinstance(value, dict) and 'conflicts' in value:
                    item_conflicts = value.get('conflicts', [])
                    if isinstance(item_conflicts, list):
                        for conflict in item_conflicts:
                            if isinstance(conflict, dict):
                                conflict['agent_id'] = agent_id
                                conflict['field'] = key
                                conflicts.append(conflict)

        return conflicts

    def _create_failed_result(
        self,
        municipality: Municipality,
        table_mode: TableMode,
        preflight_result: PreflightResult,
        error: str
    ) -> ExtractionResult:
        """Create a failed ExtractionResult."""
        self.completed_at = datetime.now()
        self.emit_event(f"Extraction FAILED: {error}")

        return ExtractionResult(
            municipality=municipality,
            table_mode=table_mode,
            preflight=preflight_result,
            systems_info_rows=[],
            public_bid_rows=[],
            total_sources_searched=0,
            total_data_points_extracted=0,
            data_gaps=[error],
            conflicts_detected=[],
            started_at=self.started_at or datetime.now(),
            completed_at=datetime.now(),
            downloaded_documents=[]
        )

    def _create_cancelled_result(
        self,
        municipality: Municipality,
        table_mode: TableMode,
        preflight_result: PreflightResult
    ) -> ExtractionResult:
        """Create a cancelled ExtractionResult."""
        self.completed_at = datetime.now()
        self.emit_event("Extraction cancelled by user")

        return ExtractionResult(
            municipality=municipality,
            table_mode=table_mode,
            preflight=preflight_result,
            systems_info_rows=[],
            public_bid_rows=[],
            total_sources_searched=0,
            total_data_points_extracted=0,
            data_gaps=["Extraction cancelled by user"],
            conflicts_detected=[],
            started_at=self.started_at or datetime.now(),
            completed_at=datetime.now(),
            downloaded_documents=[]
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get pipeline execution statistics."""
        total_duration = 0.0
        total_retries = 0
        stages_completed = 0
        stages_failed = 0

        for result in self.results.values():
            total_duration += result.duration_seconds
            total_retries += result.retries_used
            if result.success:
                stages_completed += 1
            else:
                stages_failed += 1

        return {
            'orchestrator': self.ORCHESTRATOR_NAME,
            'version': self.ORCHESTRATOR_VERSION,
            'total_stages': len(self.SYSTEMS_INFO_STAGES) + len(self.BID_STAGES),
            'stages_completed': stages_completed,
            'stages_failed': stages_failed,
            'total_retries': total_retries,
            'total_duration_seconds': total_duration,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'session_id': self._session_id
        }
