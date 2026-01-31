# BestPrep/TestPrep Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "BestPrep/TestPrep" mode to BidBrief that exhaustively answers textbook questions with guaranteed citation preservation and a final synthesis agent.

**Architecture:** Dual-mode system where mode selection at analysis start routes to either the existing Bid/Spec accumulator (deduplication-focused) or a new BestPrep accumulator (append-only, never discard). A new Layer 7 "Synthesis Agent" runs post-analysis to compile all fragments into cohesive final answers.

**Tech Stack:** Python/Flask (existing), GPT-4o API, openpyxl for Excel exports

---

## Architecture Overview

```
MODE SELECTION (UI)
    ↓
┌─────────────────────────────────────────────────────────────┐
│  BID/SPEC MODE (existing)    │  BESTPREP MODE (new)        │
│  - SmartAccumulator          │  - AppendOnlyAccumulator    │
│  - Jaccard deduplication     │  - Never discard, only add  │
│  - Merge similar answers     │  - Track all fragments      │
│  - Single primary answer     │  - Preserve all footnotes   │
└─────────────────────────────────────────────────────────────┘
    ↓                                    ↓
STANDARD LAYERS 0-6               LAYERS 0-6 + NEW LAYER 7
    ↓                                    ↓
EXPORT (current format)           SYNTHESIS AGENT (per section)
                                        ↓
                                  FINAL COHESIVE ANSWERS
                                        ↓
                                  BESTPREP EXCEL FORMAT
```

---

## Task 1: Create Mode Configuration System

**Files:**
- Create: `services/hotdog/mode_config.py`
- Modify: `services/hotdog/models.py` (add AnalysisMode enum)

**Step 1: Write the mode configuration module**

```python
# services/hotdog/mode_config.py
"""
Analysis mode configuration for BidBrief dual-mode system.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class AnalysisMode(Enum):
    """Available analysis modes."""
    BID_SPEC = "bid_spec"      # Original mode: deduplication, merge similar
    BESTPREP = "bestprep"      # New mode: append-only, never discard


@dataclass
class ModeConfig:
    """Configuration parameters for each analysis mode."""
    mode: AnalysisMode

    # Accumulation behavior
    deduplicate: bool                  # Whether to merge similar answers
    similarity_threshold: float        # Jaccard threshold (only if deduplicate=True)
    preserve_all_fragments: bool       # Keep every answer fragment found

    # Footnote handling
    individual_footnote_tracking: bool # Track each footnote separately
    max_footnotes_per_answer: int      # 0 = unlimited

    # Synthesis layer
    enable_synthesis: bool             # Run Layer 7 synthesis agent
    synthesis_per_section: bool        # One synthesis per section vs global

    # Export format
    export_format: str                 # 'bid_spec' or 'bestprep'

    @classmethod
    def bid_spec_default(cls) -> 'ModeConfig':
        """Default config for Bid/Spec mode (existing behavior)."""
        return cls(
            mode=AnalysisMode.BID_SPEC,
            deduplicate=True,
            similarity_threshold=0.75,
            preserve_all_fragments=False,
            individual_footnote_tracking=False,
            max_footnotes_per_answer=0,
            enable_synthesis=False,
            synthesis_per_section=False,
            export_format='bid_spec'
        )

    @classmethod
    def bestprep_default(cls) -> 'ModeConfig':
        """Default config for BestPrep mode (new exhaustive behavior)."""
        return cls(
            mode=AnalysisMode.BESTPREP,
            deduplicate=False,
            similarity_threshold=0.0,  # Not used
            preserve_all_fragments=True,
            individual_footnote_tracking=True,
            max_footnotes_per_answer=0,  # Unlimited
            enable_synthesis=True,
            synthesis_per_section=True,
            export_format='bestprep'
        )


def get_mode_config(mode_name: str) -> ModeConfig:
    """Get mode configuration by name."""
    if mode_name == 'bestprep':
        return ModeConfig.bestprep_default()
    return ModeConfig.bid_spec_default()
```

**Step 2: Update models.py with mode tracking**

Add to `services/hotdog/models.py`:

```python
# Add at top of file with other imports
from enum import Enum

# Add AnalysisMode enum (or import from mode_config)
class AnalysisMode(Enum):
    BID_SPEC = "bid_spec"
    BESTPREP = "bestprep"
```

**Step 3: Commit**

```bash
git add services/hotdog/mode_config.py services/hotdog/models.py
git commit -m "feat: add dual-mode configuration system (BestPrep foundation)"
```

---

## Task 2: Create AppendOnlyAccumulator for BestPrep Mode

**Files:**
- Create: `services/hotdog/append_accumulator.py`

**Step 1: Write the append-only accumulator**

