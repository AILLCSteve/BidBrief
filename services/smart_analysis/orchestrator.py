"""
Smart Analysis Orchestrator — coordinates all agents and produces SmartAnalysisResult.

Execution order:
  1. ContextAggregatorAgent  (no AI call — pure data)
  2. SCOUTAgent + MIRRORAgent + UserInputAgent  (parallel async)
  3. SynthesisAgent  (final call — receives all agent outputs)

Entry point: SmartAnalysisOrchestrator.run() — synchronous, uses new event loop.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from .models import ProfessionalAssessment, SmartAnalysisItem, SmartAnalysisResult
from .context_aggregator import ContextAggregatorAgent
from .scout_agent import SCOUTAgent
from .mirror_agent import MIRRORAgent
from .user_input_agent import UserInputAgent
from .synthesis_agent import SynthesisAgent

logger = logging.getLogger(__name__)


class SmartAnalysisOrchestrator:
    def __init__(self, api_key: str, model: str = 'gpt-4o'):
        self.api_key = api_key
        self.model = model

    def run(
        self,
        session_id: str,
        analysis_data: Dict[str, Any],
        user_input: str = '',
        doc_context: str = '',
    ) -> SmartAnalysisResult:
        """
        Synchronous entry point.
        Runs the async pipeline in a new event loop (compatible with sync Gunicorn workers).
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._run_async(session_id, analysis_data, user_input, doc_context)
            )
        finally:
            loop.close()

    async def _run_async(
        self,
        session_id: str,
        analysis_data: Dict[str, Any],
        user_input: str,
        doc_context: str,
    ) -> SmartAnalysisResult:
        logger.info(f'[SmartAnalysis] Starting for session {session_id[:12]}...')

        # Step 1: Aggregate context (no AI call)
        aggregator = ContextAggregatorAgent()
        ctx = aggregator.aggregate(analysis_data, doc_context, user_input)
        analysis_text = aggregator.build_analysis_text(ctx)

        # Step 2: Run SCOUT, MIRROR, UserInput in parallel
        logger.info('[SmartAnalysis] Running SCOUT + MIRROR + UserInput in parallel...')
        scout_agent = SCOUTAgent(self.api_key, self.model)
        mirror_agent = MIRRORAgent(self.api_key, self.model)
        user_agent = UserInputAgent(self.api_key, self.model)

        scout_findings, mirror_findings, user_responses = await asyncio.gather(
            scout_agent.analyze(ctx, analysis_text),
            mirror_agent.analyze(ctx, analysis_text),
            user_agent.process(ctx, analysis_text, user_input),
        )

        # Step 3: Synthesize
        logger.info('[SmartAnalysis] Running synthesis...')
        synthesizer = SynthesisAgent(self.api_key, self.model)
        synthesis = await synthesizer.synthesize(
            ctx, scout_findings, mirror_findings, user_responses
        )

        # Step 4: Build result object
        result = self._build_result(session_id, ctx, synthesis, user_responses)
        logger.info(
            f'[SmartAnalysis] Done — '
            f'{len(result.risks)} risks, '
            f'{len(result.opportunities)} opportunities, '
            f'{len(result.assessments)} assessments'
        )
        return result

    def _build_result(
        self,
        session_id: str,
        ctx: dict,
        synthesis: dict,
        user_responses: dict,
    ) -> SmartAnalysisResult:

        def _items(raw: list) -> list:
            out = []
            for item in (raw or []):
                if not isinstance(item, dict):
                    continue
                out.append(SmartAnalysisItem(
                    title=str(item.get('title', '')),
                    description=str(item.get('description', '')),
                    severity=str(item.get('severity', 'medium')),
                    evidence=item.get('evidence') or [],
                    page_refs=item.get('page_refs') or [],
                ))
            return out

        def _assessments(raw: list) -> list:
            out = []
            for item in (raw or []):
                if not isinstance(item, dict):
                    continue
                out.append(ProfessionalAssessment(
                    category=str(item.get('category', '')),
                    rating=str(item.get('rating', '')),
                    rationale=str(item.get('rationale', '')),
                    confidence=str(item.get('confidence', 'medium')),
                ))
            return out

        return SmartAnalysisResult(
            session_id=session_id,
            document_name=ctx['document_name'],
            document_type=ctx['document_type'],
            document_type_label=ctx['document_type_label'],
            analysis_completeness='partial' if ctx['is_partial'] else 'full',
            generated_at=datetime.now(timezone.utc).isoformat(),
            executive_summary=synthesis.get('executive_summary', ''),
            key_insights=synthesis.get('key_insights') or [],
            risks=_items(synthesis.get('risks')),
            opportunities=_items(synthesis.get('opportunities')),
            ambiguities=_items(synthesis.get('ambiguities')),
            contradictions=_items(synthesis.get('contradictions')),
            assessments=_assessments(synthesis.get('assessments')),
            follow_up_questions=synthesis.get('follow_up_questions') or [],
            strategic_recommendations=synthesis.get('strategic_recommendations') or [],
            user_question_responses=user_responses.get('responses') or [],
        )
