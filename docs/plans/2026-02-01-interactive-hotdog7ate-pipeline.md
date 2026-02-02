# Interactive HOTDOG7ATE v2 Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the v2 pipeline from automatic sequential processing to an interactive staged system with user-controlled progression, live feedback, and question selection at each stage.

**Architecture:** The pipeline becomes a state machine with PAUSED states between stages. A new Document Navigator Agent pre-scans the document to direct experts. The frontend adds stage-pause modals with question checkboxes. Each stage appends results to a shared accumulator, and the unitary log updates live for all stages, not just classic analysis.

**Tech Stack:** Python/Flask backend, vanilla JavaScript frontend, OpenAI API, existing HOTDOG7ATE components

---

## Overview: New Pipeline Flow

```
[START]
    ↓
[PRE-SCAN] Document Navigator Agent analyzes structure
    ↓ (auto)
[QUICK-SCAN] Targeted extraction based on structure hints
    ↓ (auto)
[PAUSE 1] User reviews quick-scan results
           - See all answers found
           - Checkboxes: unanswered + <90% auto-selected
           - User can add/remove questions
           - [Continue] [Export] [Stop]
    ↓ (user click)
[EXHAUSTIVE] Classic analysis on selected questions only
    ↓ (auto)
[PAUSE 2] User reviews exhaustive results
           - See updated answers
           - Remaining unanswered auto-selected
           - [Continue to Unanswered] [Skip to RAG] [Export] [Stop]
    ↓ (user click)
[UNANSWERED-ONLY] Second pass on unanswered
    ↓ (auto)
[PAUSE 3] User reviews second pass results
           - [Continue to RAG] [Export] [Stop]
    ↓ (user click)
[RAG] External search via TAVILY
    ↓ (auto)
[COMPLETE] Final results
```

---

## Task 1: Add V2 Pipeline Event Handlers to Frontend

**Files:**
- Modify: `index.html:758-970` (event handler section)

**Step 1: Add missing event handlers**

Add handlers for all v2 pipeline events that currently show "Unknown event":

```javascript
// Add after line 920 (after existing stage_1 handlers)

// V2 Pipeline lifecycle events
else if (data.event === 'pipeline_start') {
    Logger.info(`Pipeline started: ${data.pipeline || 'HOTDOG7ATE'}`);
    Logger.info(`Stages: ${(data.stages || []).join(' → ')}`);
    ProgressTracker.setMessage(`Starting ${data.pipeline || 'HOTDOG7ATE'} Pipeline...`);
}
else if (data.event === 'pipeline_complete') {
    Logger.success('Pipeline complete!');
    if (data.summary) {
        Logger.info(`Summary: ${data.summary.stages_completed?.length || 0} stages, ${data.summary.answered_questions || 0}/${data.summary.total_questions || 0} answered`);
    }
}

// Stage 2: Exhaustive Pass
else if (data.event === 'stage_2_start') {
    Logger.info(`Stage 2: ${data.stage_name || 'Exhaustive Analysis'}`);
    Logger.info(`Processing ${data.questions_count || 0} questions across ${data.windows_count || 0} windows`);
    ProgressTracker.setMessage(`Exhaustive Analysis: 0/${data.windows_count || 0} windows`);
}
else if (data.event === 'stage_2_progress') {
    const pct = Math.round((data.window / data.total_windows) * 100);
    ProgressTracker.setProgress(pct);
    ProgressTracker.setMessage(`Exhaustive: Window ${data.window}/${data.total_windows} (${data.answers_so_far || 0} answers)`);
}
else if (data.event === 'stage_2_complete') {
    Logger.success(`Exhaustive complete: ${data.answers_found || 0} answers found`);
}

// Stage 3: Second Pass (Unanswered Only)
else if (data.event === 'stage_3_start') {
    Logger.info(`Stage 3: ${data.stage_name || 'Second Pass - Unanswered Questions'}`);
    Logger.info(`Targeting ${data.unanswered_count || 0} unanswered questions`);
    ProgressTracker.setMessage(`Second Pass: ${data.unanswered_count || 0} unanswered questions`);
}
else if (data.event === 'stage_3_complete') {
    Logger.success(`Second Pass complete: ${data.answers_found || 0} new answers`);
    if (data.still_unanswered > 0) {
        Logger.warn(`Still unanswered: ${data.still_unanswered}`);
    }
}

// Stage 4: Deep RAG
else if (data.event === 'stage_4_start') {
    Logger.info(`Stage 4: ${data.stage_name || 'Deep RAG - External Search'}`);
    Logger.info(`Searching for ${data.questions_count || 0} questions`);
    ProgressTracker.setMessage('Deep RAG: Searching external sources...');
}
else if (data.event === 'stage_4_complete') {
    Logger.success(`Deep RAG complete: ${data.answers_found || 0} answers from external sources`);
    if (data.disclaimer) {
        Logger.warn(data.disclaimer);
    }
}

// Pre-scan events (new)
else if (data.event === 'prescan_start') {
    Logger.info('Document Navigator scanning structure...');
    ProgressTracker.setMessage('Analyzing document structure...');
}
else if (data.event === 'prescan_complete') {
    Logger.info(`Structure found: TOC=${data.has_toc ? 'Yes' : 'No'}, Index=${data.has_index ? 'Yes' : 'No'}`);
    if (data.expert_assignments) {
        data.expert_assignments.forEach(a => {
            Logger.info(`  ${a.expert}: Pages ${a.pages.join(', ')}`);
        });
    }
}

// Stage pause events (new)
else if (data.event === 'stage_pause') {
    Logger.info(`Pausing for user review: ${data.stage_name}`);
    showStagePauseModal(data);
}
```

**Step 2: Verify handlers work**

Run v2 pipeline and confirm no "Unknown event" messages appear in log.

**Step 3: Commit**

```bash
git add index.html
git commit -m "feat: Add v2 pipeline event handlers to frontend"
```

---

## Task 2: Create Document Navigator Agent

