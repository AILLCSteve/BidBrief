"""
Standalone Research Orchestrator (UC-2)

Orchestrates standalone municipal research without requiring a document upload.
User enters a municipality name, and the orchestrator coordinates the complete
research pipeline to return comprehensive municipal data.

Pipeline:
1. PF-O: Pre-flight Orchestrator - Validate municipality and plan extraction
2. EX-O: Extraction Orchestrator - Run all extraction agents (EX-1 through EX-6)
3. PR-3: UI Data Packager - Format results for display

CRITICAL: This orchestrator is designed for standalone use cases where the user
wants to research a municipality directly without having an RFP or document to analyze.

Version: 1.0.0
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List

from services.scraper.config import get_config, ScraperConfig
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    AgentActivityEvent,
    Municipality,
    TableMode,
    PreflightStatus,
)
from services.scraper.orchestrators.preflight import PreflightOrchestrator
from services.scraper.orchestrators.extraction import ExtractionOrchestrator
from services.scraper.agents.presentation import UIDataPackagerAgent

logger = logging.getLogger(__name__)


class StandaloneResearchOrchestrator:
    """
    UC-2: Standalone Research Orchestrator

    Enables standalone municipal research without a document upload.
    User provides a municipality name, and the orchestrator coordinates
    the complete research pipeline (PF-O -> EX-O -> PR-3).

    Flow:
        User enters "Springfield, IL"
                     |
            PF-O: Validate & Plan (PF-1 -> PF-5)
                     |
            EX-O: Extract Data (EX-1 -> EX-6)
                     |
            PR-3: Package Results
                     |
        Complete Research Results
    """

    ORCHESTRATOR_ID = "uc-2"
    ORCHESTRATOR_NAME = "Standalone Research"
    ORCHESTRATOR_VERSION = "1.0.0"

    # Pipeline stages for tracking
    STAGE_PREFLIGHT = "preflight"
    STAGE_EXTRACTION = "extraction"
    STAGE_PRESENTATION = "presentation"

    # Valid table modes
    VALID_TABLE_MODES = ("systems_info", "public_bids", "both")

    def __init__(
        self,
        config: Optional[ScraperConfig] = None,
        event_callback: Optional[Callable[[AgentActivityEvent], None]] = None
    ):
        """
        Initialize the Standalone Research Orchestrator.

        Args:
            config: Optional scraper configuration
            event_callback: Optional callback for progress events (for UI feed)
        """
        self.config = config or get_config()
        self.event_callback = event_callback

        # Track pipeline state
        self.session_id: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self._cancelled = False

        # Stage results
        self.stage_results: Dict[str, Dict[str, Any]] = {}

        # Agent activity events collected during execution
        self.agent_events: List[AgentActivityEvent] = []

        logger.info(f"Initialized {self.ORCHESTRATOR_NAME} v{self.ORCHESTRATOR_VERSION}")

    def emit_event(
        self,
        status: str,
        message: str,
        is_completed: bool = False
    ):
        """
        Emit a progress event for the UI agent activity feed.

        Args:
            status: Event status type (processing, completed, failed, etc.)
            message: Human-readable status message
            is_completed: Whether this event marks completion
        """
        event = AgentActivityEvent(
            agent_id=self.ORCHESTRATOR_ID,
            agent_name=self.ORCHESTRATOR_NAME,
            status=status,
            message=message,
            is_active=not is_completed,
            is_completed=is_completed,
            timestamp=datetime.now()
        )

        # Store event for PR-3
        self.agent_events.append(event)

        if self.event_callback:
            self.event_callback(event)
        logger.info(f"UC-2: [{status}] {message}")

    def _create_event_collector(self) -> Callable[[AgentActivityEvent], None]:
        """
        Create an event collector that stores events and forwards to callback.

        Returns:
            Callable that collects events
        """
        def collector(event: AgentActivityEvent):
            self.agent_events.append(event)
            if self.event_callback:
                self.event_callback(event)
        return collector

    def cancel(self):
        """Request cancellation of the pipeline."""
        self._cancelled = True
        logger.info("UC-2: Cancellation requested")

    def _resolve_table_mode(self, table_mode_input: str) -> TableMode:
        """
        Resolve table mode from input string.

        Args:
            table_mode_input: Input string like "systems_info", "public_bids", or "both"

        Returns:
            TableMode enum value
        """
        if not isinstance(table_mode_input, str):
            logger.warning(f"table_mode must be string, got {type(table_mode_input).__name__}")
            return TableMode.MUNICIPAL_SYSTEMS_INFO

        normalized = table_mode_input.strip().lower()

        if normalized in ("systems_info", "systems", "info"):
            return TableMode.MUNICIPAL_SYSTEMS_INFO
        elif normalized in ("public_bids", "bids"):
            return TableMode.MUNICIPAL_PUBLIC_BIDS
        elif normalized == "both":
            # For "both" mode, we default to systems_info but the extraction
            # orchestrator will handle running both pipelines
            return TableMode.MUNICIPAL_SYSTEMS_INFO

        logger.warning(f"Unknown table_mode '{table_mode_input}', defaulting to MUNICIPAL_SYSTEMS_INFO")
        return TableMode.MUNICIPAL_SYSTEMS_INFO

    async def run(
        self,
        municipality_input: str,
        table_mode: str = "systems_info",
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run the complete standalone research pipeline.

        Args:
            municipality_input: User-entered municipality (e.g., "Springfield, IL")
            table_mode: Target table type ("systems_info", "public_bids", or "both")
            session_id: Optional session ID for tracking (generated if not provided)

        Returns:
            Dict containing:
                - municipality: Normalized municipality info
                - preflight_result: Output from PF-O
                - extraction_result: Output from EX-O
                - presentation_result: Output from PR-3 (formatted tables)
                - statistics: { agents_run, sources_found, fields_extracted, processing_time }
                - success: bool
                - error: Optional error message if failed
        """
        start_time = time.time()
        self.session_id = session_id or f"uc2-{uuid.uuid4().hex[:12]}"
        self.started_at = datetime.now()
        self._cancelled = False
        self.stage_results = {}
        self.agent_events = []

        # Input validation
        validation_errors = self._validate_inputs(municipality_input, table_mode)
        if validation_errors:
            return self._create_error_result(
                f"Input validation failed: {'; '.join(validation_errors)}",
                start_time
            )

        municipality_input = municipality_input.strip()

        self.emit_event("processing", f"Starting standalone research for: {municipality_input}")

        try:
            # =================================================================
            # STAGE 1: Pre-flight Orchestrator (PF-O)
            # =================================================================
            self.emit_event("processing", "Stage 1/3: Running pre-flight validation...")

            preflight_result = await self._run_preflight(
                municipality_input=municipality_input,
                table_mode=table_mode
            )

            if preflight_result is None or preflight_result.status == PreflightStatus.FAIL:
                error_msg = "Pre-flight validation failed"
                if preflight_result and preflight_result.gaps:
                    error_msg += f": {'; '.join(preflight_result.gaps[:3])}"
                return self._create_error_result(
                    error_msg,
                    start_time,
                    preflight_result=preflight_result
                )

            if self._cancelled:
                return self._create_cancelled_result(start_time, preflight_result=preflight_result)

            municipality = preflight_result.municipality

            self.emit_event(
                "completed",
                f"Stage 1/3: Pre-flight complete for {municipality.full_name} "
                f"({preflight_result.status.value})"
            )

            # =================================================================
            # STAGE 2: Extraction Orchestrator (EX-O)
            # =================================================================
            self.emit_event("processing", "Stage 2/3: Running extraction agents...")

            extraction_result = await self._run_extraction(
                municipality=municipality,
                table_mode=self._resolve_table_mode(table_mode),
                preflight_result=preflight_result
            )

            if extraction_result is None:
                return self._create_error_result(
                    "Extraction failed: no result returned",
                    start_time,
                    preflight_result=preflight_result,
                    municipality=municipality
                )

            if self._cancelled:
                return self._create_cancelled_result(
                    start_time,
                    preflight_result=preflight_result,
                    extraction_result=extraction_result,
                    municipality=municipality
                )

            self.emit_event(
                "completed",
                f"Stage 2/3: Extraction complete - "
                f"{extraction_result.total_data_points_extracted} data points extracted"
            )

            # =================================================================
            # STAGE 3: UI Data Packager (PR-3)
            # =================================================================
            self.emit_event("processing", "Stage 3/3: Packaging results for display...")

            presentation_result = await self._run_presentation(
                extraction_result=extraction_result
            )

            if presentation_result is None:
                # Presentation failure is non-fatal - we still have extraction results
                logger.warning("UC-2 presentation failed, returning raw extraction results")
                presentation_result = {}

            self.completed_at = datetime.now()
            elapsed = time.time() - start_time

            # Calculate statistics
            statistics = self._calculate_statistics(
                preflight_result=preflight_result,
                extraction_result=extraction_result,
                elapsed=elapsed
            )

            self.emit_event(
                "completed",
                f"Research complete for {municipality.full_name}: "
                f"{statistics['fields_extracted']} fields, "
                f"{statistics['sources_found']} sources ({elapsed:.1f}s)",
                is_completed=True
            )

            return {
                'success': True,
                'session_id': self.session_id,
                'municipality': {
                    'city': municipality.city,
                    'state': municipality.state,
                    'county': municipality.county,
                    'region': municipality.region,
                    'full_name': municipality.full_name,
                },
                'preflight_result': self._serialize_preflight_result(preflight_result),
                'extraction_result': self._serialize_extraction_result(extraction_result),
                'presentation_result': presentation_result,
                'statistics': statistics,
                'processing_time_seconds': elapsed,
                'completed_at': self.completed_at.isoformat()
            }

        except (SystemExit, KeyboardInterrupt):
            # Re-raise critical exceptions
            raise
        except Exception as e:
            logger.exception(f"UC-2 unexpected error: {e}")
            return self._create_error_result(
                f"Unexpected error: {type(e).__name__}: {str(e)[:200]}",
                start_time
            )

    def _validate_inputs(
        self,
        municipality_input: Any,
        table_mode: Any
    ) -> List[str]:
        """
        Validate all inputs with type checks.

        Args:
            municipality_input: Expected string with municipality
            table_mode: Expected string with table mode

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        # Validate municipality_input
        if not isinstance(municipality_input, str):
            errors.append(
                f"municipality_input must be string, got {type(municipality_input).__name__}"
            )
        elif not municipality_input.strip():
            errors.append("municipality_input cannot be empty")
        elif len(municipality_input.strip()) < 3:
            errors.append(
                f"municipality_input too short ({len(municipality_input.strip())} chars, minimum 3)"
            )

        # Validate table_mode
        if not isinstance(table_mode, str):
            errors.append(
                f"table_mode must be string, got {type(table_mode).__name__}"
            )
        elif table_mode.strip().lower() not in self.VALID_TABLE_MODES:
            errors.append(
                f"table_mode must be one of {self.VALID_TABLE_MODES}, got '{table_mode}'"
            )

        return errors

    async def _run_preflight(
        self,
        municipality_input: str,
        table_mode: str
    ) -> Optional[Any]:
        """
        Run PF-O (Pre-flight Orchestrator).

        Args:
            municipality_input: User-entered municipality
            table_mode: Target table mode

        Returns:
            PreflightResult or None if failed
        """
        orchestrator = None
        try:
            orchestrator = PreflightOrchestrator(
                config=self.config,
                event_callback=self._create_event_collector()
            )

            # Map table mode string to display string for PF-O
            table_mode_display = "Municipal Systems Information"
            if table_mode.lower() in ("public_bids", "bids"):
                table_mode_display = "Municipal Public Bids"

            result = await orchestrator.run(
                municipality_input=municipality_input,
                table_mode=table_mode_display
            )

            self.stage_results[self.STAGE_PREFLIGHT] = {
                'success': result.status != PreflightStatus.FAIL,
                'result': result,
                'statistics': orchestrator.get_statistics()
            }

            return result

        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception as e:
            logger.exception(f"UC-2 PF-O error: {e}")
            self.stage_results[self.STAGE_PREFLIGHT] = {
                'success': False,
                'error': str(e),
                'result': None
            }
            return None

    async def _run_extraction(
        self,
        municipality: Municipality,
        table_mode: TableMode,
        preflight_result: Any
    ) -> Optional[Any]:
        """
        Run EX-O (Extraction Orchestrator).

        Args:
            municipality: Normalized municipality from pre-flight
            table_mode: Resolved TableMode enum
            preflight_result: Complete pre-flight result

        Returns:
            ExtractionResult or None if failed
        """
        orchestrator = None
        try:
            orchestrator = ExtractionOrchestrator(
                config=self.config,
                event_callback=self._create_event_collector()
            )

            result = await orchestrator.run(
                municipality=municipality,
                table_mode=table_mode,
                preflight_result=preflight_result
            )

            self.stage_results[self.STAGE_EXTRACTION] = {
                'success': True,
                'result': result,
                'statistics': orchestrator.get_statistics()
            }

            return result

        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception as e:
            logger.exception(f"UC-2 EX-O error: {e}")
            self.stage_results[self.STAGE_EXTRACTION] = {
                'success': False,
                'error': str(e),
                'result': None
            }
            return None

    async def _run_presentation(
        self,
        extraction_result: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Run PR-3 (UI Data Packager).

        Args:
            extraction_result: Complete extraction result

        Returns:
            Packaged UI data dict or None if failed
        """
        agent = None
        try:
            agent = UIDataPackagerAgent(
                config=self.config,
                event_callback=self._create_event_collector()
            )

            request = AgentRequest(
                agent_id="pr-3",
                task=f"package-ui-{self.session_id}",
                input_data={
                    'extraction_result': extraction_result,
                    'session_id': self.session_id,
                    'include_raw_data': False,
                    'agent_events': self.agent_events
                }
            )

            response = await agent.process(request)

            self.stage_results[self.STAGE_PRESENTATION] = {
                'success': response.success,
                'response': response,
                'processing_time': response.processing_time_seconds
            }

            if response.success:
                return response.output_data
            else:
                logger.warning(f"UC-2 PR-3 failed: {response.errors}")
                return None

        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception as e:
            logger.exception(f"UC-2 PR-3 error: {e}")
            self.stage_results[self.STAGE_PRESENTATION] = {
                'success': False,
                'error': str(e),
                'result': None
            }
            return None
        finally:
            if agent:
                try:
                    await agent.cleanup()
                except Exception as cleanup_error:
                    logger.warning(f"UC-2 PR-3 cleanup error: {cleanup_error}")

    def _calculate_statistics(
        self,
        preflight_result: Any,
        extraction_result: Any,
        elapsed: float
    ) -> Dict[str, Any]:
        """
        Calculate pipeline statistics.

        Args:
            preflight_result: Pre-flight result
            extraction_result: Extraction result
            elapsed: Total elapsed time in seconds

        Returns:
            Dict with statistics
        """
        agents_run = 0
        sources_found = 0
        fields_extracted = 0

        # Count from preflight
        if self.stage_results.get(self.STAGE_PREFLIGHT, {}).get('statistics'):
            pf_stats = self.stage_results[self.STAGE_PREFLIGHT]['statistics']
            agents_run += pf_stats.get('stages_completed', 0)

        # Count from extraction
        if self.stage_results.get(self.STAGE_EXTRACTION, {}).get('statistics'):
            ex_stats = self.stage_results[self.STAGE_EXTRACTION]['statistics']
            agents_run += ex_stats.get('stages_completed', 0)

        # From extraction result
        if extraction_result:
            sources_found = extraction_result.total_sources_searched
            fields_extracted = extraction_result.total_data_points_extracted

        # Count presentation agent
        if self.stage_results.get(self.STAGE_PRESENTATION, {}).get('success'):
            agents_run += 1

        return {
            'agents_run': agents_run,
            'sources_found': sources_found,
            'fields_extracted': fields_extracted,
            'processing_time': elapsed,
            'preflight_status': preflight_result.status.value if preflight_result else 'failed',
            'data_gaps_count': len(extraction_result.data_gaps) if extraction_result else 0,
            'conflicts_count': len(extraction_result.conflicts_detected) if extraction_result else 0,
        }

    def _serialize_preflight_result(self, result: Any) -> Dict[str, Any]:
        """
        Serialize PreflightResult to dict.

        Args:
            result: PreflightResult object

        Returns:
            Dict representation
        """
        if result is None:
            return {}

        serialized = {
            'status': result.status.value,
            'gaps': result.gaps,
            'recommendations': result.recommendations,
            'completed_at': result.completed_at.isoformat() if result.completed_at else None,
        }

        # Serialize jurisdiction info
        if result.jurisdiction:
            serialized['jurisdiction'] = {
                'sanitary_sewer_owner': result.jurisdiction.sanitary_sewer_owner,
                'sanitary_sewer_operator': result.jurisdiction.sanitary_sewer_operator,
                'storm_drain_owner': result.jurisdiction.storm_drain_owner,
                'storm_drain_operator': result.jurisdiction.storm_drain_operator,
                'notes': result.jurisdiction.notes,
            }

        # Serialize source map
        if result.source_map:
            sm = result.source_map
            serialized['source_map'] = {
                'official_website': sm.official_website.url if sm.official_website else None,
                'public_works_page': sm.public_works_page.url if sm.public_works_page else None,
                'sewer_utility_page': sm.sewer_utility_page.url if sm.sewer_utility_page else None,
                'stormwater_page': sm.stormwater_page.url if sm.stormwater_page else None,
                'procurement_page': sm.procurement_page.url if sm.procurement_page else None,
                'gis_portal': sm.gis_portal.url if sm.gis_portal else None,
                'cip_documents_count': len(sm.cip_documents),
                'compliance_sources_count': len(sm.compliance_sources),
            }

        # Serialize terminology
        if result.terminology:
            tm = result.terminology
            serialized['terminology'] = {
                'sanitary_terms': tm.sanitary_terms,
                'storm_terms': tm.storm_terms,
                'lift_station_terms': tm.lift_station_terms,
                'bid_portal_keywords': tm.bid_portal_keywords,
            }

        return serialized

    def _serialize_extraction_result(self, result: Any) -> Dict[str, Any]:
        """
        Serialize ExtractionResult to dict.

        Args:
            result: ExtractionResult object

        Returns:
            Dict representation
        """
        if result is None:
            return {}

        return {
            'table_mode': result.table_mode.value,
            'total_sources_searched': result.total_sources_searched,
            'total_data_points_extracted': result.total_data_points_extracted,
            'data_gaps': result.data_gaps,
            'conflicts_detected': result.conflicts_detected,
            'systems_info_rows_count': len(result.systems_info_rows),
            'public_bid_rows_count': len(result.public_bid_rows),
            'downloaded_documents_count': len(result.downloaded_documents),
            'started_at': result.started_at.isoformat() if result.started_at else None,
            'completed_at': result.completed_at.isoformat() if result.completed_at else None,
        }

    def _create_error_result(
        self,
        error_message: str,
        start_time: float,
        preflight_result: Optional[Any] = None,
        extraction_result: Optional[Any] = None,
        municipality: Optional[Municipality] = None
    ) -> Dict[str, Any]:
        """
        Create an error result with partial data if available.

        Args:
            error_message: Error description
            start_time: Pipeline start time
            preflight_result: Pre-flight result if available
            extraction_result: Extraction result if available
            municipality: Municipality if resolved

        Returns:
            Error result dict
        """
        self.completed_at = datetime.now()
        elapsed = time.time() - start_time

        self.emit_event("failed", f"Research failed: {error_message}", is_completed=True)

        result = {
            'success': False,
            'session_id': self.session_id,
            'municipality': None,
            'preflight_result': None,
            'extraction_result': None,
            'presentation_result': None,
            'statistics': {
                'agents_run': 0,
                'sources_found': 0,
                'fields_extracted': 0,
                'processing_time': elapsed,
            },
            'error': error_message,
            'processing_time_seconds': elapsed,
            'completed_at': self.completed_at.isoformat()
        }

        # Include partial results if available
        if municipality:
            result['municipality'] = {
                'city': municipality.city,
                'state': municipality.state,
                'county': municipality.county,
                'region': municipality.region,
                'full_name': municipality.full_name,
            }

        if preflight_result:
            result['preflight_result'] = self._serialize_preflight_result(preflight_result)

        if extraction_result:
            result['extraction_result'] = self._serialize_extraction_result(extraction_result)

        return result

    def _create_cancelled_result(
        self,
        start_time: float,
        preflight_result: Optional[Any] = None,
        extraction_result: Optional[Any] = None,
        municipality: Optional[Municipality] = None
    ) -> Dict[str, Any]:
        """
        Create a cancelled result.

        Args:
            start_time: Pipeline start time
            preflight_result: Pre-flight result if available
            extraction_result: Extraction result if available
            municipality: Municipality if resolved

        Returns:
            Cancelled result dict
        """
        self.completed_at = datetime.now()
        elapsed = time.time() - start_time

        self.emit_event("cancelled", "Research cancelled by user", is_completed=True)

        result = {
            'success': False,
            'session_id': self.session_id,
            'municipality': None,
            'preflight_result': None,
            'extraction_result': None,
            'presentation_result': None,
            'statistics': {
                'agents_run': 0,
                'sources_found': 0,
                'fields_extracted': 0,
                'processing_time': elapsed,
            },
            'error': 'Research cancelled by user',
            'processing_time_seconds': elapsed,
            'completed_at': self.completed_at.isoformat()
        }

        # Include partial results if available
        if municipality:
            result['municipality'] = {
                'city': municipality.city,
                'state': municipality.state,
                'county': municipality.county,
                'region': municipality.region,
                'full_name': municipality.full_name,
            }

        if preflight_result:
            result['preflight_result'] = self._serialize_preflight_result(preflight_result)

        if extraction_result:
            result['extraction_result'] = self._serialize_extraction_result(extraction_result)

        return result

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get pipeline execution statistics.

        Returns:
            Dict with execution statistics
        """
        total_duration = 0.0
        stages_completed = 0
        stages_failed = 0

        for stage_id, result in self.stage_results.items():
            if result.get('statistics'):
                total_duration += result['statistics'].get('total_duration_seconds', 0.0)
            elif result.get('processing_time'):
                total_duration += result['processing_time']

            if result.get('success'):
                stages_completed += 1
            else:
                stages_failed += 1

        return {
            'orchestrator': self.ORCHESTRATOR_NAME,
            'orchestrator_id': self.ORCHESTRATOR_ID,
            'version': self.ORCHESTRATOR_VERSION,
            'session_id': self.session_id,
            'total_stages': 3,
            'stages_completed': stages_completed,
            'stages_failed': stages_failed,
            'total_duration_seconds': total_duration,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
