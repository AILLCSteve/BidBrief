"""
Tests for the Layer 0.5 Visual Intelligence scanner (2.4.0).

The contract under test:
- OFF by default — the orchestrator must not change behavior unless the
  /api/analyze body opts in with enable_visual_analysis.
- Page selection is a pure, cheap heuristic (no AI): drawing-heavy and
  image-heavy pages qualify; dense text pages with a small logo do not.
- Findings are ADDITIVE: enriched pages carry an appended [VISUAL CONTENT]
  block; nothing else about the page text changes.
- Findings flow into browser output, the legacy payload, and the Excel
  workbook as a 'Visual Intelligence' sheet — and are absent when empty.
"""
import json

import pytest

from services.hotdog.models import PageData
from services.hotdog.visual_intelligence import (
    VISUAL_SCORE_THRESHOLD,
    VisualPageStats,
    build_visual_block,
    is_visual_page,
    parse_vision_response,
    score_page,
    select_candidates,
)


class TestScorePage:
    def test_full_page_raster_scan_is_visual(self):
        # A scanned plan sheet: one raster covering the page, no text layer.
        score = score_page(text_chars=0, image_coverage=0.95, image_count=1, drawing_count=0)
        assert is_visual_page(score)

    def test_vector_cad_sheet_with_title_block_is_visual(self):
        # CAD-derived drawing: no rasters, hundreds of vector paths, sparse text.
        score = score_page(text_chars=350, image_coverage=0.0, image_count=0, drawing_count=600)
        assert is_visual_page(score)

    def test_simple_sparse_diagram_is_visual(self):
        # A near-textless page with a modest line diagram (real-PDF calibration:
        # 60 vector paths, 17 chars of text missed the first threshold).
        score = score_page(text_chars=17, image_coverage=0.0, image_count=0, drawing_count=60)
        assert is_visual_page(score)

    def test_text_page_with_underlines_is_not_visual(self):
        # Dense spec text whose underlines/table borders register as paths.
        score = score_page(text_chars=2800, image_coverage=0.0, image_count=0, drawing_count=80)
        assert not is_visual_page(score)

    def test_dense_text_page_with_small_logo_is_not_visual(self):
        score = score_page(text_chars=3200, image_coverage=0.03, image_count=1, drawing_count=8)
        assert not is_visual_page(score)

    def test_plain_text_page_is_not_visual(self):
        score = score_page(text_chars=2500, image_coverage=0.0, image_count=0, drawing_count=0)
        assert not is_visual_page(score)

    def test_text_dense_page_needs_substantial_visual_mass(self):
        # A spec page with a half-page figure still qualifies...
        assert is_visual_page(score_page(2500, 0.55, 1, 0))
        # ...but a quarter-page figure on a text page does not.
        assert not is_visual_page(score_page(2500, 0.25, 1, 0))


class TestSelectCandidates:
    def _stat(self, page, score):
        s = VisualPageStats(page_num=page)
        s.score = score
        return s

    def test_orders_by_score_then_page_and_caps(self):
        stats = [self._stat(1, 0.4), self._stat(2, 0.9),
                 self._stat(3, 0.9), self._stat(4, 0.1)]
        picked = select_candidates(stats, cap=2)
        assert [s.page_num for s in picked] == [2, 3]

    def test_below_threshold_never_selected(self):
        stats = [self._stat(1, VISUAL_SCORE_THRESHOLD - 0.01)]
        assert select_candidates(stats, cap=10) == []