**Files:**
- Create: `services/hotdog/document_navigator.py`

**Step 1: Create the Document Navigator Agent**

```python
"""
Document Navigator Agent for HOTDOG7ATE Pre-Scan.

Analyzes document structure (TOC, index, appendix, headers) and creates
a navigation map that directs each expert to the most relevant pages/windows.
"""

import logging
import re
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from openai import AsyncOpenAI

from .models import Question, ExpertPersona, PageData
from .document_structure_analyzer import DocumentStructureAnalyzer, DocumentStructure

logger = logging.getLogger(__name__)


@dataclass
class ExpertAssignment:
    """Assignment of pages/windows to an expert based on document structure."""
    expert_name: str
    section_id: str
    primary_pages: List[int]  # Pages most likely to have answers
    context_pages: List[int]  # Window before + after for context
    keywords_found: List[str]  # Keywords that led to this assignment
    confidence: float  # How confident we are this is the right area


@dataclass
class NavigationMap:
    """Complete navigation map for all experts."""
    structure: DocumentStructure
    expert_assignments: Dict[str, ExpertAssignment]  # expert_name -> assignment
    unassigned_questions: List[str]  # Questions with no structural hints
    total_pages_to_scan: int
    estimated_reduction: float  # % reduction vs exhaustive scan


class DocumentNavigator:
    """
    Pre-scan agent that creates a navigation map for targeted extraction.

    Analyzes:
    1. Table of Contents - section-to-page mapping
    2. Index - keyword-to-page mapping
    3. Appendices - supplementary material locations
    4. Headers/Footers - section boundaries
    5. Question keywords - match to structural elements
    """

    def __init__(
        self,
        openai_client: Optional[AsyncOpenAI] = None,
        model: str = "gpt-4o"
    ):
        self.client = openai_client
        self.model = model
        self.structure_analyzer = DocumentStructureAnalyzer()

    async def create_navigation_map(
        self,
        pages: List[PageData],
        questions: List[Question],
        experts: Dict[str, ExpertPersona],
        progress_callback: Optional[callable] = None
    ) -> NavigationMap:
        """
        Create a navigation map directing experts to relevant pages.

        Args:
            pages: All document pages
            questions: Questions to answer (filtered by user selection)
            experts: Expert personas by section_id
            progress_callback: Optional callback for progress updates

        Returns:
            NavigationMap with expert assignments
        """
        logger.info("\n" + "="*64)
        logger.info("DOCUMENT NAVIGATOR: Pre-Scan Analysis")
        logger.info("="*64)

        if progress_callback:
            progress_callback('prescan_start', {
                'total_pages': len(pages),
                'total_questions': len(questions),
                'total_experts': len(experts)
            })

        # Step 1: Analyze document structure
        pages_data = [{'page_num': p.page_num, 'text': p.text} for p in pages]
        structure = self.structure_analyzer.analyze(pages_data)

        logger.info(f"  TOC Found: {structure.has_toc} ({len(structure.toc_entries)} entries)")
        logger.info(f"  Index Found: {structure.has_index} ({len(structure.index_entries)} terms)")
        logger.info(f"  Appendix Found: {structure.has_appendix} ({len(structure.appendix_pages)} pages)")

        # Step 2: Extract keywords from each expert's questions
        expert_keywords = self._extract_expert_keywords(questions, experts)

        # Step 3: Create assignments for each expert
        expert_assignments = {}
        unassigned_questions = []

        for section_id, expert in experts.items():
            # Get questions for this expert
            expert_questions = [q for q in questions if q.section_id == section_id]
            if not expert_questions:
                continue

            keywords = expert_keywords.get(section_id, [])

            # Find pages for this expert
            primary_pages = set()
            keywords_found = []

            # Check TOC entries
            for entry_name, page_num in structure.toc_entries.items():
                if self._matches_keywords(entry_name, keywords):
                    primary_pages.add(page_num)
                    # Add a few pages after TOC entry (content usually follows)
                    for offset in range(1, 4):
                        if page_num + offset <= len(pages):
                            primary_pages.add(page_num + offset)
                    keywords_found.append(f"TOC: {entry_name}")

            # Check index entries
            for term, term_pages in structure.index_entries.items():
                if self._matches_keywords(term, keywords):
                    primary_pages.update(term_pages)
                    keywords_found.append(f"Index: {term}")

            # Check section headers
            for page_num, header in structure.section_headers.items():
                if self._matches_keywords(header, keywords):
                    primary_pages.add(page_num)
                    keywords_found.append(f"Header: {header}")

            # Calculate context pages (window before + after)
            context_pages = set()
            for page in primary_pages:
                # Window before (up to 3 pages)
                for offset in range(1, 4):
                    if page - offset >= 1:
                        context_pages.add(page - offset)
                # Window after (up to 3 pages)
                for offset in range(1, 4):
                    if page + offset <= len(pages):
                        context_pages.add(page + offset)

            # Remove primary pages from context (avoid duplication)
            context_pages -= primary_pages

            if primary_pages:
                assignment = ExpertAssignment(
                    expert_name=expert.name,
                    section_id=section_id,
                    primary_pages=sorted(primary_pages),
                    context_pages=sorted(context_pages),
                    keywords_found=keywords_found[:10],  # Limit for display
                    confidence=min(0.9, 0.5 + (len(keywords_found) * 0.1))
                )
                expert_assignments[expert.name] = assignment
                logger.info(f"  {expert.name}: {len(primary_pages)} primary + {len(context_pages)} context pages")
            else:
                # No structural hints - these questions go to full exhaustive
                for q in expert_questions:
                    unassigned_questions.append(q.id)
                logger.info(f"  {expert.name}: No structural hints found")

        # Calculate reduction
        total_primary = sum(len(a.primary_pages) for a in expert_assignments.values())
        total_context = sum(len(a.context_pages) for a in expert_assignments.values())
        total_to_scan = total_primary + total_context
        estimated_reduction = 1 - (total_to_scan / (len(pages) * len(experts))) if pages and experts else 0

        nav_map = NavigationMap(
            structure=structure,
            expert_assignments=expert_assignments,
            unassigned_questions=unassigned_questions,
            total_pages_to_scan=total_to_scan,
            estimated_reduction=max(0, estimated_reduction)
        )

        if progress_callback:
            progress_callback('prescan_complete', {
                'has_toc': structure.has_toc,
                'has_index': structure.has_index,
                'has_appendix': structure.has_appendix,
                'toc_entries': len(structure.toc_entries),
                'index_terms': len(structure.index_entries),
                'expert_assignments': [
                    {
                        'expert': a.expert_name,
                        'pages': a.primary_pages[:5],  # First 5 for display
                        'total_pages': len(a.primary_pages) + len(a.context_pages),
                        'keywords': a.keywords_found[:3]
                    }
                    for a in expert_assignments.values()
                ],
                'unassigned_questions': len(unassigned_questions),
                'estimated_reduction': f"{estimated_reduction*100:.0f}%"
            })

        logger.info(f"\nNavigation Map Complete:")
        logger.info(f"  Experts with assignments: {len(expert_assignments)}")
        logger.info(f"  Total pages to quick-scan: {total_to_scan}")
        logger.info(f"  Estimated reduction: {estimated_reduction*100:.0f}%")
        logger.info(f"  Unassigned questions: {len(unassigned_questions)}")

        return nav_map

    def _extract_expert_keywords(
        self,
        questions: List[Question],
        experts: Dict[str, ExpertPersona]
    ) -> Dict[str, List[str]]:
        """Extract relevant keywords for each expert based on their questions."""
        expert_keywords = {}

        # Stop words to exclude
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'which',
            'who', 'how', 'when', 'where', 'why', 'does', 'do', 'did',
            'have', 'has', 'will', 'would', 'could', 'should', 'may',
            'required', 'requirements', 'specify', 'specified', 'project',
            'contractor', 'shall', 'must', 'for', 'with', 'this', 'that',
            'any', 'all', 'each', 'every', 'been', 'being', 'their'
        }

        for section_id, expert in experts.items():
            keywords = set()

            # Add keywords from expert name/specialization
            expert_words = re.findall(r'\b[a-zA-Z]+\b', expert.name.lower())
            keywords.update(w for w in expert_words if w not in stop_words and len(w) > 2)

            # Add keywords from questions
            section_questions = [q for q in questions if q.section_id == section_id]
            for q in section_questions:
                q_words = re.findall(r'\b[a-zA-Z]+\b', q.text.lower())
                keywords.update(w for w in q_words if w not in stop_words and len(w) > 3)

            expert_keywords[section_id] = list(keywords)[:20]  # Limit keywords

        return expert_keywords

    def _matches_keywords(self, text: str, keywords: List[str]) -> bool:
        """Check if text contains any of the keywords."""
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)
```