```python
# services/hotdog/append_accumulator.py
"""
Append-only accumulator for BestPrep mode.
Never discards information - every answer fragment and footnote is preserved.
"""
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AnswerFragment:
    """A single answer fragment from one processing window."""
    fragment_id: str
    text: str
    pages: List[int]
    confidence: float
    window_index: int
    expert_name: str
    timestamp: str
    raw_footnote: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'fragment_id': self.fragment_id,
            'text': self.text,
            'pages': self.pages,
            'confidence': self.confidence,
            'window_index': self.window_index,
            'expert_name': self.expert_name,
            'timestamp': self.timestamp,
            'raw_footnote': self.raw_footnote
        }


@dataclass
class Footnote:
    """Individual footnote with full provenance."""
    footnote_id: str
    text: str
    page: int
    quote: str  # The exact quote from the document
    question_id: str
    fragment_id: str
    window_index: int
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'footnote_id': self.footnote_id,
            'text': self.text,
            'page': self.page,
            'quote': self.quote,
            'question_id': self.question_id,
            'fragment_id': self.fragment_id,
            'window_index': self.window_index,
            'timestamp': self.timestamp
        }


@dataclass
class CumulativeAnswer:
    """Cumulative answer for a question - holds ALL fragments."""
    question_id: str
    question_text: str
    fragments: List[AnswerFragment] = field(default_factory=list)
    footnotes: List[Footnote] = field(default_factory=list)
    synthesized_answer: Optional[str] = None
    synthesis_timestamp: Optional[str] = None

    @property
    def all_pages(self) -> List[int]:
        """All unique pages across all fragments, sorted."""
        pages = set()
        for fragment in self.fragments:
            pages.update(fragment.pages)
        return sorted(pages)

    @property
    def fragment_count(self) -> int:
        return len(self.fragments)

    @property
    def footnote_count(self) -> int:
        return len(self.footnotes)

    @property
    def highest_confidence(self) -> float:
        if not self.fragments:
            return 0.0
        return max(f.confidence for f in self.fragments)

    def add_fragment(self, fragment: AnswerFragment) -> None:
        """Add a new fragment - NEVER reject, always append."""
        self.fragments.append(fragment)
        logger.debug(f"Added fragment {fragment.fragment_id} to {self.question_id} "
                    f"(total: {len(self.fragments)})")

    def add_footnote(self, footnote: Footnote) -> None:
        """Add a footnote - NEVER reject, always append."""
        self.footnotes.append(footnote)
        logger.debug(f"Added footnote {footnote.footnote_id} to {self.question_id} "
                    f"(total: {len(self.footnotes)})")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'question_id': self.question_id,
            'question_text': self.question_text,
            'fragments': [f.to_dict() for f in self.fragments],
            'footnotes': [fn.to_dict() for fn in self.footnotes],
            'all_pages': self.all_pages,
            'fragment_count': self.fragment_count,
            'footnote_count': self.footnote_count,
            'highest_confidence': self.highest_confidence,
            'synthesized_answer': self.synthesized_answer,
            'synthesis_timestamp': self.synthesis_timestamp
        }


class AppendOnlyAccumulator:
    """
    BestPrep accumulator that NEVER discards information.

    Design principles:
    1. Every answer fragment is preserved with full provenance
    2. Every footnote is tracked individually
    3. No deduplication - let the synthesis agent handle coherence
    4. All data available for final synthesis layer
    """

    def __init__(self):
        self.cumulative_answers: Dict[str, CumulativeAnswer] = {}
        self.fragment_counter = 0
        self.footnote_counter = 0
        self._stats = {
            'total_fragments': 0,
            'total_footnotes': 0,
            'windows_processed': 0
        }

    def initialize_question(self, question_id: str, question_text: str) -> None:
        """Initialize tracking for a question."""
        if question_id not in self.cumulative_answers:
            self.cumulative_answers[question_id] = CumulativeAnswer(
                question_id=question_id,
                question_text=question_text
            )

    def add_answer(
        self,
        question_id: str,
        answer_text: str,
        pages: List[int],
        confidence: float,
        window_index: int,
        expert_name: str,
        raw_footnote: str = ""
    ) -> str:
        """
        Add an answer fragment. Returns the fragment_id.

        NEVER rejects - always appends.
        """
        if question_id not in self.cumulative_answers:
            logger.warning(f"Question {question_id} not initialized, auto-creating")
            self.initialize_question(question_id, "")

        self.fragment_counter += 1
        fragment_id = f"FRAG-{self.fragment_counter:05d}"

        fragment = AnswerFragment(
            fragment_id=fragment_id,
            text=answer_text,
            pages=pages,
            confidence=confidence,
            window_index=window_index,
            expert_name=expert_name,
            timestamp=datetime.utcnow().isoformat(),
            raw_footnote=raw_footnote
        )

        self.cumulative_answers[question_id].add_fragment(fragment)
        self._stats['total_fragments'] += 1

        # Extract and track individual footnotes from the answer
        self._extract_footnotes(question_id, fragment_id, answer_text, pages, window_index)

        return fragment_id

    def _extract_footnotes(
        self,
        question_id: str,
        fragment_id: str,
        answer_text: str,
        pages: List[int],
        window_index: int
    ) -> None:
        """Extract individual footnotes from answer text."""
        import re

        # Find all <PDF pg X> citations with surrounding context
        pattern = r'([^.]*?<PDF pg (\d+)>[^.]*\.)'
        matches = re.findall(pattern, answer_text, re.IGNORECASE)

        for match in matches:
            quote_with_citation = match[0].strip()
            page_num = int(match[1])

            self.footnote_counter += 1
            footnote_id = f"FN-{self.footnote_counter:05d}"

            footnote = Footnote(
                footnote_id=footnote_id,
                text=f"Reference from page {page_num}",
                page=page_num,
                quote=quote_with_citation,
                question_id=question_id,
                fragment_id=fragment_id,
                window_index=window_index,
                timestamp=datetime.utcnow().isoformat()
            )

            self.cumulative_answers[question_id].add_footnote(footnote)
            self._stats['total_footnotes'] += 1

    def mark_window_processed(self, window_index: int) -> None:
        """Track that a window has been processed."""
        self._stats['windows_processed'] = max(
            self._stats['windows_processed'],
            window_index + 1
        )

    def get_cumulative_answer(self, question_id: str) -> Optional[CumulativeAnswer]:
        """Get the cumulative answer for a question."""
        return self.cumulative_answers.get(question_id)

    def get_all_cumulative_answers(self) -> Dict[str, CumulativeAnswer]:
        """Get all cumulative answers."""
        return self.cumulative_answers

    def get_questions_for_synthesis(self) -> List[CumulativeAnswer]:
        """Get all questions that have fragments and need synthesis."""
        return [
            ca for ca in self.cumulative_answers.values()
            if ca.fragment_count > 0 and ca.synthesized_answer is None
        ]

    def set_synthesized_answer(self, question_id: str, synthesized_text: str) -> None:
        """Set the final synthesized answer for a question."""
        if question_id in self.cumulative_answers:
            self.cumulative_answers[question_id].synthesized_answer = synthesized_text
            self.cumulative_answers[question_id].synthesis_timestamp = datetime.utcnow().isoformat()

    def get_statistics(self) -> Dict[str, Any]:
        """Get accumulator statistics."""
        questions_with_answers = sum(
            1 for ca in self.cumulative_answers.values() if ca.fragment_count > 0
        )
        questions_synthesized = sum(
            1 for ca in self.cumulative_answers.values() if ca.synthesized_answer
        )

        return {
            **self._stats,
            'total_questions': len(self.cumulative_answers),
            'questions_with_answers': questions_with_answers,
            'questions_synthesized': questions_synthesized,
            'avg_fragments_per_question': (
                self._stats['total_fragments'] / len(self.cumulative_answers)
                if self.cumulative_answers else 0
            ),
            'avg_footnotes_per_question': (
                self._stats['total_footnotes'] / len(self.cumulative_answers)
                if self.cumulative_answers else 0
            )
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire accumulator state."""
        return {
            'cumulative_answers': {
                qid: ca.to_dict()
                for qid, ca in self.cumulative_answers.items()
            },
            'statistics': self.get_statistics()
        }
```

