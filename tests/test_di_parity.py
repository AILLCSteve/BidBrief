"""Document Intelligence must reach the browser wherever it reaches Excel.

THE RECURRING BUG
Twice now the DI tab has been missing from the web results while the Excel
export showed the sheet — proving the tables existed and only the view was
losing them. `_transform_to_legacy_format` rebuilds the payload from a FIXED key
set, so it DROPS dynamic_tables/intelligence_focus (attached by app.py after the
orchestrator finishes). Every branch of /api/results has to put them back, and
in 2.5.8 the `restored` branch still did not — which was about to matter for
every analysis, since after a deploy a restored session is all you can look at.

Two surfaces disagreeing about one record is the signature. These tests assert
the agreement directly instead of trusting that each branch remembered.
"""
import inspect
import re

import pytest

import app as app_module


BRANCHES = ('restored', 'completed', 'legacy', 'partial', 'active')


def _results_source():
    return inspect.getsource(app_module.get_results)


class TestEveryBranchReattachesTheTables:
    def test_the_helper_is_called_at_least_once_per_branch(self):
        """Structural, deliberately: exercising all five branches needs a live
        orchestrator, and the failure mode is always 'a branch forgot to call
        it', which is visible in the source."""
        source = _results_source()
        calls = source.count('_attach_dynamic_intel(')
        assert calls >= len(BRANCHES), (
            f'only {calls} _attach_dynamic_intel call(s) for {len(BRANCHES)} branches — '
            'a branch will silently drop Document Intelligence')

    @pytest.mark.parametrize('branch', BRANCHES)
    def test_branch_exists_and_is_followed_by_an_attach(self, branch):
        """Each branch's body must reach the helper before it returns."""
        source = _results_source()
        marker = f"session_type == '{branch}'"
        assert marker in source, f'branch {branch} no longer exists — update this test'
        body = source.split(marker, 1)[1]
        # Up to the start of the next branch, or the end of the function.
        nxt = re.search(r"session_type == '", body)
        if nxt:
            body = body[:nxt.start()]
        assert '_attach_dynamic_intel(' in body, (
            f"the '{branch}' branch returns without re-attaching Document "
            'Intelligence — the Excel export will show the sheet and the '
            'browser tab will be missing')


class TestTheHelperNeverDowngrades:
    """A payload that already carries tables must survive a source that has
    none — otherwise a later fetch erases the tab (the 2.5.1 half of this bug)."""

    def _clear(self):
        for d in (app_module.completed_analyses, app_module.analysis_results,
                  app_module.partial_analyses, app_module.active_analyses):
            d.pop('sess_di', None)

    def test_existing_tables_survive_an_empty_source(self):
        self._clear()
        try:
            payload = {'dynamic_tables': [{'title': 'Pipe Schedule', 'rows': [{'a': 1}]}],
                       'intelligence_focus': 'pipe materials'}
            app_module._attach_dynamic_intel(payload, 'sess_di')
            assert payload['dynamic_tables'], 'a richer payload was downgraded to empty'
            assert payload['intelligence_focus'] == 'pipe materials'
        finally:
            self._clear()

    def test_tables_are_taken_from_the_session_when_the_payload_has_none(self):
        self._clear()
        app_module.completed_analyses['sess_di'] = {
            'dynamic_tables': [{'title': 'Valves', 'rows': [{'a': 1}]}],
            'intelligence_focus': 'valve types',
        }
        try:
            payload = {}
            app_module._attach_dynamic_intel(payload, 'sess_di')
            assert payload['dynamic_tables'][0]['title'] == 'Valves'
            assert payload['intelligence_focus'] == 'valve types'
        finally:
            self._clear()

    def test_the_failure_reason_is_carried_so_the_tab_can_explain_itself(self):
        self._clear()
        app_module.completed_analyses['sess_di'] = {
            'dynamic_tables': [], 'intelligence_focus': '',
            'intelligence_error': 'RateLimitError: quota exceeded',
        }
        try:
            payload = {}
            app_module._attach_dynamic_intel(payload, 'sess_di')
            assert payload['intelligence_error'] == 'RateLimitError: quota exceeded', \
                'without the reason the browser can only show an empty tab'
        finally:
            self._clear()


class TestExcelAndBrowserAgreeOnWhatCountsAsPresent:
    """The Excel generator asks `if result.get('dynamic_tables')` — truthy — and
    then iterates. The browser used to ask `.length`, which is undefined for a
    dict, so the same payload produced a sheet in Excel and no tab in the
    browser. The JS side of this is covered in tests/js/bb-di-parity.test.js."""

    def test_excel_gates_the_sheet_on_a_plain_truthiness_check(self):
        source = inspect.getsource(
            __import__('services.excel_dashboard', fromlist=['x']).ExcelDashboardGenerator)
        assert "self.result.get('dynamic_tables')" in source, \
            'Excel gating changed — re-check that the browser still agrees with it'