**Step 2: Commit**

```bash
git add services/hotdog/document_navigator.py
git commit -m "feat: Create Document Navigator Agent for pre-scan"
```

---

## Task 3: Create Interactive Stage Pause System (Backend)

**Files:**
- Modify: `app.py` (add pause state management and continuation endpoints)
- Modify: `services/hotdog/pipeline_coordinator.py` (add pause points)

**Step 1: Add pipeline state management to app.py**

Add after line 60 (after other global dicts):

```python
# Pipeline pause state management
# Stores: session_id -> {
#   'paused_at': stage_name,
#   'stage_data': {...},
#   'selected_questions': [...],
#   'accumulated_results': {...}
# }
pipeline_pause_states = {}
```

**Step 2: Add continuation endpoint to app.py**

Add after line 1500:

```python
@app.route('/api/analyze/continue/<session_id>', methods=['POST'])
def continue_analysis(session_id):
    """
    Continue paused v2 pipeline analysis.

    Request body:
    {
        "selected_questions": ["Q1", "Q2", ...],  # Questions to process in next stage
        "skip_to_stage": "rag" | null,  # Optional: skip to specific stage
        "stop_after_current": false  # If true, stop after current stage completes
    }
    """
    data = request.json or {}

    if session_id not in pipeline_pause_states:
        return jsonify({
            'success': False,
            'error': 'No paused analysis found for this session'
        }), 404

    pause_state = pipeline_pause_states[session_id]
    selected_questions = data.get('selected_questions', [])
    skip_to_stage = data.get('skip_to_stage')

    # Update pause state with user selections
    pause_state['selected_questions'] = selected_questions
    pause_state['skip_to_stage'] = skip_to_stage
    pause_state['continue_requested'] = True

    logger.info(f"Continuing analysis {session_id}")
    logger.info(f"  Selected questions: {len(selected_questions)}")
    logger.info(f"  Skip to stage: {skip_to_stage or 'none'}")

    return jsonify({
        'success': True,
        'message': 'Analysis continuing',
        'selected_questions': len(selected_questions)
    })


@app.route('/api/analyze/pause-state/<session_id>', methods=['GET'])
def get_pause_state(session_id):
    """Get current pause state for a session."""
    if session_id not in pipeline_pause_states:
        return jsonify({
            'success': False,
            'paused': False
        })

    pause_state = pipeline_pause_states[session_id]
    return jsonify({
        'success': True,
        'paused': True,
        'paused_at': pause_state.get('paused_at'),
        'stage_data': pause_state.get('stage_data', {}),
        'questions': pause_state.get('questions_for_selection', [])
    })
```

**Step 3: Add pause callback to orchestrator integration**

Modify `app.py` run_analysis_task function to include pause callback:

