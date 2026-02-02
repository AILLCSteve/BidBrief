"""
Pipeline Coordinator for HOTDOG7ATE Multi-Pass Architecture.

HOTDOG7ATE = Hierarchical Orchestrated Thorough Document Oversight & Guidance -
             Adaptive Thorough Extraction

Coordinates all 4 stages:
- Stage 1: Comprehensive Quick-Scan (TOC/Index/Headers)
- Stage 2: Selective Exhaustive Pass (current window processing)
- Stage 3: Second Pass (for unanswered questions)
- Stage 4: Deep RAG (optional, user-triggered via TAVILY)
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .models import Question, Answer, ParsedConfig, PageData, ExpertPersona, WindowContext

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    QUICK_SCAN = "quick_scan"
    EXHAUSTIVE = "exhaustive"
    SECOND_PASS = "second_pass"
    DEEP_RAG = "deep_rag"


@dataclass
class StageResult:
    """Result from a single pipeline stage."""
    stage: PipelineStage
    answers: Dict[str, Answer]
    questions_processed: int
    questions_answered: int
    duration_seconds: float


@dataclass
class PipelineState:
    """Current state of the pipeline."""
    current_stage: Optional[PipelineStage] = None
    completed_stages: List[PipelineStage] = field(default_factory=list)
    stage_results: Dict[PipelineStage, StageResult] = field(default_factory=dict)

    # Question tracking
    all_questions: Set[str] = field(default_factory=set)
    answered_questions: Set[str] = field(default_factory=set)
    high_confidence_questions: Set[str] = field(default_factory=set)  # >=90%

    # User selections
    user_selected_for_exhaustive: Set[str] = field(default_factory=set)
    user_selected_for_rag: Set[str] = field(default_factory=set)


class PipelineCoordinator:
    """
    HOTDOG7ATE Pipeline Coordinator - orchestrates multi-pass analysis.

    Flow:
    1. Quick-Scan: Get high-confidence answers fast using document structure
    2. Exhaustive: Process remaining + user-selected questions window-by-window
    3. Second Pass: Retry questions with NO answers using enhanced prompts
    4. Deep RAG: User-triggered external search via TAVILY (with disclaimers)
    """

    def __init__(
        self,
        comprehensive_processor,
        exhaustive_processor,  # MultiExpertProcessor
        second_pass_processor,
        accumulator,
        rag_processor=None,  # Optional - only if TAVILY configured
        progress_callback: Optional[Callable] = None
    ):
        self.comprehensive = comprehensive_processor
        self.exhaustive = exhaustive_processor
        self.second_pass = second_pass_processor
        self.rag = rag_processor
        self.accumulator = accumulator
        self.progress_callback = progress_callback

        self.state = PipelineState()

    def set_user_selections(
        self,
        exhaustive_questions: List[str],
        rag_questions: List[str]
    ):
        """Set user-selected questions for additional processing."""
        self.state.user_selected_for_exhaustive = set(exhaustive_questions)
        self.state.user_selected_for_rag = set(rag_questions)

    async def run_full_pipeline(
        self,
        pages: List[PageData],
        config: ParsedConfig,
        experts: Dict[str, ExpertPersona],
        windows: List[WindowContext],
        enable_second_pass: bool = True,
        enable_rag: bool = False
    ) -> Dict[str, List[Answer]]:
        """
        Run the complete HOTDOG7ATE analysis pipeline.

        Args:
            pages: Extracted document pages
            config: Question configuration
            experts: Expert personas
            windows: Pre-created 3-page windows
            enable_second_pass: Whether to run second pass for unanswered
            enable_rag: Whether to run deep RAG (usually user-triggered later)

        Returns:
            All accumulated answers (question_id -> List[Answer])
        """
        logger.info("\n" + "="*64)
        logger.info("HOTDOG7ATE Multi-Pass Pipeline Starting")
        logger.info("="*64)

        all_questions = list(config.question_map.values())
        self.state.all_questions = set(q.id for q in all_questions)

        # ============================================================
        # STAGE 1: Comprehensive Quick-Scan
        # ============================================================
        stage_1_result = await self._run_stage_1(pages, all_questions, experts)

        # Determine questions for Stage 2
        questions_for_stage_2 = self._get_questions_for_stage_2(
            all_questions,
            stage_1_result
        )

        # ============================================================
        # STAGE 2: Selective Exhaustive Pass
        # ============================================================
        if questions_for_stage_2:
            stage_2_result = await self._run_stage_2(
                windows, questions_for_stage_2, experts
            )

        # ============================================================
        # STAGE 3: Second Pass (if enabled and there are unanswered)
        # ============================================================
        if enable_second_pass:
            unanswered = self._get_unanswered_questions(all_questions)
            if unanswered:
                stage_3_result = await self._run_stage_3(
                    windows, unanswered, experts
                )

        # ============================================================
        # STAGE 4: Deep RAG (if enabled and configured)
        # ============================================================
        if enable_rag and self.rag and self.rag.is_available:
            rag_questions = self._get_questions_for_rag(all_questions)
            if rag_questions:
                stage_4_result = await self._run_stage_4(rag_questions)

        # Print pipeline summary
        self._print_summary()

        # Return all accumulated answers
        return self.accumulator.get_accumulated_answers()

    async def _run_stage_1(
        self,
        pages: List[PageData],
        questions: List[Question],
        experts: Dict
    ) -> StageResult:
        """Run Stage 1: Comprehensive Quick-Scan with live updates."""
        self.state.current_stage = PipelineStage.QUICK_SCAN
        self._emit_progress('stage_1_start', {
            'stage': 'quick_scan',
            'stage_name': 'Quick-Scan - Targeted Extraction',
            'questions_count': len(questions)
        })

        start = datetime.now()

        # Build question lookup for formatting new_answers
        question_map = {q.id: q for q in questions}

        answers, remaining = await self.comprehensive.quick_scan(
            pages, questions, experts
        )

        # Format new_answers for unitary log update
        new_answers = []

        # Update state
        for qid, answer in answers.items():
            self.state.answered_questions.add(qid)
            if answer.confidence >= 0.9:
                self.state.high_confidence_questions.add(qid)

            # Format for frontend
            question = question_map.get(qid)
            if question:
                new_answers.append({
                    'question_id': qid,
                    'question_text': question.text,
                    'section_id': question.section_id,
                    'answer_text': answer.text,
                    'pages': answer.pages,
                    'confidence': answer.confidence,
                    'expert': answer.expert,
                    'footnote': getattr(answer, 'footnote', '')
                })

        # Add to accumulator
        for qid, answer in answers.items():
            if qid not in self.accumulator.accumulation:
                self.accumulator.accumulation[qid] = []
            self.accumulator.accumulation[qid].append(answer)

        # Emit window_complete with all quick-scan answers for unitary log
        if new_answers:
            self._emit_progress('window_complete', {
                'window_num': 0,  # Special: batch update from quick-scan
                'total_windows': 1,
                'pages': [],
                'answers_found': len(new_answers),
                'new_answers': new_answers,
                'stage': 'quick_scan'
            })

        duration = (datetime.now() - start).total_seconds()

        result = StageResult(
            stage=PipelineStage.QUICK_SCAN,
            answers=answers,
            questions_processed=len(questions),
            questions_answered=len(answers),
            duration_seconds=duration
        )

        self.state.stage_results[PipelineStage.QUICK_SCAN] = result
        self.state.completed_stages.append(PipelineStage.QUICK_SCAN)

        self._emit_progress('stage_1_complete', {
            'stage': 'quick_scan',
            'high_confidence_count': len(answers),
            'questions_for_exhaustive': len(remaining),
            'duration': duration
        })

        return result

    async def _run_stage_2(
        self,
        windows: List[WindowContext],
        questions: List[Question],
        experts: Dict
    ) -> StageResult:
        """Run Stage 2: Selective Exhaustive Pass with live unitary log updates."""
        self.state.current_stage = PipelineStage.EXHAUSTIVE
        self._emit_progress('stage_2_start', {
            'stage': 'exhaustive',
            'stage_name': 'Exhaustive Analysis',
            'questions_count': len(questions),
            'windows_count': len(windows)
        })

        start = datetime.now()
        answers = {}

        # Build question lookup for formatting new_answers
        question_map = {q.id: q for q in questions}

        for window_idx, window in enumerate(windows, 1):
            # Emit window processing start
            self._emit_progress('window_processing', {
                'window_num': window_idx,
                'total_windows': len(windows),
                'pages': window.pages,
                'stage': 'exhaustive'
            })

            result = await self.exhaustive.process_window(
                window=window,
                questions=questions,
                experts=experts
            )

            # Collect NEW answers for this window (for live unitary log)
            new_answers = []

            # Accumulate answers
            for qid, answer in result.answers.items():
                is_new = qid not in answers

                if is_new:
                    answers[qid] = answer
                    self.state.answered_questions.add(qid)
                    if answer.confidence >= 0.9:
                        self.state.high_confidence_questions.add(qid)

                    # Format for frontend unitary log update
                    question = question_map.get(qid)
                    if question:
                        new_answers.append({
                            'question_id': qid,
                            'question_text': question.text,
                            'section_id': question.section_id,
                            'answer_text': answer.text,
                            'pages': answer.pages,
                            'confidence': answer.confidence,
                            'expert': answer.expert,
                            'footnote': getattr(answer, 'footnote', '')
                        })

            # Add to main accumulator
            self.accumulator.accumulate_window(result)

            # Emit window_complete with new_answers (same format as classic mode)
            self._emit_progress('window_complete', {
                'window_num': window_idx,
                'total_windows': len(windows),
                'pages': window.pages,
                'answers_found': len(result.answers),
                'tokens_used': result.tokens_used,
                'processing_time': result.processing_time,
                'new_answers': new_answers,
                'stage': 'exhaustive'
            })

            # Progress update every 5 windows
            if window_idx % 5 == 0:
                self._emit_progress('stage_2_progress', {
                    'window': window_idx,
                    'total_windows': len(windows),
                    'answers_so_far': len(answers)
                })

        duration = (datetime.now() - start).total_seconds()

        result = StageResult(
            stage=PipelineStage.EXHAUSTIVE,
            answers=answers,
            questions_processed=len(questions),
            questions_answered=len(answers),
            duration_seconds=duration
        )

        self.state.stage_results[PipelineStage.EXHAUSTIVE] = result
        self.state.completed_stages.append(PipelineStage.EXHAUSTIVE)

        self._emit_progress('stage_2_complete', {
            'stage': 'exhaustive',
            'answers_found': len(answers),
            'duration': duration
        })

        return result

    async def _run_stage_3(
        self,
        windows: List[WindowContext],
        questions: List[Question],
        experts: Dict
    ) -> StageResult:
        """Run Stage 3: Second Pass for unanswered questions with live updates."""
        self.state.current_stage = PipelineStage.SECOND_PASS
        self._emit_progress('stage_3_start', {
            'stage': 'second_pass',
            'stage_name': 'Second Pass - Enhanced Scrutiny',
            'unanswered_count': len(questions)
        })

        start = datetime.now()

        # Build question lookup for formatting new_answers
        question_map = {q.id: q for q in questions}

        answers = await self.second_pass.process_unanswered_questions(
            windows=windows,
            unanswered_questions=questions,
            experts=experts
        )

        # Format new_answers for unitary log update
        new_answers = []

        # Update state and accumulator
        for qid, answer in answers.items():
            self.state.answered_questions.add(qid)
            if qid not in self.accumulator.accumulation:
                self.accumulator.accumulation[qid] = []
            self.accumulator.accumulation[qid].append(answer)

            # Format for frontend
            question = question_map.get(qid)
            if question:
                new_answers.append({
                    'question_id': qid,
                    'question_text': question.text,
                    'section_id': question.section_id,
                    'answer_text': answer.text,
                    'pages': answer.pages,
                    'confidence': answer.confidence,
                    'expert': answer.expert,
                    'footnote': getattr(answer, 'footnote', '')
                })

        # Emit window_complete with all new answers from second pass
        # This updates the unitary log with second pass results
        if new_answers:
            self._emit_progress('window_complete', {
                'window_num': 0,  # Special: batch update from second pass
                'total_windows': len(windows),
                'pages': [],
                'answers_found': len(new_answers),
                'new_answers': new_answers,
                'stage': 'second_pass'
            })

        duration = (datetime.now() - start).total_seconds()

        result = StageResult(
            stage=PipelineStage.SECOND_PASS,
            answers=answers,
            questions_processed=len(questions),
            questions_answered=len(answers),
            duration_seconds=duration
        )

        self.state.stage_results[PipelineStage.SECOND_PASS] = result
        self.state.completed_stages.append(PipelineStage.SECOND_PASS)

        self._emit_progress('stage_3_complete', {
            'stage': 'second_pass',
            'answers_found': len(answers),
            'still_unanswered': len(questions) - len(answers),
            'duration': duration
        })

        return result

    async def _run_stage_4(
        self,
        questions: List[Question]
    ) -> StageResult:
        """Run Stage 4: Deep RAG external search."""
        self.state.current_stage = PipelineStage.DEEP_RAG
        self._emit_progress('stage_4_start', {
            'stage': 'deep_rag',
            'stage_name': 'Deep RAG (External Search via TAVILY)',
            'questions_count': len(questions)
        })

        start = datetime.now()

        # Use the TAVILY-based deep RAG processor
        rag_results = await self.rag.search_similar_projects(
            unanswered_questions=[
                {'id': q.id, 'text': q.text} for q in questions
            ]
        )

        answers = {}
        for qid, answer_data in rag_results.get('answers', {}).items():
            # RAG answers have disclaimers and lower confidence
            answer_text = answer_data.get('text', '')
            if answer_text:
                try:
                    # RAG answers don't have PDF citations - they're external
                    # Add a placeholder citation to satisfy Answer validation
                    if '<PDF pg' not in answer_text:
                        answer_text = f"{answer_text} [External Source]"

                    answer = Answer(
                        question_id=qid,
                        text=answer_text,
                        pages=[0],  # No pages for external - use 0 as placeholder
                        confidence=answer_data.get('confidence', 0.3),
                        expert=f"Deep RAG ({answer_data.get('source', 'TAVILY')})",
                        window=0
                    )
                    answers[qid] = answer
                except ValueError:
                    # Skip invalid answers
                    logger.warning(f"Could not create Answer for RAG result {qid}")
                    continue

        duration = (datetime.now() - start).total_seconds()

        result = StageResult(
            stage=PipelineStage.DEEP_RAG,
            answers=answers,
            questions_processed=len(questions),
            questions_answered=len(answers),
            duration_seconds=duration
        )

        self.state.stage_results[PipelineStage.DEEP_RAG] = result
        self.state.completed_stages.append(PipelineStage.DEEP_RAG)

        self._emit_progress('stage_4_complete', {
            'stage': 'deep_rag',
            'answers_found': len(answers),
            'duration': duration,
            'disclaimer': 'External sources - verify with official documents'
        })

        return result

    def _get_questions_for_stage_2(
        self,
        all_questions: List[Question],
        stage_1_result: StageResult
    ) -> List[Question]:
        """Determine which questions need exhaustive processing."""
        questions = []

        for q in all_questions:
            # Include if:
            # 1. Not answered in Stage 1 with high confidence, OR
            # 2. User explicitly selected for exhaustive
            if q.id not in self.state.high_confidence_questions:
                questions.append(q)
            elif q.id in self.state.user_selected_for_exhaustive:
                questions.append(q)

        return questions

    def _get_unanswered_questions(
        self,
        all_questions: List[Question]
    ) -> List[Question]:
        """Get questions with NO answers at all."""
        return [
            q for q in all_questions
            if q.id not in self.state.answered_questions
        ]

    def _get_questions_for_rag(
        self,
        all_questions: List[Question]
    ) -> List[Question]:
        """Get questions for RAG (unanswered + user-selected)."""
        questions = []

        for q in all_questions:
            if q.id not in self.state.answered_questions:
                questions.append(q)
            elif q.id in self.state.user_selected_for_rag:
                questions.append(q)

        return questions

    def _emit_progress(self, event: str, data: Dict):
        """Emit progress event."""
        if self.progress_callback:
            try:
                self.progress_callback(event, data)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    def _print_summary(self):
        """Print pipeline execution summary."""
        logger.info("\n" + "="*64)
        logger.info("HOTDOG7ATE Pipeline Summary")
        logger.info("="*64)

        for stage in self.state.completed_stages:
            result = self.state.stage_results.get(stage)
            if result:
                logger.info(f"  {stage.value}:")
                logger.info(f"    Questions processed: {result.questions_processed}")
                logger.info(f"    Answers found: {result.questions_answered}")
                logger.info(f"    Duration: {result.duration_seconds:.1f}s")

        total_answered = len(self.state.answered_questions)
        total_questions = len(self.state.all_questions)
        logger.info(f"\n  TOTAL: {total_answered}/{total_questions} answered ({total_answered/total_questions*100:.1f}%)")
        logger.info("="*64)

    def get_pipeline_summary(self) -> Dict:
        """Get summary of pipeline execution."""
        return {
            'stages_completed': [s.value for s in self.state.completed_stages],
            'total_questions': len(self.state.all_questions),
            'answered_questions': len(self.state.answered_questions),
            'high_confidence': len(self.state.high_confidence_questions),
            'stage_results': {
                stage.value: {
                    'questions_processed': result.questions_processed,
                    'answers_found': result.questions_answered,
                    'duration': result.duration_seconds
                }
                for stage, result in self.state.stage_results.items()
            }
        }
