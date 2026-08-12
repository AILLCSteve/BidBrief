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
        # The failing OPERATION is named: an unattributed "syntax error at or
        # near (" in the admin panel is a diagnosis nobody can act on.
        assert store.last_error == 'list_analysis_index: neon is asleep'
        assert 'neon is asleep' in store.last_error

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


class TestTheStatusLineTellsTheTruthRightNow:
    """The 2.5.7 diagnosis: a constant failure LOOKED intermittent.

    Two separate reporting defects made the admin status line untrustworthy —
    it kept reporting an error long after the store recovered, and it certified
    "writable" from a table that was never the one failing.
    """

    def _pool(self, fail=False):
        class Conn:
            def execute(self, sql, params=None):
                if fail:
                    raise RuntimeError('boom')
                class Cur:
                    rowcount = 0
                    def fetchone(self): return (1,)
                    def fetchall(self): return []
                return Cur()
        class Pool:
            def connection(self):
                class Ctx:
                    def __enter__(s): return Conn()
                    def __exit__(s, *a): return False
                return Ctx()
        return Pool()

    def test_a_successful_call_clears_a_stale_error(self):
        """A sticky error reports one blip forever, so the panel contradicts a
        store that is healthy right now."""
        store = Store()
        store.enabled = True
        store._pool = self._pool(fail=True)
        store.count_analyses()
        assert store.last_error is not None

        store._pool = self._pool(fail=False)
        store.count_analyses()
        assert store.last_error is None, 'a recovered store must stop reporting an old error'

    def test_the_write_check_exercises_the_analysis_statement(self, monkeypatch):
        """A probe against bb_settings certified storage healthy for six
        releases while every bb_analyses write was failing. The probe must run
        the statement it speaks for."""
        store = Store()
        store.enabled = True
        store._pool = self._pool(fail=False)
        # The settings round-trip must SUCCEED, so the only thing under test is
        # whether a failing analysis write can still be reported as healthy.
        written = {}
        monkeypatch.setattr(store, 'set_setting',
                            lambda k, v: (written.__setitem__(k, v), True)[1])
        monkeypatch.setattr(store, 'get_setting',
                            lambda k, default=None: written.get(k, default))
        monkeypatch.setattr(store, '_analysis_write_probe', lambda: False)

        result = store.self_test()
        assert result['ok'] is False
        assert result['reason'] == 'analysis_write_failed', \
            'a broken analysis write must never be reported as healthy storage'

    def test_pool_stats_expose_what_the_error_text_cannot(self):
        """A PoolTimeout means either 'cannot connect' or 'pool starved', and
        the message is identical for both. These counters are what tell them
        apart, so they must reach the admin panel."""
        from services.persistence import Store
        store = Store()
        assert store.pool_stats() == {}, 'no pool means no stats, never a crash'

        class Pool:
            def get_stats(self):
                return {'pool_size': 4, 'pool_available': 0, 'requests_waiting': 6,
                        'connections_errors': 0, 'ignored': 'dropped'}
        store._pool = Pool()
        stats = store.pool_stats()
        # Starvation reads unmistakably: full pool, nothing free, queue building,
        # and zero connection errors.
        assert stats['pool_available'] == 0 and stats['requests_waiting'] == 6
        assert stats['connections_errors'] == 0
        assert 'pool_max' in stats, 'the ceiling is needed to see saturation'
        assert 'ignored' not in stats

    def test_a_broken_pool_never_crashes_the_status_endpoint(self):
        from services.persistence import Store
        store = Store()

        class Pool:
            def get_stats(self):
                raise RuntimeError('pool is gone')
        store._pool = Pool()
        assert store.pool_stats() == {}

    def test_the_probe_and_production_share_one_statement(self):
        """DRY here is a correctness property, not tidiness: a probe running a
        different INSERT than production proves nothing about production."""
        import inspect
        from services.persistence import _INSERT_ANALYSIS
        assert 'INSERT INTO bb_analyses' in _INSERT_ANALYSIS
        for method in (Store.save_analysis, Store._analysis_write_probe):
            assert '_INSERT_ANALYSIS' in inspect.getsource(method), \
                f'{method.__name__} must use the shared statement'


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

    def test_retention_keeps_everything_by_default(self, monkeypatch):
        """Deleting a user's analyses is the one irreversible thing this module
        can do, so it must never happen unless explicitly configured."""
        monkeypatch.delenv('BIDBRIEF_DB_RETENTION_DAYS', raising=False)
        assert retention_days() == 0
        monkeypatch.setenv('BIDBRIEF_DB_RETENTION_DAYS', '')
        assert retention_days() == 0
        monkeypatch.setenv('BIDBRIEF_DB_RETENTION_DAYS', 'nonsense')
        assert retention_days() == 0, 'a typo must not start deleting data'

    def test_retention_window_is_opt_in(self, monkeypatch):
        monkeypatch.setenv('BIDBRIEF_DB_RETENTION_DAYS', '30')
        assert retention_days() == 30


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