```python
# Add to progress_callback function (around line 740):

def pause_callback(stage_name: str, stage_data: dict, questions_for_selection: list):
    """Called when pipeline reaches a pause point."""
    pipeline_pause_states[session_id] = {
        'paused_at': stage_name,
        'stage_data': stage_data,
        'questions_for_selection': questions_for_selection,
        'continue_requested': False,
        'selected_questions': [],
        'timestamp': datetime.now().isoformat()
    }

    # Emit pause event
    progress_callback('stage_pause', {
        'stage_name': stage_name,
        'stage_data': stage_data,
        'questions_for_selection': questions_for_selection
    })
```

**Step 4: Commit**

```bash
git add app.py
git commit -m "feat: Add pipeline pause state management and continuation endpoints"
```

---

## Task 4: Modify Pipeline Coordinator for Interactive Flow

**Files:**
- Modify: `services/hotdog/pipeline_coordinator.py`

**Step 1: Add pause mechanism to PipelineCoordinator**

Replace the `run_full_pipeline` method with interactive version:

```python
async def run_full_pipeline(
    self,
    pages: List[PageData],
    config: ParsedConfig,
    experts: Dict[str, ExpertPersona],
    windows: List[WindowContext],
    enable_second_pass: bool = True,
    enable_rag: bool = False,
    pause_callback: Optional[Callable] = None,
    check_continue: Optional[Callable] = None
) -> Dict[str, List[Answer]]:
    """
    Run the complete HOTDOG7ATE analysis pipeline with interactive pauses.

    Args:
        pages: Extracted document pages
        config: Question configuration
        experts: Expert personas
        windows: Pre-created 3-page windows
        enable_second_pass: Whether to run second pass for unanswered
        enable_rag: Whether to run deep RAG
        pause_callback: Callback to pause for user input
        check_continue: Callback to check if user wants to continue

    Returns:
        All accumulated answers (question_id -> List[Answer])
    """
    logger.info("\n" + "="*64)
    logger.info("HOTDOG7ATE Interactive Multi-Pass Pipeline Starting")
    logger.info("="*64)

    all_questions = list(config.question_map.values())
    self.state.all_questions = set(q.id for q in all_questions)

    # ============================================================
    # STAGE 1: Comprehensive Quick-Scan
    # ============================================================
    stage_1_result = await self._run_stage_1(pages, all_questions, experts)

    # ============================================================
    # PAUSE 1: User reviews quick-scan results
    # ============================================================
    questions_for_exhaustive = await self._pause_after_quickscan(
        all_questions,
        stage_1_result,
        pause_callback,
        check_continue
    )

    if questions_for_exhaustive is None:
        # User chose to stop/export
        self._print_summary()
        return self.accumulator.get_accumulated_answers()

    # ============================================================
    # STAGE 2: Exhaustive Pass (Classic Analysis on Selected)
    # ============================================================
    if questions_for_exhaustive:
        stage_2_result = await self._run_stage_2(
            windows, questions_for_exhaustive, experts
        )

        # ============================================================
        # PAUSE 2: User reviews exhaustive results
        # ============================================================
        unanswered, skip_to_rag = await self._pause_after_exhaustive(
            all_questions,
            pause_callback,
            check_continue
        )

        if unanswered is None:
            # User chose to stop/export
            self._print_summary()
            return self.accumulator.get_accumulated_answers()

        if skip_to_rag:
            # Skip to RAG stage
            enable_second_pass = False
    else:
        unanswered = self._get_unanswered_questions(all_questions)

    # ============================================================
    # STAGE 3: Second Pass (if enabled and there are unanswered)
    # ============================================================
    if enable_second_pass and unanswered:
        stage_3_result = await self._run_stage_3(
            windows, unanswered, experts
        )

        # ============================================================
        # PAUSE 3: User reviews second pass results
        # ============================================================
        proceed_to_rag = await self._pause_after_second_pass(
            all_questions,
            pause_callback,
            check_continue
        )

        if proceed_to_rag is None:
            # User chose to stop/export
            self._print_summary()
            return self.accumulator.get_accumulated_answers()

        enable_rag = proceed_to_rag

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


async def _pause_after_quickscan(
    self,
    all_questions: List[Question],
    stage_1_result: StageResult,
    pause_callback: Optional[Callable],
    check_continue: Optional[Callable]
) -> Optional[List[Question]]:
    """
    Pause after quick-scan for user to select questions for exhaustive pass.

    Returns:
        List of questions to process, or None if user wants to stop
    """
    # Build question list with auto-selection
    questions_for_selection = []

    for q in all_questions:
        is_answered = q.id in self.state.answered_questions
        is_high_confidence = q.id in self.state.high_confidence_questions

        # Get answer details if exists
        answer_data = None
        if q.id in stage_1_result.answers:
            answer = stage_1_result.answers[q.id]
            answer_data = {
                'text': answer.text,
                'confidence': answer.confidence,
                'pages': answer.pages
            }

        questions_for_selection.append({
            'question_id': q.id,
            'question_text': q.text,
            'section_id': q.section_id,
            'is_answered': is_answered,
            'is_high_confidence': is_high_confidence,
            'auto_selected': not is_answered or not is_high_confidence,  # Select unanswered or <90%
            'answer': answer_data
        })

    if pause_callback:
        pause_callback(
            'after_quickscan',
            {
                'high_confidence_count': len(self.state.high_confidence_questions),
                'answered_count': len(self.state.answered_questions),
                'total_questions': len(all_questions)
            },
            questions_for_selection
        )

    # Wait for user to continue
    if check_continue:
        result = await self._wait_for_continue(check_continue)
        if result is None:
            return None

        # Filter questions based on user selection
        selected_ids = set(result.get('selected_questions', []))
        return [q for q in all_questions if q.id in selected_ids]

    # No interactive mode - use default logic
    return self._get_questions_for_stage_2(all_questions, stage_1_result)


async def _wait_for_continue(
    self,
    check_continue: Callable,
    poll_interval: float = 0.5,
    timeout: float = 3600  # 1 hour timeout
) -> Optional[Dict]:
    """
    Wait for user to click continue or stop.

    Returns:
        Dict with user selections, or None if stopped/timeout
    """
    import asyncio
    elapsed = 0

    while elapsed < timeout:
        result = check_continue()

        if result.get('continue_requested'):
            return result

        if result.get('stop_requested'):
            return None

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    logger.warning("Pause timeout reached")
    return None
```