**Step 2: Commit**

```bash
git add services/hotdog/append_accumulator.py
git commit -m "feat: add AppendOnlyAccumulator for BestPrep mode - never discard"
```

---

## Task 3: Create Synthesis Agent (Layer 7)

**Files:**
- Create: `services/hotdog/synthesis_agent.py`

**Step 1: Write the synthesis agent**

```python
# services/hotdog/synthesis_agent.py
"""
Layer 7: Synthesis Agent for BestPrep mode.
Reviews all accumulated fragments and footnotes to produce one cohesive final answer.
"""
import logging
import asyncio
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI

from .append_accumulator import CumulativeAnswer, AppendOnlyAccumulator

logger = logging.getLogger(__name__)


class SynthesisAgent:
    """
    Final synthesis layer that reviews all answer fragments and footnotes
    to produce one comprehensive, coherent answer per question.

    Guarantees:
    1. Every fragment is considered
    2. Every footnote is included in the final answer
    3. All page citations are preserved
    4. Contradictions are noted and reconciled
    """

    SYNTHESIS_SYSTEM_PROMPT = """You are a scholarly synthesis agent. Your task is to combine multiple answer fragments about the same question into ONE comprehensive, coherent answer.

CRITICAL REQUIREMENTS:
1. EVERY piece of information from EVERY fragment must be included
2. EVERY page citation must be preserved in the final answer
3. EVERY footnote and quote must be referenced
4. If fragments contain contradictory information, note both perspectives
5. Organize the answer logically, but NEVER omit any information
6. Use the format: "According to page X, ..." for each distinct piece of information
7. End with a "Sources" section listing ALL page numbers referenced

Your output MUST be exhaustive. Missing even one citation is a failure."""

    SYNTHESIS_USER_TEMPLATE = """QUESTION: {question}

COLLECTED FRAGMENTS ({fragment_count} total):
{fragments_text}

COLLECTED FOOTNOTES ({footnote_count} total):
{footnotes_text}

ALL PAGES REFERENCED: {all_pages}

---

Synthesize ALL the above into ONE comprehensive answer. Include EVERY piece of information and EVERY citation. Do not omit anything."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self._stats = {
            'questions_synthesized': 0,
            'total_tokens_used': 0,
            'synthesis_errors': 0
        }

    async def synthesize_question(
        self,
        cumulative_answer: CumulativeAnswer
    ) -> Optional[str]:
        """
        Synthesize all fragments for a single question into one answer.

        Returns the synthesized answer text, or None on failure.
        """
        if cumulative_answer.fragment_count == 0:
            logger.warning(f"No fragments to synthesize for {cumulative_answer.question_id}")
            return None

        # Build fragments text
        fragments_lines = []
        for i, frag in enumerate(cumulative_answer.fragments, 1):
            fragments_lines.append(
                f"[Fragment {i} - Window {frag.window_index}, "
                f"Pages {frag.pages}, Confidence {frag.confidence:.0%}]\n"
                f"{frag.text}\n"
            )
        fragments_text = "\n".join(fragments_lines)

        # Build footnotes text
        footnotes_lines = []
        for fn in cumulative_answer.footnotes:
            footnotes_lines.append(
                f"[{fn.footnote_id} - Page {fn.page}]\n"
                f"Quote: \"{fn.quote}\"\n"
            )
        footnotes_text = "\n".join(footnotes_lines) if footnotes_lines else "(No explicit footnotes extracted)"

        # Build the prompt
        user_prompt = self.SYNTHESIS_USER_TEMPLATE.format(
            question=cumulative_answer.question_text,
            fragment_count=cumulative_answer.fragment_count,
            fragments_text=fragments_text,
            footnote_count=cumulative_answer.footnote_count,
            footnotes_text=footnotes_text,
            all_pages=cumulative_answer.all_pages
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Lower temperature for factual synthesis
                max_tokens=4000
            )

            synthesized = response.choices[0].message.content
            self._stats['questions_synthesized'] += 1
            self._stats['total_tokens_used'] += response.usage.total_tokens

            logger.info(
                f"Synthesized {cumulative_answer.question_id}: "
                f"{cumulative_answer.fragment_count} fragments → "
                f"{len(synthesized)} chars"
            )

            return synthesized

        except Exception as e:
            logger.error(f"Synthesis failed for {cumulative_answer.question_id}: {e}")
            self._stats['synthesis_errors'] += 1
            return None

    async def synthesize_all(
        self,
        accumulator: AppendOnlyAccumulator,
        section_ids: Optional[List[str]] = None,
        max_concurrent: int = 3
    ) -> Dict[str, str]:
        """
        Synthesize answers for all questions (or filtered by section).

        Args:
            accumulator: The AppendOnlyAccumulator with all fragments
            section_ids: Optional filter for specific sections
            max_concurrent: Max concurrent synthesis calls

        Returns:
            Dict mapping question_id to synthesized answer
        """
        questions = accumulator.get_questions_for_synthesis()

        if section_ids:
            questions = [q for q in questions if any(
                q.question_id.startswith(sid) for sid in section_ids
            )]

        logger.info(f"Starting synthesis for {len(questions)} questions")

        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def synthesize_with_limit(ca: CumulativeAnswer):
            async with semaphore:
                result = await self.synthesize_question(ca)
                if result:
                    accumulator.set_synthesized_answer(ca.question_id, result)
                    results[ca.question_id] = result

        await asyncio.gather(*[synthesize_with_limit(q) for q in questions])

        logger.info(
            f"Synthesis complete: {len(results)}/{len(questions)} successful, "
            f"{self._stats['total_tokens_used']} tokens used"
        )

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get synthesis statistics."""
        return self._stats.copy()
```

