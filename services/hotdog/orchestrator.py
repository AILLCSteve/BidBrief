"""
HOTDOG AI Orchestrator
Hierarchical Orchestrated Thorough Document Oversight & Guidance

Main coordinator that orchestrates all 6 layers to perform complete document analysis.

ARCHITECTURE:
Layer 0: Document Ingestion - PDF extraction
Layer 1: Configuration Loader - Question loading
Layer 2: Expert Persona Generator - Dynamic expert creation
Layer 3: Multi-Expert Processor - Parallel AI execution
Layer 4: Smart Accumulator - Answer deduplication
Layer 5: Token Budget Manager - Token tracking
Layer 6: Output Compiler - Export formatting

CRITICAL FEATURES:
- Dynamic expert generation from section headings
- Perfect PDF page citation preservation
- Smart deduplication with information merging
- Exhaustive coverage within token limits
- Flexible question configuration
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional, Callable
from datetime import datetime
from pathlib import Path
from openai import AsyncOpenAI

from .layers import (
    DocumentIngestionLayer,
    ConfigurationLoader,
    ExpertPersonaGenerator,
    TokenBudgetManager
)
from .multi_expert_processor import MultiExpertProcessor
from .smart_accumulator import SmartAccumulator
from .output_compiler import OutputCompiler
from .second_pass_processor import SecondPassProcessor
from .token_optimizer import TokenOptimizer
from .key_document_details_extractor import KeyDocumentDetailsExtractor
from .mode_config import ModeConfig, AnalysisMode, get_mode_config
from .append_accumulator import AppendOnlyAccumulator
from .synthesis_agent import SynthesisAgent
from .models import (
    AnalysisResult,
    ParsedConfig,
    ExpertPersona,
    WindowContext,
    Question,
    AnswerAccumulation
)

logger = logging.getLogger(__name__)


class HotdogOrchestrator:
    """
    Main orchestrator for HOTDOG AI document analysis.

    Coordinates all 6 layers to perform thorough, exhaustive document analysis
    with perfect page citation preservation.

    Design Principles:
    - Dependency Inversion: Depends on layer abstractions, not implementations
    - Single Responsibility: Only handles coordination, not implementation
    - Open/Closed: Extensible through layer replacement
    """

    def __init__(
        self,
        openai_api_key: str,
        config_path: Optional[str] = None,
        max_parallel_experts: int = 5,
        similarity_threshold: float = 0.75,
        progress_callback: Optional[Callable] = None,
        context_guardrails: Optional[str] = None,
        mode: str = 'bid_spec',
        recheck_empty_windows: bool = False,
        use_pipeline_v2: bool = False,
        enable_second_pass: bool = False,
        enable_deep_rag: bool = False
    ):
        """
        Initialize the HOTDOG orchestrator.

        Args:
            openai_api_key: OpenAI API key for GPT-4 calls
            config_path: Path to question configuration JSON (optional)
            max_parallel_experts: Maximum concurrent expert API calls
            similarity_threshold: Similarity threshold for answer merging (0.0-1.0)
            progress_callback: Optional callback for progress updates
                              Signature: callback(event_type: str, data: dict)
            context_guardrails: Optional global context rules for analysis
                              (e.g., "Only answer within CIPP lining context")
            mode: Analysis mode - 'bid_spec' (default) or 'bestprep'
            recheck_empty_windows: If True, retry extraction on windows that found 0 answers
            use_pipeline_v2: If True, use HOTDOG7ATE multi-pass pipeline (Bid/Spec only)
            enable_second_pass: If True, run second pass for unanswered questions
            enable_deep_rag: If True, enable Deep RAG with TAVILY for external search
        """
        self.openai_client = AsyncOpenAI(api_key=openai_api_key)
        self.config_path = config_path
        self.progress_callback = progress_callback
        self.context_guardrails = context_guardrails or ""

        # Mode configuration
        self.mode_config = get_mode_config(mode)
        self.mode = self.mode_config.mode
        self.recheck_empty_windows = recheck_empty_windows
        self.use_pipeline_v2 = use_pipeline_v2
        self.enable_second_pass = enable_second_pass
        self.enable_deep_rag = enable_deep_rag

        # Detect model limits using TokenOptimizer
        self.model = "gpt-4o"  # Most robust available model
        model_limits = TokenOptimizer.detect_model_limits(self.model)

        # Initialize all layers with optimized token limits
        self.layer0_ingestion = DocumentIngestionLayer()
        self.layer1_config = ConfigurationLoader()
        self.layer2_experts = ExpertPersonaGenerator(
            openai_client=self.openai_client,
            model=self.model,
            context_guardrails=self.context_guardrails
        )
        self.layer3_processor = MultiExpertProcessor(
            openai_client=self.openai_client,
            max_parallel_experts=max_parallel_experts,
            model=self.model,
            max_completion_tokens=model_limits.recommended_completion_tokens,
            context_guardrails=self.context_guardrails
        )
        self.layer3_5_second_pass = SecondPassProcessor(
            openai_client=self.openai_client,
            max_parallel_experts=max_parallel_experts,
            context_guardrails=self.context_guardrails,
            model=self.model,
            max_completion_tokens=model_limits.recommended_completion_tokens
        )

        # Initialize appropriate accumulator based on mode
        if self.mode == AnalysisMode.BESTPREP:
            self.layer4_accumulator = None  # Not used in BestPrep mode
            self.bestprep_accumulator = AppendOnlyAccumulator()
            self.synthesis_agent = SynthesisAgent(openai_api_key, model=self.model)
        else:
            self.layer4_accumulator = SmartAccumulator(
                similarity_threshold=similarity_threshold
            )
            self.bestprep_accumulator = None
            self.synthesis_agent = None

        self.layer5_token_manager = TokenBudgetManager(
            max_prompt_tokens=model_limits.recommended_prompt_tokens,  # 75K for GPT-4o
            max_completion_tokens=model_limits.recommended_completion_tokens  # 16K for GPT-4o
        )
        self.layer6_compiler = OutputCompiler()

        # Key Document Details Extractor - ALWAYS runs regardless of selected sections
        self.key_details_extractor = KeyDocumentDetailsExtractor(
            api_key=openai_api_key,
            model=self.model
        )
        self.extracted_key_details = []  # Store extracted details (list of KeyDocumentDetail)
        self.optimized_scan_data = {}  # Store v2 pipeline navigation/optimized scan data for exports

        # Store windows and experts for second pass
        self.cached_windows = []
        self.cached_experts = {}
        self.cached_config = None

        # Stop flag for graceful cancellation
        self.stop_requested = False

        logger.info("HOTDOG AI Orchestrator initialized")
        logger.info(f"   Mode: {self.mode.value}")
        logger.info(f"   Model: {self.model}")
        logger.info(f"   Prompt Budget: {model_limits.recommended_prompt_tokens:,} tokens")
        logger.info(f"   Completion Limit: {model_limits.recommended_completion_tokens:,} tokens")
        if self.use_pipeline_v2 and self.mode == AnalysisMode.BID_SPEC:
            logger.info("   Pipeline: HOTDOG7ATE Multi-Pass (Optimized Scan -> Exhaustive -> Second Pass -> RAG)")
        else:
            logger.info("   Pipeline: Classic (Exhaustive window-based)")
        if self.mode == AnalysisMode.BESTPREP:
            logger.info("   📚 BestPrep Mode: Append-only accumulation, synthesis enabled")
        if self.context_guardrails:
            logger.info(f"📋 Context Guardrails: {self.context_guardrails[:100]}...")

    async def analyze_document(
        self,
        pdf_path: str,
        config_path: Optional[str] = None,
        enabled_sections: Optional[List[str]] = None
    ) -> AnalysisResult:
        """
        Perform complete document analysis.

        This is the main entry point that coordinates all layers.

        Args:
            pdf_path: Path to PDF document to analyze
            config_path: Path to question configuration (overrides default)
            enabled_sections: Optional list of section IDs to analyze (if None, analyze all)

        Returns:
            Complete AnalysisResult with all answers and metadata

        Raises:
            ValueError: If PDF or config not found
            RuntimeError: If analysis fails critically
        """
        started_at = datetime.now()
        logger.info(f"🚀 Starting HOTDOG analysis: {pdf_path}")
        self._emit_progress('analysis_started', {
            'pdf_path': pdf_path,
            'document': os.path.basename(pdf_path),  # For frontend display
            'started_at': started_at.isoformat()  # Convert to JSON-serializable string
        })

        try:
            # ============================================================
            # LAYER 0: DOCUMENT INGESTION
            # ============================================================
            logger.info("📄 Layer 0: Document Ingestion")
            self._emit_progress('layer_0_start', {'layer': 'Document Ingestion'})

            pages, doc_metadata = self.layer0_ingestion.extract_pdf(pdf_path)
            windows = self.layer0_ingestion.create_windows(pages, window_size=3)

            logger.info(f"  ✅ Extracted {len(pages)} pages into {len(windows)} windows")
            self._emit_progress('document_ingested', {
                'document_name': doc_metadata.get('document_name', 'Unknown'),
                'total_pages': len(pages),
                'window_count': len(windows),
                'window_size': 3  # Standard window size
            })

            # Cache windows for potential second pass
            self.cached_windows = windows

            # ============================================================
            # KEY DOCUMENT DETAILS EXTRACTION (runs ALWAYS, regardless of sections)
            # ============================================================
            logger.info("🔑 Extracting Key Document Details...")
            self._emit_progress('key_requirements_start', {'layer': 'Key Document Details Extraction'})

            try:
                # Build pages data for extractor
                pages_for_extraction = [
                    {'page_num': p.page_num, 'text': p.text}
                    for p in pages
                ]
                self.extracted_key_details = await self.key_details_extractor.extract_from_document(
                    pages_for_extraction
                )
                logger.info(f"  ✅ Extracted {len(self.extracted_key_details)} key document details")
                self._emit_progress('key_requirements_complete', {
                    'count': len(self.extracted_key_details),
                    'requirements': self.key_details_extractor.get_summary_data()
                })
            except Exception as e:
                logger.warning(f"  ⚠️ Key document details extraction failed (non-fatal): {e}")
                self._emit_progress('key_requirements_failed', {'error': str(e)})

            # ============================================================
            # LAYER 1: CONFIGURATION LOADING
            # ============================================================
            logger.info("⚙️  Layer 1: Configuration Loading")
            self._emit_progress('layer_1_start', {'layer': 'Configuration Loading'})

            config_file = config_path or self.config_path
            if not config_file:
                raise ValueError("No configuration file provided")

            config = self.layer1_config.load_from_json(config_file)

            # FILTER CONFIG: Only include enabled sections if specified
            if enabled_sections is not None:
                original_section_count = len(config.sections)
                original_question_count = config.total_questions

                # Filter to only enabled sections
                config.sections = [s for s in config.sections if s.id in enabled_sections]

                # Rebuild maps based on filtered sections
                config.section_map = {s.id: s for s in config.sections}
                config.question_map = {}
                for section in config.sections:
                    for question in section.questions:
                        config.question_map[question.id] = question

                # Log filtering (properties auto-compute from filtered data)
                logger.info(f"  🔍 Filtered to {config.total_sections}/{original_section_count} enabled sections")
                logger.info(f"  🔍 Analyzing {config.total_questions}/{original_question_count} questions")

            logger.info(f"  ✅ Loaded {config.total_questions} questions in {config.total_sections} sections")
            self._emit_progress('config_loaded', {
                'total_questions': config.total_questions,
                'section_count': config.total_sections,
                'sections': [s.name for s in config.sections]
            })

            # Cache config for potential second pass
            self.cached_config = config

            # Register question texts with accumulator for Key Requirement detection
            if self.mode == AnalysisMode.BID_SPEC:
                for question_id, question in config.question_map.items():
                    self.layer4_accumulator.register_question_text(question_id, question.text)
            else:
                # BestPrep mode: initialize questions in append-only accumulator
                for question_id, question in config.question_map.items():
                    self.bestprep_accumulator.initialize_question(question_id, question.text)

            # ============================================================
            # LAYER 2: EXPERT PERSONA GENERATION
            # ============================================================
            logger.info("🤖 Layer 2: Expert Persona Generation")
            self._emit_progress('layer_2_start', {'layer': 'Expert Persona Generation'})

            experts = {}  # section_id -> ExpertPersona
            for section in config.sections:
                expert = await self.layer2_experts.generate_expert(section)
                experts[section.id] = expert
                logger.info(f"  ✅ Generated expert: {expert.name}")
                self._emit_progress('expert_generated', {
                    'expert_name': expert.name,
                    'section': section.name
                })

            # Cache experts for potential second pass
            self.cached_experts = experts

            # ============================================================
            # PIPELINE SELECTION: HOTDOG7ATE vs Classic
            # ============================================================
            if self.mode == AnalysisMode.BID_SPEC and self.use_pipeline_v2:
                # ============================================================
                # HOTDOG7ATE MULTI-PASS PIPELINE
                # ============================================================
                logger.info("\n" + "="*64)
                logger.info("HOTDOG7ATE Multi-Pass Pipeline")
                logger.info("="*64)
                self._emit_progress('pipeline_start', {
                    'pipeline': 'HOTDOG7ATE',
                    'stages': ['optimized_scan', 'exhaustive', 'second_pass', 'deep_rag']
                })

                from .pipeline_coordinator import PipelineCoordinator
                from .comprehensive_processor import ComprehensiveProcessor
                from .deep_rag_processor import DeepRAGProcessor

                # Initialize pipeline components
                comprehensive = ComprehensiveProcessor(
                    self.openai_client,
                    self.model,
                    confidence_threshold=0.90
                )

                rag = None
                if self.enable_deep_rag:
                    rag = DeepRAGProcessor()

                coordinator = PipelineCoordinator(
                    comprehensive_processor=comprehensive,
                    exhaustive_processor=self.layer3_processor,
                    second_pass_processor=self.layer3_5_second_pass,
                    accumulator=self.layer4_accumulator,
                    rag_processor=rag,
                    progress_callback=self._emit_progress,
                    stop_check_callback=lambda: self.stop_requested  # Pass stop flag check
                )

                # Run the full pipeline
                accumulated_answers = await coordinator.run_full_pipeline(
                    pages=pages,
                    config=config,
                    experts=experts,
                    windows=windows,
                    enable_second_pass=self.enable_second_pass,
                    enable_rag=self.enable_deep_rag
                )

                # Store navigation map data for exports/modals (Optimized Scan Pass)
                if coordinator.navigation_map:
                    nav_map = coordinator.navigation_map
                    self.optimized_scan_data = {
                        'pipeline': 'HOTDOG7ATE',
                        'structure': {
                            'has_toc': nav_map.structure.has_toc,
                            'has_index': nav_map.structure.has_index,
                            'has_appendix': nav_map.structure.has_appendix,
                            'toc_entries_count': len(nav_map.structure.toc_entries),
                            'index_terms_count': len(nav_map.structure.index_entries),
                            'appendix_pages': nav_map.structure.appendix_pages,
                            'running_headers_count': len(nav_map.structure.running_headers),
                            'spec_divisions_count': len(nav_map.structure.spec_divisions),
                            'topic_hotspots_count': len(nav_map.structure.topic_hotspots)
                        },
                        'expert_assignments': [
                            {
                                'expert': a.expert_name,
                                'section_id': a.section_id,
                                'primary_pages': a.primary_pages,
                                'context_pages': a.context_pages,
                                'total_pages': len(a.primary_pages) + len(a.context_pages),
                                'keywords_matched': a.keywords_found,
                                'expert_keywords': getattr(a, 'expert_recommended_keywords', []),
                                'confidence': a.confidence
                            }
                            for a in nav_map.expert_assignments.values()
                        ],
                        'all_keywords_by_section': nav_map.all_keywords_by_expert,
                        'unassigned_questions': nav_map.unassigned_questions,
                        'topic_hotspots_found': nav_map.topic_hotspots_found,
                        'estimated_reduction': f"{nav_map.estimated_reduction*100:.0f}%" if nav_map.estimated_reduction else 'N/A',
                        'stage_results': coordinator.get_pipeline_summary()
                    }

                self._emit_progress('pipeline_complete', {
                    'pipeline': 'HOTDOG7ATE',
                    'summary': coordinator.get_pipeline_summary()
                })

                # v2 pipeline handled all processing - skip classic loop
                skip_classic_processing = True

            else:
                # ============================================================
                # CLASSIC PIPELINE: Exhaustive window-based processing
                # ============================================================
                logger.info(f"Processing {len(windows)} windows...")
                self._emit_progress('processing_start', {'total_windows': len(windows)})
                skip_classic_processing = False

            # Track windows with no answers for potential recheck
            empty_windows = []  # List of (window_idx, window) tuples

            # Classic processing loop (skipped if using v2 pipeline)
            windows_to_process = [] if skip_classic_processing else list(enumerate(windows, 1))

            for window_idx, window in windows_to_process:
                # Check for stop request
                if self.stop_requested:
                    logger.warning(f"⏹️  Analysis stopped by user at window {window_idx}/{len(windows)}")
                    raise Exception("Analysis stopped by user")

                logger.info(f"\n{'='*64}")
                logger.info(f"Window {window_idx}/{len(windows)}: Pages {window.page_range_str}")
                logger.info(f"{'='*64}")

                self._emit_progress('window_processing', {
                    'window_num': window_idx,
                    'total_windows': len(windows),
                    'pages': window.page_range_str
                })

                # -----------------------------------------------------
                # LAYER 5: Token Budget Check (before processing)
                # -----------------------------------------------------
                adjusted_context, within_budget = self.layer5_token_manager.check_budget_before_window(
                    window_num=window_idx,
                    context_text=window.text,
                    question_count=config.total_questions
                )

                if adjusted_context != window.text:
                    logger.warning(f"⚠️  Context truncated for token budget")
                    # Create adjusted window
                    window = WindowContext(
                        window_num=window.window_num,
                        pages=window.pages,
                        text=adjusted_context,
                        page_data=window.page_data
                    )

                # -----------------------------------------------------
                # LAYER 3: Multi-Expert Processing
                # -----------------------------------------------------
                logger.info(f"🤖 Dispatching {len(experts)} experts to analyze {config.total_questions} questions")
                self._emit_progress('experts_dispatched', {
                    'window_num': window_idx,
                    'expert_count': len(experts),
                    'question_count': config.total_questions,
                    'sections': [section.name for section in config.sections]
                })

                window_result = await self.layer3_processor.process_window(
                    window=window,
                    questions=list(config.question_map.values()),
                    experts=experts
                )

                logger.info(f"✅ Experts returned {len(window_result.answers)} answers from window {window_idx}")
                self._emit_progress('experts_complete', {
                    'window_num': window_idx,
                    'answers_returned': len(window_result.answers),
                    'tokens_used': window_result.tokens_used
                })

                # Track empty windows for potential recheck
                if len(window_result.answers) == 0:
                    empty_windows.append((window_idx, window))
                    logger.info(f"📝 Window {window_idx} returned 0 answers - marked for potential recheck")

                # Record actual token usage
                self.layer5_token_manager.record_usage(
                    window_num=window_idx,
                    prompt_tokens=window_result.tokens_used // 2,  # Rough split
                    completion_tokens=window_result.tokens_used // 2
                )

                # -----------------------------------------------------
                # LAYER 4: Smart Accumulation (mode-aware)
                # -----------------------------------------------------
                if self.mode == AnalysisMode.BESTPREP:
                    # BestPrep: Append-only accumulation
                    for question_id, answer in window_result.answers.items():
                        self.bestprep_accumulator.add_answer(
                            question_id=question_id,
                            answer_text=answer.text,
                            pages=answer.pages,
                            confidence=answer.confidence,
                            window_index=window_idx,
                            expert_name=answer.expert,
                            raw_footnote=answer.footnote
                        )
                    self.bestprep_accumulator.mark_window_processed(window_idx)
                    accumulation_stats = {
                        'window_num': window_idx,
                        'new_answers': len(window_result.answers),
                        'merges': 0,
                        'appends': len(window_result.answers)
                    }
                    # Build accumulated_so_far compatible format for live display
                    accumulated_so_far = {}
                    for qid, ca in self.bestprep_accumulator.get_all_cumulative_answers().items():
                        if ca.fragments:
                            # Create a mock Answer object for display compatibility
                            from .models import Answer
                            best_frag = max(ca.fragments, key=lambda f: f.confidence)
                            try:
                                mock_answer = Answer(
                                    question_id=qid,
                                    text=best_frag.text,
                                    pages=best_frag.pages,
                                    confidence=best_frag.confidence,
                                    expert=best_frag.expert_name,
                                    window=best_frag.window_index,
                                    footnote=best_frag.raw_footnote
                                )
                                accumulated_so_far[qid] = [mock_answer]
                            except ValueError:
                                # Skip invalid answers (missing citations)
                                pass
                else:
                    # Bid/Spec: Smart accumulation with deduplication
                    accumulation_stats = self.layer4_accumulator.accumulate_window(window_result)
                    accumulated_so_far = self.layer4_accumulator.get_accumulated_answers()

                # Format unitary log for live display (answers found so far)
                unitary_log_markdown = self._format_live_unitary_log(
                    accumulated_so_far, config, window_idx, len(windows)
                )

                # Build new_answers array with full details for frontend table
                # MODE-AWARE: BestPrep sends CUMULATIVE data, Bid/Spec sends current window
                new_answers = []
                if self.mode == AnalysisMode.BESTPREP:
                    # BestPrep: Send CUMULATIVE data for ALL questions with fragments
                    for qid, ca in self.bestprep_accumulator.get_all_cumulative_answers().items():
                        if ca.fragments:
                            question = config.question_map.get(qid)
                            if question:
                                section = config.section_map.get(question.section_id)
                                # Combine all fragment texts with separator
                                combined_text = " [...] ".join([f.text for f in ca.fragments])
                                new_answers.append({
                                    'question_id': qid,
                                    'question_text': question.text,
                                    'section_id': question.section_id,
                                    'section_name': section.name if section else question.section_id,
                                    'answer_text': combined_text,  # All fragments combined
                                    'pages': ca.all_pages,         # ALL pages across all fragments
                                    'confidence': ca.highest_confidence,
                                    'footnote': " | ".join([fn.quote for fn in ca.footnotes]) if ca.footnotes else "",
                                    'fragment_count': ca.fragment_count,  # For display
                                    'is_cumulative': True  # Flag for frontend
                                })
                else:
                    # Bid/Spec: Send current window's answers (existing behavior)
                    for answer in window_result.answers.values():
                        question = config.question_map.get(answer.question_id)
                        if question:
                            section = config.section_map.get(question.section_id)
                            new_answers.append({
                                'question_id': answer.question_id,
                                'question_text': question.text,
                                'section_id': question.section_id,
                                'section_name': section.name if section else question.section_id,
                                'answer_text': answer.text,
                                'pages': answer.pages,
                                'confidence': answer.confidence,
                                'footnote': answer.footnote
                            })

                self._emit_progress('window_complete', {
                    'window_num': window_idx,
                    'answers_found': len(window_result.answers),
                    'tokens_used': window_result.tokens_used,
                    'processing_time': window_result.processing_time,
                    'accumulation_stats': accumulation_stats,
                    'unitary_log_markdown': unitary_log_markdown,  # LIVE UNITARY LOG
                    'new_answers': new_answers  # NEW: Full answer details with footnotes
                })

                # Progress update every 3 windows
                if window_idx % 3 == 0:
                    progress_summary = f"{window_idx}/{len(windows)} windows processed"
                    logger.info(f"\n📊 Progress: {progress_summary}")
                    logger.info(self.layer5_token_manager.get_statistics())
                    # Use appropriate accumulator based on mode
                    if self.mode == AnalysisMode.BESTPREP:
                        logger.info(self.bestprep_accumulator.get_statistics())
                    else:
                        logger.info(self.layer4_accumulator.get_statistics())

                    self._emit_progress('progress_milestone', {
                        'windows_processed': window_idx,
                        'total_windows': len(windows),
                        'progress_summary': progress_summary
                    })

            # ============================================================
            # RECHECK EMPTY WINDOWS (if enabled)
            # ============================================================
            if self.recheck_empty_windows and empty_windows:
                logger.info(f"\n{'='*64}")
                logger.info(f"🔄 RECHECKING {len(empty_windows)} EMPTY WINDOWS")
                logger.info(f"{'='*64}")

                self._emit_progress('recheck_start', {
                    'empty_window_count': len(empty_windows),
                    'windows_to_recheck': [w[0] for w in empty_windows]
                })

                recheck_answers_found = 0

                for recheck_idx, (window_idx, window) in enumerate(empty_windows, 1):
                    # Check for stop request
                    if self.stop_requested:
                        logger.warning(f"⏹️  Recheck stopped by user at window {recheck_idx}/{len(empty_windows)}")
                        break

                    logger.info(f"\n🔄 Rechecking Window {window_idx} ({recheck_idx}/{len(empty_windows)}): Pages {window.page_range_str}")

                    self._emit_progress('recheck_window_processing', {
                        'recheck_num': recheck_idx,
                        'total_rechecks': len(empty_windows),
                        'original_window_num': window_idx,
                        'pages': window.page_range_str
                    })

                    # Re-process this window with the same experts
                    window_result = await self.layer3_processor.process_window(
                        window=window,
                        questions=list(config.question_map.values()),
                        experts=experts
                    )

                    logger.info(f"  ✅ Recheck found {len(window_result.answers)} answers from window {window_idx}")

                    # Accumulate any new answers (mode-aware)
                    if len(window_result.answers) > 0:
                        recheck_answers_found += len(window_result.answers)

                        if self.mode == AnalysisMode.BESTPREP:
                            for question_id, answer in window_result.answers.items():
                                self.bestprep_accumulator.add_answer(
                                    question_id=question_id,
                                    answer_text=answer.text,
                                    pages=answer.pages,
                                    confidence=answer.confidence,
                                    window_index=window_idx,
                                    expert_name=answer.expert + " (Recheck)",
                                    raw_footnote=answer.footnote
                                )
                        else:
                            # Bid/Spec mode: use smart accumulator
                            self.layer4_accumulator.accumulate_window(window_result)

                    self._emit_progress('recheck_window_complete', {
                        'recheck_num': recheck_idx,
                        'original_window_num': window_idx,
                        'answers_found': len(window_result.answers)
                    })

                logger.info(f"\n✅ Recheck complete: Found {recheck_answers_found} additional answers from {len(empty_windows)} windows")

                self._emit_progress('recheck_complete', {
                    'windows_rechecked': len(empty_windows),
                    'total_new_answers': recheck_answers_found
                })

            # ============================================================
            # LAYER 7: SYNTHESIS (BestPrep mode only)
            # ============================================================
            if self.mode == AnalysisMode.BESTPREP and self.synthesis_agent:
                logger.info("\n🧠 Layer 7: Synthesis Agent")
                self._emit_progress('layer_7_start', {
                    'layer': 'Synthesis Agent',
                    'questions_to_synthesize': len(self.bestprep_accumulator.get_questions_for_synthesis())
                })

                synthesis_results = await self.synthesis_agent.synthesize_all(
                    self.bestprep_accumulator,
                    max_concurrent=3
                )

                logger.info(f"  ✅ Synthesized {len(synthesis_results)} answers")
                self._emit_progress('layer_7_complete', {
                    'synthesized_count': len(synthesis_results),
                    'synthesis_stats': self.synthesis_agent.get_statistics()
                })

            # ============================================================
            # LAYER 6: OUTPUT COMPILATION
            # ============================================================
            logger.info("\n📋 Layer 6: Output Compilation")
            self._emit_progress('layer_6_start', {'layer': 'Output Compilation'})

            completed_at = datetime.now()

            # Get accumulated answers based on mode
            if self.mode == AnalysisMode.BESTPREP:
                # Build accumulated_answers from BestPrep accumulator
                accumulated_answers = {}
                for qid, ca in self.bestprep_accumulator.get_all_cumulative_answers().items():
                    if ca.fragments:
                        # Use synthesized answer if available, else best fragment
                        from .models import Answer
                        if ca.synthesized_answer:
                            text = ca.synthesized_answer
                        else:
                            best_frag = max(ca.fragments, key=lambda f: f.confidence)
                            text = best_frag.text

                        # Get all pages from fragments
                        all_pages = ca.all_pages
                        if not all_pages:
                            # Fallback: collect pages from fragments
                            all_pages = list(set(p for f in ca.fragments for p in f.pages))
                            all_pages.sort()

                        # CRITICAL: Answer model requires <PDF pg X> marker in text
                        # Add citation if missing (synthesized answers may not have it)
                        if '<PDF pg' not in text and all_pages:
                            pages_str = ', '.join(map(str, all_pages))
                            text = f"{text} <PDF pg {pages_str}>"

                        # Skip if still no pages (shouldn't happen but safety check)
                        if not all_pages:
                            logger.warning(f"Skipping {qid}: no pages found in any fragments")
                            continue

                        try:
                            answer = Answer(
                                question_id=qid,
                                text=text,
                                pages=all_pages,
                                confidence=ca.highest_confidence,
                                expert="Synthesis Agent" if ca.synthesized_answer else ca.fragments[0].expert_name,
                                window=0,
                                footnote=""
                            )
                            accumulated_answers[qid] = [answer]
                        except ValueError as e:
                            # Log the error instead of silently skipping
                            logger.error(f"Failed to create Answer for {qid}: {e}")
                            logger.error(f"  text preview: {text[:100]}...")
                            logger.error(f"  pages: {all_pages}")
                            logger.error(f"  confidence: {ca.highest_confidence}")
            else:
                accumulated_answers = self.layer4_accumulator.get_accumulated_answers()

            total_tokens = self.layer5_token_manager.total_tokens_used

            result = self.layer6_compiler.compile_results(
                accumulation=accumulated_answers,
                config=config,
                metadata=doc_metadata,
                started_at=started_at,
                completed_at=completed_at,
                total_tokens=total_tokens
            )

            logger.info(f"  ✅ Compilation complete")
            self._emit_progress('layer_6_complete', {
                'questions_answered': result.questions_answered,
                'total_questions': config.total_questions,
                'footnotes': len(result.footnotes)
            })

            # ============================================================
            # FINAL REPORT
            # ============================================================
            self._print_final_summary(result, config)
            self._emit_progress('analysis_complete', {
                'questions_answered': result.questions_answered,
                'total_questions': config.total_questions,
                'processing_time': result.processing_time_seconds,
                'total_tokens': result.total_tokens,
                'estimated_cost': result.estimated_cost
            })

            return result

        except Exception as e:
            # Preserve detailed error information for debugging
            error_type = type(e).__name__
            error_msg = str(e)

            logger.error(f"❌ Analysis failed ({error_type}): {error_msg}", exc_info=True)
            self._emit_progress('analysis_failed', {'error': error_msg, 'error_type': error_type})

            # Provide helpful context based on error type
            if "JSON" in error_msg or "Unexpected token" in error_msg:
                detailed_error = (
                    f"OpenAI API returned invalid response (expected JSON, got HTML). "
                    f"This usually indicates an API authentication error. "
                    f"Original error: {error_msg}"
                )
                raise RuntimeError(detailed_error) from e
            else:
                raise RuntimeError(f"HOTDOG analysis failed ({error_type}): {error_msg}") from e

    def _print_final_summary(self, result: AnalysisResult, config: ParsedConfig):
        """Print final analysis summary."""
        logger.info("\n" + "="*64)
        logger.info("🎉 HOTDOG ANALYSIS COMPLETE")
        logger.info("="*64)
        logger.info(f"Document: {result.document_name}")
        logger.info(f"Pages: {result.total_pages}")
        logger.info(f"Questions Answered: {result.questions_answered}/{config.total_questions}")
        logger.info(f"Average Confidence: {result.average_confidence:.0%}")
        logger.info(f"Total Footnotes: {len(result.footnotes)}")
        logger.info(f"Processing Time: {result.processing_time_seconds:.2f}s")
        logger.info(f"Total Tokens: {result.total_tokens:,}")
        logger.info(f"Estimated Cost: ${result.estimated_cost:.4f}")
        logger.info("="*64)

        # Layer statistics
        logger.info("\n📊 LAYER STATISTICS")
        logger.info(self.layer3_processor.get_statistics())
        if self.mode == AnalysisMode.BESTPREP:
            logger.info(self.bestprep_accumulator.get_statistics())
            if self.synthesis_agent:
                logger.info(self.synthesis_agent.get_statistics())
        else:
            logger.info(self.layer4_accumulator.get_statistics())
            # Print accumulation report
            logger.info("\n" + self.layer4_accumulator.generate_report())
        logger.info(self.layer5_token_manager.get_statistics())

    async def run_second_pass(self, first_pass_result: AnalysisResult) -> AnalysisResult:
        """
        Run second-pass analysis on unanswered questions from first pass.

        This method uses enhanced scrutiny and creative interpretation to find
        answers to questions that were not answered in the first pass.

        Args:
            first_pass_result: Result from the first pass analysis

        Returns:
            Updated AnalysisResult with second-pass answers merged in

        Raises:
            ValueError: If cached data not available (must run first pass first)
            RuntimeError: If second pass fails critically
        """
        if not self.cached_windows or not self.cached_experts or not self.cached_config:
            raise ValueError("Second pass requires cached data from first pass. Run analyze_document() first.")

        logger.info(f"\n{'='*64}")
        logger.info(f"🔍 STARTING SECOND PASS - ENHANCED SCRUTINY")
        logger.info(f"{'='*64}")

        started_at = datetime.now()
        self._emit_progress('second_pass_started', {
            'first_pass_questions_answered': first_pass_result.questions_answered,
            'total_questions': self.cached_config.total_questions
        })

        try:
            # Identify unanswered questions
            unanswered_questions = self._identify_unanswered_questions(
                first_pass_result,
                self.cached_config
            )

            logger.info(f"📊 First Pass Results:")
            logger.info(f"   Answered: {first_pass_result.questions_answered}/{self.cached_config.total_questions}")
            logger.info(f"   Unanswered: {len(unanswered_questions)}")
            logger.info(f"   Completion Rate: {first_pass_result.questions_answered/self.cached_config.total_questions*100:.1f}%")

            if not unanswered_questions:
                logger.info("🎉 All questions answered in first pass! No second pass needed.")
                return first_pass_result

            # Run second-pass processor
            logger.info(f"\n🔍 Running second pass on {len(unanswered_questions)} unanswered questions...")
            self._emit_progress('second_pass_processing', {
                'unanswered_count': len(unanswered_questions)
            })

            second_pass_answers = await self.layer3_5_second_pass.process_unanswered_questions(
                windows=self.cached_windows,
                unanswered_questions=unanswered_questions,
                experts=self.cached_experts
            )

            logger.info(f"✅ Second pass found {len(second_pass_answers)} new answers")

            # Merge second-pass answers into accumulator
            logger.info(f"\n🔄 Merging second-pass answers into first-pass results...")
            for question_id, answer in second_pass_answers.items():
                # Add to accumulator (will handle deduplication)
                if question_id not in first_pass_result.questions:
                    first_pass_result.questions[question_id] = []
                first_pass_result.questions[question_id].append(answer)
                logger.info(f"   ✅ Added answer for {question_id}")

            # Recompile results with merged answers
            completed_at = datetime.now()
            total_tokens = (
                first_pass_result.total_tokens +
                self.layer3_5_second_pass.total_tokens_used
            )

            # Recalculate cost
            estimated_cost = total_tokens * 0.00003  # ~$0.03 per 1K tokens

            # Update result metadata
            first_pass_result.total_tokens = total_tokens
            first_pass_result.estimated_cost = estimated_cost
            first_pass_result.completed_at = completed_at

            # Recompile footnotes
            from .output_compiler import OutputCompiler
            compiler = OutputCompiler()
            first_pass_result.footnotes = compiler._compile_footnotes(first_pass_result.questions)

            # Final statistics
            logger.info(f"\n{'='*64}")
            logger.info(f"🎉 SECOND PASS COMPLETE")
            logger.info(f"{'='*64}")
            logger.info(f"Questions Answered (First Pass): {first_pass_result.questions_answered - len(second_pass_answers)}")
            logger.info(f"Questions Answered (Second Pass): {len(second_pass_answers)}")
            logger.info(f"Total Questions Answered: {first_pass_result.questions_answered}/{self.cached_config.total_questions}")
            logger.info(f"New Completion Rate: {first_pass_result.questions_answered/self.cached_config.total_questions*100:.1f}%")
            logger.info(f"Second Pass Success Rate: {len(second_pass_answers)/len(unanswered_questions)*100:.1f}%")
            logger.info(f"Total Tokens: {total_tokens:,}")
            logger.info(f"Estimated Cost: ${estimated_cost:.4f}")
            logger.info(f"{'='*64}")

            # Print second-pass statistics
            logger.info("\n📊 SECOND PASS STATISTICS")
            logger.info(self.layer3_5_second_pass.get_statistics())

            self._emit_progress('second_pass_complete', {
                'second_pass_answers_found': len(second_pass_answers),
                'total_questions_answered': first_pass_result.questions_answered,
                'completion_rate': first_pass_result.questions_answered/self.cached_config.total_questions,
                'total_tokens': total_tokens,
                'estimated_cost': estimated_cost
            })

            return first_pass_result

        except Exception as e:
            logger.error(f"❌ Second pass failed: {str(e)}", exc_info=True)
            self._emit_progress('second_pass_failed', {'error': str(e)})
            raise RuntimeError(f"Second pass analysis failed: {str(e)}") from e

    def _identify_unanswered_questions(
        self,
        result: AnalysisResult,
        config: ParsedConfig
    ) -> List[Question]:
        """
        Identify questions that were not answered in the first pass.

        Args:
            result: First pass analysis result
            config: Question configuration

        Returns:
            List of Question objects that have no answers
        """
        unanswered = []

        for question_id, question in config.question_map.items():
            # Check if this question has any answers
            if question_id not in result.questions or not result.questions[question_id]:
                unanswered.append(question)

        return unanswered

    def _emit_progress(self, event_type: str, data: dict):
        """Emit progress event to callback if provided."""
        if self.progress_callback:
            try:
                self.progress_callback(event_type, data)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    def _format_live_unitary_log(
        self,
        accumulated_answers: AnswerAccumulation,
        config: ParsedConfig,
        current_window: int,
        total_windows: int
    ) -> str:
        """
        Format accumulated answers as markdown for live unitary log display.

        Returns markdown-formatted string with:
        - All questions and answers found so far
        - Full citations with PDF page numbers
        - Section grouping
        - Progress indicator
        """
        lines = []
        lines.append(f"# 📊 Live Analysis Progress: Window {current_window}/{total_windows}\n")

        total_answered = 0
        total_questions = config.total_questions

        # Group answers by section
        for section in config.sections:
            section_lines = []
            section_answered = 0

            for question in section.questions:
                if question.id in accumulated_answers and accumulated_answers[question.id]:
                    # Get best answer (highest confidence)
                    best_answer = accumulated_answers[question.id][0]

                    section_lines.append(f"**Q{question.id}:** {question.text}")
                    section_lines.append(f"**Answer:** {best_answer.text}")
                    section_lines.append(f"*Confidence: {best_answer.confidence:.0%}, Expert: {best_answer.expert}*\n")

                    section_answered += 1
                    total_answered += 1

            # Only include section if it has answers
            if section_lines:
                lines.append(f"## {section.name} ({section_answered}/{len(section.questions)} answered)\n")
                lines.extend(section_lines)
                lines.append("")

        pct = (total_answered / total_questions * 100) if total_questions > 0 else 0.0
        lines.append(f"\n---\n**Total Progress: {total_answered}/{total_questions} questions answered ({pct:.1f}%)**")

        return "\n".join(lines)

    def get_browser_output(self, result: AnalysisResult, config: ParsedConfig) -> dict:
        """
        Get formatted output for browser display.

        Args:
            result: Analysis result
            config: Question configuration

        Returns:
            Dict ready to serialize to JSON for frontend
        """
        output = self.layer6_compiler.format_for_browser(result, config)
        # Add extracted key requirements (from Key Requirements Extractor)
        output['key_requirements'] = self.key_details_extractor.get_summary_data()
        return output

    def get_excel_output(self, result: AnalysisResult, config: ParsedConfig) -> dict:
        """
        Get formatted output for Excel export.

        Args:
            result: Analysis result
            config: Question configuration

        Returns:
            Dict with sheet data for Excel generation
        """
        return self.layer6_compiler.format_for_excel(result, config)

    def get_text_report(self, result: AnalysisResult, config: ParsedConfig) -> str:
        """
        Get human-readable text report.

        Args:
            result: Analysis result
            config: Question configuration

        Returns:
            Formatted text report
        """
        return self.layer6_compiler.generate_text_report(result, config)

    def get_bestprep_accumulator_data(self) -> Optional[dict]:
        """
        Get BestPrep accumulator data for export (BestPrep mode only).

        Returns:
            Dict with cumulative_answers and statistics, or None if not in BestPrep mode
        """
        if self.mode == AnalysisMode.BESTPREP and self.bestprep_accumulator:
            return self.bestprep_accumulator.to_dict()
        return None

    def _build_partial_browser_output(self, accumulated_answers: dict, config: ParsedConfig) -> dict:
        """
        Build partial browser output from accumulated answers (for in-progress analyses).

        Args:
            accumulated_answers: Dict mapping question_id -> List[Answer]
            config: Question configuration

        Returns:
            Dict ready for browser display (partial results)
        """
        sections = []

        for section in config.sections:
            section_data = {
                'section_id': section.id,
                'section_name': section.name,
                'description': section.description,
                'questions': []
            }

            for question in section.questions:
                answers_list = accumulated_answers.get(question.id, [])

                # Get primary answer if exists
                if answers_list:
                    primary = answers_list[0]
                    primary_text = primary.text
                    primary_footnote = primary.footnote

                    question_data = {
                        'question_id': question.id,
                        'question_text': question.text,
                        'has_answer': True,
                        'primary_answer': {
                            'text': primary_text,
                            'pages': primary.pages,
                            'confidence': primary.confidence,
                            'footnote': primary_footnote  # Include footnote for partial results
                        }
                    }
                else:
                    # No answer yet
                    question_data = {
                        'question_id': question.id,
                        'question_text': question.text,
                        'has_answer': False,
                        'primary_answer': None
                    }

                section_data['questions'].append(question_data)

            sections.append(section_data)

        return {
            'sections': sections,
            'key_requirements': self.key_details_extractor.get_summary_data()
        }


# =============================================================================
# CONVENIENCE FUNCTION FOR SIMPLE USAGE
# =============================================================================

async def analyze_pdf_simple(
    pdf_path: str,
    config_path: str,
    openai_api_key: str
) -> AnalysisResult:
    """
    Simplified interface for analyzing a PDF document.

    Example usage:
        import asyncio
        from services.hotdog import analyze_pdf_simple

        async def main():
            result = await analyze_pdf_simple(
                pdf_path="document.pdf",
                config_path="questions.json",
                openai_api_key="sk-..."
            )
            print(f"Analyzed {result.total_pages} pages")
            print(f"Answered {result.questions_answered} questions")

        asyncio.run(main())

    Args:
        pdf_path: Path to PDF document
        config_path: Path to question configuration JSON
        openai_api_key: OpenAI API key

    Returns:
        Complete AnalysisResult
    """
    orchestrator = HotdogOrchestrator(
        openai_api_key=openai_api_key,
        config_path=config_path
    )

    result = await orchestrator.analyze_document(pdf_path)
    return result