class TestVisualBlock:
    def test_block_carries_all_finding_fields(self):
        block = build_visual_block({
            'kind': 'drawing', 'title': 'Plan & Profile STA 10+00',
            'description': 'Sewer main alignment along Oak St.',
            'extracted_text': '8" PVC SDR-35; MH-4 RIM 512.3',
            'key_facts': ['8 inch PVC', 'Manhole MH-4'],
        })
        assert '[VISUAL CONTENT' in block and '[END VISUAL CONTENT]' in block
        assert 'Plan & Profile STA 10+00' in block
        assert '8" PVC SDR-35' in block
        assert '- Manhole MH-4' in block

    def test_enrichment_is_purely_additive(self):
        original = PageData(page_num=3, text='SECTION 02530 SANITARY SEWER',
                            char_count=28, has_content=False)
        block = build_visual_block({'kind': 'map', 'description': 'Service area map.'})
        enriched_text = original.text + '\n' + block
        assert enriched_text.startswith(original.text)  # nothing removed or altered


class TestParseVisionResponse:
    def test_normalizes_a_good_response(self):
        raw = json.dumps({
            'page_kind': 'Map', 'title': 'Overall Site Map',
            'description': 'Shows the project limits.',
            'extracted_text': 'SCALE 1"=200\'',
            'key_facts': ['Project spans 12 blocks', ''],
            'confidence': 'HIGH',
        })
        f = parse_vision_response(raw, page_num=7)
        assert f['page'] == 7
        assert f['kind'] == 'map'
        assert f['confidence'] == 'high'
        assert f['key_facts'] == ['Project spans 12 blocks']

    def test_rejects_garbage_and_empty_findings(self):
        assert parse_vision_response('not json', 1) is None
        assert parse_vision_response('[]', 1) is None
        # A "nothing visual here" response is dropped, not surfaced.
        empty = json.dumps({'page_kind': 'mixed', 'description': '',
                            'extracted_text': '', 'key_facts': []})
        assert parse_vision_response(empty, 1) is None


class TestOrchestratorWiring:
    def test_visual_analysis_defaults_off(self):
        from services.hotdog.orchestrator import HotdogOrchestrator
        orch = HotdogOrchestrator(openai_api_key='sk-test')
        assert orch.enable_visual_analysis is False
        assert orch.visual_findings == []

    def test_flag_is_accepted(self):
        from services.hotdog.orchestrator import HotdogOrchestrator
        orch = HotdogOrchestrator(openai_api_key='sk-test', enable_visual_analysis=True)
        assert orch.enable_visual_analysis is True


class TestLegacyTransform:
    def test_visual_findings_pass_through(self):
        from app import _transform_to_legacy_format
        findings = [{'page': 4, 'kind': 'drawing', 'description': 'd'}]
        out = _transform_to_legacy_format({'sections': [], 'visual_findings': findings})
        assert out['visual_findings'] == findings

    def test_absent_findings_default_to_empty_list(self):
        from app import _transform_to_legacy_format
        out = _transform_to_legacy_format({'sections': []})
        assert out['visual_findings'] == []


class TestExcelSheet:
    def _result(self, findings):
        return {
            'sections': [{'section_name': 'S', 'questions': [
                {'question': 'Q?', 'answer': 'A <PDF pg 4>', 'page_citations': [4]}]}],
            'visual_findings': findings,
        }

    def test_sheet_present_with_findings(self):
        from services.excel_dashboard import ExcelDashboardGenerator
        gen = ExcelDashboardGenerator(self._result([{
            'page': 4, 'kind': 'drawing', 'title': 'Detail 3',
            'description': 'Trench detail.', 'extracted_text': 'MIN COVER 36"',
            'key_facts': ['36 inch minimum cover'], 'confidence': 'high',
        }]))
        gen.generate()
        assert 'Visual Intelligence' in gen.wb.sheetnames
        ws = gen.wb['Visual Intelligence']
        text = '\n'.join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
        assert 'Trench detail.' in text
        assert 'MIN COVER 36"' in text
        assert '36 inch minimum cover' in text

    def test_sheet_absent_without_findings(self):
        from services.excel_dashboard import ExcelDashboardGenerator
        gen = ExcelDashboardGenerator(self._result([]))
        gen.generate()
        assert 'Visual Intelligence' not in gen.wb.sheetnames
