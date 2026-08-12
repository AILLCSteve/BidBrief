"""Every SQL statement the store can execute must be valid PostgreSQL.

WHY THIS FILE EXISTS
The rest of the persistence suite drives the Store through fake connections that
RECORD sql and hand back canned rows. That proves the control flow — no-op when
disabled, failure-safe when the database is down — but a fake will happily
"execute" a statement Postgres would reject, so the suite was structurally blind
to malformed SQL.

It stayed blind for six releases. The 2.5.3 timezone hotfix rewrote
`completed_at` inside the INSERT's COLUMN LIST as `_aware_utc(completed_at)` — a
Python call pasted into SQL. Postgres answered `syntax error at or near "("` for
every analysis, `_run()` swallowed it exactly as designed (a database problem
must never fail a finished analysis), and `bb_analyses` silently took zero rows
while every other table kept working.

The fix here is not the one-line SQL correction; it is making that class of
defect impossible to ship again. Each statement is parsed by pglast — bindings
for libpg_query, the REAL Postgres parser — so a typo anywhere in this module
fails a test instead of a production write.

Requires the dev dependency: pip install -r requirements-dev.txt
"""
from datetime import datetime, timezone

import pytest

pglast = pytest.importorskip(
    'pglast',
    reason='pglast (libpg_query) is required to validate SQL — pip install -r requirements-dev.txt')

from services.persistence import Store, _SCHEMA  # noqa: E402


class _Cursor:
    rowcount = 0

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class RecordingConnection:
    """Captures SQL and its params instead of running them."""

    def __init__(self, sink):
        self._sink = sink

    def execute(self, sql, params=None):
        self._sink.append((sql, params))
        return _Cursor()


class RecordingPool:
    def __init__(self, sink):
        self._sink = sink

    def connection(self):
        sink = self._sink

        class Ctx:
            def __enter__(self):
                return RecordingConnection(sink)

            def __exit__(self, *exc):
                return False

        return Ctx()


def _exercise_every_write_and_read():
    """Drive every public method, returning the SQL each one emitted.

    Named per method so a failure report says WHICH operation is broken rather
    than pointing at an anonymous statement.
    """
    statements = []
    store = Store()
    store.enabled = True
    store._pool = RecordingPool(statements)
    moment = datetime.now(timezone.utc)

    operations = {
        'save_analysis': lambda: store.save_analysis(
            'sess_1', owner='u', pdf_filename='f.pdf', mode='bid_spec',
            status='completed', snapshot={'result': {}}, completed_at=moment),
        'load_analysis': lambda: store.load_analysis('sess_1'),
        'count_analyses': lambda: store.count_analyses(),
        'list_analysis_index': lambda: store.list_analysis_index(limit=5),
        'mark_interrupted_analyses': lambda: store.mark_interrupted_analyses(),
        'delete_analysis': lambda: store.delete_analysis('sess_1'),
        'purge_expired': lambda: store.purge_expired(),
        'health': lambda: store.health(),
        'save_auth_session': lambda: store.save_auth_session(
            'tok', {'username': 'u', 'name': 'U', 'role': 'user', 'expires_at': moment}),
        'delete_auth_session': lambda: store.delete_auth_session('tok'),
        'delete_auth_sessions_for': lambda: store.delete_auth_sessions_for('u'),
        'load_auth_sessions': lambda: store.load_auth_sessions(),
        'save_beta_tester': lambda: store.save_beta_tester(
            {'username': 'beta-1', 'name': 'T', 'created_at': moment, 'last_seen': moment}),
        'delete_beta_tester': lambda: store.delete_beta_tester('beta-1'),
        'load_beta_testers': lambda: store.load_beta_testers(),
        'set_bonus_user_granted': lambda: store.set_bonus_user('a@b.c', True),
        'set_bonus_user_revoked': lambda: store.set_bonus_user('a@b.c', False),
        'load_bonus_users': lambda: store.load_bonus_users(),
        'save_smart_analysis': lambda: store.save_smart_analysis('sess_1', {'p': 1}),
        'load_smart_analysis': lambda: store.load_smart_analysis('sess_1'),
        'set_setting': lambda: store.set_setting('k', {'v': 1}),
        'get_setting': lambda: store.get_setting('k'),
        'delete_setting': lambda: store.delete_setting('k'),
    }

    emitted = {}
    for name, run in operations.items():
        before = len(statements)
        run()
        emitted[name] = statements[before:]
    return emitted


def _assert_parses(sql, label):
    """Parse one statement. psycopg's %s placeholders are not SQL, so they
    become NULL literals — a value's TYPE is irrelevant to syntax."""
    pglast.parse_sql(sql.replace('%s', 'NULL'))


EMITTED = _exercise_every_write_and_read()


def test_the_schema_bootstrap_is_valid_sql():
    _assert_parses(_SCHEMA, '_SCHEMA')


def test_every_operation_actually_emitted_sql():
    """Guards the guard: an operation that silently stopped touching the
    database would otherwise pass this file by emitting nothing at all."""
    silent = [name for name, sql in EMITTED.items() if not sql]
    assert not silent, f'these operations executed no SQL: {silent}'


@pytest.mark.parametrize('operation', sorted(EMITTED))
def test_operation_emits_valid_postgres(operation):
    for sql, _params in EMITTED[operation]:
        _assert_parses(sql, operation)


@pytest.mark.parametrize('operation', sorted(EMITTED))
def test_operation_survives_psycopg_placeholder_parsing(operation):
    """The layer pglast CANNOT see, caught in production by the E2E button:
    psycopg parses every % in a statement as a placeholder whenever params are
    passed. A literal LIKE pattern ('%probe%') inlined into such a statement
    dies with "only '%s', '%b', '%t' are allowed as placeholders, got '%p'" —
    valid SQL, invalid psycopg. Run each statement WITH its real params through
    psycopg's own query converter."""
    psycopg = pytest.importorskip('psycopg')
    from psycopg._queries import PostgresQuery
    from psycopg.adapt import Transformer
    for sql, params in EMITTED[operation]:
        try:
            PostgresQuery(Transformer()).convert(sql, params)
        except Exception as e:
            pytest.fail(f'{operation}: psycopg rejects the statement/params: {e}')


def test_save_analysis_column_list_holds_only_column_names():
    """The exact 2.5.3 regression, stated in the terms it failed in.

    A parse failure is the general net; this is the specific one, so the next
    reader sees what went wrong rather than only that something did.
    """
    sql = EMITTED['save_analysis'][0][0]
    columns = sql.split('(', 1)[1].split(')', 1)[0]
    for column in (c.strip() for c in columns.split(',')):
        assert column.isidentifier(), \
            f'{column!r} is not a column name — a Python call leaked into SQL'
