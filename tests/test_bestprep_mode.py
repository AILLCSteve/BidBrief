"""
Integration tests for BestPrep mode.

Tests the dual-mode system, append-only accumulator, and synthesis agent.
"""
import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.hotdog.mode_config import get_mode_config, AnalysisMode, ModeConfig
from services.hotdog.append_accumulator import (
    AppendOnlyAccumulator,
    AnswerFragment,
    Footnote,
    CumulativeAnswer
)


class TestModeConfig:
    """Test mode configuration system."""

    def test_bid_spec_mode_defaults(self):
        """Bid/Spec mode should have deduplication enabled."""
        config = get_mode_config('bid_spec')
        assert config.mode == AnalysisMode.BID_SPEC
        assert config.deduplicate is True
        assert config.enable_synthesis is False
        assert config.similarity_threshold == 0.75

    def test_bestprep_mode_defaults(self):
        """BestPrep mode should preserve all fragments and enable synthesis."""
        config = get_mode_config('bestprep')
        assert config.mode == AnalysisMode.BESTPREP
        assert config.deduplicate is False
        assert config.preserve_all_fragments is True
        assert config.enable_synthesis is True
        assert config.individual_footnote_tracking is True

    def test_unknown_mode_defaults_to_bid_spec(self):
        """Unknown mode names should default to bid_spec."""
        config = get_mode_config('unknown_mode')
        assert config.mode == AnalysisMode.BID_SPEC

    def test_mode_config_export_format(self):
        """Export format should match mode."""
        bid_spec = get_mode_config('bid_spec')
        bestprep = get_mode_config('bestprep')

        assert bid_spec.export_format == 'bid_spec'
        assert bestprep.export_format == 'bestprep'


