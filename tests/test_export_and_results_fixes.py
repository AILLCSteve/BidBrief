"""Mobile-first Excel sizing + partial-results stats regression tests."""
from openpyxl import Workbook

from services.excel_mobile import MAX_COL_WIDTH, mobile_optimize


def test_mobile_optimize_clamps_wide_columns_and_wraps():
    wb = Workbook()
    ws = wb.active
    ws['A1'] = 'a very long answer that used to need a desktop-width column'
    ws['B1'] = 'narrow'
    ws.column_dimensions['A'].width = 90
    ws.column_dimensions['B'].width = 20

    mobile_optimize(wb)

    assert ws.column_dimensions['A'].width == MAX_COL_WIDTH
    assert ws.column_dimensions['B'].width == 20  # untouched
    assert ws['A1'].alignment.wrap_text is True
    assert ws.page_setup.fitToWidth == 1
    assert ws.page_setup.orientation == 'portrait'


def test_all_generators_apply_mobile_optimize():
    # Source-level guard: every Excel generator must call mobile_optimize.
    import inspect
    from services import bestprep_excel, excel_dashboard
    from services.smart_analysis import excel_generator as smart_excel
    from services.scraper.agents.presentation import excel_generator as scraper_excel

    for module in (excel_dashboard, bestprep_excel, smart_excel, scraper_excel):
        assert 'mobile_optimize' in inspect.getsource(module), module.__name__


def test_partial_browser_output_includes_stats():
    """Regression: mid-packaging/stopped fetches rendered '0/0 questions, 0 pages'
    because the partial output lacked the top-level stat keys."""
    from services.hotdog.models import ParsedConfig, Question, Section
    from services.hotdog.orchestrator import HotdogOrchestrator

    orch = HotdogOrchestrator(openai_api_key='sk-test-offline')
    question = Question(id='Q1', text='What is the scope?', section_id='s1')
    section = Section(id='s1', name='Scope', description='', questions=[question])
    config = ParsedConfig(
        name='test',
        version='1.0',
        sections=[section],
        section_map={'s1': section},
        question_map={'Q1': question},
    )

    out = orch._build_partial_browser_output({}, config)
    assert out['total_questions'] == 1
    assert out['questions_answered'] == 0
    assert 'total_pages' in out
    assert out['sections'][0]['questions'][0]['has_answer'] is False
