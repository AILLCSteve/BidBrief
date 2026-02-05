"""
Scraper Dispatcher Agent (BR-4)

Coordinates the CityScraper pipeline execution from HOTDOG bridge requests.
This is a MECHANICAL agent - it dispatches to existing orchestrators rather
than calling LLM directly.

Part of the Bridge Layer connecting HOTDOG AI to the CityScraper pipeline.

Responsibilities:
- Validate municipality input from BR-1
- Create dispatch session with unique ID
- Run PF-O (Pre-flight Orchestrator) to validate and prepare
- Run EX-O (Extraction Orchestrator) if preflight passes
- Run PR-3 (UI Data Packager) on results
- Return packaged results to HOTDOG

This agent does NOT need LLM - it performs mechanical orchestration.

Version: 1.0.0
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    Municipality,
    TableMode,
    PreflightStatus,
    AgentActivityEvent,
)
from services.scraper.prompts.br4_scraper_dispatcher import (
    get_config,
    get_error_message,
    STATUS_DISPATCHED,
    STATUS_RUNNING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    TABLE_MODE_SYSTEMS_INFO,
    TABLE_MODE_PUBLIC_BIDS,
    TABLE_MODE_BOTH,
    VALID_TABLE_MODES,
)

logger = logging.getLogger(__name__)


class ScraperDispatcherAgent(BaseAgent):
    """
    BR-4: Scraper Dispatcher Agent

    Coordinates the CityScraper pipeline execution from HOTDOG bridge requests.
    This is a MECHANICAL agent - no LLM calls required.

    The dispatcher:
    1. Validates municipality input
    2. Creates a dispatch session with unique ID
    3. Runs PF-O (Pre-flight Orchestrator)
    4. If preflight passes, runs EX-O (Extraction Orchestrator)
    5. Runs PR-3 (UI Data Packager) on results
    6. Returns packaged results

    This agent does NOT need LLM - it performs mechanical orchestration.
    """

    AGENT_ID = "br-4"
    AGENT_NAME = "Scraper Dispatcher"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "1.0.0"  # Config version, not LLM prompt
    PROMPT_LAST_REFINED = "2026-02-04"

    def __init__(self, *args, **kwargs):
        """Initialize the Scraper Dispatcher Agent."""
        super().__init__(*args, **kwargs)
        self._dispatch_config = get_config()
        self._active_dispatches: Dict[str, Dict[str, Any]] = {}

    def get_system_prompt(self) -> str:
        """
        Get system prompt - not used for this mechanical agent.

        The Scraper Dispatcher performs mechanical orchestration and
        does not require LLM calls for standard operation.
        """
        return """You are a Scraper Dispatcher specialist for municipal data.

