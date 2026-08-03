"""
Document Intelligence evidence building.

Two guarantees:
  1. Compaction shortens ONLY the prompt. The stored answers, the results
     payload and every export keep their full text — a user's data is never
     truncated to make an AI call cheaper.
  2. A DI failure is never silent again. It reports a reason, because a missing
     Document Intelligence tab was previously undiagnosable without server logs.
"""
import copy

import app


FULL_ANSWER = (
    'The contractor shall furnish all labor and materials for the complete CIPP lining '
    'installation per ASTM F1216, including bypass pumping. <PDF pg 12> <VIS pg 7 drawing>\n'
    '[VISUAL CONTENT - AI vision analysis]\nType: drawing\n'
    'What it shows: plan and profile of the sewer main.\n[END VISUAL CONTENT]'
) * 4


def _payload():
    return {'sections': [{'section_name': 'Scope', 'questions': [
        {'question': 'What is the scope?', 'answer': FULL_ANSWER,
         'page_citations': [12], 'answer_summary': 'Full CIPP install.'}]}]}


class TestEvidenceNeverMutatesTheAnalysis:
    def test_the_payload_is_untouched(self):
        payload = _payload()
        before = copy.deepcopy(payload)
        app._analysis_intel_evidence(payload, None, 'doc ctx')
        assert payload == before, 'building evidence must never alter the analysis'

    def test_the_stored_answer_keeps_its_full_text(self):
        payload = _payload()
        app._analysis_intel_evidence(payload, None, 'doc ctx')
        assert payload['sections'][0]['questions'][0]['answer'] == FULL_ANSWER

    def test_the_excel_export_still_carries_the_whole_answer(self):
        from services.excel_dashboard import ExcelDashboardGenerator
        payload = _payload()
        app._analysis_intel_evidence(payload, None, 'doc ctx')
        gen = ExcelDashboardGenerator(payload)
        gen.generate()
        cell = gen.wb['Detailed Results'].cell(3, 4).value
        assert len(cell) == len(FULL_ANSWER), 'the export must show the full answer'


class TestEvidenceIsCompactedForThePromptOnly:
    def test_visual_blocks_and_markers_are_stripped_from_the_prompt(self):
        evidence = app._analysis_intel_evidence(_payload(), None, '')
        assert '[VISUAL CONTENT' not in evidence
        assert '<PDF pg' not in evidence
        assert '<VIS pg' not in evidence
        assert 'from a drawing/map' in evidence, 'visual provenance is still signalled'

    def test_the_prompt_is_much_smaller_than_the_raw_answers(self):
        evidence = app._analysis_intel_evidence(_payload(), None, '')
        assert len(evidence) < len(FULL_ANSWER), 'compaction must actually compact'

    def test_every_question_is_represented(self):
        """Breadth is the point: truncation used to drop most of the document."""
        payload = {'sections': [{'section_name': 'S', 'questions': [
            {'question': f'Question number {i}?', 'answer': FULL_ANSWER, 'page_citations': [i]}
            for i in range(40)]}]}
        evidence = app._analysis_intel_evidence(payload, None, '')
        for i in (0, 20, 39):
            assert f'Question number {i}?' in evidence, f'question {i} missing from the evidence'


class TestFailuresAreReported:
    def test_no_evidence_reports_a_reason_and_emits(self):
        events = []
        result = app._generate_analysis_dynamic_intel(
            {'sections': []}, None, '', 'sk-test', 'gpt-5.6-terra', 'label',
            emit=lambda e, d: events.append((e, d)))
        assert result['tables'] == []
        assert result.get('error'), 'a failure must carry a reason'
        assert any(e == 'dynamic_intel_failed' for e, _ in events)

    def test_an_exception_is_reported_not_swallowed(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError('model unavailable')
        monkeypatch.setattr(app, '_analysis_intel_evidence', boom)
        events = []
        result = app._generate_analysis_dynamic_intel(
            {'sections': []}, None, '', 'sk-test', 'm', 'label',
            emit=lambda e, d: events.append((e, d)))
        assert 'model unavailable' in result['error']
        assert events and events[-1][0] == 'dynamic_intel_failed'
