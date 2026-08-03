"""
Tests for the Layer 0.5 INTERWEAVE (2.4.0) — visual evidence as a first-class
resource inside HOTDOG, not a separate report.

The contract under test:
- Windows know which of their pages carry drawings/maps/imagery, and that
  tagging survives token-budget truncation.
- Expert prompts (first AND second pass) declare the visual evidence and demand
  a <VIS pg N kind> marker when an answer uses it.
- Markers parse into Answer.visual_sources, bounded by the pages actually
  analyzed, so a hallucinated marker cannot invent a graphic.
- Provenance survives merging (Bid/Spec) and fragment accumulation (BestPrep),
  and reaches the browser payload, the legacy API shape and the Excel columns.
"""
import pytest

from services.hotdog.models import Answer, PageData, WindowContext
from services.hotdog.layers import DocumentIngestionLayer
from services.hotdog.visual_intelligence import (
    extract_visual_sources,
    format_visual_sources,
)


def _page(num, text='text', kind=''):
    return PageData(page_num=num, text=text, char_count=len(text),
                    has_content=True, visual_kind=kind)


def _answer(qid='Q1', text='Answer <PDF pg 7>', pages=(7,), sources=None):
    return Answer(question_id=qid, text=text, pages=list(pages), confidence=0.8,
                  expert='Expert', window=1, visual_sources=list(sources or []))


class TestWindowsCarryVisualTagging:
    def test_create_windows_collects_visual_pages(self):
        pages = [_page(1), _page(2, kind='drawing'), _page(3, kind='map')]
        windows = DocumentIngestionLayer().create_windows(pages, window_size=3)
        assert windows[0].visual_pages == {2: 'drawing', 3: 'map'}
        assert windows[0].has_visual_evidence
        assert windows[0].visual_summary() == '2 (drawing), 3 (map)'

    def test_text_only_window_has_no_visual_evidence(self):
        windows = DocumentIngestionLayer().create_windows([_page(1), _page(2)])
        assert windows[0].visual_pages == {}
        assert not windows[0].has_visual_evidence

    def test_truncated_window_keeps_its_tagging(self):
        """The orchestrator rebuilds a WindowContext when a window exceeds the
        token budget. Dropping visual_pages there would disarm the citation
        contract for exactly the biggest, most drawing-heavy windows."""
        original = WindowContext(window_num=1, pages=[1, 2], text='long',
                                 page_data=[], visual_pages={2: 'drawing'})
        rebuilt = WindowContext(window_num=original.window_num,
                                pages=original.pages, text='truncated',
                                page_data=original.page_data,
                                visual_pages=original.visual_pages)
        assert rebuilt.visual_pages == {2: 'drawing'}


class TestExpertPromptDeclaresVisualEvidence:
    def _processor(self):
        from services.hotdog.multi_expert_processor import MultiExpertProcessor
        return MultiExpertProcessor(openai_client=None)

    def test_block_names_pages_kinds_and_the_marker_contract(self):
        window = WindowContext(window_num=1, pages=[7, 8], text='t', page_data=[],
                               visual_pages={7: 'drawing', 8: 'map'})
        block = self._processor()._visual_evidence_block(window)
        assert 'page 7 (engineering drawing)' in block
        assert 'page 8 (map)' in block
        assert '<VIS pg 7 drawing>' in block
        assert 'REAL EVIDENCE FROM THE DOCUMENT' in block
        assert 'ATTRIBUTION IS MANDATORY' in block

    def test_text_only_window_gets_no_block_at_all(self):
        """With no visual pass (or no visual pages) the prompt must be exactly
        what it was before 2.4.0 - the feature can never tax a text-only run."""
        window = WindowContext(window_num=1, pages=[1], text='t', page_data=[])
        assert self._processor()._visual_evidence_block(window) == ''
        assert self._processor()._visual_reminder(window) == ''

    def test_full_prompt_embeds_the_block(self):
        from services.hotdog.models import ExpertPersona, Question
        window = WindowContext(window_num=1, pages=[7], text='DOC TEXT',
                               page_data=[], visual_pages={7: 'drawing'})
        expert = ExpertPersona(id='e1', name='E', section_id='s', section_name='S',
                               specialization='Spec.', system_prompt='sp',
                               citation_strategy='cite', answer_format='fmt')
        question = Question(id='Q1', text='What size pipe?', section_id='s')
        prompt = self._processor()._build_expert_prompt(window, expert, [question])
        assert 'VISUAL EVIDENCE AVAILABLE IN THIS EXCERPT' in prompt
        assert '<VIS pg N kind>' in prompt
        assert 'DOC TEXT' in prompt


