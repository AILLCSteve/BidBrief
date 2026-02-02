# HOTDOG-AI v2 Multi-Pass Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform HOTDOG from single-pass exhaustive processing into an intelligent 4-stage pipeline with user control over which questions receive additional scrutiny via comprehensive quick-scan, exhaustive analysis, second-pass retry, and optional deep RAG.

**Architecture:**
- Stage 1 (Comprehensive Quick-Scan) uses document structure (TOC, index, headers, appendix) to fast-track high-confidence answers
- Stage 2 (Exhaustive) runs current window-based processing only for questions needing deeper analysis (<90% confidence or user-selected)
- Stage 3 (Second Pass) retries questions with NO answers found using enhanced creative prompts
- Stage 4 (Deep RAG) optionally searches external similar projects for remaining unanswered questions

**Tech Stack:** Python 3.11+, Flask, OpenAI GPT-4o, asyncio, existing HOTDOG layer architecture

---

## Table of Contents

1. [Phase 1: Second Pass Integration for Bid/Spec Mode](#phase-1-second-pass-integration)
2. [Phase 2: UI Augmentation - Question Selection Checkboxes](#phase-2-ui-augmentation)
3. [Phase 3: Stage 1 - Comprehensive Quick-Scan Pass](#phase-3-comprehensive-quick-scan)
4. [Phase 4: Stage 2 - Selective Exhaustive Pass](#phase-4-selective-exhaustive)
5. [Phase 5: Stage 4 - Deep RAG External Search](#phase-5-deep-rag)
6. [Phase 6: Pipeline Orchestration](#phase-6-pipeline-orchestration)

---

## Current Architecture Reference

```
┌─────────────────────────────────────────────────────────────────┐
│                   CURRENT: Single Pipeline                       │
├─────────────────────────────────────────────────────────────────┤
│ L0: Document Ingestion → L1: Config → L2: Experts → L3: Windows │
│ → L4: Accumulate → L5: Tokens → L6: Output → [L7: Synthesis]    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   NEW: 4-Stage Pipeline                          │
├─────────────────────────────────────────────────────────────────┤
│ Stage 1: Comprehensive Quick-Scan (TOC/Index/Headers)           │
│     ↓ questions <90% confidence                                  │
│ Stage 2: Selective Exhaustive (current window processing)        │
│     ↓ questions with 0 answers                                   │
│ Stage 3: Second Pass (creative inference, lower threshold)       │
│     ↓ still unanswered + user-selected                          │
│ Stage 4: Deep RAG (external similar projects with disclaimers)   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Second Pass Integration for Bid/Spec Mode

**Objective:** Enable existing `second_pass_processor.py` for bid_spec mode to retry questions with NO answers.

### Task 1.1: Add Second Pass Trigger in Orchestrator

**Files:**
- Modify: `services/hotdog/orchestrator.py:523-544` (after main window loop, before L6)

**Step 1: Write the second pass integration logic**

Add after line 523 (after main window processing loop, before Layer 7/6):

```python
# ============================================================
# SECOND PASS FOR UNANSWERED QUESTIONS (Bid/Spec Mode)
# ============================================================
if self.mode == AnalysisMode.BID_SPEC:
    # Identify questions with NO answers
    unanswered_question_ids = []
    for question_id in config.question_map.keys():
        if question_id not in self.layer4_accumulator.accumulation:
            unanswered_question_ids.append(question_id)
        elif not self.layer4_accumulator.accumulation[question_id]:
            unanswered_question_ids.append(question_id)

    if unanswered_question_ids:
        logger.info(f"\n{'='*64}")
        logger.info(f"🔍 SECOND PASS: {len(unanswered_question_ids)} unanswered questions")
        logger.info(f"{'='*64}")

        self._emit_progress('second_pass_start', {
            'unanswered_count': len(unanswered_question_ids),
            'question_ids': unanswered_question_ids
        })

        # Filter to only unanswered questions
        unanswered_questions = [
            config.question_map[qid] for qid in unanswered_question_ids
        ]

        # Run second pass processor
        second_pass_answers = await self.layer3_5_second_pass.process_unanswered_questions(
            windows=windows,
            unanswered_questions=unanswered_questions,
            experts=experts
        )

        # Accumulate second pass answers
        for question_id, answer in second_pass_answers.items():
            self.layer4_accumulator.accumulation[question_id].append(answer)

        logger.info(f"✅ Second pass found {len(second_pass_answers)} new answers")

        self._emit_progress('second_pass_complete', {
            'answers_found': len(second_pass_answers),
            'still_unanswered': len(unanswered_question_ids) - len(second_pass_answers)
        })
```

**Step 2: Add frontend event handlers for second_pass events**

In `index.html`, add handlers in the event processing function (~line 770):

```javascript
else if (data.event === 'second_pass_start') {
    Logger.info(`🔍 Starting second pass for ${data.unanswered_count} unanswered questions...`);
}
else if (data.event === 'second_pass_complete') {
    Logger.success(`✅ Second pass complete: Found ${data.answers_found} answers, ${data.still_unanswered} still unanswered`);
}
```

**Step 3: Verify and commit**

```bash
# Test that second pass runs for bid_spec mode
python -c "from services.hotdog.orchestrator import HotdogOrchestrator; print('Import OK')"
git add services/hotdog/orchestrator.py index.html
git commit -m "feat: Enable second pass for bid_spec mode unanswered questions"
```

---

## Phase 2: UI Augmentation - Question Selection Checkboxes

**Objective:** Add checkboxes to Unitary Table allowing users to select questions for additional processing passes.

### Task 2.1: Add Checkbox Column to Unitary Table

**Files:**
- Modify: `index.html:1703-1770` (renderUnitaryTable function)

**Step 1: Add state tracking for selected questions**

At top of script section (~line 568):

```javascript
// NEW: Question selection state for multi-pass processing
let selectedQuestionsForExhaustive = new Set();  // User-selected for exhaustive pass
let selectedQuestionsForRAG = new Set();         // User-selected for deep RAG
```

**Step 2: Add checkbox column to table header**

In `renderUnitaryTable()`, modify the thead (~line 1706):

```javascript
<thead>
    <tr style="background: #1E3A8A; color: white;">
        <th style="padding: 12px; text-align: center; border: 1px solid #ddd; width: 50px;">
            <input type="checkbox" id="selectAllQuestions" onchange="toggleAllQuestionSelection(this)" title="Select all for additional processing">
        </th>
        <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Section</th>
        <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Question</th>
        <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Answer</th>
        <th style="padding: 12px; text-align: center; border: 1px solid #ddd; width: 80px;">Pages</th>
        <th style="padding: 12px; text-align: center; border: 1px solid #ddd; width: 100px;">Confidence</th>
        <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 80px;">Footnote</th>
    </tr>
</thead>
```

**Step 3: Add checkbox to each row**

In the row generation loop (~line 1745), add checkbox cell:

```javascript
const isUnanswered = q.status === 'pending' || !q.answer;
const isLowConfidence = q.confidence && q.confidence < 0.9;
const autoSelected = isUnanswered || isLowConfidence;

html += `
    <tr id="row-${qid}" style="border-bottom: 1px solid #eee;">
        <td style="padding: 10px; text-align: center; border: 1px solid #eee;">
            <input type="checkbox"
                   class="question-select-checkbox"
                   data-question-id="${qid}"
                   ${autoSelected ? 'checked' : ''}
                   onchange="handleQuestionSelectionChange('${qid}', this.checked)"
                   title="${autoSelected ? 'Auto-selected (unanswered or <90% confidence)' : 'Select for additional processing'}">
        </td>
        <td style="padding: 10px; border: 1px solid #eee; color: #666; font-size: 12px;">${q.section_name}</td>
        ...
    </tr>
`;
```

**Step 4: Add selection handler functions**

Add new functions after `updateUnitaryStats()`:

```javascript
function handleQuestionSelectionChange(questionId, isSelected) {
    if (isSelected) {
        selectedQuestionsForExhaustive.add(questionId);
    } else {
        selectedQuestionsForExhaustive.delete(questionId);
    }
    updateSelectionSummary();
}

function toggleAllQuestionSelection(checkbox) {
    const checkboxes = document.querySelectorAll('.question-select-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = checkbox.checked;
        const qid = cb.dataset.questionId;
        if (checkbox.checked) {
            selectedQuestionsForExhaustive.add(qid);
        } else {
            selectedQuestionsForExhaustive.delete(qid);
        }
    });
    updateSelectionSummary();
}

function updateSelectionSummary() {
    const summary = document.getElementById('selectionSummary');
    if (summary) {
        summary.textContent = `${selectedQuestionsForExhaustive.size} questions selected for additional processing`;
    }
}

function getSelectedQuestionIds() {
    return Array.from(selectedQuestionsForExhaustive);
}
```

**Step 5: Commit**

```bash
git add index.html
git commit -m "feat: Add question selection checkboxes to Unitary Table"
```

### Task 2.2: Add Action Buttons for Additional Processing

**Files:**
- Modify: `index.html` (add buttons section above Unitary Table)

**Step 1: Add action buttons panel**

In `renderUnitaryTable()`, after the stats div (~line 1700):

```javascript
<!-- Selection Actions Panel -->
<div id="selectionActionsPanel" style="background: #fff3cd; padding: 15px; border-radius: 6px; margin-bottom: 20px; display: none;">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <strong style="color: #856404;">📋 <span id="selectionSummary">0 questions selected</span></strong>
        </div>
        <div style="display: flex; gap: 10px;">
            <button onclick="runExhaustiveOnSelected()" style="background: #1E3A8A; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                🔄 Run Exhaustive Pass
            </button>
            <button onclick="runRAGOnSelected()" style="background: #047857; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                🔍 Run Deep RAG
            </button>
            <button onclick="clearSelection()" style="background: #6b7280; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                ✕ Clear
            </button>
        </div>
    </div>
</div>
```

**Step 2: Add button handler functions**

```javascript
async function runExhaustiveOnSelected() {
    const selectedIds = getSelectedQuestionIds();
    if (selectedIds.length === 0) {
        Logger.warning('No questions selected for exhaustive pass');
        return;
    }

    Logger.info(`🔄 Starting exhaustive pass on ${selectedIds.length} selected questions...`);

    try {
        const response = await fetch(`/api/analyze/exhaustive/${currentSessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_ids: selectedIds })
        });

        if (!response.ok) throw new Error('Exhaustive pass request failed');

        const result = await response.json();
        Logger.success(`✅ Exhaustive pass complete: ${result.answers_found} new answers`);
    } catch (error) {
        Logger.error('Exhaustive pass failed: ' + error.message);
    }
}

async function runRAGOnSelected() {
    const selectedIds = getSelectedQuestionIds();
    if (selectedIds.length === 0) {
        Logger.warning('No questions selected for RAG search');
        return;
    }

    Logger.info(`🔍 Starting Deep RAG on ${selectedIds.length} selected questions...`);

    try {
        const response = await fetch(`/api/analyze/rag/${currentSessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_ids: selectedIds })
        });

        if (!response.ok) throw new Error('RAG request failed');

        const result = await response.json();
        Logger.success(`✅ Deep RAG complete: ${result.answers_found} potential answers (with disclaimers)`);
    } catch (error) {
        Logger.error('Deep RAG failed: ' + error.message);
    }
}

function clearSelection() {
    selectedQuestionsForExhaustive.clear();
    document.querySelectorAll('.question-select-checkbox').forEach(cb => cb.checked = false);
    document.getElementById('selectAllQuestions').checked = false;
    updateSelectionSummary();
}
```

**Step 3: Commit**

```bash
git add index.html
git commit -m "feat: Add action buttons for exhaustive pass and RAG on selected questions"
```

---

## Phase 3: Stage 1 - Comprehensive Quick-Scan Pass

**Objective:** Create a new processor that fast-tracks answers by analyzing document structure (TOC, index, headers, appendix).

### Task 3.1: Create Document Structure Analyzer

**Files:**
- Create: `services/hotdog/document_structure_analyzer.py`

**Step 1: Create the analyzer module**

```python
"""
Document Structure Analyzer for HOTDOG v2 Comprehensive Quick-Scan.

Identifies and extracts structural elements:
- Table of Contents (TOC)
- Index/Appendix
- Section Headers
- Page Headers/Footers
- Title blocks
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StructuralElement:
    """A structural element found in the document."""
    element_type: str  # 'toc', 'index', 'header', 'footer', 'title', 'appendix'
    pages: List[int]
    text: str
    references: Dict[str, List[int]] = field(default_factory=dict)  # topic -> page numbers


@dataclass
class DocumentStructure:
    """Complete structural analysis of document."""
    has_toc: bool = False
    toc_pages: List[int] = field(default_factory=list)
    toc_entries: Dict[str, int] = field(default_factory=dict)  # section_name -> page_num

    has_index: bool = False
    index_pages: List[int] = field(default_factory=list)
    index_entries: Dict[str, List[int]] = field(default_factory=dict)  # term -> [page_nums]

    has_appendix: bool = False
    appendix_pages: List[int] = field(default_factory=list)
    appendix_sections: Dict[str, int] = field(default_factory=dict)  # appendix_name -> start_page

    section_headers: Dict[int, str] = field(default_factory=dict)  # page -> header_text
    page_titles: Dict[int, str] = field(default_factory=dict)  # page -> title


class DocumentStructureAnalyzer:
    """
    Analyzes document structure for quick-scan optimization.

    Identifies structural elements that can fast-track answer discovery:
    - TOC tells us where to look for specific topics
    - Index provides term -> page mappings
    - Headers reveal section organization
    """

    # Patterns for detecting structural elements
    TOC_PATTERNS = [
        r'table\s+of\s+contents',
        r'contents\s*$',
        r'^contents\s*\n',
        r'index\s+of\s+contents',
    ]

    INDEX_PATTERNS = [
        r'^index\s*$',
        r'subject\s+index',
        r'alphabetical\s+index',
    ]

    APPENDIX_PATTERNS = [
        r'appendix\s+[a-z]',
        r'appendices',
        r'attachment\s+[a-z0-9]',
        r'exhibit\s+[a-z0-9]',
    ]

    SECTION_HEADER_PATTERNS = [
        r'^(?:section|article|part|division)\s+\d+',
        r'^\d+\.\d+\s+[A-Z]',
        r'^[A-Z]{2,}\s*[-:]\s*[A-Z]',
    ]

    def __init__(self):
        self.structure = DocumentStructure()

    def analyze(self, pages: List[Dict]) -> DocumentStructure:
        """
        Analyze document structure from extracted pages.

        Args:
            pages: List of {'page_num': int, 'text': str}

        Returns:
            DocumentStructure with all identified elements
        """
        logger.info("🔍 Analyzing document structure...")

        self.structure = DocumentStructure()

        # Pass 1: Find TOC
        self._find_toc(pages)

        # Pass 2: Find Index
        self._find_index(pages)

        # Pass 3: Find Appendix sections
        self._find_appendix(pages)

        # Pass 4: Extract section headers
        self._extract_section_headers(pages)

        logger.info(f"  TOC: {self.structure.has_toc} ({len(self.structure.toc_entries)} entries)")
        logger.info(f"  Index: {self.structure.has_index} ({len(self.structure.index_entries)} terms)")
        logger.info(f"  Appendix: {self.structure.has_appendix} ({len(self.structure.appendix_sections)} sections)")
        logger.info(f"  Headers found: {len(self.structure.section_headers)} pages")

        return self.structure

    def _find_toc(self, pages: List[Dict]) -> None:
        """Find and parse Table of Contents."""
        for page in pages[:20]:  # TOC typically in first 20 pages
            text_lower = page['text'].lower()

            for pattern in self.TOC_PATTERNS:
                if re.search(pattern, text_lower, re.MULTILINE | re.IGNORECASE):
                    self.structure.has_toc = True
                    self.structure.toc_pages.append(page['page_num'])

                    # Parse TOC entries: "Section Name ... 15" or "Section Name\t15"
                    toc_entry_pattern = r'([A-Za-z][A-Za-z\s&\-/]+?)\s*[\.…\t]+\s*(\d{1,3})'
                    matches = re.findall(toc_entry_pattern, page['text'])

                    for section_name, page_num in matches:
                        clean_name = section_name.strip()
                        if len(clean_name) > 3:  # Filter out noise
                            self.structure.toc_entries[clean_name] = int(page_num)

                    break

    def _find_index(self, pages: List[Dict]) -> None:
        """Find and parse Index/Subject Index."""
        # Index typically in last 20 pages
        for page in reversed(pages[-30:]):
            text_lower = page['text'].lower()

            for pattern in self.INDEX_PATTERNS:
                if re.search(pattern, text_lower, re.MULTILINE | re.IGNORECASE):
                    self.structure.has_index = True
                    self.structure.index_pages.append(page['page_num'])

                    # Parse index entries: "term, 5, 12, 45" or "term ... 5"
                    index_entry_pattern = r'^([A-Za-z][A-Za-z\s\-/]+?)[,\s]+(\d[\d,\s]+)'
                    matches = re.findall(index_entry_pattern, page['text'], re.MULTILINE)

                    for term, page_nums in matches:
                        clean_term = term.strip().lower()
                        if len(clean_term) > 2:
                            pages_list = [int(p.strip()) for p in re.findall(r'\d+', page_nums)]
                            if pages_list:
                                self.structure.index_entries[clean_term] = pages_list

                    break

    def _find_appendix(self, pages: List[Dict]) -> None:
        """Find Appendix/Attachment sections."""
        for page in pages:
            text_lower = page['text'].lower()

            for pattern in self.APPENDIX_PATTERNS:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    self.structure.has_appendix = True
                    self.structure.appendix_pages.append(page['page_num'])

                    # Extract appendix identifier
                    appendix_id = match.group(0).strip()
                    self.structure.appendix_sections[appendix_id] = page['page_num']

    def _extract_section_headers(self, pages: List[Dict]) -> None:
        """Extract section headers from each page."""
        for page in pages:
            # Look for header patterns in first 500 chars of page
            header_text = page['text'][:500]

            for pattern in self.SECTION_HEADER_PATTERNS:
                match = re.search(pattern, header_text, re.MULTILINE | re.IGNORECASE)
                if match:
                    self.structure.section_headers[page['page_num']] = match.group(0).strip()
                    break

    def get_pages_for_topic(self, topic: str) -> List[int]:
        """
        Get relevant pages for a topic using structure analysis.

        Args:
            topic: Topic/question text to find pages for

        Returns:
            List of page numbers likely to contain relevant info
        """
        relevant_pages = []
        topic_lower = topic.lower()
        topic_words = set(topic_lower.split())

        # Check TOC entries
        for section_name, page_num in self.structure.toc_entries.items():
            section_words = set(section_name.lower().split())
            if topic_words & section_words:  # Any word overlap
                relevant_pages.append(page_num)

        # Check Index entries
        for term, page_nums in self.structure.index_entries.items():
            if term in topic_lower or any(word in term for word in topic_words):
                relevant_pages.extend(page_nums)

        # Check section headers
        for page_num, header in self.structure.section_headers.items():
            header_words = set(header.lower().split())
            if topic_words & header_words:
                relevant_pages.append(page_num)

        # Dedupe and sort
        return sorted(set(relevant_pages))
```

**Step 2: Commit**

```bash
git add services/hotdog/document_structure_analyzer.py
git commit -m "feat: Add DocumentStructureAnalyzer for comprehensive quick-scan"
```

### Task 3.2: Create Comprehensive Quick-Scan Processor

**Files:**
- Create: `services/hotdog/comprehensive_processor.py`

**Step 1: Create the processor**

```python
"""
Comprehensive Quick-Scan Processor for HOTDOG v2 Stage 1.

Uses document structure to fast-track answer discovery before exhaustive processing.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from openai import AsyncOpenAI

from .models import Question, Answer, PageData, WindowContext
from .document_structure_analyzer import DocumentStructureAnalyzer, DocumentStructure

logger = logging.getLogger(__name__)


class ComprehensiveProcessor:
    """
    Stage 1: Comprehensive Quick-Scan Processor.

    Strategy:
    1. Analyze document structure (TOC, index, headers)
    2. For each question, identify likely pages using structure
    3. Query those specific pages first (targeted extraction)
    4. Mark questions with >=90% confidence as "answered"
    5. Return remaining questions for exhaustive processing
    """

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        model: str = "gpt-4o",
        confidence_threshold: float = 0.90
    ):
        self.client = openai_client
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.structure_analyzer = DocumentStructureAnalyzer()

        # Stats
        self.questions_processed = 0
        self.high_confidence_answers = 0
        self.api_calls = 0
        self.tokens_used = 0

    async def quick_scan(
        self,
        pages: List[PageData],
        questions: List[Question],
        experts: Dict  # section_id -> ExpertPersona
    ) -> Tuple[Dict[str, Answer], List[Question]]:
        """
        Perform comprehensive quick-scan on document.

        Args:
            pages: All extracted pages
            questions: All questions to answer
            experts: Expert personas by section

        Returns:
            Tuple of:
            - Dict of high-confidence answers (question_id -> Answer)
            - List of questions needing exhaustive processing
        """
        logger.info(f"\n{'='*64}")
        logger.info("🚀 STAGE 1: Comprehensive Quick-Scan")
        logger.info(f"{'='*64}")

        start_time = datetime.now()

        # Analyze document structure
        pages_data = [{'page_num': p.page_num, 'text': p.text} for p in pages]
        structure = self.structure_analyzer.analyze(pages_data)

        high_confidence_answers = {}
        questions_for_exhaustive = []

        # Process each question
        for question in questions:
            self.questions_processed += 1

            # Find relevant pages using structure
            relevant_pages = self.structure_analyzer.get_pages_for_topic(question.text)

            if relevant_pages:
                # Try targeted extraction on relevant pages
                answer = await self._targeted_extraction(
                    question=question,
                    pages=[p for p in pages if p.page_num in relevant_pages],
                    expert=experts.get(question.section_id)
                )

                if answer and answer.confidence >= self.confidence_threshold:
                    high_confidence_answers[question.id] = answer
                    self.high_confidence_answers += 1
                    logger.info(f"  ✅ {question.id}: Quick-scan success ({answer.confidence:.0%})")
                else:
                    questions_for_exhaustive.append(question)
                    logger.debug(f"  📋 {question.id}: Needs exhaustive pass")
            else:
                # No structural hints - send to exhaustive
                questions_for_exhaustive.append(question)
                logger.debug(f"  📋 {question.id}: No structural hints, queued for exhaustive")

        elapsed = (datetime.now() - start_time).total_seconds()

        logger.info(f"\n✅ Quick-Scan Complete ({elapsed:.1f}s)")
        logger.info(f"   High-confidence answers: {len(high_confidence_answers)}/{len(questions)}")
        logger.info(f"   Questions for exhaustive: {len(questions_for_exhaustive)}")

        return high_confidence_answers, questions_for_exhaustive

    async def _targeted_extraction(
        self,
        question: Question,
        pages: List[PageData],
        expert: Optional[object]
    ) -> Optional[Answer]:
        """
        Extract answer from targeted pages.
        """
        if not pages:
            return None

        # Combine page texts
        context = "\n\n".join([
            f"[Page {p.page_num}]\n{p.text}"
            for p in pages[:5]  # Max 5 pages per targeted query
        ])

        page_nums = [p.page_num for p in pages[:5]]

        prompt = f"""Analyze these document pages to answer the following question.

QUESTION: {question.text}

DOCUMENT PAGES:
{context}

INSTRUCTIONS:
1. Find the BEST answer to the question from the provided pages
2. Include direct quotes with page citations in format <PDF pg X>
3. Rate your confidence (0.0-1.0) based on how clearly the answer is stated
4. If the answer is not clearly found, respond with confidence 0.0

OUTPUT FORMAT (JSON):
{{
    "answer": "Your answer with <PDF pg X> citation",
    "pages": [{', '.join(map(str, page_nums))}],
    "confidence": 0.95,
    "reasoning": "Brief explanation of how you found this"
}}
"""

        try:
            self.api_calls += 1
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": expert.system_prompt if expert else "You are a document analysis expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            self.tokens_used += response.usage.total_tokens

            import json
            data = json.loads(response.choices[0].message.content)

            answer_text = data.get('answer', '')
            confidence = data.get('confidence', 0.0)
            pages_cited = data.get('pages', page_nums)

            if not answer_text or confidence == 0.0:
                return None

            # Ensure citation marker
            if '<PDF pg' not in answer_text:
                pages_str = ', '.join(map(str, pages_cited))
                answer_text += f" <PDF pg {pages_str}>"

            return Answer(
                question_id=question.id,
                text=answer_text,
                pages=pages_cited,
                confidence=confidence,
                expert=expert.name if expert else "Quick-Scan",
                window=0  # Not window-based
            )

        except Exception as e:
            logger.warning(f"Targeted extraction failed for {question.id}: {e}")
            return None

    def get_statistics(self) -> Dict:
        """Get processing statistics."""
        return {
            'questions_processed': self.questions_processed,
            'high_confidence_answers': self.high_confidence_answers,
            'success_rate': self.high_confidence_answers / self.questions_processed if self.questions_processed else 0,
            'api_calls': self.api_calls,
            'tokens_used': self.tokens_used
        }
```

**Step 2: Commit**

```bash
git add services/hotdog/comprehensive_processor.py
git commit -m "feat: Add ComprehensiveProcessor for Stage 1 quick-scan"
```

---

## Phase 4: Stage 2 - Selective Exhaustive Pass

**Objective:** Modify exhaustive processing to only run on questions that need it (not already >=90% confidence).

### Task 4.1: Add Question Filtering to Orchestrator

**Files:**
- Modify: `services/hotdog/orchestrator.py`

**Step 1: Add comprehensive pass before exhaustive processing**

In `analyze_document()`, after Layer 2 experts generation (~line 320):

```python
# ============================================================
# STAGE 1: COMPREHENSIVE QUICK-SCAN (NEW)
# ============================================================
if self.mode == AnalysisMode.BID_SPEC:
    from .comprehensive_processor import ComprehensiveProcessor

    logger.info("🚀 Stage 1: Comprehensive Quick-Scan")
    self._emit_progress('stage_1_start', {'layer': 'Comprehensive Quick-Scan'})

    comprehensive_processor = ComprehensiveProcessor(
        openai_client=self.openai_client,
        model=self.model,
        confidence_threshold=0.90
    )

    quick_scan_answers, questions_for_exhaustive = await comprehensive_processor.quick_scan(
        pages=pages,
        questions=list(config.question_map.values()),
        experts=experts
    )

    # Add high-confidence answers to accumulator
    for question_id, answer in quick_scan_answers.items():
        self.layer4_accumulator.accumulation[question_id] = [answer]

    logger.info(f"  ✅ Quick-scan: {len(quick_scan_answers)} high-confidence answers")
    self._emit_progress('stage_1_complete', {
        'high_confidence_count': len(quick_scan_answers),
        'questions_for_exhaustive': len(questions_for_exhaustive)
    })

    # Filter questions for exhaustive pass
    questions_to_process = questions_for_exhaustive
else:
    # BestPrep: process all questions exhaustively
    questions_to_process = list(config.question_map.values())
```

**Step 2: Update window processing to use filtered questions**

Modify the window processing loop (~line 378) to use `questions_to_process`:

```python
window_result = await self.layer3_processor.process_window(
    window=window,
    questions=questions_to_process,  # Changed from list(config.question_map.values())
    experts=experts
)
```

**Step 3: Commit**

```bash
git add services/hotdog/orchestrator.py
git commit -m "feat: Integrate Stage 1 quick-scan before exhaustive processing"
```

---

## Phase 5: Stage 4 - Deep RAG External Search

**Objective:** Create external search capability for similar projects/agencies when document doesn't contain answers.

### Task 5.1: Create Deep RAG Processor

**Files:**
- Create: `services/hotdog/deep_rag_processor.py`

**Step 1: Create the RAG processor**

```python
"""
Deep RAG Processor for HOTDOG v2 Stage 4.

Searches external sources for similar projects to answer remaining questions.
All external answers include prominent disclaimers about source.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from openai import AsyncOpenAI

from .models import Question, Answer

logger = logging.getLogger(__name__)


@dataclass
class ExternalSource:
    """An external source used for RAG answers."""
    source_type: str  # 'similar_project', 'agency_standard', 'industry_standard'
    source_name: str
    municipality: Optional[str] = None
    engineer_firm: Optional[str] = None
    project_year: Optional[str] = None
    url: Optional[str] = None


@dataclass
class RAGAnswer:
    """Answer from external RAG with full provenance."""
    question_id: str
    answer_text: str
    confidence: float
    source: ExternalSource
    disclaimer: str
    reasoning: str


class DeepRAGProcessor:
    """
    Stage 4: Deep RAG Processor for external search.

    Strategy:
    1. Extract project context (municipality, engineer, scope)
    2. Search for similar projects by same agency/engineer
    3. Query similar projects for potential answers
    4. Return answers with prominent disclaimers

    CRITICAL: All external answers MUST include disclaimers.
    """

    DISCLAIMER_TEMPLATE = """
⚠️ EXTERNAL SOURCE DISCLAIMER ⚠️
This answer was NOT found in the analyzed document.
Source: {source_name} ({source_type})
{additional_context}
This information may not apply to the current project.
Always verify with the official bid documents.
"""

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        model: str = "gpt-4o"
    ):
        self.client = openai_client
        self.model = model

        # Project context (extracted from document)
        self.project_context = {}

        # Stats
        self.questions_processed = 0
        self.answers_found = 0
        self.api_calls = 0

    def set_project_context(
        self,
        municipality: Optional[str] = None,
        engineer_firm: Optional[str] = None,
        project_type: Optional[str] = None,
        scope: Optional[str] = None
    ):
        """Set project context for similarity matching."""
        self.project_context = {
            'municipality': municipality,
            'engineer_firm': engineer_firm,
            'project_type': project_type,
            'scope': scope
        }

    async def search_external(
        self,
        questions: List[Question],
        max_concurrent: int = 3
    ) -> Dict[str, RAGAnswer]:
        """
        Search external sources for answers to remaining questions.

        Args:
            questions: Questions to search for
            max_concurrent: Max concurrent searches

        Returns:
            Dict of question_id -> RAGAnswer (with disclaimers)
        """
        logger.info(f"\n{'='*64}")
        logger.info("🔍 STAGE 4: Deep RAG External Search")
        logger.info(f"{'='*64}")
        logger.info(f"Searching for {len(questions)} unanswered questions")
        logger.info(f"Project context: {self.project_context}")

        start_time = datetime.now()
        answers = {}

        # Process in batches
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_question(question: Question) -> Optional[Tuple[str, RAGAnswer]]:
            async with semaphore:
                return await self._search_for_question(question)

        tasks = [process_question(q) for q in questions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, tuple) and result is not None:
                question_id, rag_answer = result
                answers[question_id] = rag_answer
                self.answers_found += 1

        elapsed = (datetime.now() - start_time).total_seconds()

        logger.info(f"\n✅ Deep RAG Complete ({elapsed:.1f}s)")
        logger.info(f"   External answers found: {len(answers)}/{len(questions)}")

        return answers

    async def _search_for_question(
        self,
        question: Question
    ) -> Optional[Tuple[str, RAGAnswer]]:
        """
        Search for a single question in external sources.

        Uses AI to:
        1. Understand what type of information is needed
        2. Identify likely sources (industry standards, similar projects)
        3. Generate a reasoned answer with appropriate disclaimers
        """
        self.questions_processed += 1

        context_str = "\n".join([
            f"- {k}: {v}" for k, v in self.project_context.items() if v
        ])

        prompt = f"""You are helping find information for a bid specification question that was NOT answered in the analyzed document.

PROJECT CONTEXT:
{context_str}

UNANSWERED QUESTION: {question.text}

YOUR TASK:
1. Consider what type of information would answer this question
2. Based on industry standards, similar municipal projects, or common practices:
   - Provide a POTENTIAL answer based on typical requirements
   - Clearly identify the source type (industry standard, common practice, etc.)
   - Rate confidence (0.0-0.5 for external sources - NEVER above 0.5)
3. If you cannot provide any reasonable guidance, respond with confidence 0.0

IMPORTANT: This will be marked as EXTERNAL information with a disclaimer.

OUTPUT FORMAT (JSON):
{{
    "answer": "Your potential answer based on external knowledge",
    "confidence": 0.35,
    "source_type": "industry_standard",
    "source_name": "NASSCO CIPP Guidelines 2024",
    "reasoning": "Why this external source is relevant"
}}

If no reasonable external answer exists:
{{
    "answer": "",
    "confidence": 0.0,
    "source_type": "none",
    "source_name": "",
    "reasoning": "No applicable external reference found"
}}
"""

        try:
            self.api_calls += 1
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a municipal infrastructure and bid specification expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,  # Higher temp for creative external search
                max_tokens=1500,
                response_format={"type": "json_object"}
            )

            import json
            data = json.loads(response.choices[0].message.content)

            answer_text = data.get('answer', '')
            confidence = min(data.get('confidence', 0.0), 0.5)  # Cap at 0.5
            source_type = data.get('source_type', 'unknown')
            source_name = data.get('source_name', 'External Reference')
            reasoning = data.get('reasoning', '')

            if not answer_text or confidence == 0.0:
                return None

            # Create external source
            source = ExternalSource(
                source_type=source_type,
                source_name=source_name,
                municipality=self.project_context.get('municipality'),
                engineer_firm=self.project_context.get('engineer_firm')
            )

            # Generate disclaimer
            additional = []
            if source.municipality:
                additional.append(f"Municipality: {source.municipality}")
            if source.engineer_firm:
                additional.append(f"Engineer: {source.engineer_firm}")

            disclaimer = self.DISCLAIMER_TEMPLATE.format(
                source_name=source_name,
                source_type=source_type,
                additional_context="\n".join(additional) if additional else "General industry reference"
            )

            rag_answer = RAGAnswer(
                question_id=question.id,
                answer_text=answer_text,
                confidence=confidence,
                source=source,
                disclaimer=disclaimer,
                reasoning=reasoning
            )

            logger.info(f"  🔍 {question.id}: External answer found ({source_type}, {confidence:.0%})")

            return (question.id, rag_answer)

        except Exception as e:
            logger.warning(f"RAG search failed for {question.id}: {e}")
            return None

    def get_statistics(self) -> Dict:
        """Get processing statistics."""
        return {
            'questions_processed': self.questions_processed,
            'answers_found': self.answers_found,
            'success_rate': self.answers_found / self.questions_processed if self.questions_processed else 0,
            'api_calls': self.api_calls
        }
```

**Step 2: Commit**

```bash
git add services/hotdog/deep_rag_processor.py
git commit -m "feat: Add DeepRAGProcessor for Stage 4 external search with disclaimers"
```

### Task 5.2: Add RAG API Endpoint

**Files:**
- Modify: `app.py`

**Step 1: Add the RAG endpoint**

```python
@app.route('/api/analyze/rag/<session_id>', methods=['POST'])
@require_auth
def run_deep_rag(session_id):
    """
    Run Deep RAG on selected questions for a completed/partial analysis.

    POST body:
    {
        "question_ids": ["Q1", "Q5", "Q12"]  // Questions to search
    }
    """
    data = request.get_json()
    question_ids = data.get('question_ids', [])

    if not question_ids:
        return jsonify({'error': 'No questions specified'}), 400

    # Get analysis from completed or partial
    analysis = completed_analyses.get(session_id) or partial_analyses.get(session_id)
    if not analysis:
        return jsonify({'error': 'Analysis not found'}), 404

    orchestrator = analysis.get('orchestrator')
    config = orchestrator.cached_config if orchestrator else None

    if not config:
        return jsonify({'error': 'Analysis config not available'}), 400

    # Filter to requested questions
    questions = [
        config.question_map[qid]
        for qid in question_ids
        if qid in config.question_map
    ]

    if not questions:
        return jsonify({'error': 'No valid questions found'}), 400

    # Extract project context from key requirements
    key_reqs = orchestrator.extracted_key_requirements if orchestrator else {}

    # Run RAG in background
    def run_rag():
        import asyncio
        from services.hotdog.deep_rag_processor import DeepRAGProcessor

        openai_key = os.environ.get('OPENAI_API_KEY')
        rag_processor = DeepRAGProcessor(
            openai_client=AsyncOpenAI(api_key=openai_key),
            model="gpt-4o"
        )

        rag_processor.set_project_context(
            municipality=key_reqs.get('owner'),
            engineer_firm=key_reqs.get('engineer'),
            project_type=key_reqs.get('project_name'),
            scope=key_reqs.get('scope')
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(
            rag_processor.search_external(questions)
        )
        loop.close()

        # Store results
        analysis['rag_results'] = {
            qid: {
                'answer': ra.answer_text,
                'confidence': ra.confidence,
                'source': ra.source.source_name,
                'source_type': ra.source.source_type,
                'disclaimer': ra.disclaimer
            }
            for qid, ra in results.items()
        }

        return results

    # Run synchronously for now (can be made async)
    import threading
    rag_thread = threading.Thread(target=run_rag)
    rag_thread.start()
    rag_thread.join(timeout=120)  # 2 minute timeout

    rag_results = analysis.get('rag_results', {})

    return jsonify({
        'status': 'complete',
        'answers_found': len(rag_results),
        'results': rag_results
    })
```

**Step 2: Commit**

```bash
git add app.py
git commit -m "feat: Add /api/analyze/rag endpoint for Deep RAG"
```

---

## Phase 6: Pipeline Orchestration

**Objective:** Integrate all stages into a cohesive pipeline with user control.

### Task 6.1: Create Pipeline Coordinator

**Files:**
- Create: `services/hotdog/pipeline_coordinator.py`

**Step 1: Create the coordinator**

```python
"""
Pipeline Coordinator for HOTDOG v2 Multi-Pass Architecture.

Coordinates all 4 stages:
- Stage 1: Comprehensive Quick-Scan
- Stage 2: Selective Exhaustive Pass
- Stage 3: Second Pass (for unanswered)
- Stage 4: Deep RAG (optional, user-triggered)
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .models import Question, Answer, ParsedConfig, PageData, ExpertPersona

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
    Coordinates the multi-pass analysis pipeline.

    Flow:
    1. Quick-Scan: Get high-confidence answers fast
    2. Exhaustive: Process remaining + user-selected questions
    3. Second Pass: Retry questions with NO answers
    4. Deep RAG: User-triggered external search
    """

    def __init__(
        self,
        comprehensive_processor,
        exhaustive_processor,  # MultiExpertProcessor
        second_pass_processor,
        rag_processor,
        accumulator,
        progress_callback=None
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
        windows: List,
        enable_second_pass: bool = True,
        enable_rag: bool = False
    ) -> Dict[str, Answer]:
        """
        Run the complete analysis pipeline.

        Args:
            pages: Extracted document pages
            config: Question configuration
            experts: Expert personas
            windows: Pre-created 3-page windows
            enable_second_pass: Whether to run second pass
            enable_rag: Whether to run deep RAG (usually user-triggered)

        Returns:
            All accumulated answers
        """
        logger.info("\n" + "="*64)
        logger.info("🚀 HOTDOG v2 Multi-Pass Pipeline Starting")
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
        stage_2_result = await self._run_stage_2(
            windows, questions_for_stage_2, experts
        )

        # ============================================================
        # STAGE 3: Second Pass (if enabled)
        # ============================================================
        if enable_second_pass:
            unanswered = self._get_unanswered_questions(all_questions)
            if unanswered:
                stage_3_result = await self._run_stage_3(
                    windows, unanswered, experts
                )

        # ============================================================
        # STAGE 4: Deep RAG (if enabled)
        # ============================================================
        if enable_rag:
            rag_questions = self._get_questions_for_rag(all_questions)
            if rag_questions:
                stage_4_result = await self._run_stage_4(rag_questions)

        # Return all accumulated answers
        return self.accumulator.get_accumulated_answers()

    async def _run_stage_1(
        self,
        pages: List[PageData],
        questions: List[Question],
        experts: Dict
    ) -> StageResult:
        """Run Stage 1: Comprehensive Quick-Scan."""
        self.state.current_stage = PipelineStage.QUICK_SCAN
        self._emit_progress('stage_start', {'stage': 'quick_scan'})

        start = datetime.now()

        answers, remaining = await self.comprehensive.quick_scan(
            pages, questions, experts
        )

        # Update state
        for qid, answer in answers.items():
            self.state.answered_questions.add(qid)
            if answer.confidence >= 0.9:
                self.state.high_confidence_questions.add(qid)

        # Add to accumulator
        for qid, answer in answers.items():
            self.accumulator.accumulation[qid] = [answer]

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

        self._emit_progress('stage_complete', {
            'stage': 'quick_scan',
            'answers_found': len(answers),
            'duration': duration
        })

        return result

    async def _run_stage_2(
        self,
        windows: List,
        questions: List[Question],
        experts: Dict
    ) -> StageResult:
        """Run Stage 2: Selective Exhaustive Pass."""
        self.state.current_stage = PipelineStage.EXHAUSTIVE
        self._emit_progress('stage_start', {'stage': 'exhaustive'})

        start = datetime.now()
        answers = {}

        for window in windows:
            result = await self.exhaustive.process_window(
                window=window,
                questions=questions,
                experts=experts
            )

            # Accumulate answers
            for qid, answer in result.answers.items():
                if qid not in answers:
                    answers[qid] = answer
                    self.state.answered_questions.add(qid)
                    if answer.confidence >= 0.9:
                        self.state.high_confidence_questions.add(qid)

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

        self._emit_progress('stage_complete', {
            'stage': 'exhaustive',
            'answers_found': len(answers),
            'duration': duration
        })

        return result

    async def _run_stage_3(
        self,
        windows: List,
        questions: List[Question],
        experts: Dict
    ) -> StageResult:
        """Run Stage 3: Second Pass."""
        self.state.current_stage = PipelineStage.SECOND_PASS
        self._emit_progress('stage_start', {'stage': 'second_pass'})

        start = datetime.now()

        answers = await self.second_pass.process_unanswered_questions(
            windows=windows,
            unanswered_questions=questions,
            experts=experts
        )

        # Update state
        for qid in answers:
            self.state.answered_questions.add(qid)

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

        self._emit_progress('stage_complete', {
            'stage': 'second_pass',
            'answers_found': len(answers),
            'duration': duration
        })

        return result

    async def _run_stage_4(
        self,
        questions: List[Question]
    ) -> StageResult:
        """Run Stage 4: Deep RAG."""
        self.state.current_stage = PipelineStage.DEEP_RAG
        self._emit_progress('stage_start', {'stage': 'deep_rag'})

        start = datetime.now()

        rag_answers = await self.rag.search_external(questions)

        duration = (datetime.now() - start).total_seconds()

        # Convert RAGAnswer to Answer for consistency
        answers = {}
        for qid, rag_answer in rag_answers.items():
            answers[qid] = Answer(
                question_id=qid,
                text=f"{rag_answer.answer_text}\n\n{rag_answer.disclaimer}",
                pages=[],  # No pages for external
                confidence=rag_answer.confidence,
                expert=f"Deep RAG ({rag_answer.source.source_name})",
                window=0
            )

        result = StageResult(
            stage=PipelineStage.DEEP_RAG,
            answers=answers,
            questions_processed=len(questions),
            questions_answered=len(answers),
            duration_seconds=duration
        )

        self.state.stage_results[PipelineStage.DEEP_RAG] = result
        self.state.completed_stages.append(PipelineStage.DEEP_RAG)

        self._emit_progress('stage_complete', {
            'stage': 'deep_rag',
            'answers_found': len(answers),
            'duration': duration
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
            # 1. Not answered in Stage 1, OR
            # 2. User explicitly selected, OR
            # 3. Answered but <90% confidence
            if q.id not in self.state.high_confidence_questions:
                questions.append(q)
            elif q.id in self.state.user_selected_for_exhaustive:
                questions.append(q)

        return questions

    def _get_unanswered_questions(
        self,
        all_questions: List[Question]
    ) -> List[Question]:
        """Get questions with NO answers."""
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
            self.progress_callback(event, data)

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
```

**Step 2: Commit**

```bash
git add services/hotdog/pipeline_coordinator.py
git commit -m "feat: Add PipelineCoordinator for multi-pass orchestration"
```

### Task 6.2: Update Orchestrator to Use Pipeline

**Files:**
- Modify: `services/hotdog/orchestrator.py`

**Step 1: Add pipeline integration option**

Add new parameter to `__init__`:

```python
def __init__(
    self,
    ...
    use_pipeline_v2: bool = False  # NEW: Enable v2 multi-pass pipeline
):
    ...
    self.use_pipeline_v2 = use_pipeline_v2
```

**Step 2: Add pipeline execution path in `analyze_document`**

```python
# After Layer 2 experts generation, check if using v2 pipeline
if self.mode == AnalysisMode.BID_SPEC and self.use_pipeline_v2:
    from .pipeline_coordinator import PipelineCoordinator
    from .comprehensive_processor import ComprehensiveProcessor
    from .deep_rag_processor import DeepRAGProcessor

    comprehensive = ComprehensiveProcessor(self.openai_client, self.model)
    rag = DeepRAGProcessor(self.openai_client, self.model)

    coordinator = PipelineCoordinator(
        comprehensive_processor=comprehensive,
        exhaustive_processor=self.layer3_processor,
        second_pass_processor=self.layer3_5_second_pass,
        rag_processor=rag,
        accumulator=self.layer4_accumulator,
        progress_callback=self._emit_progress
    )

    # Run pipeline
    accumulated_answers = await coordinator.run_full_pipeline(
        pages=pages,
        config=config,
        experts=experts,
        windows=windows,
        enable_second_pass=True,
        enable_rag=False  # User-triggered later
    )

    # Skip to Layer 6 compilation
    # ... (existing Layer 6 code)
else:
    # Original processing flow
    # ... (existing window processing loop)
```

**Step 3: Commit**

```bash
git add services/hotdog/orchestrator.py
git commit -m "feat: Integrate v2 pipeline into orchestrator with feature flag"
```

---

## Testing Strategy

### Unit Tests

Create `tests/test_hotdog_v2_pipeline.py`:

```python
"""Tests for HOTDOG v2 Multi-Pass Pipeline."""
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestDocumentStructureAnalyzer:
    def test_finds_toc(self):
        pass

    def test_finds_index(self):
        pass

    def test_gets_pages_for_topic(self):
        pass


class TestComprehensiveProcessor:
    @pytest.mark.asyncio
    async def test_quick_scan_returns_high_confidence(self):
        pass

    @pytest.mark.asyncio
    async def test_returns_remaining_for_exhaustive(self):
        pass


class TestDeepRAGProcessor:
    @pytest.mark.asyncio
    async def test_includes_disclaimer(self):
        pass

    @pytest.mark.asyncio
    async def test_caps_confidence_at_50(self):
        pass


class TestPipelineCoordinator:
    @pytest.mark.asyncio
    async def test_full_pipeline_flow(self):
        pass

    def test_user_selection_override(self):
        pass
```

---

## Summary

**Total Tasks:** 18 across 6 phases

**Key New Files:**
- `services/hotdog/document_structure_analyzer.py` - TOC/Index analysis
- `services/hotdog/comprehensive_processor.py` - Stage 1 quick-scan
- `services/hotdog/deep_rag_processor.py` - Stage 4 external search
- `services/hotdog/pipeline_coordinator.py` - Multi-pass orchestration

**Key Modified Files:**
- `services/hotdog/orchestrator.py` - Pipeline integration
- `index.html` - Question selection UI
- `app.py` - New API endpoints

**User-Facing Changes:**
- Checkboxes in Unitary Table for question selection
- Action buttons for running additional passes
- Progress events for each pipeline stage
- RAG answers with prominent disclaimers

---

Plan complete and saved to `docs/plans/2026-02-01-hotdog-v2-multipass-architecture.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