**Step 2: Commit**

```bash
git add services/hotdog/pipeline_coordinator.py
git commit -m "feat: Add interactive pause points to pipeline coordinator"
```

---

## Task 5: Create Stage Pause Modal (Frontend)

**Files:**
- Modify: `index.html` (add modal HTML and JavaScript)

**Step 1: Add modal HTML**

Add after the results modal (around line 400):

```html
<!-- Stage Pause Modal -->
<div id="stagePauseModal" class="modal" style="display: none;">
    <div class="modal-content" style="max-width: 900px; max-height: 90vh; overflow-y: auto;">
        <div class="modal-header" style="background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%); color: white; padding: 20px;">
            <h2 id="pauseModalTitle" style="margin: 0;">Stage Complete - Review Results</h2>
            <p id="pauseModalSubtitle" style="margin: 10px 0 0 0; opacity: 0.9;"></p>
        </div>

        <div class="modal-body" style="padding: 20px;">
            <!-- Stage Summary -->
            <div id="pauseStageSummary" style="background: #f8fafc; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                <h3 style="margin: 0 0 10px 0; color: #1E3A8A;">Stage Summary</h3>
                <div id="pauseSummaryContent"></div>
            </div>

            <!-- Question Selection -->
            <div id="pauseQuestionSelection" style="margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h3 style="margin: 0; color: #1E3A8A;">Select Questions for Next Stage</h3>
                    <div>
                        <button onclick="selectAllPauseQuestions()" class="btn-secondary" style="margin-right: 10px;">Select All</button>
                        <button onclick="deselectAllPauseQuestions()" class="btn-secondary">Deselect All</button>
                    </div>
                </div>

                <div id="pauseQuestionsContainer" style="max-height: 400px; overflow-y: auto; border: 1px solid #e5e7eb; border-radius: 8px;">
                    <!-- Questions will be populated here -->
                </div>

                <div id="pauseSelectionSummary" style="margin-top: 10px; color: #6b7280; font-size: 14px;">
                    <span id="selectedCount">0</span> questions selected for next stage
                </div>
            </div>

            <!-- Action Buttons -->
            <div style="display: flex; justify-content: space-between; border-top: 1px solid #e5e7eb; padding-top: 20px;">
                <div>
                    <button onclick="exportCurrentResults()" class="btn-secondary" style="margin-right: 10px;">
                        Export Current Results
                    </button>
                    <button onclick="stopAnalysisFromPause()" class="btn-danger">
                        Stop Analysis
                    </button>
                </div>
                <div>
                    <button id="skipToRagBtn" onclick="skipToRag()" class="btn-secondary" style="margin-right: 10px; display: none;">
                        Skip to RAG
                    </button>
                    <button onclick="continueToNextStage()" class="btn-primary">
                        Continue Analysis
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>
```

**Step 2: Add JavaScript for pause modal**

Add after line 1900:

```javascript
// ============================================================
// STAGE PAUSE MODAL FUNCTIONS
// ============================================================

let currentPauseData = null;

function showStagePauseModal(data) {
    currentPauseData = data;
    const modal = document.getElementById('stagePauseModal');

    // Set titles based on stage
    const titles = {
        'after_quickscan': {
            title: 'Quick-Scan Complete',
            subtitle: 'Review answers found and select questions for detailed analysis'
        },
        'after_exhaustive': {
            title: 'Exhaustive Analysis Complete',
            subtitle: 'Review results and select remaining questions for second pass'
        },
        'after_second_pass': {
            title: 'Second Pass Complete',
            subtitle: 'Review results - proceed to external search (RAG)?'
        }
    };

    const stageInfo = titles[data.stage_name] || { title: 'Stage Complete', subtitle: '' };
    document.getElementById('pauseModalTitle').textContent = stageInfo.title;
    document.getElementById('pauseModalSubtitle').textContent = stageInfo.subtitle;

    // Populate summary
    const summaryHtml = `
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px;">
            <div style="text-align: center; padding: 10px; background: #dcfce7; border-radius: 8px;">
                <div style="font-size: 24px; font-weight: bold; color: #16a34a;">${data.stage_data.answered_count || 0}</div>
                <div style="color: #166534; font-size: 13px;">Answered</div>
            </div>
            <div style="text-align: center; padding: 10px; background: #dbeafe; border-radius: 8px;">
                <div style="font-size: 24px; font-weight: bold; color: #2563eb;">${data.stage_data.high_confidence_count || 0}</div>
                <div style="color: #1d4ed8; font-size: 13px;">High Confidence (90%+)</div>
            </div>
            <div style="text-align: center; padding: 10px; background: #fef3c7; border-radius: 8px;">
                <div style="font-size: 24px; font-weight: bold; color: #d97706;">${data.stage_data.total_questions - (data.stage_data.answered_count || 0)}</div>
                <div style="color: #92400e; font-size: 13px;">Unanswered</div>
            </div>
        </div>
    `;
    document.getElementById('pauseSummaryContent').innerHTML = summaryHtml;

    // Populate questions
    populatePauseQuestions(data.questions_for_selection || []);

    // Show/hide skip to RAG button
    if (data.stage_name === 'after_exhaustive') {
        document.getElementById('skipToRagBtn').style.display = 'inline-block';
    } else {
        document.getElementById('skipToRagBtn').style.display = 'none';
    }

    modal.style.display = 'flex';
}

function populatePauseQuestions(questions) {
    const container = document.getElementById('pauseQuestionsContainer');

    let html = '<table style="width: 100%; border-collapse: collapse;">';
    html += `
        <thead style="background: #f1f5f9; position: sticky; top: 0;">
            <tr>
                <th style="padding: 10px; text-align: left; width: 50px;">Select</th>
                <th style="padding: 10px; text-align: left;">Question</th>
                <th style="padding: 10px; text-align: center; width: 100px;">Status</th>
                <th style="padding: 10px; text-align: center; width: 100px;">Confidence</th>
            </tr>
        </thead>
        <tbody>
    `;

    questions.forEach((q, idx) => {
        const checked = q.auto_selected ? 'checked' : '';
        const statusBadge = q.is_high_confidence
            ? '<span style="background: #dcfce7; color: #16a34a; padding: 2px 8px; border-radius: 4px; font-size: 12px;">High Confidence</span>'
            : q.is_answered
                ? '<span style="background: #fef3c7; color: #d97706; padding: 2px 8px; border-radius: 4px; font-size: 12px;">Low Confidence</span>'
                : '<span style="background: #fee2e2; color: #dc2626; padding: 2px 8px; border-radius: 4px; font-size: 12px;">Unanswered</span>';

        const confidence = q.answer?.confidence ? `${Math.round(q.answer.confidence * 100)}%` : '-';
        const rowBg = idx % 2 === 0 ? '#ffffff' : '#f8fafc';

        html += `
            <tr style="background: ${rowBg}; border-bottom: 1px solid #e5e7eb;">
                <td style="padding: 10px; text-align: center;">
                    <input type="checkbox" id="pauseQ_${q.question_id}"
                           data-question-id="${q.question_id}"
                           class="pause-question-checkbox"
                           ${checked}
                           onchange="updatePauseSelectionCount()">
                </td>
                <td style="padding: 10px;">
                    <div style="font-weight: 500; color: #1E3A8A;">${q.question_id}</div>
                    <div style="color: #4b5563; font-size: 13px;">${q.question_text}</div>
                    ${q.answer ? `<div style="color: #6b7280; font-size: 12px; margin-top: 5px; font-style: italic;">${q.answer.text.substring(0, 150)}...</div>` : ''}
                </td>
                <td style="padding: 10px; text-align: center;">${statusBadge}</td>
                <td style="padding: 10px; text-align: center; font-weight: 600; color: ${q.answer?.confidence >= 0.9 ? '#16a34a' : '#d97706'};">${confidence}</td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    container.innerHTML = html;

    updatePauseSelectionCount();
}

