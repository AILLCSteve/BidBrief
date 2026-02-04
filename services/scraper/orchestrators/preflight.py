"""
Pre-flight Orchestrator (PF-O)

Orchestrates the complete pre-flight validation pipeline by dispatching
PF-1 through PF-5 agents in sequence and aggregating results.

Pipeline:
1. PF-1: Municipality Normalizer - Validate and normalize municipality identity
2. PF-2: Jurisdiction Mapper - Determine system owners/operators
3. PF-3: Source Discovery - Build baseline source map
4. PF-4: Terminology Extractor - Lock local naming conventions
5. PF-5: Readiness Validator - Aggregate and determine extraction readiness

Responsibilities:
- Sequential agent dispatch with dependency handling
- Error handling and retry logic for transient failures
- Progress tracking and event emission
- Aggregation of all results into PreflightResult
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

from services.scraper.config import get_config, ScraperConfig
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    PreflightResult,
    PreflightStatus,
    Municipality,
    TableMode,
    AgentActivityEvent
)
from services.scraper.agents.preflight import (
    MunicipalityNormalizerAgent,
    JurisdictionMapperAgent,
    SourceDiscoveryAgent,
    TerminologyExtractorAgent,
    ReadinessValidatorAgent
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineStage:
    """Configuration for a pipeline stage."""
    agent_id: str
    agent_name: str
    agent_class: type
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


class PreflightOrchestrator:
    """
    Orchestrates the pre-flight validation pipeline.

    Dispatches PF-1 through PF-5 in sequence, handling errors and aggregating
    results into a final PreflightResult.
    """

    ORCHESTRATOR_ID = "pf-o"
    ORCHESTRATOR_NAME = "Pre-flight Orchestrator"
    ORCHESTRATOR_VERSION = "1.0.0"

    # Pipeline configuration
    PIPELINE_STAGES = [
        PipelineStage("pf-1", "Municipality Normalizer", MunicipalityNormalizerAgent, required=True),
        PipelineStage("pf-2", "Jurisdiction Mapper", JurisdictionMapperAgent, required=True),
        PipelineStage("pf-3", "Source Discovery", SourceDiscoveryAgent, required=True),
        PipelineStage("pf-4", "Terminology Extractor", TerminologyExtractorAgent, required=False),
        PipelineStage("pf-5", "Readiness Validator", ReadinessValidatorAgent, required=True),
    ]

    def __init__(
        self,
        config: Optional[ScraperConfig] = None,
        event_callback: Optional[Callable[[AgentActivityEvent], None]] = None
    ):
        """
        Initialize the Pre-flight Orchestrator.

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
        logger.info(f"PF-O: {message}")

    def cancel(self):
        """Request cancellation of the pipeline."""
        self._cancelled = True
        logger.info("PF-O: Cancellation requested")

    async def run(
        self,
        municipality_input: str,
        table_mode: str = "Municipal Systems Information"
    ) -> PreflightResult:
        """
        Run the complete pre-flight pipeline.

        Args:
            municipality_input: Raw municipality input (e.g., "Springfield, IL")
            table_mode: Target table type

        Returns:
            PreflightResult with aggregated validation results
        """
        self.started_at = datetime.now()
        self._cancelled = False
        self.results = {}

        self.emit_event(f"Starting pre-flight for: {municipality_input}")

        try:
            # Stage 1: Municipality Normalizer (PF-1)
            pf1_result = await self._run_stage(
                stage=self.PIPELINE_STAGES[0],
                input_data={'municipality_input': municipality_input}
            )

            if not pf1_result.success:
                return self._create_failed_result(
                    municipality_input, table_mode,
                    f"Municipality normalization failed: {pf1_result.error}"
                )

            # Extract normalized municipality info
            pf1_output = pf1_result.response.output_data
            normalized = pf1_output.get('normalized', {})
            municipality_name = normalized.get('city', municipality_input)
            state = normalized.get('state', '')

            if self._cancelled:
                return self._create_cancelled_result(municipality_name, state, table_mode)

            # Stage 2: Jurisdiction Mapper (PF-2)
            pf2_result = await self._run_stage(
                stage=self.PIPELINE_STAGES[1],
                input_data={
                    'municipality_name': municipality_name,
                    'state': state
                }
            )

            if not pf2_result.success and self.PIPELINE_STAGES[1].required:
                return self._create_failed_result(
                    municipality_name, table_mode,
                    f"Jurisdiction mapping failed: {pf2_result.error}",
                    state=state
                )

            if self._cancelled:
                return self._create_cancelled_result(municipality_name, state, table_mode)

            # Stage 3: Source Discovery (PF-3)
            pf3_result = await self._run_stage(
                stage=self.PIPELINE_STAGES[2],
                input_data={
                    'municipality_name': municipality_name,
                    'state': state
                }
            )

            if not pf3_result.success and self.PIPELINE_STAGES[2].required:
                return self._create_failed_result(
                    municipality_name, table_mode,
                    f"Source discovery failed: {pf3_result.error}",
                    state=state
                )

            if self._cancelled:
                return self._create_cancelled_result(municipality_name, state, table_mode)

            # Stage 4: Terminology Extractor (PF-4)
            pf4_result = await self._run_stage(
                stage=self.PIPELINE_STAGES[3],
                input_data={
                    'municipality_name': municipality_name,
                    'state': state
                }
            )
            # PF-4 is not required - continue even if it fails

            if self._cancelled:
                return self._create_cancelled_result(municipality_name, state, table_mode)

            # Stage 5: Readiness Validator (PF-5)
            pf5_result = await self._run_stage(
                stage=self.PIPELINE_STAGES[4],
                input_data={
                    'municipality_name': municipality_name,
                    'state': state,
                    'table_mode': table_mode,
                    'pf1_result': pf1_result.response.output_data if pf1_result.response else {},
                    'pf2_result': pf2_result.response.output_data if pf2_result.response else {},
                    'pf3_result': pf3_result.response.output_data if pf3_result.response else {},
                    'pf4_result': pf4_result.response.output_data if pf4_result.response else {}
                }
            )

            self.completed_at = datetime.now()

            if pf5_result.success and pf5_result.response:
                # Use PF-5's conversion to PreflightResult
                validator = ReadinessValidatorAgent()
                preflight_result = validator.to_preflight_result(
                    output=pf5_result.response.output_data,
                    municipality_name=municipality_name,
                    state=state,
                    table_mode=table_mode,
                    pf2_result=pf2_result.response.output_data if pf2_result.response else None,
                    pf3_result=pf3_result.response.output_data if pf3_result.response else None,
                    pf4_result=pf4_result.response.output_data if pf4_result.response else None
                )

                if preflight_result:
                    self.emit_event(f"Pre-flight complete: {preflight_result.status.value}")
                    return preflight_result

            # Fallback: Create result from aggregated data
            return self._aggregate_results(
                municipality_name, state, table_mode,
                pf1_result, pf2_result, pf3_result, pf4_result, pf5_result
            )

        except Exception as e:
            logger.exception(f"PF-O pipeline error: {e}")
            self.completed_at = datetime.now()
            return self._create_failed_result(
                municipality_input, table_mode,
                f"Pipeline error: {str(e)}"
            )

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

                # Cleanup
                await agent.cleanup()

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
                    self.results[stage.agent_id] = result
                    return result
                else:
                    last_error = "; ".join(response.errors) if response.errors else "Unknown error"
                    logger.warning(f"{stage.agent_id} failed: {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.error(f"{stage.agent_id} exception: {e}")

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
        self.results[stage.agent_id] = result
        return result

    def _create_failed_result(
        self,
        municipality: str,
        table_mode: str,
        error: str,
        state: str = ""
    ) -> PreflightResult:
        """Create a FAIL PreflightResult."""
        self.completed_at = datetime.now()
        self.emit_event(f"Pre-flight FAILED: {error}")

        return PreflightResult(
            municipality=Municipality(city=municipality, state=state or "Unknown"),
            table_mode=TableMode.MUNICIPAL_SYSTEMS_INFO if "Systems" in table_mode else TableMode.MUNICIPAL_PUBLIC_BIDS,
            status=PreflightStatus.FAIL,
            gaps=[error],
            recommendations=["Review error and retry"],
            completed_at=datetime.now()
        )

    def _create_cancelled_result(
        self,
        municipality: str,
        state: str,
        table_mode: str
    ) -> PreflightResult:
        """Create a cancelled PreflightResult."""
        self.completed_at = datetime.now()
        self.emit_event("Pre-flight cancelled by user")

        return PreflightResult(
            municipality=Municipality(city=municipality, state=state or "Unknown"),
            table_mode=TableMode.MUNICIPAL_SYSTEMS_INFO if "Systems" in table_mode else TableMode.MUNICIPAL_PUBLIC_BIDS,
            status=PreflightStatus.FAIL,
            gaps=["Pipeline cancelled by user"],
            recommendations=["Restart pre-flight when ready"],
            completed_at=datetime.now()
        )

    def _aggregate_results(
        self,
        municipality_name: str,
        state: str,
        table_mode: str,
        pf1: PipelineResult,
        pf2: PipelineResult,
        pf3: PipelineResult,
        pf4: PipelineResult,
        pf5: PipelineResult
    ) -> PreflightResult:
        """Aggregate results into PreflightResult when PF-5 fails to produce one."""
        # Determine status based on successful stages
        required_success = all([
            pf1.success,
            pf2.success,
            pf3.success,
            pf5.success
        ])

        if required_success:
            status = PreflightStatus.PASS
        elif pf1.success and pf2.success:
            status = PreflightStatus.PARTIAL
        else:
            status = PreflightStatus.FAIL

        gaps = []
        for result in [pf1, pf2, pf3, pf4, pf5]:
            if not result.success and result.error:
                gaps.append(f"{result.stage_id}: {result.error}")

        self.emit_event(f"Pre-flight complete: {status.value}")

        return PreflightResult(
            municipality=Municipality(city=municipality_name, state=state or "Unknown"),
            table_mode=TableMode.MUNICIPAL_SYSTEMS_INFO if "Systems" in table_mode else TableMode.MUNICIPAL_PUBLIC_BIDS,
            status=status,
            gaps=gaps,
            recommendations=["Review pre-flight results before extraction"],
            completed_at=datetime.now()
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
            'total_stages': len(self.PIPELINE_STAGES),
            'stages_completed': stages_completed,
            'stages_failed': stages_failed,
            'total_retries': total_retries,
            'total_duration_seconds': total_duration,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