class TestRestoredSessionsAreAdminOnly:
    """Persisting analyses must not silently hand end users a history feature.

    Restored sessions are an admin capability by default — including the
    dangerous case of a pre-auth analysis stored with owner=None, which the
    ordinary ownership rule would treat as public.
    """

    @pytest.fixture
    def restored(self, monkeypatch):
        import app as app_module
        monkeypatch.delenv('BIDBRIEF_RESTORED_SESSIONS_ADMIN_ONLY', raising=False)
        app_module.restored_analyses['sess_old'] = {
            'pdf_filename': 'old.pdf', 'owner': 'alice', 'mode': 'bid_spec',
            'status': 'completed', 'statistics': {},
        }
        app_module.restored_analyses['sess_unowned'] = {
            'pdf_filename': 'anon.pdf', 'owner': None, 'mode': 'bid_spec',
            'status': 'completed', 'statistics': {},
        }
        yield app_module
        app_module.restored_analyses.clear()

    def _as(self, app_module, monkeypatch, username, role):
        monkeypatch.setattr(app_module, '_current_user_info', lambda: (username, role))

    def test_owner_is_denied_their_own_restored_analysis(self, restored, monkeypatch):
        self._as(restored, monkeypatch, 'alice', 'user')
        with restored.app.test_request_context('/'):
            assert restored._is_authorized_for_session('sess_old') is False

    def test_other_users_are_denied(self, restored, monkeypatch):
        self._as(restored, monkeypatch, 'bob', 'user')
        with restored.app.test_request_context('/'):
            assert restored._is_authorized_for_session('sess_old') is False

    def test_admin_is_allowed(self, restored, monkeypatch):
        self._as(restored, monkeypatch, 'admin@x', 'admin')
        with restored.app.test_request_context('/'):
            assert restored._is_authorized_for_session('sess_old') is True

    def test_unowned_restored_analysis_is_not_public(self, restored, monkeypatch):
        """Analyses created before /api/analyze required auth have owner=None.
        The plain ownership rule calls those public — the admin gate must win."""
        self._as(restored, monkeypatch, None, None)
        with restored.app.test_request_context('/'):
            assert restored._is_authorized_for_session('sess_unowned') is False

    def test_flag_can_open_it_to_owners(self, restored, monkeypatch):
        monkeypatch.setenv('BIDBRIEF_RESTORED_SESSIONS_ADMIN_ONLY', 'false')
        self._as(restored, monkeypatch, 'alice', 'user')
        with restored.app.test_request_context('/'):
            assert restored._is_authorized_for_session('sess_old') is True
        # ...but never to somebody else's analysis
        self._as(restored, monkeypatch, 'bob', 'user')
        with restored.app.test_request_context('/'):
            assert restored._is_authorized_for_session('sess_old') is False

    def test_live_sessions_are_unaffected_by_the_gate(self, restored, monkeypatch):
        """The gate applies ONLY to restored history. A user reading their own
        live analysis in this process must keep working exactly as before."""
        restored.completed_analyses['sess_live'] = {
            'pdf_filename': 'live.pdf', 'owner': 'alice', 'mode': 'bid_spec'}
        try:
            self._as(restored, monkeypatch, 'alice', 'user')
            with restored.app.test_request_context('/'):
                assert restored._is_authorized_for_session('sess_live') is True
        finally:
            restored.completed_analyses.pop('sess_live', None)


class TestHistoryAccumulatesForever:
    """Beta iterations must accumulate without ever losing a session."""

    def test_each_analysis_gets_its_own_row_key(self):
        """Rows are keyed by session_id, which /api/analyze mints per run as
        sess_<32 hex>. Two analyses can never collide onto one row, so the
        upsert can only ever update the SAME analysis, never overwrite another."""
        import re
        import app as app_module
        ids = {f'sess_{__import__("secrets").token_hex(16)}' for _ in range(200)}
        assert len(ids) == 200, 'session ids must be unique per analysis'
        for sid in list(ids)[:5]:
            assert re.fullmatch(r'sess_[0-9a-f]{32}', sid)
        assert 'secrets.token_hex(16)' in open(
            app_module.__file__.replace('.pyc', '.py'), encoding='utf-8').read()

    def test_index_limit_is_memory_only_and_generous(self, monkeypatch):
        from services.persistence import index_limit
        monkeypatch.delenv('BIDBRIEF_DB_INDEX_LIMIT', raising=False)
        assert index_limit() == 10000
        monkeypatch.setenv('BIDBRIEF_DB_INDEX_LIMIT', '50000')
        assert index_limit() == 50000
        monkeypatch.setenv('BIDBRIEF_DB_INDEX_LIMIT', 'nonsense')
        assert index_limit() == 10000

    def test_nothing_is_deleted_without_an_explicit_retention_window(self, monkeypatch):
        """purge_expired must not touch analyses under the default settings."""
        monkeypatch.delenv('BIDBRIEF_DB_RETENTION_DAYS', raising=False)
        executed = []

        class RecordingConn:
            def execute(self, sql, params=None):
                executed.append(' '.join(sql.split()))
                class Cur:
                    rowcount = 0
                return Cur()

        class Pool:
            def connection(self):
                class Ctx:
                    def __enter__(self_inner): return RecordingConn()
                    def __exit__(self_inner, *a): return False
                return Ctx()

        store = Store()
        store.enabled = True
        store._pool = Pool()
        store.purge_expired()

        assert not any('DELETE FROM bb_analyses' in s for s in executed), \
            'analyses must never be deleted by default'
        assert any('bb_auth_sessions' in s for s in executed), \
            'expired auth tokens are still cleared'