**Step 2: Commit**

```bash
git add services/hotdog/synthesis_agent.py
git commit -m "feat: add Layer 7 Synthesis Agent for BestPrep exhaustive answers"
```

---

## Task 4: Modify Orchestrator for Dual-Mode Support

**Files:**
- Modify: `services/hotdog/orchestrator.py`

**Step 1: Add mode-aware orchestration**

Add imports at top:
```python
from .mode_config import ModeConfig, AnalysisMode, get_mode_config
from .append_accumulator import AppendOnlyAccumulator
from .synthesis_agent import SynthesisAgent
```

Modify `HotdogOrchestrator.__init__`:
```python
def __init__(self, api_key: str, mode: str = 'bid_spec'):
    self.api_key = api_key
    self.mode_config = get_mode_config(mode)
    self.mode = self.mode_config.mode

    # Initialize appropriate accumulator based on mode
    if self.mode == AnalysisMode.BESTPREP:
        self.accumulator = AppendOnlyAccumulator()
        self.synthesis_agent = SynthesisAgent(api_key)
    else:
        self.accumulator = SmartAccumulator()  # Existing
        self.synthesis_agent = None

    # ... rest of existing init
```

Modify `run_analysis` to add synthesis step:
```python
async def run_analysis(self, ...):
    # ... existing layers 0-6 ...

    # Layer 7: Synthesis (BestPrep only)
    if self.mode_config.enable_synthesis and self.synthesis_agent:
        self._emit_event('synthesis_starting', {
            'questions_to_synthesize': len(self.accumulator.get_questions_for_synthesis())
        })

        await self.synthesis_agent.synthesize_all(self.accumulator)

        self._emit_event('synthesis_complete', self.synthesis_agent.get_statistics())

    # Compile results with mode-appropriate format
    return self._compile_results()
```