function updatePauseSelectionCount() {
    const checkboxes = document.querySelectorAll('.pause-question-checkbox:checked');
    document.getElementById('selectedCount').textContent = checkboxes.length;
}

function selectAllPauseQuestions() {
    document.querySelectorAll('.pause-question-checkbox').forEach(cb => cb.checked = true);
    updatePauseSelectionCount();
}

function deselectAllPauseQuestions() {
    document.querySelectorAll('.pause-question-checkbox').forEach(cb => cb.checked = false);
    updatePauseSelectionCount();
}

function getSelectedPauseQuestions() {
    const selected = [];
    document.querySelectorAll('.pause-question-checkbox:checked').forEach(cb => {
        selected.push(cb.dataset.questionId);
    });
    return selected;
}

async function continueToNextStage() {
    const selectedQuestions = getSelectedPauseQuestions();

    try {
        const response = await fetch(`/api/analyze/continue/${currentSessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                selected_questions: selectedQuestions
            })
        });

        const data = await response.json();
        if (data.success) {
            closePauseModal();
            Logger.info(`Continuing with ${selectedQuestions.length} questions`);
        } else {
            Logger.error('Failed to continue: ' + data.error);
        }
    } catch (err) {
        Logger.error('Failed to continue analysis: ' + err.message);
    }
}

async function skipToRag() {
    const selectedQuestions = getSelectedPauseQuestions();

    try {
        const response = await fetch(`/api/analyze/continue/${currentSessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                selected_questions: selectedQuestions,
                skip_to_stage: 'rag'
            })
        });

        const data = await response.json();
        if (data.success) {
            closePauseModal();
            Logger.info('Skipping to Deep RAG stage');
        }
    } catch (err) {
        Logger.error('Failed to skip to RAG: ' + err.message);
    }
}

function exportCurrentResults() {
    // Trigger export with current results
    closePauseModal();
    exportAnalysis();
}

function stopAnalysisFromPause() {
    closePauseModal();
    stopAnalysis();
}

function closePauseModal() {
    document.getElementById('stagePauseModal').style.display = 'none';
    currentPauseData = null;
}