class TestAdminCanDeleteAnything:
    """Deleting an analysis is admin-only and wipes it everywhere at once."""

    @pytest.fixture
    def client(self):
        from app import app as flask_app
        flask_app.config['TESTING'] = True
        with flask_app.test_client() as c:
            yield c

    def _login(self, client, token, username, role):
        from app import active_sessions
        from datetime import timedelta
        active_sessions[token] = {
            'username': username, 'name': username, 'role': role,
            'is_beta': False, 'expires_at': datetime.now() + timedelta(hours=1),
        }
        client.set_cookie('bidbrief_auth', token)

    def test_delete_removes_from_memory_and_storage(self, client, monkeypatch):
        import app as app_module
        calls = []
        monkeypatch.setattr(app_module.persistence_store, 'delete_analysis',
                            lambda sid: (calls.append(sid), True)[1])
        self._login(client, 'tok-del-admin', 'admin@test.local', 'admin')

        app_module.completed_analyses['sess_del'] = {'pdf_filename': 'x.pdf', 'owner': 'u'}
        app_module.restored_analyses['sess_del'] = {'pdf_filename': 'x.pdf', 'owner': 'u'}
        app_module.smart_analysis_results['sess_del'] = object()
        try:
            resp = client.delete('/api/admin/analyses/sess_del')
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['success'] is True
            assert 'database' in body['removed_from']
            assert calls == ['sess_del']
            assert 'sess_del' not in app_module.completed_analyses
            assert 'sess_del' not in app_module.restored_analyses
            assert 'sess_del' not in app_module.smart_analysis_results
        finally:
            for d in (app_module.completed_analyses, app_module.restored_analyses,
                      app_module.smart_analysis_results):
                d.pop('sess_del', None)
            app_module.active_sessions.pop('tok-del-admin', None)

    def test_deleting_an_unknown_session_is_a_404(self, client, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module.persistence_store, 'delete_analysis', lambda sid: False)
        self._login(client, 'tok-del-admin', 'admin@test.local', 'admin')
        try:
            assert client.delete('/api/admin/analyses/sess_missing').status_code == 404
        finally:
            app_module.active_sessions.pop('tok-del-admin', None)

    def test_non_admins_cannot_delete(self, client):
        import app as app_module
        app_module.completed_analyses['sess_guard'] = {'pdf_filename': 'x.pdf', 'owner': 'bob'}
        self._login(client, 'tok-del-user', 'bob', 'user')
        try:
            assert client.delete('/api/admin/analyses/sess_guard').status_code in (302, 403)
            assert 'sess_guard' in app_module.completed_analyses, 'nothing may be deleted'
        finally:
            app_module.completed_analyses.pop('sess_guard', None)
            app_module.active_sessions.pop('tok-del-user', None)


