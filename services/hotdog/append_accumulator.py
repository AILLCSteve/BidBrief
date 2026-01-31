"""
Append-only accumulator for BestPrep mode.
Never discards information - every answer fragment and footnote is preserved.
"""
import logging
import re
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