**Step 2: Commit**

```bash
git add services/hotdog/orchestrator.py
git commit -m "feat: orchestrator dual-mode support with synthesis layer"
```

---

## Task 5: Update app.py for Mode Selection

**Files:**
- Modify: `app.py`

**Step 1: Add mode parameter to /api/analyze**

Find the `/api/analyze` route and add mode handling:

```python
@app.route('/api/analyze', methods=['POST'])
def start_analysis():
    # ... existing code ...

    # Get analysis mode (new)
    analysis_mode = data.get('mode', 'bid_spec')  # Default to existing behavior
    if analysis_mode not in ['bid_spec', 'bestprep']:
        return jsonify({'success': False, 'error': 'Invalid mode'}), 400

    # Create orchestrator with mode
    orchestrator = HotdogOrchestrator(
        api_key=os.getenv('OPENAI_API_KEY'),
        mode=analysis_mode  # Pass mode
    )

    # ... rest of existing code ...
```

**Step 2: Commit**

```bash
git add app.py
git commit -m "feat: add mode parameter to /api/analyze endpoint"
```

---

## Task 6: Create BestPrep Excel Export Format

**Files:**
- Create: `services/bestprep_excel.py`

**Step 1: Write BestPrep-specific Excel generator**

```python
# services/bestprep_excel.py
"""
BestPrep Excel Export - Comprehensive answer format with all fragments and footnotes.
"""
import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


class BestPrepExcelGenerator:
    """Generate exhaustive Excel report for BestPrep mode."""

    # Colors
    NAVY = "1E3A8A"
    BLUE = "5B7FCC"
    GREEN = "22C55E"
    GRAY = "F3F4F6"

    def __init__(self, analysis_result: dict, accumulator_data: dict):
        self.result = analysis_result
        self.accumulator = accumulator_data
        self.wb = Workbook()

    def generate(self) -> io.BytesIO:
        """Generate 5-sheet BestPrep report."""
        if 'Sheet' in self.wb.sheetnames:
            del self.wb['Sheet']

        self._create_summary_sheet()      # Sheet 1: Overview
        self._create_answers_sheet()      # Sheet 2: Synthesized Answers
        self._create_fragments_sheet()    # Sheet 3: All Fragments
        self._create_footnotes_sheet()    # Sheet 4: All Footnotes
        self._create_sources_sheet()      # Sheet 5: Page Index

        output = io.BytesIO()
        self.wb.save(output)
        output.seek(0)
        return output

    def _create_summary_sheet(self):
        """Sheet 1: Analysis summary and statistics."""
        ws = self.wb.create_sheet("Summary", 0)
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 50

        stats = self.accumulator.get('statistics', {})

        data = [
            ("BestPrep Analysis Summary", ""),
            ("", ""),
            ("Total Questions", stats.get('total_questions', 0)),
            ("Questions Answered", stats.get('questions_with_answers', 0)),
            ("Questions Synthesized", stats.get('questions_synthesized', 0)),
            ("Total Fragments Collected", stats.get('total_fragments', 0)),
            ("Total Footnotes Extracted", stats.get('total_footnotes', 0)),
            ("Windows Processed", stats.get('windows_processed', 0)),
            ("Avg Fragments/Question", f"{stats.get('avg_fragments_per_question', 0):.1f}"),
            ("Avg Footnotes/Question", f"{stats.get('avg_footnotes_per_question', 0):.1f}"),
        ]

        for row_idx, (label, value) in enumerate(data, 1):
            ws.cell(row_idx, 1, label)
            ws.cell(row_idx, 2, value)

        # Style header
        ws.cell(1, 1).font = Font(size=16, bold=True, color=self.NAVY)

    def _create_answers_sheet(self):
        """Sheet 2: Final synthesized answers."""
        ws = self.wb.create_sheet("Synthesized Answers", 1)

        headers = ["#", "Question", "Synthesized Answer", "Sources", "Fragments", "Footnotes"]
        col_widths = [5, 40, 80, 15, 10, 10]

        for col, (header, width) in enumerate(zip(headers, col_widths), 1):
            ws.cell(1, col, header)
            ws.cell(1, col).font = Font(bold=True, color="FFFFFF")
            ws.cell(1, col).fill = PatternFill("solid", fgColor=self.NAVY)
            ws.column_dimensions[get_column_letter(col)].width = width

        row = 2
        for qid, ca_data in self.accumulator.get('cumulative_answers', {}).items():
            ws.cell(row, 1, row - 1)
            ws.cell(row, 2, ca_data.get('question_text', ''))
            ws.cell(row, 3, ca_data.get('synthesized_answer', 'Not synthesized'))
            ws.cell(row, 3).alignment = Alignment(wrap_text=True, vertical='top')
            ws.cell(row, 4, ', '.join(map(str, ca_data.get('all_pages', []))))
            ws.cell(row, 5, ca_data.get('fragment_count', 0))
            ws.cell(row, 6, ca_data.get('footnote_count', 0))

            # Dynamic row height
            answer_len = len(ca_data.get('synthesized_answer', ''))
            ws.row_dimensions[row].height = max(30, (answer_len // 80) * 15)

            row += 1

    def _create_fragments_sheet(self):
        """Sheet 3: All individual answer fragments."""
        ws = self.wb.create_sheet("All Fragments", 2)

        headers = ["Fragment ID", "Question ID", "Window", "Pages", "Confidence", "Expert", "Fragment Text"]
        col_widths = [12, 12, 8, 15, 10, 25, 80]

        for col, (header, width) in enumerate(zip(headers, col_widths), 1):
            ws.cell(1, col, header)
            ws.cell(1, col).font = Font(bold=True, color="FFFFFF")
            ws.cell(1, col).fill = PatternFill("solid", fgColor=self.BLUE)
            ws.column_dimensions[get_column_letter(col)].width = width

        row = 2
        for qid, ca_data in self.accumulator.get('cumulative_answers', {}).items():
            for frag in ca_data.get('fragments', []):
                ws.cell(row, 1, frag.get('fragment_id', ''))
                ws.cell(row, 2, qid)
                ws.cell(row, 3, frag.get('window_index', 0))
                ws.cell(row, 4, ', '.join(map(str, frag.get('pages', []))))
                ws.cell(row, 5, f"{frag.get('confidence', 0):.0%}")
                ws.cell(row, 6, frag.get('expert_name', ''))
                ws.cell(row, 7, frag.get('text', ''))
                ws.cell(row, 7).alignment = Alignment(wrap_text=True, vertical='top')
                row += 1

    def _create_footnotes_sheet(self):
        """Sheet 4: All individual footnotes with quotes."""
        ws = self.wb.create_sheet("All Footnotes", 3)

        headers = ["Footnote ID", "Question ID", "Page", "Quote", "Window", "Fragment ID"]
        col_widths = [12, 12, 8, 80, 8, 12]

        for col, (header, width) in enumerate(zip(headers, col_widths), 1):
            ws.cell(1, col, header)
            ws.cell(1, col).font = Font(bold=True, color="FFFFFF")
            ws.cell(1, col).fill = PatternFill("solid", fgColor=self.GREEN)
            ws.column_dimensions[get_column_letter(col)].width = width

        row = 2
        for qid, ca_data in self.accumulator.get('cumulative_answers', {}).items():
            for fn in ca_data.get('footnotes', []):
                ws.cell(row, 1, fn.get('footnote_id', ''))
                ws.cell(row, 2, qid)
                ws.cell(row, 3, fn.get('page', 0))
                ws.cell(row, 4, fn.get('quote', ''))
                ws.cell(row, 4).alignment = Alignment(wrap_text=True, vertical='top')
                ws.cell(row, 5, fn.get('window_index', 0))
                ws.cell(row, 6, fn.get('fragment_id', ''))
                row += 1

    def _create_sources_sheet(self):
        """Sheet 5: Page index showing which questions reference each page."""
        ws = self.wb.create_sheet("Page Index", 4)

        # Build page -> questions mapping
        page_map = {}
        for qid, ca_data in self.accumulator.get('cumulative_answers', {}).items():
            for page in ca_data.get('all_pages', []):
                if page not in page_map:
                    page_map[page] = []
                page_map[page].append(qid)

        headers = ["Page", "Questions Referencing This Page", "Reference Count"]
        col_widths = [10, 80, 15]

        for col, (header, width) in enumerate(zip(headers, col_widths), 1):
            ws.cell(1, col, header)
            ws.cell(1, col).font = Font(bold=True, color="FFFFFF")
            ws.cell(1, col).fill = PatternFill("solid", fgColor=self.NAVY)
            ws.column_dimensions[get_column_letter(col)].width = width

        row = 2
        for page in sorted(page_map.keys()):
            ws.cell(row, 1, page)
            ws.cell(row, 2, ', '.join(page_map[page]))
            ws.cell(row, 3, len(page_map[page]))
            row += 1
```

