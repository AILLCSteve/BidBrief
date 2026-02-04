"""
Document Enrichment Orchestrator (UC-1)

Orchestrates the complete document enrichment pipeline by coordinating
bridge agents BR-1, BR-4, and BR-3 to enrich HOTDOG document analysis
with external CityScraper research.

Pipeline:
1. BR-1: Municipality Detector - Detect municipality from uploaded document
2. BR-4: Scraper Dispatcher - Run full CityScraper pipeline (PF-O -> EX-O -> PR-3)
3. BR-3: Data Merger - Merge scraped data with HOTDOG results

CRITICAL: All external research data MUST be tagged with [External Research - CityScraper].
This is NON-NEGOTIABLE for source attribution transparency.

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
)
from services.scraper.agents.bridge import (
    MunicipalityDetectorAgent,
    DataMergerAgent,
    ScraperDispatcherAgent,
)

logger = logging.getLogger(__name__)


class DocumentEnrichmentOrchestrator:
    """
    UC-1: Document Enrichment Orchestrator

    Orchestrates the automatic enrichment of HOTDOG document analysis results
    with external municipal research from CityScraper.

    Flow:
        HOTDOG Results + Document Content
                     |
            BR-1: Detect Municipality
                     |
            BR-4: Dispatch Scraper (PF-O -> EX-O -> PR-3)
                     |
            BR-3: Merge Results
                     |
        Enriched Results with [External Research - CityScraper] tags
    """

    ORCHESTRATOR_ID = "uc-1"
    ORCHESTRATOR_NAME = "Document Enrichment"
    ORCHESTRATOR_VERSION = "1.0.0"

    # Pipeline stages for tracking
    STAGE_MUNICIPALITY_DETECTION = "municipality_detection"
    STAGE_SCRAPER_DISPATCH = "scraper_dispatch"
    STAGE_DATA_MERGE = "data_merge"

    # Status constants
    STATUS_STARTED = "started"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    def __init__(
        self,
        config: Optional[ScraperConfig] = None,
        event_callback: Optional[Callable[[AgentActivityEvent], None]] = None
    ):
        """
        Initialize the Document Enrichment Orchestrator.

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
        if self.event_callback:
            event = AgentActivityEvent(
                agent_id=self.ORCHESTRATOR_ID,
                agent_name=self.ORCHESTRATOR_NAME,
                status=status,
                message=message,
                is_active=not is_completed,
                is_completed=is_completed,
                timestamp=datetime.now()
            )
            self.event_callback(event)
        logger.info(f"UC-1: [{status}] {message}")

    def cancel(self):
        """Request cancellation of the pipeline."""
        self._cancelled = True
        logger.info("UC-1: Cancellation requested")

    async def run(
        self,
        hotdog_session_data: Dict[str, Any],
        document_content: str,
        document_filename: str = "unknown.pdf",
        table_mode: str = "systems_info",
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run the complete document enrichment pipeline.

        Args:
            hotdog_session_data: HOTDOG analysis results including:
                - answered_questions: list of Q&A pairs from document
                - unanswered_questions: list of questions without answers
                - summary: document summary
                - metadata: any additional metadata
            document_content: Raw text content of the uploaded document
            document_filename: Original filename of the document
            table_mode: Target table type ("systems_info" or "public_bids")
            session_id: Optional session ID for tracking (generated if not provided)

        Returns:
            Dict containing:
                - original_hotdog_data: The original HOTDOG results
                - detected_municipality: What BR-1 found
                - scraper_result: Full CityScraper extraction
                - merged_result: Combined data from BR-3
                - enrichment_stats: { fields_added, fields_enhanced, sources_added }
                - success: bool
                - error: Optional error message if failed
        """
        start_time = time.time()
        self.session_id = session_id or f"uc1-{uuid.uuid4().hex[:12]}"
        self.started_at = datetime.now()
        self._cancelled = False
        self.stage_results = {}

        # Input validation
        validation_errors = self._validate_inputs(
            hotdog_session_data, document_content, document_filename
        )
        if validation_errors:
            return self._create_error_result(
                hotdog_session_data,
                f"Input validation failed: {'; '.join(validation_errors)}",
                start_time
            )

        self.emit_event("processing", f"Starting document enrichment for: {document_filename}")

        try:
            # =================================================================
            # STAGE 1: Municipality Detection (BR-1)
            # =================================================================
            self.emit_event("processing", "Stage 1/3: Detecting municipality from document...")

            br1_result = await self._run_municipality_detection(
                document_content=document_content,
                document_filename=document_filename,
                hotdog_metadata=hotdog_session_data.get('metadata', {})
            )

            if not br1_result['success']:
                return self._create_error_result(
                    hotdog_session_data,
                    f"Municipality detection failed: {br1_result.get('error', 'Unknown error')}",
                    start_time,
                    detected_municipality=br1_result.get('data', {})
                )

            if self._cancelled:
                return self._create_cancelled_result(hotdog_session_data, start_time)

            detected_municipality = br1_result['data']
            municipality_name = detected_municipality.get('municipality_name', '')
            state = detected_municipality.get('state', '')

            if not municipality_name or not state:
                return self._create_error_result(
                    hotdog_session_data,
                    "Could not detect municipality from document. "
                    "Please ensure the document contains location information.",
                    start_time,
                    detected_municipality=detected_municipality
                )

            self.emit_event(
                "completed",
                f"Stage 1/3: Detected {municipality_name}, {state} "
                f"({detected_municipality.get('confidence', 'UNKNOWN')} confidence)"
            )

            # =================================================================
            # STAGE 2: Scraper Dispatch (BR-4)
            # =================================================================
            self.emit_event("processing", "Stage 2/3: Running CityScraper pipeline...")

            br4_result = await self._run_scraper_dispatch(
                municipality_name=municipality_name,
                state=state,
                table_mode=table_mode
            )

            if not br4_result['success']:
                return self._create_error_result(
                    hotdog_session_data,
                    f"Scraper dispatch failed: {br4_result.get('error', 'Unknown error')}",
                    start_time,
                    detected_municipality=detected_municipality,
                    scraper_result=br4_result.get('data', {})
                )

            if self._cancelled:
                return self._create_cancelled_result(
                    hotdog_session_data, start_time,
                    detected_municipality=detected_municipality
                )

            scraper_result = br4_result['data']
            self.emit_event(
                "completed",
                f"Stage 2/3: CityScraper extraction complete"
            )

            # =================================================================
            # STAGE 3: Data Merge (BR-3)
            # =================================================================
            self.emit_event("processing", "Stage 3/3: Merging research with document analysis...")

            br3_result = await self._run_data_merge(
                hotdog_results=hotdog_session_data,
                scraper_results=scraper_result,
                detected_municipality=detected_municipality
            )

            if not br3_result['success']:
                # Data merge failure is non-fatal - we still have scraper results
                logger.warning(f"UC-1 data merge failed: {br3_result.get('error')}")
                merged_result = None
                merge_error = br3_result.get('error', 'Merge failed')
            else:
                merged_result = br3_result['data']
                merge_error = None

            self.completed_at = datetime.now()
            elapsed = time.time() - start_time

            # Calculate enrichment statistics
            enrichment_stats = self._calculate_enrichment_stats(
                hotdog_session_data,
                scraper_result,
                merged_result
            )

            # Build completion message
            if merged_result:
                self.emit_event(
                    "completed",
                    f"Document enrichment complete: {enrichment_stats['fields_added']} fields added, "
                    f"{enrichment_stats['sources_added']} sources added ({elapsed:.1f}s)",
                    is_completed=True
                )
            else:
                self.emit_event(
                    "completed",
                    f"Document enrichment partially complete: merge step failed ({elapsed:.1f}s)",
                    is_completed=True
                )

            return {
                'success': True,
                'session_id': self.session_id,
                'original_hotdog_data': hotdog_session_data,
                'detected_municipality': detected_municipality,
                'scraper_result': scraper_result,
                'merged_result': merged_result,
                'enrichment_stats': enrichment_stats,
                'merge_error': merge_error,
                'processing_time_seconds': elapsed,
                'completed_at': self.completed_at.isoformat()
            }

        except (SystemExit, KeyboardInterrupt):
            # Re-raise critical exceptions
            raise
        except Exception as e:
            logger.exception(f"UC-1 unexpected error: {e}")
            return self._create_error_result(
                hotdog_session_data,
                f"Unexpected error: {type(e).__name__}: {str(e)[:200]}",
                start_time
            )

    def _validate_inputs(
        self,
        hotdog_session_data: Any,
        document_content: Any,
        document_filename: Any
    ) -> List[str]:
        """
        Validate all inputs with type checks.

        Args:
            hotdog_session_data: Expected dict with HOTDOG results
            document_content: Expected string with document text
            document_filename: Expected string with filename

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        # Validate hotdog_session_data
        if not isinstance(hotdog_session_data, dict):
            errors.append(
                f"hotdog_session_data must be dict, got {type(hotdog_session_data).__name__}"
            )

        # Validate document_content
        if not isinstance(document_content, str):
            errors.append(
                f"document_content must be string, got {type(document_content).__name__}"
            )
        elif not document_content.strip():
            errors.append("document_content cannot be empty")
        elif len(document_content.strip()) < 100:
            errors.append(
                f"document_content too short ({len(document_content.strip())} chars, minimum 100)"
            )

        # Validate document_filename
        if not isinstance(document_filename, str):
            errors.append(
                f"document_filename must be string, got {type(document_filename).__name__}"
            )

        return errors

    async def _run_municipality_detection(
        self,
        document_content: str,
        document_filename: str,
        hotdog_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run BR-1 Municipality Detector.

        Args:
            document_content: Raw document text
            document_filename: Original filename
            hotdog_metadata: Metadata from HOTDOG (may contain location hints)

        Returns:
            Dict with 'success', 'data', 'error' keys
        """
        agent = None
        try:
            agent = MunicipalityDetectorAgent(
                config=self.config,
                event_callback=self.event_callback
            )

            request = AgentRequest(
                agent_id="br-1",
                task=f"detect-municipality-{self.session_id}",
                input_data={
                    'document_content': document_content,
                    'document_filename': document_filename,
                    'document_metadata': hotdog_metadata
                }
            )

            response = await agent.process(request)

            self.stage_results[self.STAGE_MUNICIPALITY_DETECTION] = {
                'success': response.success,
                'response': response,
                'processing_time': response.processing_time_seconds
            }

            if response.success:
                return {
                    'success': True,
                    'data': response.output_data,
                    'error': None
                }
            else:
                error_msg = "; ".join(response.errors) if response.errors else "Detection failed"
                return {
                    'success': False,
                    'data': response.output_data,
                    'error': error_msg
                }

        except Exception as e:
            logger.exception(f"UC-1 BR-1 error: {e}")
            return {
                'success': False,
                'data': {},
                'error': f"Municipality detection error: {str(e)[:200]}"
            }
        finally:
            if agent:
                try:
                    await agent.cleanup()
                except Exception as cleanup_error:
                    logger.warning(f"UC-1 BR-1 cleanup error: {cleanup_error}")

    async def _run_scraper_dispatch(
        self,
        municipality_name: str,
        state: str,
        table_mode: str
    ) -> Dict[str, Any]:
        """
        Run BR-4 Scraper Dispatcher (which orchestrates PF-O -> EX-O -> PR-3).

        Args:
            municipality_name: Detected city name
            state: Detected state name
            table_mode: Target table mode

        Returns:
            Dict with 'success', 'data', 'error' keys
        """
        agent = None
        try:
            agent = ScraperDispatcherAgent(
                config=self.config,
                event_callback=self.event_callback
            )

            request = AgentRequest(
                agent_id="br-4",
                task=f"dispatch-scraper-{self.session_id}",
                input_data={
                    'municipality': {
                        'city': municipality_name,
                        'state': state
                    },
                    'table_mode': table_mode,
                    'session_id': self.session_id
                }
            )

            response = await agent.process(request)

            self.stage_results[self.STAGE_SCRAPER_DISPATCH] = {
                'success': response.success,
                'response': response,
                'processing_time': response.processing_time_seconds
            }

            if response.success:
                return {
                    'success': True,
                    'data': response.output_data,
                    'error': None
                }
            else:
                error_msg = "; ".join(response.errors) if response.errors else "Dispatch failed"
                return {
                    'success': False,
                    'data': response.output_data,
                    'error': error_msg
                }

        except Exception as e:
            logger.exception(f"UC-1 BR-4 error: {e}")
            return {
                'success': False,
                'data': {},
                'error': f"Scraper dispatch error: {str(e)[:200]}"
            }
        finally:
            if agent:
                try:
                    await agent.cleanup()
                except Exception as cleanup_error:
                    logger.warning(f"UC-1 BR-4 cleanup error: {cleanup_error}")

    async def _run_data_merge(
        self,
        hotdog_results: Dict[str, Any],
        scraper_results: Dict[str, Any],
        detected_municipality: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run BR-3 Data Merger.

        Args:
            hotdog_results: Original HOTDOG analysis results
            scraper_results: CityScraper extraction results (from BR-4/PR-3)
            detected_municipality: Municipality detection results from BR-1

        Returns:
            Dict with 'success', 'data', 'error' keys
        """
        agent = None
        try:
            agent = DataMergerAgent(
                config=self.config,
                event_callback=self.event_callback
            )

            # Build gap analysis from detected municipality and results
            # This helps BR-3 understand what gaps we were trying to fill
            gap_analysis = self._build_gap_analysis(
                hotdog_results,
                detected_municipality
            )

            request = AgentRequest(
                agent_id="br-3",
                task=f"merge-data-{self.session_id}",
                input_data={
                    'hotdog_results': hotdog_results,
                    'scraper_results': scraper_results.get('presentation_result', {}),
                    'gap_analysis': gap_analysis,
                    'merge_mode': 'supplement'  # Enrich, don't replace
                }
            )

            response = await agent.process(request)

            self.stage_results[self.STAGE_DATA_MERGE] = {
                'success': response.success,
                'response': response,
                'processing_time': response.processing_time_seconds
            }

            if response.success:
                return {
                    'success': True,
                    'data': response.output_data,
                    'error': None
                }
            else:
                error_msg = "; ".join(response.errors) if response.errors else "Merge failed"
                return {
                    'success': False,
                    'data': response.output_data,
                    'error': error_msg
                }

        except Exception as e:
            logger.exception(f"UC-1 BR-3 error: {e}")
            return {
                'success': False,
                'data': {},
                'error': f"Data merge error: {str(e)[:200]}"
            }
        finally:
            if agent:
                try:
                    await agent.cleanup()
                except Exception as cleanup_error:
                    logger.warning(f"UC-1 BR-3 cleanup error: {cleanup_error}")

    def _build_gap_analysis(
        self,
        hotdog_results: Dict[str, Any],
        detected_municipality: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build a gap analysis structure for BR-3.

        This helps the merger understand what HOTDOG couldn't answer
        so it can prioritize filling those gaps.

        Args:
            hotdog_results: HOTDOG analysis results
            detected_municipality: BR-1 detection results

        Returns:
            Gap analysis dict compatible with BR-3 input
        """
        unanswered = hotdog_results.get('unanswered_questions', [])

        # Convert unanswered to answerable_gaps format
        answerable_gaps = []
        for i, question in enumerate(unanswered[:20]):  # Limit for performance
            if isinstance(question, str):
                answerable_gaps.append({
                    'question': question,
                    'priority': 'HIGH' if i < 5 else 'MEDIUM',
                    'data_source': 'cityscraper'
                })
            elif isinstance(question, dict):
                answerable_gaps.append({
                    'question': question.get('question', str(question)),
                    'priority': question.get('priority', 'MEDIUM'),
                    'data_source': 'cityscraper'
                })

        return {
            'enrichment_recommendation': 'ENRICH',
            'recommended_table_mode': 'systems_info',
            'answerable_gaps': answerable_gaps,
            'unanswerable_gaps': [],
            'analysis_notes': (
                f"Auto-generated gap analysis from HOTDOG session. "
                f"Municipality: {detected_municipality.get('municipality_name', 'Unknown')}, "
                f"{detected_municipality.get('state', 'Unknown')}"
            )
        }

    def _calculate_enrichment_stats(
        self,
        hotdog_data: Dict[str, Any],
        scraper_result: Dict[str, Any],
        merged_result: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate statistics about the enrichment.

        Args:
            hotdog_data: Original HOTDOG results
            scraper_result: CityScraper extraction results
            merged_result: Merged data (may be None if merge failed)

        Returns:
            Dict with enrichment statistics
        """
        stats = {
            'fields_added': 0,
            'fields_enhanced': 0,
            'sources_added': 0,
            'gaps_filled': 0,
            'gaps_remaining': 0
        }

        # Count from scraper results
        extraction_result = scraper_result.get('extraction_result', {})
        stats['sources_added'] = extraction_result.get('total_sources_searched', 0)
        stats['fields_added'] = extraction_result.get('total_data_points_extracted', 0)

        # Count from merged results if available
        if merged_result:
            stats['gaps_filled'] = len(merged_result.get('gaps_filled', []))
            stats['gaps_remaining'] = len(merged_result.get('gaps_remaining', []))

            # Count enhanced fields (combined answers)
            source_summary = merged_result.get('source_summary', {})
            stats['fields_enhanced'] = source_summary.get('combined_answers', 0)

        return stats

    def _create_error_result(
        self,
        hotdog_data: Dict[str, Any],
        error_message: str,
        start_time: float,
        detected_municipality: Optional[Dict[str, Any]] = None,
        scraper_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an error result with partial data if available.

        Args:
            hotdog_data: Original HOTDOG data
            error_message: Error description
            start_time: Pipeline start time
            detected_municipality: BR-1 result if available
            scraper_result: BR-4 result if available

        Returns:
            Error result dict
        """
        self.completed_at = datetime.now()
        elapsed = time.time() - start_time

        self.emit_event("failed", f"Document enrichment failed: {error_message}", is_completed=True)

        return {
            'success': False,
            'session_id': self.session_id,
            'original_hotdog_data': hotdog_data,
            'detected_municipality': detected_municipality,
            'scraper_result': scraper_result,
            'merged_result': None,
            'enrichment_stats': {
                'fields_added': 0,
                'fields_enhanced': 0,
                'sources_added': 0,
                'gaps_filled': 0,
                'gaps_remaining': 0
            },
            'error': error_message,
            'processing_time_seconds': elapsed,
            'completed_at': self.completed_at.isoformat()
        }

    def _create_cancelled_result(
        self,
        hotdog_data: Dict[str, Any],
        start_time: float,
        detected_municipality: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a cancelled result.

        Args:
            hotdog_data: Original HOTDOG data
            start_time: Pipeline start time
            detected_municipality: BR-1 result if available

        Returns:
            Cancelled result dict
        """
        self.completed_at = datetime.now()
        elapsed = time.time() - start_time

        self.emit_event("cancelled", "Document enrichment cancelled by user", is_completed=True)

        return {
            'success': False,
            'session_id': self.session_id,
            'original_hotdog_data': hotdog_data,
            'detected_municipality': detected_municipality,
            'scraper_result': None,
            'merged_result': None,
            'enrichment_stats': {
                'fields_added': 0,
                'fields_enhanced': 0,
                'sources_added': 0,
                'gaps_filled': 0,
                'gaps_remaining': 0
            },
            'error': 'Pipeline cancelled by user',
            'processing_time_seconds': elapsed,
            'completed_at': self.completed_at.isoformat()
        }

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
            total_duration += result.get('processing_time', 0.0)
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
