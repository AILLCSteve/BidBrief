"""
Comparative Intelligence Orchestrator (UC-3)

Orchestrates parallel municipal research across multiple municipalities,
comparing results and generating comparative analysis reports.

Pipeline:
1. Validate input list (2-5 municipalities)
2. Run UC-2 (Standalone Research) for each municipality in parallel
3. Aggregate all results
4. Generate comparison tables
5. Produce Comparative Intelligence Report

CRITICAL: This orchestrator is designed for comparing multiple municipalities
side-by-side to identify patterns, rankings, and differences.

Version: 1.0.0
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List, Tuple

from services.scraper.config import get_config, ScraperConfig
from services.scraper.models import (
    AgentActivityEvent,
)
from services.scraper.orchestrators.standalone_research import StandaloneResearchOrchestrator

logger = logging.getLogger(__name__)


class ComparativeIntelligenceOrchestrator:
    """
    UC-3: Comparative Intelligence Orchestrator

    Enables parallel research across multiple municipalities with
    comparative analysis. User provides a list of 2-5 municipalities,
    and the orchestrator runs UC-2 for each in parallel, then generates
    comparison tables and rankings.

    Flow:
        User enters ["Springfield, IL", "Decatur, IL", "Peoria, IL"]
                     |
            For each: UC-2 (PF-O -> EX-O -> PR-3) in parallel
                     |
            Aggregate all results
                     |
            Generate comparison tables
                     |
        Comparative Intelligence Report
    """

    ORCHESTRATOR_ID = "uc-3"
    ORCHESTRATOR_NAME = "Comparative Intelligence"
    ORCHESTRATOR_VERSION = "1.0.0"

    # Validation constraints
    MIN_MUNICIPALITIES = 2
    MAX_MUNICIPALITIES = 5

    # Metrics for comparison
    COMPARISON_METRICS = [
        "sanitary_sewer_pipe",
        "storm_drain_pipe",
        "storm_drain_assets",
        "equipment_owned",
        "sewage_incidents",
        "storm_incidents",
        "sources_found",
        "fields_extracted",
    ]

    def __init__(
        self,
        config: Optional[ScraperConfig] = None,
        event_callback: Optional[Callable[[AgentActivityEvent], None]] = None
    ):
        """
        Initialize the Comparative Intelligence Orchestrator.

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

        # Results storage
        self.individual_results: Dict[str, Dict[str, Any]] = {}
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

        # Store event
        self.agent_events.append(event)

        if self.event_callback:
            self.event_callback(event)
        logger.info(f"UC-3: [{status}] {message}")

    def _create_event_collector(self, municipality: str) -> Callable[[AgentActivityEvent], None]:
        """
        Create an event collector that prefixes events with municipality name.

        Args:
            municipality: Municipality name for prefixing

        Returns:
            Callable that collects events
        """
        def collector(event: AgentActivityEvent):
            # Prefix the message with municipality
            prefixed_event = AgentActivityEvent(
                agent_id=event.agent_id,
                agent_name=event.agent_name,
                status=event.status,
                message=f"[{municipality}] {event.message}",
                is_active=event.is_active,
                is_completed=event.is_completed,
                timestamp=event.timestamp
            )
            self.agent_events.append(prefixed_event)
            if self.event_callback:
                self.event_callback(prefixed_event)
        return collector

    def cancel(self):
        """Request cancellation of the pipeline."""
        self._cancelled = True
        logger.info("UC-3: Cancellation requested")

    async def run(
        self,
        municipalities: List[str],
        table_mode: str = "systems_info",
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run comparative research across multiple municipalities.

        Args:
            municipalities: List of municipality strings (2-5 cities)
            table_mode: Target table type ("systems_info", "public_bids", or "both")
            session_id: Optional session ID for tracking (generated if not provided)

        Returns:
            Dict containing:
                - municipalities: List of processed municipalities
                - individual_results: Dict mapping city to UC-2 result
                - comparison_tables: Generated comparison tables
                - rankings: Comparative rankings
                - cross_patterns: Common patterns found
                - statistics: { total_municipalities, successful, failed, sources_found, processing_time }
                - success: bool (True if at least 2 municipalities succeeded)
                - error: Optional error message if failed
        """
        start_time = time.time()
        self.session_id = session_id or f"uc3-{uuid.uuid4().hex[:12]}"
        self.started_at = datetime.now()
        self._cancelled = False
        self.individual_results = {}
        self.agent_events = []

        # Input validation
        validation_errors = self._validate_inputs(municipalities, table_mode)
        if validation_errors:
            return self._create_error_result(
                f"Input validation failed: {'; '.join(validation_errors)}",
                start_time
            )

        # Normalize municipalities list
        normalized_municipalities = [m.strip() for m in municipalities if isinstance(m, str) and m.strip()]

        self.emit_event(
            "processing",
            f"Starting comparative research for {len(normalized_municipalities)} municipalities: "
            f"{', '.join(normalized_municipalities)}"
        )

        try:
            # =================================================================
            # STAGE 1: Run UC-2 for each municipality in parallel
            # =================================================================
            self.emit_event(
                "processing",
                f"Stage 1/2: Running parallel research for {len(normalized_municipalities)} municipalities..."
            )

            # Create tasks for parallel execution
            research_tasks = []
            for municipality in normalized_municipalities:
                task = self._run_single_research(
                    municipality=municipality,
                    table_mode=table_mode
                )
                research_tasks.append(task)

            # Execute all research tasks in parallel
            results = await asyncio.gather(*research_tasks, return_exceptions=True)

            # Process results
            successful_count = 0
            failed_count = 0
            total_sources = 0
            total_fields = 0

            for i, (municipality, result) in enumerate(zip(normalized_municipalities, results)):
                if isinstance(result, Exception):
                    # Task raised an exception
                    self.individual_results[municipality] = {
                        'success': False,
                        'error': f"{type(result).__name__}: {str(result)[:200]}"
                    }
                    failed_count += 1
                    logger.error(f"UC-3: Research failed for {municipality}: {result}")
                elif isinstance(result, dict):
                    self.individual_results[municipality] = result
                    if result.get('success'):
                        successful_count += 1
                        stats = result.get('statistics', {})
                        total_sources += stats.get('sources_found', 0)
                        total_fields += stats.get('fields_extracted', 0)
                    else:
                        failed_count += 1
                else:
                    self.individual_results[municipality] = {
                        'success': False,
                        'error': f"Unexpected result type: {type(result).__name__}"
                    }
                    failed_count += 1

            if self._cancelled:
                return self._create_cancelled_result(start_time, normalized_municipalities)

            self.emit_event(
                "completed",
                f"Stage 1/2: Parallel research complete - "
                f"{successful_count} succeeded, {failed_count} failed"
            )

            # Check if we have enough successful results
            if successful_count < self.MIN_MUNICIPALITIES:
                return self._create_error_result(
                    f"Insufficient successful research results: {successful_count} succeeded, "
                    f"minimum {self.MIN_MUNICIPALITIES} required",
                    start_time,
                    partial_results=self.individual_results,
                    municipalities=normalized_municipalities
                )

            # =================================================================
            # STAGE 2: Generate comparison tables and rankings
            # =================================================================
            self.emit_event("processing", "Stage 2/2: Generating comparison tables and rankings...")

            comparison_tables = self._generate_comparison_tables()
            rankings = self._generate_rankings()
            cross_patterns = self._identify_cross_patterns()

            self.completed_at = datetime.now()
            elapsed = time.time() - start_time

            # Calculate final statistics
            statistics = {
                'total_municipalities': len(normalized_municipalities),
                'successful': successful_count,
                'failed': failed_count,
                'sources_found': total_sources,
                'fields_extracted': total_fields,
                'processing_time': elapsed,
            }

            self.emit_event(
                "completed",
                f"Comparative analysis complete: {successful_count}/{len(normalized_municipalities)} "
                f"municipalities, {total_fields} total fields ({elapsed:.1f}s)",
                is_completed=True
            )

            return {
                'success': True,
                'session_id': self.session_id,
                'municipalities': normalized_municipalities,
                'individual_results': self.individual_results,
                'comparison_tables': comparison_tables,
                'rankings': rankings,
                'cross_patterns': cross_patterns,
                'statistics': statistics,
                'processing_time_seconds': elapsed,
                'completed_at': self.completed_at.isoformat()
            }

        except (SystemExit, KeyboardInterrupt):
            # Re-raise critical exceptions
            raise
        except Exception as e:
            logger.exception(f"UC-3 unexpected error: {e}")
            return self._create_error_result(
                f"Unexpected error: {type(e).__name__}: {str(e)[:200]}",
                start_time,
                partial_results=self.individual_results,
                municipalities=normalized_municipalities if 'normalized_municipalities' in locals() else []
            )

    def _validate_inputs(
        self,
        municipalities: Any,
        table_mode: Any
    ) -> List[str]:
        """
        Validate all inputs with type checks.

        Args:
            municipalities: Expected list of municipality strings
            table_mode: Expected string with table mode

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        # Validate municipalities is a list
        if not isinstance(municipalities, list):
            errors.append(
                f"municipalities must be a list, got {type(municipalities).__name__}"
            )
            return errors  # Can't continue validation

        # Validate list length
        if len(municipalities) < self.MIN_MUNICIPALITIES:
            errors.append(
                f"municipalities list too short: {len(municipalities)} items, "
                f"minimum {self.MIN_MUNICIPALITIES} required"
            )
        elif len(municipalities) > self.MAX_MUNICIPALITIES:
            errors.append(
                f"municipalities list too long: {len(municipalities)} items, "
                f"maximum {self.MAX_MUNICIPALITIES} allowed"
            )

        # Validate each municipality entry
        valid_municipalities = 0
        for i, m in enumerate(municipalities):
            if not isinstance(m, str):
                errors.append(
                    f"municipalities[{i}] must be string, got {type(m).__name__}"
                )
            elif not m.strip():
                errors.append(f"municipalities[{i}] cannot be empty")
            elif len(m.strip()) < 3:
                errors.append(
                    f"municipalities[{i}] too short ({len(m.strip())} chars, minimum 3)"
                )
            else:
                valid_municipalities += 1

        # Check we have enough valid entries after validation
        if valid_municipalities < self.MIN_MUNICIPALITIES and not errors:
            errors.append(
                f"Not enough valid municipalities: {valid_municipalities}, "
                f"minimum {self.MIN_MUNICIPALITIES} required"
            )

        # Check for duplicates
        normalized = [m.strip().lower() for m in municipalities if isinstance(m, str)]
        if len(normalized) != len(set(normalized)):
            errors.append("municipalities list contains duplicates")

        # Validate table_mode
        if not isinstance(table_mode, str):
            errors.append(
                f"table_mode must be string, got {type(table_mode).__name__}"
            )
        elif table_mode.strip().lower() not in ("systems_info", "public_bids", "both", "systems", "info", "bids"):
            errors.append(
                f"table_mode must be one of ('systems_info', 'public_bids', 'both'), got '{table_mode}'"
            )

        return errors

    async def _run_single_research(
        self,
        municipality: str,
        table_mode: str
    ) -> Dict[str, Any]:
        """
        Run UC-2 for a single municipality.

        Args:
            municipality: Municipality string
            table_mode: Table mode string

        Returns:
            UC-2 result dict
        """
        orchestrator = None
        try:
            orchestrator = StandaloneResearchOrchestrator(
                config=self.config,
                event_callback=self._create_event_collector(municipality)
            )

            result = await orchestrator.run(
                municipality_input=municipality,
                table_mode=table_mode,
                session_id=f"{self.session_id}-{municipality.replace(' ', '_').replace(',', '')[:20]}"
            )

            return result

        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception as e:
            logger.exception(f"UC-3: Error researching {municipality}: {e}")
            return {
                'success': False,
                'municipality': municipality,
                'error': f"{type(e).__name__}: {str(e)[:200]}"
            }

    def _generate_comparison_tables(self) -> Dict[str, Any]:
        """
        Generate comparison tables from individual results.

        Returns:
            Dict containing various comparison table data
        """
        tables = {
            'side_by_side': [],
            'data_availability': {},
            'source_comparison': {},
        }

        successful_results = {
            k: v for k, v in self.individual_results.items()
            if v.get('success')
        }

        if not successful_results:
            return tables

        # Build side-by-side comparison
        municipalities = list(successful_results.keys())
        tables['municipalities'] = municipalities

        # Compare key metrics
        metrics_comparison = {}
        for metric in self.COMPARISON_METRICS:
            metrics_comparison[metric] = {}
            for muni, result in successful_results.items():
                value = self._extract_metric_value(result, metric)
                metrics_comparison[metric][muni] = value

        tables['metrics_comparison'] = metrics_comparison

        # Data availability matrix
        for muni, result in successful_results.items():
            stats = result.get('statistics', {})
            tables['data_availability'][muni] = {
                'sources_found': stats.get('sources_found', 0),
                'fields_extracted': stats.get('fields_extracted', 0),
                'data_gaps': stats.get('data_gaps_count', 0),
                'conflicts': stats.get('conflicts_count', 0),
            }

        # Source comparison
        for muni, result in successful_results.items():
            preflight = result.get('preflight_result', {})
            source_map = preflight.get('source_map', {})
            tables['source_comparison'][muni] = {
                'has_official_website': bool(source_map.get('official_website')),
                'has_public_works_page': bool(source_map.get('public_works_page')),
                'has_procurement_page': bool(source_map.get('procurement_page')),
                'has_gis_portal': bool(source_map.get('gis_portal')),
                'cip_documents': source_map.get('cip_documents_count', 0),
                'compliance_sources': source_map.get('compliance_sources_count', 0),
            }

        return tables

    def _extract_metric_value(self, result: Dict[str, Any], metric: str) -> Any:
        """
        Extract a metric value from a UC-2 result.

        Args:
            result: UC-2 result dict
            metric: Metric name to extract

        Returns:
            Extracted value or None
        """
        # Check statistics first
        stats = result.get('statistics', {})
        if metric in stats:
            return stats[metric]

        # Check extraction result
        extraction = result.get('extraction_result', {})
        if metric in extraction:
            return extraction[metric]

        # Check presentation result for table data
        presentation = result.get('presentation_result', {})
        if presentation:
            # Try to find in rendered tables
            tables = presentation.get('tables', {})
            for table_name, table_data in tables.items():
                if metric in table_data:
                    return table_data[metric]

        return None

    def _generate_rankings(self) -> Dict[str, List[Tuple[str, Any]]]:
        """
        Generate rankings for various metrics.

        Returns:
            Dict mapping metric names to ranked lists of (municipality, value) tuples
        """
        rankings = {}

        successful_results = {
            k: v for k, v in self.individual_results.items()
            if v.get('success')
        }

        if not successful_results:
            return rankings

        # Rank by sources found
        sources_data = []
        for muni, result in successful_results.items():
            stats = result.get('statistics', {})
            sources_data.append((muni, stats.get('sources_found', 0)))
        rankings['by_sources_found'] = sorted(
            sources_data, key=lambda x: x[1], reverse=True
        )

        # Rank by fields extracted
        fields_data = []
        for muni, result in successful_results.items():
            stats = result.get('statistics', {})
            fields_data.append((muni, stats.get('fields_extracted', 0)))
        rankings['by_fields_extracted'] = sorted(
            fields_data, key=lambda x: x[1], reverse=True
        )

        # Rank by data completeness (fewer gaps = better)
        gaps_data = []
        for muni, result in successful_results.items():
            stats = result.get('statistics', {})
            gaps_data.append((muni, stats.get('data_gaps_count', 0)))
        rankings['by_data_completeness'] = sorted(
            gaps_data, key=lambda x: x[1]  # Lower is better
        )

        # Rank by processing time (faster = better)
        time_data = []
        for muni, result in successful_results.items():
            proc_time = result.get('processing_time_seconds', 0)
            time_data.append((muni, round(proc_time, 2)))
        rankings['by_processing_time'] = sorted(
            time_data, key=lambda x: x[1]  # Lower is better
        )

        return rankings

    def _identify_cross_patterns(self) -> Dict[str, Any]:
        """
        Identify patterns that appear across multiple municipalities.

        Returns:
            Dict containing identified patterns
        """
        patterns = {
            'common_data_gaps': [],
            'common_source_types': [],
            'regional_patterns': [],
            'infrastructure_similarities': [],
        }

        successful_results = {
            k: v for k, v in self.individual_results.items()
            if v.get('success')
        }

        if len(successful_results) < 2:
            return patterns

        # Find common data gaps
        all_gaps = {}
        for muni, result in successful_results.items():
            extraction = result.get('extraction_result', {})
            gaps = extraction.get('data_gaps', [])
            for gap in gaps:
                if gap not in all_gaps:
                    all_gaps[gap] = []
                all_gaps[gap].append(muni)

        # Gaps that appear in 50%+ of municipalities are "common"
        threshold = len(successful_results) / 2
        for gap, municipalities in all_gaps.items():
            if len(municipalities) >= threshold:
                patterns['common_data_gaps'].append({
                    'gap': gap,
                    'municipalities': municipalities,
                    'frequency': f"{len(municipalities)}/{len(successful_results)}"
                })

        # Find common source availability
        source_availability = {
            'official_website': 0,
            'public_works_page': 0,
            'procurement_page': 0,
            'gis_portal': 0,
        }

        for muni, result in successful_results.items():
            preflight = result.get('preflight_result', {})
            source_map = preflight.get('source_map', {})
            for source_type in source_availability:
                if source_map.get(source_type):
                    source_availability[source_type] += 1

        for source_type, count in source_availability.items():
            if count >= threshold:
                patterns['common_source_types'].append({
                    'source_type': source_type,
                    'count': count,
                    'total': len(successful_results),
                    'percentage': round(count / len(successful_results) * 100, 1)
                })

        # Regional pattern detection (same state)
        states = {}
        for muni, result in successful_results.items():
            muni_data = result.get('municipality', {})
            state = muni_data.get('state', 'Unknown')
            if state not in states:
                states[state] = []
            states[state].append(muni)

        for state, municipalities in states.items():
            if len(municipalities) >= 2:
                patterns['regional_patterns'].append({
                    'state': state,
                    'municipalities': municipalities,
                    'count': len(municipalities)
                })

        return patterns

    def _create_error_result(
        self,
        error_message: str,
        start_time: float,
        partial_results: Optional[Dict[str, Dict[str, Any]]] = None,
        municipalities: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create an error result with partial data if available.

        Args:
            error_message: Error description
            start_time: Pipeline start time
            partial_results: Individual results if available
            municipalities: List of municipalities if available

        Returns:
            Error result dict
        """
        self.completed_at = datetime.now()
        elapsed = time.time() - start_time

        self.emit_event("failed", f"Comparative analysis failed: {error_message}", is_completed=True)

        # Count successes/failures in partial results
        successful = 0
        failed = 0
        if partial_results:
            for result in partial_results.values():
                if result.get('success'):
                    successful += 1
                else:
                    failed += 1

        return {
            'success': False,
            'session_id': self.session_id,
            'municipalities': municipalities or [],
            'individual_results': partial_results or {},
            'comparison_tables': {},
            'rankings': {},
            'cross_patterns': {},
            'statistics': {
                'total_municipalities': len(municipalities) if municipalities else 0,
                'successful': successful,
                'failed': failed,
                'sources_found': 0,
                'processing_time': elapsed,
            },
            'error': error_message,
            'processing_time_seconds': elapsed,
            'completed_at': self.completed_at.isoformat()
        }

    def _create_cancelled_result(
        self,
        start_time: float,
        municipalities: List[str]
    ) -> Dict[str, Any]:
        """
        Create a cancelled result.

        Args:
            start_time: Pipeline start time
            municipalities: List of municipalities

        Returns:
            Cancelled result dict
        """
        self.completed_at = datetime.now()
        elapsed = time.time() - start_time

        self.emit_event("cancelled", "Comparative analysis cancelled by user", is_completed=True)

        # Count successes/failures in partial results
        successful = 0
        failed = 0
        for result in self.individual_results.values():
            if result.get('success'):
                successful += 1
            else:
                failed += 1

        return {
            'success': False,
            'session_id': self.session_id,
            'municipalities': municipalities,
            'individual_results': self.individual_results,
            'comparison_tables': {},
            'rankings': {},
            'cross_patterns': {},
            'statistics': {
                'total_municipalities': len(municipalities),
                'successful': successful,
                'failed': failed,
                'sources_found': 0,
                'processing_time': elapsed,
            },
            'error': 'Comparative analysis cancelled by user',
            'processing_time_seconds': elapsed,
            'completed_at': self.completed_at.isoformat()
        }

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get pipeline execution statistics.

        Returns:
            Dict with execution statistics
        """
        successful = 0
        failed = 0
        total_sources = 0
        total_fields = 0

        for result in self.individual_results.values():
            if result.get('success'):
                successful += 1
                stats = result.get('statistics', {})
                total_sources += stats.get('sources_found', 0)
                total_fields += stats.get('fields_extracted', 0)
            else:
                failed += 1

        duration = 0.0
        if self.started_at and self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()

        return {
            'orchestrator': self.ORCHESTRATOR_NAME,
            'orchestrator_id': self.ORCHESTRATOR_ID,
            'version': self.ORCHESTRATOR_VERSION,
            'session_id': self.session_id,
            'total_municipalities': len(self.individual_results),
            'successful_municipalities': successful,
            'failed_municipalities': failed,
            'total_sources_found': total_sources,
            'total_fields_extracted': total_fields,
            'total_duration_seconds': duration,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
