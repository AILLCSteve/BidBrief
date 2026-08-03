"""
Tests for durable session storage (services/persistence.py).

These run WITHOUT a database. The contract that matters most is the one they can
prove offline: with no DATABASE_URL the store is inert and the app behaves
exactly as it did before persistence existed. A real Neon round-trip is proven
separately by `python -m services.persistence`, which needs live credentials.
"""
import json
from datetime import datetime

import pytest

from services.persistence import Store, _json_default, retention_days
from services.beta_access import BetaAccess


@pytest.fixture
def disabled_store(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    return Store()


class TestDisabledWithoutDatabaseUrl:
    """The single most important property: this module is never load-bearing."""

    def test_init_reports_disabled(self, disabled_store):
        assert disabled_store.init() is False
        assert disabled_store.enabled is False

    def test_every_write_is_a_silent_noop(self, disabled_store):
        assert disabled_store.save_analysis(
            'sess_1', owner='u', pdf_filename='f.pdf', mode='bid_spec',
            status='completed', snapshot={'result': {}}) is False
        assert disabled_store.save_auth_session('t', {'username': 'u'}) is False
        assert disabled_store.save_beta_tester({'username': 'beta-1'}) is False
        assert disabled_store.set_bonus_user('a@b.c', True) is False
        assert disabled_store.save_smart_analysis('sess_1', {}) is False
        assert disabled_store.set_setting('k', True) is False

    def test_every_read_returns_an_empty_default(self, disabled_store):
        assert disabled_store.load_analysis('sess_1') is None
        assert disabled_store.list_analysis_index() == []
        assert disabled_store.load_auth_sessions() == {}
        assert disabled_store.load_beta_testers() == []
        assert disabled_store.load_bonus_users() == []
        assert disabled_store.load_smart_analysis('sess_1') is None
        assert disabled_store.get_setting('missing', 'fallback') == 'fallback'

    def test_maintenance_calls_are_harmless(self, disabled_store):
        assert disabled_store.mark_interrupted_analyses() == 0
        assert disabled_store.purge_expired() == 0
        assert disabled_store.delete_analysis('sess_1') is False
        assert disabled_store.health() == {'enabled': False, 'error': None}


class TestFailureIsAlwaysSafe:
    """A database outage must degrade, never raise — an analysis that already
    succeeded can't be failed by a storage problem."""

    def test_a_throwing_connection_is_swallowed(self, monkeypatch):
        store = Store()
        store.enabled = True

        class ExplodingPool:
            def connection(self):
                raise RuntimeError('neon is asleep')

        store._pool = ExplodingPool()
        assert store.save_analysis('s', owner=None, pdf_filename='f', mode='m',
                                   status='completed', snapshot={}) is False
        assert store.load_analysis('s') is None
        assert store.list_analysis_index() == []
        assert store.last_error == 'neon is asleep'

    def test_health_reports_unreachable_instead_of_raising(self):
        store = Store()
        store.enabled = True

        class ExplodingPool:
            def connection(self):
                raise RuntimeError('down')

        store._pool = ExplodingPool()
        health = store.health()
        assert health['enabled'] is True
        assert health['reachable'] is False


class TestSnapshotSerialization:
    def test_datetimes_survive_json_encoding(self):
        moment = datetime(2026, 8, 2, 12, 30)
        encoded = json.dumps({'when': moment}, default=_json_default)
        assert '2026-08-02T12:30:00' in encoded

    def test_unexpected_objects_do_not_break_a_write(self):
        class Weird:
            def __str__(self):
                return 'weird'
        assert 'weird' in json.dumps({'x': Weird()}, default=_json_default)

    def test_retention_default_and_override(self, monkeypatch):
        monkeypatch.delenv('BIDBRIEF_DB_RETENTION_DAYS', raising=False)
        assert retention_days() == 90
        monkeypatch.setenv('BIDBRIEF_DB_RETENTION_DAYS', '7')
        assert retention_days() == 7
        monkeypatch.setenv('BIDBRIEF_DB_RETENTION_DAYS', 'nonsense')
        assert retention_days() == 90


class TestAnalysisSnapshotShape:
    """The snapshot must carry everything the read paths need after a restart,
    because the orchestrator they normally use is gone."""

    def test_snapshot_captures_every_field_the_api_serves(self):
        from app import _build_analysis_snapshot
        snapshot = _build_analysis_snapshot(
            'sess_1',
            {'sections': [], 'document_name': 'spec.pdf'},
            {'questions_answered': 5, 'total_questions': 10},
            orchestrator=None, mode='bid_spec', pdf_filename='spec.pdf',
            doc_context='ctx')
        for key in ('result', 'statistics', 'key_details', 'key_details_list',
                    'document_type', 'document_type_label', 'bestprep_data',
                    'mode', 'pdf_filename', 'doc_context', 'is_partial'):
            assert key in snapshot, f'{key} missing — a read path would break'
        assert snapshot['statistics']['questions_answered'] == 5
        assert snapshot['doc_context'] == 'ctx'

    def test_snapshot_is_json_serializable(self):
        from app import _build_analysis_snapshot
        snapshot = _build_analysis_snapshot(
            'sess_1', {'sections': []}, {'t': 1}, orchestrator=None)
        json.dumps(snapshot, default=_json_default)  # must not raise

    def test_partial_flag_round_trips(self):
        from app import _build_analysis_snapshot
        snapshot = _build_analysis_snapshot(
            'sess_1', {}, {}, orchestrator=None, is_partial=True)
        assert snapshot['is_partial'] is True


class TestBetaRestore:
    def test_restore_loads_testers(self):
        beta = BetaAccess(enabled=False, doc_limit=5)
        added = beta.restore([{'username': 'beta-abc', 'name': 'Tester',
                               'docs_used': 2, 'doc_limit': 5,
                               'created_at': datetime.now(),
                               'last_seen': datetime.now()}])
        assert added == 1
        record = beta.get('beta-abc')
        assert record['docs_used'] == 2
        assert beta.remaining('beta-abc') == 3

    def test_restore_never_clobbers_a_live_tester(self):
        """A tester minted since boot must win over a stale stored copy."""
        beta = BetaAccess(enabled=True, doc_limit=5)
        live = beta.mint()
        beta.consume_document(live['username'])
        added = beta.restore([{'username': live['username'], 'docs_used': 0,
                               'doc_limit': 5}])
        assert added == 0
        assert beta.get(live['username'])['docs_used'] == 1

    def test_restore_tolerates_junk_rows(self):
        beta = BetaAccess(enabled=False, doc_limit=5)
        assert beta.restore([{}, {'username': ''}]) == 0
        assert beta.restore([]) == 0


class TestAdminContractUnchanged:
    """Recovered rows fold into the existing buckets: the four bucket names are
    what the iOS dashboard decodes, so persistence must not add a fifth."""

    def test_bucket_names_are_still_exactly_four(self):
        import app as app_module
        app_module.restored_analyses.clear()
        app_module.restored_analyses['sess_restored'] = {
            'pdf_filename': 'old.pdf', 'owner': 'u', 'mode': 'bid_spec',
            'status': 'completed', 'statistics': {'questions_answered': 3},
            'restored': True,
        }
        try:
            buckets = app_module._snapshot_sessions_by_bucket()
            assert set(buckets.keys()) == {'active', 'completed', 'partial', 'legacy'}
            ids = [r['session_id'] for r in buckets['completed']]
            assert 'sess_restored' in ids
            row = next(r for r in buckets['completed'] if r['session_id'] == 'sess_restored')
            assert row['restored'] is True
            assert row['questions_answered'] == 3
        finally:
            app_module.restored_analyses.clear()

    def test_stopped_rows_land_in_partial(self):
        import app as app_module
        app_module.restored_analyses.clear()
        app_module.restored_analyses['sess_stopped'] = {
            'pdf_filename': 'x.pdf', 'owner': 'u', 'mode': 'bid_spec',
            'status': 'interrupted', 'statistics': {},
        }
        try:
            buckets = app_module._snapshot_sessions_by_bucket()
            # Membership, not equality: these module dicts are shared across the
            # suite, so other tests' sessions can legitimately be present too.
            assert 'sess_stopped' in [r['session_id'] for r in buckets['partial']]
            assert 'sess_stopped' not in [r['session_id'] for r in buckets['completed']]
        finally:
            app_module.restored_analyses.clear()

    def test_a_live_session_always_wins_over_a_recovered_copy(self):
        import app as app_module
        app_module.restored_analyses.clear()
        app_module.completed_analyses['sess_dup'] = {
            'pdf_filename': 'live.pdf', 'owner': 'u', 'mode': 'bid_spec'}
        app_module.restored_analyses['sess_dup'] = {
            'pdf_filename': 'stale.pdf', 'owner': 'u', 'mode': 'bid_spec',
            'status': 'completed', 'statistics': {}}
        try:
            buckets = app_module._snapshot_sessions_by_bucket()
            rows = [r for r in buckets['completed'] if r['session_id'] == 'sess_dup']
            assert len(rows) == 1
            assert rows[0]['pdf_filename'] == 'live.pdf'
        finally:
            app_module.completed_analyses.pop('sess_dup', None)
            app_module.restored_analyses.clear()