// Close modal on outside click
document.getElementById('stagePauseModal')?.addEventListener('click', function(e) {
    if (e.target === this) {
        closePauseModal();
    }
});
```

**Step 3: Commit**

```bash
git add index.html
git commit -m "feat: Add interactive stage pause modal with question selection"
```

---

## Task 6: Update Pipeline to Emit Live Unitary Log for All Stages

**Files:**
- Modify: `services/hotdog/pipeline_coordinator.py`

**Step 1: Add unitary log emission to Stage 2**

Update `_run_stage_2` to emit `window_complete` events like classic mode:

```python
async def _run_stage_2(
    self,
    windows: List[WindowContext],
    questions: List[Question],
    experts: Dict
) -> StageResult:
    """Run Stage 2: Exhaustive Pass with live unitary log updates."""
    self.state.current_stage = PipelineStage.EXHAUSTIVE
    self._emit_progress('stage_2_start', {
        'stage': 'exhaustive',
        'stage_name': 'Exhaustive Analysis',
        'questions_count': len(questions),
        'windows_count': len(windows)
    })

    start = datetime.now()
    answers = {}

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

        # Collect new answers for this window
        new_answers = []
        for qid, answer in result.answers.items():
            if qid not in answers:
                answers[qid] = answer
                self.state.answered_questions.add(qid)
                if answer.confidence >= 0.9:
                    self.state.high_confidence_questions.add(qid)

                # Format for frontend
                question = next((q for q in questions if q.id == qid), None)
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

        # Emit window complete with new answers (for live unitary log)
        self._emit_progress('window_complete', {
            'window_num': window_idx,
            'total_windows': len(windows),
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
```

**Step 2: Similarly update Stage 3 to emit live updates**

```python
async def _run_stage_3(
    self,
    windows: List[WindowContext],
    questions: List[Question],
    experts: Dict
) -> StageResult:
    """Run Stage 3: Second Pass with live unitary log updates."""
    self.state.current_stage = PipelineStage.SECOND_PASS
    self._emit_progress('stage_3_start', {
        'stage': 'second_pass',
        'stage_name': 'Second Pass - Enhanced Scrutiny',
        'unanswered_count': len(questions)
    })

    start = datetime.now()

    # Process with live updates
    answers = {}
    total_windows = len(windows)

    for window_idx, window in enumerate(windows, 1):
        self._emit_progress('window_processing', {
            'window_num': window_idx,
            'total_windows': total_windows,
            'pages': window.pages,
            'stage': 'second_pass'
        })

        # Get answers for this window
        window_answers = await self.second_pass._process_window_enhanced(
            window=window,
            questions=questions,
            experts=experts
        )

        # Collect new answers
        new_answers = []
        for qid, answer in window_answers.answers.items():
            if qid not in answers:
                answers[qid] = answer
                self.state.answered_questions.add(qid)

                question = next((q for q in questions if q.id == qid), None)
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
            else:
                # Merge with existing
                answers[qid].merge_with(answer)

        # Add to accumulator
        if qid not in self.accumulator.accumulation:
            self.accumulator.accumulation[qid] = []
        self.accumulator.accumulation[qid].append(answer)

        # Emit window complete
        if new_answers:
            self._emit_progress('window_complete', {
                'window_num': window_idx,
                'total_windows': total_windows,
                'answers_found': len(window_answers.answers),
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
```

**Step 3: Commit**

```bash
git add services/hotdog/pipeline_coordinator.py
git commit -m "feat: Emit live unitary log updates for all v2 pipeline stages"
```

---

## Task 7: Integrate Document Navigator with Quick-Scan

**Files:**
- Modify: `services/hotdog/comprehensive_processor.py`
- Modify: `services/hotdog/pipeline_coordinator.py`

**Step 1: Update ComprehensiveProcessor to use navigation map**

```python
async def quick_scan_with_navigation(
    self,
    pages: List[PageData],
    questions: List[Question],
    experts: Dict,
    navigation_map: NavigationMap
) -> Tuple[Dict[str, Answer], List[Question]]:
    """
    Perform quick-scan using navigation map for targeted extraction.

    Uses expert assignments from Document Navigator to focus extraction
    on pages most likely to contain answers.
    """
    logger.info(f"\n{'='*64}")
    logger.info("STAGE 1: HOTDOG7ATE Targeted Quick-Scan")
    logger.info(f"Using Navigation Map: {len(navigation_map.expert_assignments)} expert assignments")
    logger.info(f"{'='*64}")

    start_time = datetime.now()
    high_confidence_answers = {}
    questions_for_exhaustive = []

    # Process each expert's assigned pages
    for expert_name, assignment in navigation_map.expert_assignments.items():
        expert = next((e for e in experts.values() if e.name == expert_name), None)
        if not expert:
            continue

        # Get questions for this expert
        expert_questions = [q for q in questions if q.section_id == assignment.section_id]
        if not expert_questions:
            continue

        logger.info(f"\n{expert_name}:")
        logger.info(f"  Primary pages: {assignment.primary_pages[:10]}{'...' if len(assignment.primary_pages) > 10 else ''}")
        logger.info(f"  Questions: {len(expert_questions)}")

        # Combine primary + context pages
        all_assigned_pages = set(assignment.primary_pages) | set(assignment.context_pages)
        assigned_page_data = [p for p in pages if p.page_num in all_assigned_pages]

        # Process each question with assigned pages
        for question in expert_questions:
            self.questions_processed += 1

            answer = await self._targeted_extraction(
                question=question,
                pages=assigned_page_data,
                expert=expert
            )

            if answer and answer.confidence >= self.confidence_threshold:
                high_confidence_answers[question.id] = answer
                self.high_confidence_answers += 1
                logger.info(f"    {question.id}: Quick-scan success ({answer.confidence:.0%})")
            else:
                questions_for_exhaustive.append(question)
                logger.debug(f"    {question.id}: Needs exhaustive pass")

    # Add unassigned questions directly to exhaustive
    unassigned = [q for q in questions if q.id in navigation_map.unassigned_questions]
    questions_for_exhaustive.extend(unassigned)
    if unassigned:
        logger.info(f"\nUnassigned questions (no structural hints): {len(unassigned)}")

    elapsed = (datetime.now() - start_time).total_seconds()

    logger.info(f"\nQuick-Scan Complete ({elapsed:.1f}s)")
    logger.info(f"   High-confidence answers: {len(high_confidence_answers)}/{len(questions)}")
    logger.info(f"   Questions for exhaustive: {len(questions_for_exhaustive)}")

    return high_confidence_answers, questions_for_exhaustive
```

**Step 2: Update pipeline coordinator to use Document Navigator**

```python
# At top of pipeline_coordinator.py, add import:
from .document_navigator import DocumentNavigator, NavigationMap

# In PipelineCoordinator.__init__, add:
self.navigator = DocumentNavigator(openai_client, model) if openai_client else None

# In run_full_pipeline, before Stage 1:
# ============================================================
# PRE-SCAN: Document Navigator Analysis
# ============================================================
navigation_map = None
if self.navigator:
    navigation_map = await self.navigator.create_navigation_map(
        pages=pages,
        questions=all_questions,
        experts=experts,
        progress_callback=self._emit_progress
    )

# In _run_stage_1, use navigation map if available:
if navigation_map:
    answers, remaining = await self.comprehensive.quick_scan_with_navigation(
        pages, questions, experts, navigation_map
    )
else:
    answers, remaining = await self.comprehensive.quick_scan(
        pages, questions, experts
    )
```

**Step 3: Commit**

```bash
git add services/hotdog/comprehensive_processor.py services/hotdog/pipeline_coordinator.py
git commit -m "feat: Integrate Document Navigator with Quick-Scan stage"
```

---

## Task 8: Update Frontend Unitary Log for Stage Indicators

**Files:**
- Modify: `index.html`

**Step 1: Update unitary table to show stage source**

Modify `updateUnitaryTableWithNewAnswers` to include stage information:

```javascript
function updateUnitaryTableWithNewAnswers(newAnswers, stage = 'classic') {
    const stageLabels = {
        'quick_scan': 'Quick-Scan',
        'exhaustive': 'Exhaustive',
        'second_pass': 'Second Pass',
        'deep_rag': 'Deep RAG',
        'classic': ''
    };

    const stageColors = {
        'quick_scan': '#8b5cf6',  // Purple
        'exhaustive': '#3b82f6',  // Blue
        'second_pass': '#f59e0b', // Amber
        'deep_rag': '#10b981',    // Green
        'classic': '#6b7280'      // Gray
    };

    const updatedQuestionIds = [];

    newAnswers.forEach(answer => {
        if (allQuestions[answer.question_id]) {
            const q = allQuestions[answer.question_id];
            q.status = 'found';
            q.answer = answer.answer_text;
            q.pages = answer.pages;
            q.footnote = answer.footnote;
            q.stage = stage;  // Track which stage found this
            q.stageLabel = stageLabels[stage] || '';
            q.stageColor = stageColors[stage] || '#6b7280';

            updatedQuestionIds.push(answer.question_id);
        }
    });

    updateUnitaryTableRows(updatedQuestionIds);
}

// Update handleEvent to pass stage information:
else if (data.event === 'window_complete') {
    if (data.new_answers && data.new_answers.length > 0) {
        const stage = data.stage || 'classic';
        updateUnitaryTableWithNewAnswers(data.new_answers, stage);

        // Log with stage info
        const stageLabel = data.stage ? ` [${data.stage}]` : '';
        Logger.info(`Window ${data.window_num}: ${data.new_answers.length} answers${stageLabel}`);
    }
}
```

**Step 2: Update table row rendering to show stage badge**

```javascript
function renderUnitaryTableRow(q) {
    // ... existing code ...

    // Add stage badge if present
    let stageBadge = '';
    if (q.stageLabel) {
        stageBadge = `<span style="background: ${q.stageColor}; color: white; padding: 1px 6px; border-radius: 3px; font-size: 10px; margin-left: 5px;">${q.stageLabel}</span>`;
    }

    // Include in answer cell
    // ...
}
```

**Step 3: Commit**

```bash
git add index.html
git commit -m "feat: Show stage source badges in unitary log table"
```

---

## Task 9: Wire Up Complete Interactive Flow

**Files:**
- Modify: `app.py`
- Modify: `services/hotdog/orchestrator.py`

**Step 1: Update orchestrator to pass pause/continue callbacks**

```python
# In orchestrator.py, modify the v2 pipeline section:

if self.mode == AnalysisMode.BID_SPEC and self.use_pipeline_v2:
    # ... existing setup code ...

    # Create pause/continue callbacks
    def pause_callback(stage_name: str, stage_data: dict, questions: list):
        self._emit_progress('stage_pause', {
            'stage_name': stage_name,
            'stage_data': stage_data,
            'questions_for_selection': questions
        })

    def check_continue():
        # This will be set by app.py
        return self._continue_state or {}

    coordinator = PipelineCoordinator(
        comprehensive_processor=comprehensive,
        exhaustive_processor=self.layer3_processor,
        second_pass_processor=self.layer3_5_second_pass,
        accumulator=self.layer4_accumulator,
        rag_processor=rag,
        progress_callback=self._emit_progress,
        pause_callback=pause_callback,
        check_continue_callback=check_continue
    )
```

**Step 2: Update app.py to manage continue state**

```python
# Add to run_analysis_task:

# Set up continue state management
orchestrator._continue_state = {}

def update_continue_state(session_id):
    """Update orchestrator continue state from pause_states."""
    if session_id in pipeline_pause_states:
        orchestrator._continue_state = pipeline_pause_states[session_id]
    else:
        orchestrator._continue_state = {}

# Pass to orchestrator initialization
orchestrator.continue_state_updater = lambda: update_continue_state(session_id)
```

**Step 3: Commit**

```bash
git add app.py services/hotdog/orchestrator.py
git commit -m "feat: Wire up interactive pipeline pause/continue flow"
```

---

## Task 10: Final Integration Testing

**Step 1: Manual test checklist**

1. Start v2 pipeline analysis
2. Verify pre-scan events appear in log with expert assignments
3. Verify quick-scan completes and pause modal appears
4. Verify questions are auto-selected (unanswered + <90%)
5. Select/deselect questions and click Continue
6. Verify exhaustive stage runs only on selected questions
7. Verify unitary log updates live during exhaustive stage
8. Verify pause appears after exhaustive with Skip to RAG option
9. Test Export button at pause points
10. Test Stop button at pause points
11. Complete full pipeline to RAG stage

**Step 2: Commit final integration**

```bash
git add .
git commit -m "feat: Complete interactive HOTDOG7ATE v2 pipeline implementation"
```

---

## Summary

This plan implements:

1. **Frontend Event Handlers** - All v2 pipeline events properly handled
2. **Document Navigator Agent** - Pre-scans document structure to direct experts
3. **Interactive Pause System** - Backend state management + continuation endpoints
4. **Stage Pause Modal** - User reviews results and selects questions
5. **Live Unitary Log** - All stages emit window_complete with new_answers
6. **Navigation-Guided Quick-Scan** - Uses structural hints for targeted extraction
7. **Stage Source Badges** - Shows which stage found each answer
8. **Full Interactive Flow** - Pause after each stage, export/stop anytime

Total: 10 tasks, estimated ~2-3 hours implementation time