class TestAppendOnlyAccumulator:
    """Test the append-only accumulator for BestPrep mode."""

    def test_initialization(self):
        """Accumulator should initialize empty."""
        acc = AppendOnlyAccumulator()
        assert len(acc.cumulative_answers) == 0
        assert acc.fragment_counter == 0
        assert acc.footnote_counter == 0

    def test_initialize_question(self):
        """Questions should be initialized with empty fragments."""
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "What is the project name?")

        assert "Q1" in acc.cumulative_answers
        ca = acc.cumulative_answers["Q1"]
        assert ca.question_text == "What is the project name?"
        assert ca.fragment_count == 0

    def test_never_rejects_fragments(self):
        """Accumulator should NEVER reject fragments - always append."""
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "Test question")

        # Add 100 identical fragments - ALL should be kept
        for i in range(100):
            acc.add_answer(
                question_id="Q1",
                answer_text="Same answer text <PDF pg 5>.",
                pages=[5],
                confidence=0.9,
                window_index=i,
                expert_name="Expert1"
            )

        ca = acc.get_cumulative_answer("Q1")
        assert ca.fragment_count == 100, "All fragments should be preserved"

    def test_fragment_ids_are_unique(self):
        """Each fragment should have a unique ID."""
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "Test")

        frag_ids = []
        for i in range(10):
            frag_id = acc.add_answer("Q1", f"Answer {i} <PDF pg {i}>.", [i], 0.8, i, "Expert")
            frag_ids.append(frag_id)

        assert len(frag_ids) == len(set(frag_ids)), "All fragment IDs should be unique"

    def test_footnote_extraction(self):
        """Footnotes should be extracted from answer text with <PDF pg X> markers."""
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "Test")

        answer = "Found on <PDF pg 5>. Also see <PDF pg 10> and <PDF pg 15>."
        acc.add_answer("Q1", answer, [5, 10, 15], 0.9, 0, "Expert1")

        ca = acc.get_cumulative_answer("Q1")
        # Should extract at least 3 footnotes from the citations
        assert ca.footnote_count >= 3, "Should extract footnotes from citations"

    def test_all_pages_aggregation(self):
        """all_pages property should aggregate all unique pages."""
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "Test")

        acc.add_answer("Q1", "Text <PDF pg 1>.", [1], 0.8, 0, "Expert")
        acc.add_answer("Q1", "Text <PDF pg 3>.", [3], 0.8, 1, "Expert")
        acc.add_answer("Q1", "Text <PDF pg 2>.", [2], 0.8, 2, "Expert")
        acc.add_answer("Q1", "Text <PDF pg 1>.", [1], 0.8, 3, "Expert")  # Duplicate page

        ca = acc.get_cumulative_answer("Q1")
        assert ca.all_pages == [1, 2, 3], "Should return sorted unique pages"

    def test_highest_confidence(self):
        """highest_confidence should return max confidence across fragments."""
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "Test")

        acc.add_answer("Q1", "Low <PDF pg 1>.", [1], 0.3, 0, "Expert")
        acc.add_answer("Q1", "Medium <PDF pg 2>.", [2], 0.6, 1, "Expert")
        acc.add_answer("Q1", "High <PDF pg 3>.", [3], 0.95, 2, "Expert")
        acc.add_answer("Q1", "Medium2 <PDF pg 4>.", [4], 0.7, 3, "Expert")

        ca = acc.get_cumulative_answer("Q1")
        assert ca.highest_confidence == 0.95

    def test_statistics(self):
        """Statistics should accurately track accumulation."""
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "Question 1")
        acc.initialize_question("Q2", "Question 2")

        acc.add_answer("Q1", "Answer <PDF pg 1>.", [1], 0.8, 0, "Expert")
        acc.add_answer("Q1", "Answer <PDF pg 2>.", [2], 0.9, 1, "Expert")
        acc.add_answer("Q2", "Answer <PDF pg 3>.", [3], 0.7, 0, "Expert")
        acc.mark_window_processed(1)

        stats = acc.get_statistics()
        assert stats['total_questions'] == 2
        assert stats['total_fragments'] == 3
        assert stats['questions_with_answers'] == 2
        assert stats['windows_processed'] == 2

    def test_get_questions_for_synthesis(self):
        """Should return only questions with fragments that need synthesis."""
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "Has fragments")
        acc.initialize_question("Q2", "No fragments")
        acc.initialize_question("Q3", "Already synthesized")

        acc.add_answer("Q1", "Text <PDF pg 1>.", [1], 0.8, 0, "Expert")
        acc.add_answer("Q3", "Text <PDF pg 2>.", [2], 0.8, 0, "Expert")
        acc.set_synthesized_answer("Q3", "Synthesized text")

        to_synthesize = acc.get_questions_for_synthesis()
        assert len(to_synthesize) == 1
        assert to_synthesize[0].question_id == "Q1"

    def test_auto_create_question_on_add(self):
        """Adding answer to non-existent question should auto-create it."""
        acc = AppendOnlyAccumulator()

        # Don't call initialize_question - just add answer
        acc.add_answer("Q99", "Answer <PDF pg 5>.", [5], 0.8, 0, "Expert")

        assert "Q99" in acc.cumulative_answers
        assert acc.get_cumulative_answer("Q99").fragment_count == 1

    def test_serialization(self):
        """to_dict should produce serializable output."""
        acc = AppendOnlyAccumulator()
        acc.initialize_question("Q1", "Test question")
        acc.add_answer("Q1", "Answer <PDF pg 1>.", [1], 0.8, 0, "Expert")

        data = acc.to_dict()

        assert 'cumulative_answers' in data
        assert 'statistics' in data
        assert 'Q1' in data['cumulative_answers']

        # Should be JSON-serializable
        import json
        json_str = json.dumps(data)
        assert len(json_str) > 0


class TestCumulativeAnswer:
    """Test the CumulativeAnswer dataclass."""

    def test_add_fragment(self):
        """Fragments should be appended."""
        ca = CumulativeAnswer(question_id="Q1", question_text="Test")

        frag = AnswerFragment(
            fragment_id="FRAG-1",
            text="Test answer",
            pages=[1, 2],
            confidence=0.8,
            window_index=0,
            expert_name="Expert",
            timestamp="2026-01-30T12:00:00"
        )
        ca.add_fragment(frag)

        assert len(ca.fragments) == 1
        assert ca.fragments[0].fragment_id == "FRAG-1"

    def test_add_footnote(self):
        """Footnotes should be appended."""
        ca = CumulativeAnswer(question_id="Q1", question_text="Test")

        fn = Footnote(
            footnote_id="FN-1",
            text="Reference",
            page=5,
            quote="Quoted text",
            question_id="Q1",
            fragment_id="FRAG-1",
            window_index=0,
            timestamp="2026-01-30T12:00:00"
        )
        ca.add_footnote(fn)

        assert len(ca.footnotes) == 1
        assert ca.footnotes[0].page == 5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