class TestNoUserFacingExposure:
    """End users must not learn that history is stored, or that it can be
    restored. The gate is one half; the absence of any UI is the other."""

    def test_no_web_asset_mentions_storage_or_restoring(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / 'shared' / 'assets'
        banned = ('restored', 'persistence', 'database', 'neon')
        offenders = []
        for path in list(root.rglob('*.js')) + list(root.rglob('*.css')):
            if path.name == 'bb-admin.js':
                continue  # admin-only screen
            for line in path.read_text(encoding='utf-8').splitlines():
                stripped = line.strip()
                if stripped.startswith(('//', '/*', '*')):
                    continue  # comments are not shipped UI text
                low = line.lower()
                if any(word in low for word in banned):
                    offenders.append(f'{path.name}: {stripped[:80]}')
        assert not offenders, 'user-facing assets leak persistence wording: ' + str(offenders)


class TestTimezoneAwareSessionsCannotBreakAuth:
    """The 2.5.2 outage: enabling DATABASE_URL made every page return
    {"error":"An unexpected error occurred..."}.

    Postgres TIMESTAMPTZ round-trips as a timezone-AWARE datetime. Restored auth
    sessions carried one, check_auth_cookie compared it to a naive
    datetime.now(), and the TypeError reached the global exception handler — so
    one bad datetime 500'd every authenticated request on the site.
    """

    @pytest.fixture
    def client(self):
        from app import app
        app.config['TESTING'] = False
        with app.test_client() as c:
            yield c

    def _session(self, expires_at):
        from app import active_sessions
        active_sessions['tz-test'] = {
            'username': 'admin@test.local', 'name': 'Admin', 'role': 'admin',
            'is_beta': False, 'expires_at': expires_at,
        }

    def test_an_aware_expiry_no_longer_500s_the_site(self, client):
        from datetime import timedelta, timezone
        self._session(datetime.now(timezone.utc) + timedelta(hours=24))
        client.set_cookie('bidbrief_auth', 'tz-test')
        assert client.get('/').status_code == 200

    def test_an_expired_aware_session_is_still_rejected(self, client):
        from datetime import timedelta, timezone
        self._session(datetime.now(timezone.utc) - timedelta(hours=1))
        client.set_cookie('bidbrief_auth', 'tz-test')
        assert client.get('/').status_code in (301, 302), 'must bounce to login'

    def test_an_unreadable_expiry_fails_closed(self, client):
        """Anything unparseable is treated as expired. An auth check must never
        take the site down, whatever ends up in the field."""
        self._session('not-a-datetime')
        client.set_cookie('bidbrief_auth', 'tz-test')
        assert client.get('/').status_code in (301, 302)


class TestNothingTimezoneAwareEscapesTheStore:
    def test_naive_local_strips_awareness(self):
        from datetime import timezone
        from services.persistence import _naive_local
        aware = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
        assert _naive_local(aware).tzinfo is None
        naive = datetime(2026, 8, 2, 12, 0)
        assert _naive_local(naive) is naive, 'already-naive values pass through'
        assert _naive_local(None) is None

    def test_writes_store_explicit_utc(self):
        from services.persistence import _aware_utc
        assert _aware_utc(datetime(2026, 8, 2, 12, 0)).tzinfo is not None
        assert _aware_utc(None) is None

    def test_the_round_trip_preserves_the_instant(self):
        from services.persistence import _aware_utc, _naive_local
        moment = datetime(2026, 8, 2, 23, 0, 0)
        assert _naive_local(_aware_utc(moment)) == moment


class TestAFailedInitNeverLeaksAPool:
    """A ConnectionPool runs a background worker that keeps opening connections.
    Dropping the reference on a failed init leaked that worker AND its
    server-side connections; with a retry loop it leaked one pool per attempt
    until the database refused everything with
    'couldn't get a connection after N sec'.
    """

    def test_every_failed_pool_is_closed(self, monkeypatch):
        import psycopg_pool
        from services.persistence import Store

        created, closed = [], []
        real = psycopg_pool.ConnectionPool

        class Tracked(real):
            def __init__(self, *a, **k):
                created.append(self)
                super().__init__(*a, **k)

            def close(self, *a, **k):
                closed.append(self)
                return super().close(*a, **k)

        monkeypatch.setattr(psycopg_pool, 'ConnectionPool', Tracked)
        monkeypatch.setenv('DATABASE_URL',
                           'postgresql://nobody:nope@127.0.0.1:1/none?connect_timeout=1')

        store = Store()
        for _ in range(3):
            store._last_init_attempt = 0.0
            store.init()

        assert len(created) == 3
        assert len(closed) == len(created), 'a failed pool must always be closed'
        assert store.enabled is False

    def test_retry_is_throttled_so_it_cannot_hammer_the_database(self, monkeypatch):
        from services.persistence import Store
        monkeypatch.setenv('DATABASE_URL', 'postgresql://stub/db')
        store = Store()
        attempts = {'n': 0}

        def failing_init():
            attempts['n'] += 1
            return False

        store.init = failing_init
        store._last_init_attempt = 0.0
        assert store.load_analysis('x') is None
        assert attempts['n'] == 1
        assert store.load_analysis('x') is None
        assert attempts['n'] == 1, 'retry must be throttled, not per-call'

    def test_no_retry_at_all_without_a_database_url(self, monkeypatch):
        from services.persistence import Store
        monkeypatch.delenv('DATABASE_URL', raising=False)
        store = Store()
        attempts = {'n': 0}
        store.init = lambda: (attempts.__setitem__('n', attempts['n'] + 1), False)[1]
        assert store.load_analysis('x') is None
        assert attempts['n'] == 0