class TestSecondPassPromptDeclaresVisualEvidence:
    def test_unanswered_questions_get_pushed_at_the_graphics(self):
        from services.hotdog.second_pass_processor import SecondPassProcessor
        from services.hotdog.models import Question
        window = WindowContext(window_num=1, pages=[7], text='t', page_data=[],
                               visual_pages={7: 'drawing'})
        prompt = SecondPassProcessor(openai_client=None)._build_enhanced_user_prompt(
            window, [Question(id='Q1', text='q', section_id='s')])
        assert 'VISUAL EVIDENCE IN THIS SECTION' in prompt
        assert '<VIS pg 7 drawing>' in prompt


class TestMarkerParsing:
    def test_parses_page_and_kind(self):
        out = extract_visual_sources('Pipe is 8" <PDF pg 7> <VIS pg 7 drawing>')
        assert out == [{'page': 7, 'kind': 'drawing'}]

    def test_tolerates_missing_kind_and_backfills_from_the_window(self):
        out = extract_visual_sources('x <VIS pg 9>', page_kinds={9: 'map'})
        assert out == [{'page': 9, 'kind': 'map'}]

    def test_missing_kind_with_no_context_falls_back_to_visual(self):
        assert extract_visual_sources('x <VIS pg 9>') == [{'page': 9, 'kind': 'visual'}]

    def test_dedupes_and_orders_by_page(self):
        out = extract_visual_sources(
            '<VIS pg 9 map> <VIS pg 7 drawing> <VIS pg 9 map>')
        assert out == [{'page': 7, 'kind': 'drawing'}, {'page': 9, 'kind': 'map'}]

    def test_rejects_pages_that_were_never_analyzed(self):
        """A hallucinated marker must not invent a drawing the vision pass
        never read - provenance has to be trustworthy to be worth showing."""
        out = extract_visual_sources('<VIS pg 42 drawing>', allowed_pages=[7])
        assert out == []

    def test_no_markers_means_no_provenance(self):
        assert extract_visual_sources('Plain answer <PDF pg 3>') == []
        assert extract_visual_sources('') == []


class TestProvenanceSurvivesAccumulation:
    def test_merge_unions_visual_sources(self):
        a = _answer(sources=[{'page': 7, 'kind': 'drawing'}])
        b = _answer(text='More <PDF pg 9>', pages=(9,),
                    sources=[{'page': 9, 'kind': 'map'}])
        a.merge_with(b)
        assert a.visual_sources == [{'page': 7, 'kind': 'drawing'},
                                    {'page': 9, 'kind': 'map'}]

    def test_merge_does_not_duplicate_the_same_graphic(self):
        a = _answer(sources=[{'page': 7, 'kind': 'drawing'}])
        b = _answer(text='Same <PDF pg 7>', sources=[{'page': 7, 'kind': 'drawing'}])
        a.merge_with(b)
        assert a.visual_sources == [{'page': 7, 'kind': 'drawing'}]

    def test_text_only_answer_keeps_empty_provenance(self):
        a = _answer()
        a.merge_with(_answer(text='More <PDF pg 7>'))
        assert a.visual_sources == []

    def test_bestprep_fragments_aggregate_visual_sources(self):
        from services.hotdog.append_accumulator import AppendOnlyAccumulator
        acc = AppendOnlyAccumulator()
        acc.initialize_question('Q1', 'q')
        acc.add_answer('Q1', 'a <PDF pg 7>', [7], 0.8, 1, 'E',
                       visual_sources=[{'page': 7, 'kind': 'drawing'}])
        acc.add_answer('Q1', 'b <PDF pg 9>', [9], 0.7, 2, 'E',
                       visual_sources=[{'page': 9, 'kind': 'map'}])
        ca = acc.get_cumulative_answer('Q1')
        assert ca.all_visual_sources == [{'page': 7, 'kind': 'drawing'},
                                         {'page': 9, 'kind': 'map'}]

    def test_bestprep_fragment_serializes_its_sources(self):
        from services.hotdog.append_accumulator import AppendOnlyAccumulator
        acc = AppendOnlyAccumulator()
        acc.initialize_question('Q1', 'q')
        acc.add_answer('Q1', 'a <PDF pg 7>', [7], 0.8, 1, 'E',
                       visual_sources=[{'page': 7, 'kind': 'drawing'}])
        frag = acc.get_cumulative_answer('Q1').fragments[0].to_dict()
        assert frag['visual_sources'] == [{'page': 7, 'kind': 'drawing'}]