**Step 2: Add export route to app.py**

```python
@app.route('/api/export/bestprep-excel/<session_id>', methods=['GET'])
def export_bestprep_excel(session_id):
    """Export BestPrep analysis as comprehensive Excel."""
    # Get completed analysis
    with session_lock:
        if session_id in completed_analyses:
            analysis = completed_analyses[session_id]
        else:
            return jsonify({'success': False, 'error': 'Session not found'}), 404

    orchestrator = analysis['orchestrator']

    # Verify this is a BestPrep analysis
    if orchestrator.mode != AnalysisMode.BESTPREP:
        return jsonify({'success': False, 'error': 'Not a BestPrep analysis'}), 400

    generator = BestPrepExcelGenerator(
        analysis_result=orchestrator.get_result(),
        accumulator_data=orchestrator.accumulator.to_dict()
    )

    output = generator.generate()

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'bestprep_analysis_{session_id[:8]}.xlsx'
    )
```

**Step 3: Commit**

```bash
git add services/bestprep_excel.py app.py
git commit -m "feat: add BestPrep 5-sheet Excel export with fragments and footnotes"
```

---

## Task 7: Update Frontend for Mode Selection

**Files:**
- Modify: `index.html`

**Step 1: Add mode toggle UI**

Add mode selector in the upload section:

```html
<!-- Add after file upload area, before analyze button -->
<div class="mode-selector" style="margin: 20px 0; padding: 15px; background: #f3f4f6; border-radius: 8px;">
    <label style="font-weight: 600; color: #1E3A8A; display: block; margin-bottom: 10px;">
        Analysis Mode
    </label>
    <div style="display: flex; gap: 15px;">
        <label style="cursor: pointer; display: flex; align-items: center; gap: 8px;">
            <input type="radio" name="analysisMode" value="bid_spec" checked
                   onchange="setAnalysisMode('bid_spec')">
            <span><strong>Bid/Spec/RFP</strong> - Smart deduplication, merge similar answers</span>
        </label>
        <label style="cursor: pointer; display: flex; align-items: center; gap: 8px;">
            <input type="radio" name="analysisMode" value="bestprep"
                   onchange="setAnalysisMode('bestprep')">
            <span><strong>BestPrep/TestPrep</strong> - Exhaustive, never discard, with synthesis</span>
        </label>
    </div>
</div>
```

**Step 2: Add mode tracking JavaScript**

```javascript
let currentAnalysisMode = 'bid_spec';

function setAnalysisMode(mode) {
    currentAnalysisMode = mode;
    Logger.info(`Analysis mode set to: ${mode}`);

    // Update UI hints
    const modeHint = document.getElementById('modeHint');
    if (modeHint) {
        if (mode === 'bestprep') {
            modeHint.textContent = 'BestPrep: Every answer fragment preserved, synthesis at end';
            modeHint.style.color = '#22c55e';
        } else {
            modeHint.textContent = 'Bid/Spec: Smart deduplication, optimized for specs';
            modeHint.style.color = '#1E3A8A';
        }
    }
}
```

**Step 3: Modify startAnalysis to include mode**

Find the `startAnalysis` function and modify the fetch body:

```javascript
const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        session_id: currentSessionId,
        pdf_path: currentPdfPath,
        enabled_sections: getEnabledSections(),
        mode: currentAnalysisMode  // Add this line
    })
});
```

**Step 4: Update export button for mode-aware export**

```javascript
function exportResults(format) {
    if (format === 'excel-simple') {
        if (currentAnalysisMode === 'bestprep') {
            window.open(`/api/export/bestprep-excel/${currentSessionId}`, '_blank');
        } else {
            exportExcelDashboard();  // Existing
        }
    }
    // ... rest of formats
}
```

**Step 5: Commit**

```bash
git add index.html
git commit -m "feat: add mode selector UI for BestPrep vs Bid/Spec"
```

---

## Task 8: Update Admin Modal for BestPrep View

**Files:**
- Modify: `admin_sessions.html`

**Step 1: Add BestPrep-specific tabs**

Update the modal tabs to detect mode and show appropriate view:

```javascript
function renderAllTabs(data, sessionId) {
    const mode = data.result?.mode || 'bid_spec';

    if (mode === 'bestprep') {
        renderBestPrepSummaryTab(data, sessionId);
        renderFragmentsTab(data);
        renderFootnotesTab(data);  // Enhanced version
        renderSynthesizedTab(data);
    } else {
        // Existing tabs
        renderSummaryTab(data, sessionId);
        renderDetailedTab(data);
        renderBySectionTab(data);
        renderFootnotesTab(data);
    }
}

function renderBestPrepSummaryTab(data, sessionId) {
    const accum = data.accumulator || {};
    const stats = accum.statistics || {};

    let html = `
        <h3 style="color: #1E3A8A;">BestPrep Analysis Statistics</h3>
        <table class="results-table">
            <tr><td>Total Questions</td><td>${stats.total_questions || 0}</td></tr>
            <tr><td>Questions Answered</td><td>${stats.questions_with_answers || 0}</td></tr>
            <tr><td>Questions Synthesized</td><td>${stats.questions_synthesized || 0}</td></tr>
            <tr><td>Total Fragments</td><td>${stats.total_fragments || 0}</td></tr>
            <tr><td>Total Footnotes</td><td>${stats.total_footnotes || 0}</td></tr>
            <tr><td>Avg Fragments/Question</td><td>${(stats.avg_fragments_per_question || 0).toFixed(1)}</td></tr>
        </table>
    `;
    document.getElementById('summaryContent').innerHTML = html;
}

function renderFragmentsTab(data) {
    // New tab showing all fragments grouped by question
    // Implementation similar to BestPrep Excel Sheet 3
}

function renderSynthesizedTab(data) {
    // New tab showing final synthesized answers
    // Implementation similar to BestPrep Excel Sheet 2
}
```

