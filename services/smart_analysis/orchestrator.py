"""
Smart Analysis Orchestrator — coordinates all agents and produces SmartAnalysisResult.

v2 execution order:
  1. ContextAggregatorAgent     (no AI — fixed field names, richer context)
  2. DocumentProfileAgent       (1 AI call — grounding pass, evidence inventory, expertise)
  3. SCOUTAgent + MIRRORAgent + UserInputAgent  (parallel async — now doc-profile-aware)
  4. SynthesisAgent             (final call — all outputs + doc_profile + language discipline)

Entry point: SmartAnalysisOrchestrator.run() — synchronous, uses new event loop.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from .models import ProfessionalAssessment, SmartAnalysisItem, SmartAnalysisResult
from .context_aggregator import ContextAggregatorAgent
from .document_profile_agent import DocumentProfileAgent
from .scout_agent import SCOUTAgent
from .mirror_agent import MIRRORAgent
from .user_input_agent import UserInputAgent
from .synthesis_agent import SynthesisAgent

logger = logging.getLogger(__name__)


class SmartAnalysisOrchestrator:
    def __init__(self, api_key: str, model: str = ''):
        self.api_key = api_key
        if not model:
            from services.ai_models import standard_model
            model = standard_model()
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
        rich_analysis_text = aggregator.build_rich_analysis_text(ctx)

        logger.info(
            f'[SmartAnalysis] Context built — '
            f'{ctx["questions_answered"]}/{ctx["total_questions"]} answered, '
            f'analysis_text={len(analysis_text)}c, '
            f'rich_text={len(rich_analysis_text)}c'
        )

        # Step 2: Document profile + expertise (serial — required before parallel agents)
        logger.info('[SmartAnalysis] Running document profile pass...')
        profile_agent = DocumentProfileAgent(self.api_key, self.model)
        doc_profile = await profile_agent.profile(ctx, rich_analysis_text)

        # Step 3: SCOUT, MIRROR, UserInput + Dynamic Intelligence in parallel
        # (all receive doc_profile; dynamic intelligence senses THIS document's
        # prevalent data dimensions and builds document-specific tables)
        logger.info('[SmartAnalysis] Running SCOUT + MIRROR + UserInput + DynamicIntel in parallel...')
        from services.dynamic_intelligence import DynamicIntelligenceEngine
        scout_agent = SCOUTAgent(self.api_key, self.model)
        mirror_agent = MIRRORAgent(self.api_key, self.model)
        user_agent = UserInputAgent(self.api_key, self.model)
        intel_engine = DynamicIntelligenceEngine(self.api_key, self.model)

        expertise = (doc_profile.get('expertise_profile') or {})
        focus_note = expertise.get('role', '')
        overview = (doc_profile.get('document_understanding') or {}).get('document_overview', '')
        if overview:
            focus_note = f'{focus_note}. Document: {overview}' if focus_note else overview

        scout_findings, mirror_findings, user_responses, dynamic_intel = await asyncio.gather(
            scout_agent.analyze(ctx, analysis_text, doc_profile),
            mirror_agent.analyze(ctx, analysis_text, doc_profile),
            user_agent.process(ctx, analysis_text, user_input, doc_profile),
            intel_engine.generate(
                context_label=f'Smart Analysis of {ctx.get("document_name", "document")} '
                              f'({ctx.get("document_type_label") or ctx.get("document_type", "document")})',
                evidence=rich_analysis_text,
                focus_note=focus_note,
            ),
        )

        # Step 4: Synthesis (receives all outputs + doc_profile)
        logger.info('[SmartAnalysis] Running synthesis...')
        synthesizer = SynthesisAgent(self.api_key, self.model)
        synthesis = await synthesizer.synthesize(
            ctx, scout_findings, mirror_findings, user_responses, doc_profile
        )

        # Step 5: Build typed result
        result = self._build_result(session_id, ctx, synthesis, user_responses, doc_profile,
                                    dynamic_intel)
        logger.info(
            f'[SmartAnalysis] Done — '
            f'{len(result.risks)} risks, '
            f'{len(result.opportunities)} opportunities, '
            f'{len(result.assessments)} assessments, '
            f'{len(result.dynamic_tables)} dynamic tables'
        )
        return result

    def _build_result(
        self,
        session_id: str,
        ctx: dict,
        synthesis: dict,
        user_responses: dict,
        doc_profile: dict,
        dynamic_intel: dict = None,
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
                    follow_up_direction=item.get('follow_up_direction') or {},
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
            evidence_classification=synthesis.get('evidence_classification') or {},
            document_understanding=doc_profile.get('document_understanding') or {},
            dynamic_tables=(dynamic_intel or {}).get('tables') or [],
            intelligence_focus=(dynamic_intel or {}).get('intelligence_focus') or '',
        )