class TestProvenanceReachesTheClient:
    def test_browser_format_carries_visual_sources(self):
        from services.hotdog.output_compiler import OutputCompiler
        answer = _answer(sources=[{'page': 7, 'kind': 'drawing'}])
        out = OutputCompiler()._format_answer_for_browser(answer)
        assert out['visual_sources'] == [{'page': 7, 'kind': 'drawing'}]

    def test_legacy_payload_carries_visual_sources(self):
        from app import _transform_to_legacy_format
        payload = _transform_to_legacy_format({'sections': [{
            'section_id': 's', 'section_name': 'S', 'questions': [{
                'question_id': 'Q1', 'question_text': 'q', 'has_answer': True,
                'primary_answer': {'text': 'a', 'pages': [7],
                                   'visual_sources': [{'page': 7, 'kind': 'drawing'}]}}]}]})
        q = payload['sections'][0]['questions'][0]
        assert q['visual_sources'] == [{'page': 7, 'kind': 'drawing'}]

    def test_unanswered_question_gets_an_empty_list_not_a_missing_key(self):
        from app import _transform_to_legacy_format
        payload = _transform_to_legacy_format({'sections': [{
            'section_id': 's', 'section_name': 'S', 'questions': [{
                'question_id': 'Q1', 'question_text': 'q', 'has_answer': False,
                'primary_answer': None}]}]})
        assert payload['sections'][0]['questions'][0]['visual_sources'] == []


class TestExcelSurfacing:
    def test_format_visual_sources_reads_like_a_cell(self):
        assert format_visual_sources([{'page': 7, 'kind': 'drawing'},
                                      {'page': 9, 'kind': 'map'}]) == 'Drawing p.7; Map p.9'
        assert format_visual_sources([]) == ''
        assert format_visual_sources(None) == ''

    def test_detailed_results_has_a_visual_source_column(self):
        from services.excel_dashboard import ExcelDashboardGenerator
        gen = ExcelDashboardGenerator({'sections': [{'section_name': 'S', 'questions': [
            {'question': 'Pipe size?', 'answer': '8 inch <PDF pg 7>',
             'page_citations': [7], 'visual_sources': [{'page': 7, 'kind': 'drawing'}]}]}]})
        gen.generate()
        ws = gen.wb['Detailed Results']
        headers = [c.value for c in ws[2]]
        assert 'Visual Source' in headers
        col = headers.index('Visual Source') + 1
        assert ws.cell(3, col).value == 'Drawing p.7'

    def test_by_section_has_a_visual_source_column(self):
        from services.excel_dashboard import ExcelDashboardGenerator
        gen = ExcelDashboardGenerator({'sections': [{'section_name': 'S', 'questions': [
            {'question': 'Route?', 'answer': 'Along Oak <PDF pg 9>',
             'page_citations': [9], 'visual_sources': [{'page': 9, 'kind': 'map'}]}]}]})
        gen.generate()
        ws = gen.wb['By Section']
        text = '\n'.join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
        assert 'Visual Source' in text
        assert 'Map p.9' in text

    def test_text_only_answers_show_a_dash_not_a_blank_shear(self):
        from services.excel_dashboard import ExcelDashboardGenerator
        gen = ExcelDashboardGenerator({'sections': [{'section_name': 'S', 'questions': [
            {'question': 'q', 'answer': 'a <PDF pg 1>', 'page_citations': [1]}]}]})
        gen.generate()
        ws = gen.wb['Detailed Results']
        headers = [c.value for c in ws[2]]
        col = headers.index('Visual Source') + 1
        assert ws.cell(3, col).value == '-'
        # Status must still be the LAST column - a shear here is silent corruption
        assert headers[-1] == 'Status'
        assert ws.cell(3, len(headers)).value == 'Found'
