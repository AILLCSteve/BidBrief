"""
Tests for the enabled_sections filter (extracted from HotdogOrchestrator).

The iOS/web clients send `enabled_sections` on /api/analyze; the orchestrator
must analyze ONLY those sections (experts, windows, everything downstream).
A silent no-op here means deselected sections still get experts — the exact
field bug reported 2026-07-05.
"""
import pytest

from services.hotdog.models import ParsedConfig, Section, Question
from services.hotdog.orchestrator import apply_enabled_sections


def _make_config():
    s1 = Section(id="general_info", name="General", description="d1")
    s1.add_question(Question(id="Q1", text="What is the name?", section_id="general_info"))
    s1.add_question(Question(id="Q2", text="What is the date?", section_id="general_info"))
    s2 = Section(id="materials", name="Materials", description="d2")
    s2.add_question(Question(id="Q3", text="What pipe sizes?", section_id="materials"))
    return ParsedConfig(
        name="test", version="1.0", sections=[s1, s2],
        section_map={"general_info": s1, "materials": s2},
        question_map={"Q1": s1.questions[0], "Q2": s1.questions[1], "Q3": s2.questions[0]},
    )


class TestApplyEnabledSections:
    def test_filters_to_requested_sections_and_rebuilds_maps(self):
        config = _make_config()
        result = apply_enabled_sections(config, ["materials"])
        assert [s.id for s in result.sections] == ["materials"]
        assert set(result.section_map.keys()) == {"materials"}
        assert set(result.question_map.keys()) == {"Q3"}
        assert result.total_questions == 1
        assert result.total_sections == 1

    def test_none_passes_through_untouched(self):
        config = _make_config()
        result = apply_enabled_sections(config, None)
        assert result.total_sections == 2
        assert result.total_questions == 3

    def test_unknown_only_ids_raise_value_error(self):
        config = _make_config()
        with pytest.raises(ValueError):
            apply_enabled_sections(config, ["nope_1", "nope_2"])

    def test_empty_list_raises_value_error(self):
        # An empty explicit list is a client bug — nothing would be analyzed.
        config = _make_config()
        with pytest.raises(ValueError):
            apply_enabled_sections(config, [])

    def test_unknown_ids_alongside_known_are_dropped_not_fatal(self):
        config = _make_config()
        result = apply_enabled_sections(config, ["general_info", "stale_old_id"])
        assert [s.id for s in result.sections] == ["general_info"]
        assert set(result.question_map.keys()) == {"Q1", "Q2"}