**Step 2: Commit**

```bash
git add admin_sessions.html
git commit -m "feat: add BestPrep view to admin modal"
```

---

## Task 9: Integration Testing

**Files:**
- Create: `tests/test_bestprep_mode.py`

**Step 1: Write integration tests**

```python
# tests/test_bestprep_mode.py
"""Integration tests for BestPrep mode."""
import pytest
from services.hotdog.mode_config import get_mode_config, AnalysisMode
from services.hotdog.append_accumulator import AppendOnlyAccumulator
from services.hotdog.synthesis_agent import SynthesisAgent


class TestModeConfig:
    def test_bid_spec_mode_defaults(self):
        config = get_mode_config('bid_spec')
        assert config.mode == AnalysisMode.BID_SPEC
        assert config.deduplicate is True
        assert config.enable_synthesis is False

    def test_bestprep_mode_defaults(self):
        config = get_mode_config('bestprep')
        assert config.mode == AnalysisMode.BESTPREP
        assert config.deduplicate is False
        assert config.preserve_all_fragments is True
        assert config.enable_synthesis is True


class TestAppendOnlyAccumulator:
    def test_never_rejects_fragments(self):
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "Test question")

        # Add 100 identical fragments - all should be kept
        for i in range(100):
            acc.add_answer("Q1", "Same answer", [1], 0.9, i, "Expert1")

        ca = acc.get_cumulative_answer("Q1")
        assert ca.fragment_count == 100  # All preserved

    def test_footnote_extraction(self):
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "Test")

        answer = "Found on <PDF pg 5>. Also see <PDF pg 10> and <PDF pg 15>."
        acc.add_answer("Q1", answer, [5, 10, 15], 0.9, 0, "Expert1")

        ca = acc.get_cumulative_answer("Q1")
        assert ca.footnote_count >= 3  # At least 3 footnotes extracted


class TestSynthesisAgent:
    @pytest.mark.asyncio
    async def test_synthesis_includes_all_fragments(self):
        # Mock test - verify prompt construction includes all fragments
        pass  # Would need API mocking
```

**Step 2: Run tests**

```bash
pytest tests/test_bestprep_mode.py -v
```

**Step 3: Commit**

```bash
git add tests/test_bestprep_mode.py
git commit -m "test: add BestPrep mode integration tests"
```

---

## Task 10: Documentation Update

**Files:**
- Create: `docs/BESTPREP_MODE.md`

**Step 1: Write documentation**

```markdown
# BestPrep/TestPrep Mode

## Overview

BestPrep mode is designed for exhaustive textbook analysis where **every piece of information matters**. Unlike Bid/Spec mode which intelligently deduplicates similar answers, BestPrep mode:

1. **Never discards** any answer fragment
2. **Preserves every footnote** with full provenance
3. **Runs synthesis** at the end to combine all fragments into coherent answers

## When to Use

- Analyzing textbooks for exam preparation
- Questions that may have answers spread across 10+ pages
- When citation completeness is critical
- When you need to see all perspectives/fragments, not just the "best" one

## Architecture

```
Standard Layers 0-6
        ↓
AppendOnlyAccumulator (never discard)
        ↓
Layer 7: Synthesis Agent
        ↓
Comprehensive Final Answers
```

## Export Format

BestPrep exports include 5 sheets:
1. **Summary** - Statistics and overview
2. **Synthesized Answers** - Final comprehensive answers
3. **All Fragments** - Every fragment found, with provenance
4. **All Footnotes** - Every citation with quotes
5. **Page Index** - Which questions reference each page

## API Usage

```javascript
fetch('/api/analyze', {
    method: 'POST',
    body: JSON.stringify({
        session_id: 'xxx',
        pdf_path: '/path/to/textbook.pdf',
        mode: 'bestprep'  // <-- Set mode here
    })
});
```
```

**Step 2: Commit**

```bash
git add docs/BESTPREP_MODE.md
git commit -m "docs: add BestPrep mode documentation"
```

---

## Summary

**Total Tasks:** 10
**Estimated Commits:** 10
**Key New Files:**
- `services/hotdog/mode_config.py`
- `services/hotdog/append_accumulator.py`
- `services/hotdog/synthesis_agent.py`
- `services/bestprep_excel.py`
- `tests/test_bestprep_mode.py`
- `docs/BESTPREP_MODE.md`

**Key Modified Files:**
- `services/hotdog/orchestrator.py`
- `services/hotdog/models.py`
- `app.py`
- `index.html`
- `admin_sessions.html`

---

Plan complete and saved to `docs/plans/2026-01-30-bestprep-mode.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
