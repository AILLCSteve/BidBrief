"""Tests for the shared dynamic intelligence engine's output normalization."""
from services.dynamic_intelligence import MAX_ROWS, MAX_TABLES, _normalize


def _table(tid='t1', n_rows=2):
    return {
        'table_id': tid,
        'title': 'Bid Items',
        'why_relevant': 'because',
        'columns': [{'key': 'item', 'label': 'Item'}, {'key': 'qty', 'label': 'Qty'}],
        'rows': [{'item': f'Item {i}', 'qty': i} for i in range(n_rows)],
        'insights': ['dense pricing section'],
    }


def test_normalize_happy_path():
    out = _normalize({'intelligence_focus': 'focus!', 'tables': [_table()]})
    assert out['intelligence_focus'] == 'focus!'
    t = out['tables'][0]
    assert t['table_id'] == 't1'
    assert [c['key'] for c in t['columns']] == ['item', 'qty']
    # numeric cells coerced to strings
    assert t['rows'][1]['qty'] == '1'
    assert t['insights'] == ['dense pricing section']


def test_normalize_drops_empty_and_invalid_tables():
    raw = {'tables': [
        {'title': 'no columns', 'columns': [], 'rows': [{'a': 1}]},
        {'title': 'no rows', 'columns': [{'key': 'a', 'label': 'A'}], 'rows': []},
        'not-a-dict',
        _table('good'),
    ]}
    out = _normalize(raw)
    assert len(out['tables']) == 1
    assert out['tables'][0]['table_id'] == 'good'


def test_normalize_clamps_counts():
    raw = {'tables': [_table(f't{i}', n_rows=MAX_ROWS + 10) for i in range(MAX_TABLES + 3)]}
    out = _normalize(raw)
    assert len(out['tables']) == MAX_TABLES
    assert all(len(t['rows']) == MAX_ROWS for t in out['tables'])


def test_normalize_missing_cells_become_not_found():
    raw = {'tables': [{
        'table_id': 'gaps',
        'title': 'Gaps',
        'columns': [{'key': 'a', 'label': 'A'}, {'key': 'b', 'label': 'B'}],
        'rows': [{'a': 'present'}, {'a': 'x', 'b': None}],
    }]}
    out = _normalize(raw)
    rows = out['tables'][0]['rows']
    assert rows[0]['b'] == 'Not found'
    assert rows[1]['b'] == 'Not found'


def test_normalize_duplicate_ids_deduped():
    raw = {'tables': [_table('dup'), _table('dup')]}
    out = _normalize(raw)
    ids = [t['table_id'] for t in out['tables']]
    assert len(set(ids)) == 2


def test_focus_presets_complete():
    from services.scraper.config import (
        DEFAULT_RESEARCH_FOCUS,
        RESEARCH_FOCUS_PRESETS,
        focus_directive,
    )
    assert DEFAULT_RESEARCH_FOCUS == 'full_system'
    assert set(RESEARCH_FOCUS_PRESETS) == {
        'full_system', 'sewer_wastewater', 'stormwater', 'water_distribution', 'streets_row'}
    for key in RESEARCH_FOCUS_PRESETS:
        assert focus_directive(key)
    # unknown focus falls back to the default directive
    assert focus_directive('nonsense') == focus_directive('full_system')