This agent performs mechanical orchestration and does not typically
require LLM assistance. If invoked, help with dispatch decisions."""

    # =========================================================================
    # INPUT VALIDATION
    # =========================================================================

    def _validate_municipality(self, municipality: Any) -> tuple:
        """
        Validate municipality input.

        Args:
            municipality: Municipality input (dict or Municipality object)

        Returns:
            Tuple of (is_valid: bool, error_message: str or None, normalized: Municipality or None)
        """
        if municipality is None:
            return False, get_error_message("missing_municipality"), None

        # Handle Municipality object
        if isinstance(municipality, Municipality):
            return True, None, municipality

        # Handle dict
        if isinstance(municipality, dict):
            city = municipality.get('city', '').strip()
            state = municipality.get('state', '').strip()

            if not city or not state:
                return False, get_error_message("invalid_municipality"), None

            try:
                normalized = Municipality(
                    city=city,
                    state=state,
                    county=municipality.get('county'),
                    region=municipality.get('region')
                )
                return True, None, normalized
            except ValueError as e:
                return False, str(e), None

        return False, f"Municipality must be dict or Municipality object, got {type(municipality).__name__}", None

    def _validate_table_mode(self, table_mode: Any) -> tuple:
        """
        Validate and normalize table mode input.

        Args:
            table_mode: Table mode string

        Returns:
            Tuple of (is_valid: bool, error_message: str or None, normalized: TableMode or None)
        """
        if table_mode is None:
            # Default to systems_info if not specified
            return True, None, TableMode.MUNICIPAL_SYSTEMS_INFO

        if not isinstance(table_mode, str):
            return False, f"table_mode must be string, got {type(table_mode).__name__}", None

        normalized = table_mode.strip().lower()

        if normalized not in VALID_TABLE_MODES:
            return False, get_error_message("invalid_table_mode"), None

        # Map to TableMode enum
        if normalized == TABLE_MODE_SYSTEMS_INFO:
            return True, None, TableMode.MUNICIPAL_SYSTEMS_INFO
        elif normalized == TABLE_MODE_PUBLIC_BIDS:
            return True, None, TableMode.MUNICIPAL_PUBLIC_BIDS
        elif normalized == TABLE_MODE_BOTH:
            # For "both" mode, we'll handle it specially in the pipeline
            # Use systems_info as the primary mode but flag for both
            return True, None, TableMode.MUNICIPAL_SYSTEMS_INFO

        return False, get_error_message("invalid_table_mode"), None

    # =========================================================================
    # DISPATCH SESSION MANAGEMENT
    # =========================================================================

    def _create_dispatch_session(
        self,
        municipality: Municipality,
        table_mode: TableMode,
        session_id: str,
        run_both_modes: bool = False
    ) -> str:
        """
        Create a new dispatch session.

        Args:
            municipality: Validated municipality
            table_mode: Validated table mode
            session_id: HOTDOG session ID
            run_both_modes: Whether to run both systems_info and public_bids

        Returns:
            Unique dispatch ID
        """
        dispatch_id = f"dispatch-{uuid.uuid4().hex[:12]}"

        self._active_dispatches[dispatch_id] = {
            'dispatch_id': dispatch_id,
            'session_id': session_id,
            'municipality': municipality,
            'table_mode': table_mode,
            'run_both_modes': run_both_modes,
            'status': STATUS_DISPATCHED,
            'created_at': datetime.now(),
            'preflight_result': None,
            'extraction_result': None,
            'presentation_result': None,
            'error': None,
        }

        logger.info(f"BR-4 created dispatch session: {dispatch_id} for {municipality.full_name}")
        return dispatch_id

    def _update_dispatch_status(
        self,
        dispatch_id: str,
        status: str,
        error: Optional[str] = None
    ):
        """Update dispatch session status."""
        if dispatch_id in self._active_dispatches:
            self._active_dispatches[dispatch_id]['status'] = status
            if error:
                self._active_dispatches[dispatch_id]['error'] = error
            self._active_dispatches[dispatch_id]['updated_at'] = datetime.now()

    # =========================================================================
    # PIPELINE EXECUTION
    # =========================================================================

    async def _run_preflight(
        self,
        municipality: Municipality,
        table_mode: TableMode
    ) -> Dict[str, Any]:
        """
        Run the Pre-flight Orchestrator (PF-O).

        Args:
            municipality: Validated municipality
            table_mode: Table mode for extraction

        Returns:
            Dict with success flag and preflight result
        """
        # Import here to avoid circular imports
        from services.scraper.orchestrators.preflight import PreflightOrchestrator

        self.emit_event("processing", f"Running pre-flight for {municipality.full_name}...")

        try:
            orchestrator = PreflightOrchestrator(
                config=self.config,
                event_callback=self.event_callback
            )

            preflight_result = await orchestrator.run(
                municipality_input=municipality.full_name,
                table_mode=table_mode.value
            )

            if preflight_result.status == PreflightStatus.FAIL:
                gaps_msg = "; ".join(preflight_result.gaps[:3]) if preflight_result.gaps else "Unknown failure"
                return {
                    'success': False,
                    'result': preflight_result,
                    'error': f"Pre-flight failed: {gaps_msg}"
                }

            self.emit_event(
                "completed",
                f"Pre-flight {preflight_result.status.value}: {len(preflight_result.gaps)} gaps"
            )

            return {
                'success': True,
                'result': preflight_result,
                'error': None
            }

        except Exception as e:
            logger.exception(f"BR-4 pre-flight error: {e}")
            return {
                'success': False,
                'result': None,
                'error': f"Pre-flight error: {str(e)[:200]}"
            }

    async def _run_extraction(
        self,
        municipality: Municipality,
        table_mode: TableMode,
        preflight_result: Any
    ) -> Dict[str, Any]:
        """
        Run the Extraction Orchestrator (EX-O).

        Args:
            municipality: Validated municipality
            table_mode: Table mode for extraction
            preflight_result: Result from PF-O

        Returns:
            Dict with success flag and extraction result
        """
        # Import here to avoid circular imports
        from services.scraper.orchestrators.extraction import ExtractionOrchestrator

        self.emit_event("processing", f"Running extraction for {municipality.full_name}...")

        try:
            orchestrator = ExtractionOrchestrator(
                config=self.config,
                event_callback=self.event_callback
            )

            extraction_result = await orchestrator.run(
                municipality=municipality,
                table_mode=table_mode,
                preflight_result=preflight_result
            )

            # Check for extraction success (has data)
            has_data = bool(
                extraction_result.systems_info_rows or
                extraction_result.public_bid_rows
            )

            if not has_data:
                return {
                    'success': False,
                    'result': extraction_result,
                    'error': "Extraction completed but no data extracted"
                }

            data_points = extraction_result.total_data_points_extracted
            self.emit_event(
                "completed",
                f"Extraction complete: {data_points} data points extracted"
            )

            return {
                'success': True,
                'result': extraction_result,
                'error': None
            }

        except Exception as e:
            logger.exception(f"BR-4 extraction error: {e}")
            return {
                'success': False,
                'result': None,
                'error': f"Extraction error: {str(e)[:200]}"
            }

    async def _run_presentation(
        self,
        extraction_result: Any,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Run the UI Data Packager (PR-3) on extraction results.

        Args:
            extraction_result: Result from EX-O
            session_id: Session ID for export URLs

        Returns:
            Dict with success flag and packaged result
        """
        # Import here to avoid circular imports
        from services.scraper.agents.presentation import UIDataPackagerAgent

        self.emit_event("processing", "Packaging results for UI...")

        packager = None
        try:
            packager = UIDataPackagerAgent(
                config=self.config,
                event_callback=self.event_callback
            )

            request = AgentRequest(
                agent_id="pr-3",
                task=f"package-{session_id}",
                input_data={
                    'extraction_result': extraction_result,
                    'session_id': session_id,
                    'include_raw_data': False,
                }
            )

            response = await packager.process(request)

            if not response.success:
                errors_msg = "; ".join(response.errors) if response.errors else "Packaging failed"
                return {
                    'success': False,
                    'result': None,
                    'error': errors_msg
                }

            self.emit_event("completed", "Results packaged for UI display")

            return {
                'success': True,
                'result': response.output_data,
                'error': None
            }

        except Exception as e:
            logger.exception(f"BR-4 presentation error: {e}")
            return {
                'success': False,
                'result': None,
                'error': f"Packaging error: {str(e)[:200]}"
            }
        finally:
            # Ensure packager resources are cleaned up
            if packager is not None:
                try:
                    await packager.cleanup()
                except Exception as cleanup_error:
                    logger.warning(f"BR-4 packager cleanup error: {cleanup_error}")

    # =========================================================================
    # MAIN PROCESS METHOD
    # =========================================================================

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process scraper dispatch request.

        Expected input_data:
        - municipality: dict - Normalized municipality from BR-1 (with 'city' and 'state')
        - table_mode: str - "systems_info", "public_bids", or "both" (from BR-2)
        - gap_analysis: dict - BR-2 output (optional, for prioritization)
        - session_id: str - HOTDOG session ID for tracking
        - async_mode: bool - Whether to run async (default True) - NOT YET IMPLEMENTED

        Returns AgentResponse with:
        - dispatch_id: str - Unique ID for this dispatch
        - status: str - "dispatched", "running", "completed", "failed"
        - preflight_result: dict - PF-O output when complete
        - extraction_result: dict - EX-O output when complete
        - presentation_result: dict - PR-3 packaged output when complete
        - error: str - Error message if failed
        """
        start_time = time.time()

        # Extract input data
        municipality_input = request.input_data.get('municipality')
        table_mode_input = request.input_data.get('table_mode', TABLE_MODE_SYSTEMS_INFO)
        gap_analysis = request.input_data.get('gap_analysis', {})
        session_id = request.input_data.get('session_id', f"session-{uuid.uuid4().hex[:8]}")
        # async_mode = request.input_data.get('async_mode', True)  # Reserved for future use

        # Validate municipality
        is_valid, error_msg, municipality = self._validate_municipality(municipality_input)
        if not is_valid:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={
                    'dispatch_id': None,
                    'status': STATUS_FAILED,
                    'error': error_msg
                },
                errors=[error_msg],
                processing_time_seconds=time.time() - start_time
            )

        # Validate table mode
        is_valid, error_msg, table_mode = self._validate_table_mode(table_mode_input)
        if not is_valid:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={
                    'dispatch_id': None,
                    'status': STATUS_FAILED,
                    'error': error_msg
                },
                errors=[error_msg],
                processing_time_seconds=time.time() - start_time
            )

        # Determine if running both modes
        run_both_modes = (
            isinstance(table_mode_input, str) and
            table_mode_input.strip().lower() == TABLE_MODE_BOTH
        )

        # Create dispatch session
        dispatch_id = self._create_dispatch_session(
            municipality=municipality,
            table_mode=table_mode,
            session_id=session_id,
            run_both_modes=run_both_modes
        )

        self.emit_event("processing", f"Dispatch {dispatch_id} started for {municipality.full_name}")

        try:
            # Update status to running
            self._update_dispatch_status(dispatch_id, STATUS_RUNNING)

            # Run Pre-flight
            preflight_output = await self._run_preflight(municipality, table_mode)
            self._active_dispatches[dispatch_id]['preflight_result'] = preflight_output.get('result')

            if not preflight_output['success']:
                self._update_dispatch_status(
                    dispatch_id, STATUS_FAILED, preflight_output['error']
                )
                self.emit_event(
                    "failed",
                    f"Pre-flight failed: {preflight_output['error'][:100]}",
                    is_completed=True
                )
                return AgentResponse(
                    agent_id=self.AGENT_ID,
                    task=request.task,
                    success=False,
                    output_data={
                        'dispatch_id': dispatch_id,
                        'status': STATUS_FAILED,
                        'preflight_result': self._serialize_preflight(preflight_output.get('result')),
                        'extraction_result': None,
                        'presentation_result': None,
                        'error': preflight_output['error']
                    },
                    errors=[preflight_output['error']],
                    processing_time_seconds=time.time() - start_time
                )

            preflight_result = preflight_output['result']

            # Run Extraction
            extraction_output = await self._run_extraction(
                municipality, table_mode, preflight_result
            )
            self._active_dispatches[dispatch_id]['extraction_result'] = extraction_output.get('result')

            if not extraction_output['success']:
                self._update_dispatch_status(
                    dispatch_id, STATUS_FAILED, extraction_output['error']
                )
                self.emit_event(
                    "failed",
                    f"Extraction failed: {extraction_output['error'][:100]}",
                    is_completed=True
                )
                return AgentResponse(
                    agent_id=self.AGENT_ID,
                    task=request.task,
                    success=False,
                    output_data={
                        'dispatch_id': dispatch_id,
                        'status': STATUS_FAILED,
                        'preflight_result': self._serialize_preflight(preflight_result),
                        'extraction_result': self._serialize_extraction(extraction_output.get('result')),
                        'presentation_result': None,
                        'error': extraction_output['error']
                    },
                    errors=[extraction_output['error']],
                    processing_time_seconds=time.time() - start_time
                )

            extraction_result = extraction_output['result']

            # Run Presentation (PR-3)
            presentation_output = await self._run_presentation(extraction_result, session_id)
            self._active_dispatches[dispatch_id]['presentation_result'] = presentation_output.get('result')

            if not presentation_output['success']:
                # Presentation failure is non-fatal - we still have extraction results
                logger.warning(f"BR-4 presentation failed: {presentation_output['error']}")
                # Continue with partial success

            # Update status to completed
            self._update_dispatch_status(dispatch_id, STATUS_COMPLETED)

            elapsed = time.time() - start_time

            completion_msg = (
                f"Dispatch {dispatch_id} completed for {municipality.full_name} "
                f"in {elapsed:.1f}s"
            )
            self.emit_event("completed", completion_msg, is_completed=True)

            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=True,
                output_data={
                    'dispatch_id': dispatch_id,
                    'status': STATUS_COMPLETED,
                    'preflight_result': self._serialize_preflight(preflight_result),
                    'extraction_result': self._serialize_extraction(extraction_result),
                    'presentation_result': presentation_output.get('result'),
                    'error': None
                },
                errors=[],
                processing_time_seconds=elapsed
            )

        except Exception as e:
            # Handle unexpected errors
            if isinstance(e, (SystemExit, KeyboardInterrupt)):
                raise

            logger.exception(f"BR-4 unexpected error: {e}")
            self._update_dispatch_status(dispatch_id, STATUS_FAILED, str(e))
            self.emit_event(
                "failed",
                f"Dispatch error: {str(e)[:100]}",
                is_completed=True
            )

            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={
                    'dispatch_id': dispatch_id,
                    'status': STATUS_FAILED,
                    'preflight_result': self._active_dispatches.get(dispatch_id, {}).get('preflight_result'),
                    'extraction_result': self._active_dispatches.get(dispatch_id, {}).get('extraction_result'),
                    'presentation_result': None,
                    'error': f"Unexpected error: {str(e)[:200]}"
                },
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:200]}"],
                processing_time_seconds=time.time() - start_time
            )

    # =========================================================================
    # SERIALIZATION HELPERS
    # =========================================================================

    def _serialize_preflight(self, preflight_result: Any) -> Optional[Dict[str, Any]]:
        """Serialize PreflightResult to dict for output."""
        if preflight_result is None:
            return None

        try:
            return {
                'municipality': {
                    'city': preflight_result.municipality.city,
                    'state': preflight_result.municipality.state,
                },
                'table_mode': preflight_result.table_mode.value,
                'status': preflight_result.status.value,
                'gaps': preflight_result.gaps,
                'recommendations': preflight_result.recommendations,
            }
        except (AttributeError, TypeError) as e:
            logger.warning(f"BR-4 preflight serialization error: {e}")
            return None

    def _serialize_extraction(self, extraction_result: Any) -> Optional[Dict[str, Any]]:
        """Serialize ExtractionResult to dict for output."""
        if extraction_result is None:
            return None

        try:
            return {
                'municipality': {
                    'city': extraction_result.municipality.city,
                    'state': extraction_result.municipality.state,
                },
                'table_mode': extraction_result.table_mode.value,
                'total_sources_searched': extraction_result.total_sources_searched,
                'total_data_points_extracted': extraction_result.total_data_points_extracted,
                'systems_info_rows_count': len(extraction_result.systems_info_rows or []),
                'public_bid_rows_count': len(extraction_result.public_bid_rows or []),
                'data_gaps': (extraction_result.data_gaps or [])[:50],  # Increased from 10 for comprehensive reporting
                'downloaded_documents_count': len(extraction_result.downloaded_documents or []),
            }
        except (AttributeError, TypeError) as e:
            logger.warning(f"BR-4 extraction serialization error: {e}")
            return None

    # =========================================================================
    # STATUS QUERY METHODS
    # =========================================================================

    def get_dispatch_status(self, dispatch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current status of a dispatch.

        Args:
            dispatch_id: Unique dispatch ID

        Returns:
            Dict with dispatch status or None if not found
        """
        dispatch = self._active_dispatches.get(dispatch_id)
        if not dispatch:
            return None

        return {
            'dispatch_id': dispatch['dispatch_id'],
            'session_id': dispatch['session_id'],
            'municipality': dispatch['municipality'].full_name,
            'table_mode': dispatch['table_mode'].value,
            'status': dispatch['status'],
            'error': dispatch.get('error'),
            'created_at': dispatch['created_at'].isoformat(),
            'has_preflight': dispatch.get('preflight_result') is not None,
            'has_extraction': dispatch.get('extraction_result') is not None,
            'has_presentation': dispatch.get('presentation_result') is not None,
        }

    def list_active_dispatches(self) -> List[Dict[str, Any]]:
        """
        List all active dispatches.

        Returns:
            List of dispatch status dicts
        """
        return [
            self.get_dispatch_status(dispatch_id)
            for dispatch_id in self._active_dispatches.keys()
        ]

    # =========================================================================
    # VALIDATION METHOD (required by BaseAgent)
    # =========================================================================

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """
        Validate dispatcher output.

        Args:
            output: Output data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required fields
        required_fields = ['dispatch_id', 'status']
        for field in required_fields:
            if field not in output:
                errors.append(f"Missing required field: '{field}'")

        # Validate status value
        if 'status' in output:
            status = output['status']
            if status not in (STATUS_DISPATCHED, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED):
                errors.append(f"Invalid status: {status}")

        # If failed, error message should be present
        if output.get('status') == STATUS_FAILED:
            if not output.get('error'):
                errors.append("Failed status requires error message")

        # If completed, should have results
        if output.get('status') == STATUS_COMPLETED:
            if not output.get('preflight_result'):
                errors.append("Completed status should have preflight_result")
            if not output.get('extraction_result'):
                errors.append("Completed status should have extraction_result")

        return errors
