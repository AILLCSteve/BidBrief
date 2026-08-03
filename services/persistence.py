"""
Durable storage for BidBrief server state (Neon / any Postgres).

WHY THIS EXISTS
Every dict in app.py lives in one gunicorn worker's memory, so a restart or a
Render deploy wipes logins, entitlements and every completed analysis. This
module gives that state a home without changing how the app behaves while it is
running: memory stays the hot path, Postgres is the durable mirror.

THE ONE THING THAT CANNOT BE PERSISTED
A completed analysis holds a live HotdogOrchestrator (an OpenAI client, cached
windows, accumulators). That object cannot be serialized. So instead of trying,
we persist the SNAPSHOT the API already derives from it — the legacy result
payload, statistics, key details and BestPrep data — all plain JSON. Everything
a user reads after the fact (results, Excel/CSV exports, Smart Analysis) is
served from that snapshot. Only second-pass and Deep RAG genuinely need the live
objects, and those refuse with a clear message on a restored session.

DESIGN RULES (do not break)
1. No DATABASE_URL -> every function here is a no-op and the app behaves exactly
   as it did before. This module may never be required for the app to run.
2. Every operation is failure-safe: a database problem logs and returns a
   default. A Neon hiccup must NEVER fail a 15-minute analysis or a login.
3. The snapshot is one JSONB blob, not a wide table. Payload shapes evolve every
   release; a blob means new fields need no migration.
4. Writes happen from analysis worker threads, so the pool must be thread-safe.

ENVIRONMENT
  DATABASE_URL                  Neon connection string (required to enable)
  BIDBRIEF_DB_RETENTION_DAYS    delete analyses older than N days. UNSET/0 =
                                keep forever (the default — nothing is ever
                                deleted unless you ask for it)
  BIDBRIEF_DB_POOL_MAX          max concurrent DATABASE CONNECTIONS, default 4.
                                This is a connection limit, NOT a storage limit:
                                it caps how many sockets the app opens to Neon
                                so it cannot exhaust the connection allowance.
                                It has no effect on how much data is stored.
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bb_analyses (
    session_id    TEXT PRIMARY KEY,
    owner         TEXT,
    pdf_filename  TEXT,
    mode          TEXT,
    status        TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    snapshot      JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS bb_analyses_owner_idx ON bb_analyses (owner);
CREATE INDEX IF NOT EXISTS bb_analyses_updated_idx ON bb_analyses (updated_at DESC);

CREATE TABLE IF NOT EXISTS bb_auth_sessions (
    token       TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    name        TEXT,
    role        TEXT,
    is_beta     BOOLEAN DEFAULT FALSE,
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS bb_auth_expires_idx ON bb_auth_sessions (expires_at);

CREATE TABLE IF NOT EXISTS bb_beta_testers (
    username    TEXT PRIMARY KEY,
    name        TEXT,
    created_at  TIMESTAMPTZ,
    last_seen   TIMESTAMPTZ,
    docs_used   INTEGER DEFAULT 0,
    doc_limit   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bb_bonus_users (
    email      TEXT PRIMARY KEY,
    granted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bb_smart_analyses (
    session_id   TEXT PRIMARY KEY,
    payload      JSONB NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bb_settings (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""


def database_url() -> str:
    return (os.environ.get('DATABASE_URL') or '').strip()


def retention_days() -> int:
    """Days to keep analyses. 0 (the default) means KEEP FOREVER.

    Deliberately opt-in: silently deleting a user's analyses is the one
    irreversible thing this module could do, so it does nothing unless asked.
    """
    raw = (os.environ.get('BIDBRIEF_DB_RETENTION_DAYS', '') or '').strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def index_limit() -> int:
    """How many analyses the boot index holds in memory (newest first).

    This is a MEMORY bound, never a storage bound: rows beyond it stay in the
    table untouched and are still loadable by session id. Metadata is tiny
    (~200 bytes/row), so the default comfortably covers many thousands of beta
    sessions; raise BIDBRIEF_DB_INDEX_LIMIT if the dashboard should list more.
    """
    try:
        return max(1, int(os.environ.get('BIDBRIEF_DB_INDEX_LIMIT', '10000')))
    except ValueError:
        return 10000


def _pool_max() -> int:
    try:
        return max(1, int(os.environ.get('BIDBRIEF_DB_POOL_MAX', '4')))
    except ValueError:
        return 4


def _json_default(value):
    """datetimes and stray objects must never break a snapshot write."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class Store:
    """
    The durable store. Construct once at import; call `init()` at boot.

    `enabled` is False when DATABASE_URL is unset or the driver/schema could not
    be brought up — in that state every method is a silent no-op so the app runs
    exactly as it did before this module existed.
    """

    def __init__(self):
        self._pool = None
        self._lock = threading.Lock()
        self.enabled = False
        self.last_error: Optional[str] = None

    # ---- lifecycle -----------------------------------------------------------

    def init(self) -> bool:
        """Open the pool and ensure the schema. Returns True when usable."""
        url = database_url()
        if not url:
            logger.info("💾 Persistence disabled (no DATABASE_URL) — state is in-memory only")
            return False

        try:
            from psycopg_pool import ConnectionPool
        except ImportError as e:
            self.last_error = f'psycopg not installed: {e}'
            logger.error("💾 DATABASE_URL is set but the Postgres driver is missing "
                         "(pip install 'psycopg[binary]' psycopg-pool) — running in-memory")
            return False

        try:
            # Neon suspends idle compute, so the first connection after a quiet
            # spell can be slow; check connections on checkout and let the pool
            # reopen dead ones rather than handing a broken socket to a request.
            self._pool = ConnectionPool(
                conninfo=url, min_size=0, max_size=_pool_max(),
                timeout=30, max_idle=120, num_workers=1, open=True,
                check=ConnectionPool.check_connection,
                kwargs={'autocommit': True},
            )
            with self._pool.connection() as conn:
                conn.execute(_SCHEMA)
            self.enabled = True
            self.last_error = None
            days = retention_days()
            logger.info("💾 Persistence ENABLED — session state survives restarts "
                        + (f"(retention {days}d)" if days > 0 else "(analyses kept indefinitely)"))
            return True
        except Exception as e:
            self.last_error = str(e)
            self._pool = None
            logger.error(f"💾 Could not initialize persistence ({e}) — running in-memory. "
                         "Analyses and logins will NOT survive a restart.")
            return False

    def close(self):
        if self._pool is not None:
            try:
                self._pool.close()
            except Exception:
                pass
        self._pool = None
        self.enabled = False

    # ---- plumbing ------------------------------------------------------------

    def _run(self, fn, default=None, label='db'):
        """Execute fn(conn), swallowing every failure. The app must survive a
        database outage — degraded persistence beats a failed analysis."""
        if not self.enabled or self._pool is None:
            return default
        try:
            with self._pool.connection() as conn:
                return fn(conn)
        except Exception as e:
            self.last_error = str(e)
            logger.warning(f"💾 {label} failed (non-fatal): {e}")
            return default

    def health(self) -> Dict[str, Any]:
        if not self.enabled:
            return {'enabled': False, 'error': self.last_error}
        ok = self._run(lambda c: c.execute('SELECT 1').fetchone() is not None,
                       default=False, label='health')
        return {'enabled': True, 'reachable': bool(ok), 'error': self.last_error}

    # ---- analyses ------------------------------------------------------------

    def save_analysis(self, session_id: str, *, owner: Optional[str], pdf_filename: str,
                      mode: str, status: str, snapshot: Dict[str, Any],
                      completed_at: Optional[datetime] = None) -> bool:
        """Upsert one analysis snapshot. Called at completion, stop and failure."""
        def _op(conn):
            conn.execute(
                """
                INSERT INTO bb_analyses
                    (session_id, owner, pdf_filename, mode, status, completed_at,
                     updated_at, snapshot)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    owner = EXCLUDED.owner,
                    pdf_filename = EXCLUDED.pdf_filename,
                    mode = EXCLUDED.mode,
                    status = EXCLUDED.status,
                    completed_at = EXCLUDED.completed_at,
                    updated_at = NOW(),
                    snapshot = EXCLUDED.snapshot
                """,
                (session_id, owner, pdf_filename, mode, status, completed_at,
                 json.dumps(snapshot, default=_json_default)),
            )
            return True
        return bool(self._run(_op, default=False, label='save_analysis'))

    def load_analysis(self, session_id: str) -> Optional[Dict[str, Any]]:
        """The full snapshot for one session, or None."""
        def _op(conn):
            row = conn.execute(
                'SELECT snapshot FROM bb_analyses WHERE session_id = %s',
                (session_id,)).fetchone()
            if not row:
                return None
            snapshot = row[0]
            return json.loads(snapshot) if isinstance(snapshot, str) else snapshot
        return self._run(_op, default=None, label='load_analysis')

    def count_analyses(self) -> int:
        """Total stored analyses — the truth about how much history exists,
        independent of how many the boot index loaded."""
        def _op(conn):
            row = conn.execute('SELECT COUNT(*) FROM bb_analyses').fetchone()
            return int(row[0]) if row else 0
        return int(self._run(_op, default=0, label='count_analyses') or 0)

    def list_analysis_index(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lightweight metadata for every stored analysis, newest first.

        Deliberately does NOT return snapshots: the admin dashboard and the
        ownership check only need metadata, and pulling every full payload into
        memory at boot would defeat the point of persisting them.

        The limit bounds only how many rows this index holds in memory — it
        NEVER bounds what is stored. Every analysis stays in the table; a row
        outside the index is still on disk and still loadable by session id.
        """
        if limit is None:
            limit = index_limit()

        def _op(conn):
            rows = conn.execute(
                """
                SELECT session_id, owner, pdf_filename, mode, status,
                       created_at, completed_at,
                       snapshot -> 'statistics' AS statistics
                FROM bb_analyses
                ORDER BY updated_at DESC
                LIMIT %s
                """, (limit,)).fetchall()
            out = []
            for r in rows:
                stats = r[7]
                if isinstance(stats, str):
                    try:
                        stats = json.loads(stats)
                    except ValueError:
                        stats = {}
                out.append({
                    'session_id': r[0], 'owner': r[1], 'pdf_filename': r[2],
                    'mode': r[3], 'status': r[4],
                    'created_at': r[5], 'completed_at': r[6],
                    'statistics': stats or {},
                })
            return out
        return self._run(_op, default=[], label='list_analysis_index') or []

    def mark_interrupted_analyses(self) -> int:
        """Flip rows left 'active' by a previous process to 'interrupted'.

        A restart kills the analysis thread, so an in-flight row can never
        resume. Saying so is far better than showing a run that will never move.
        """
        def _op(conn):
            cur = conn.execute(
                """
                UPDATE bb_analyses SET status = 'interrupted', updated_at = NOW()
                WHERE status IN ('active', 'running', 'initializing')
                """)
            return cur.rowcount or 0
        return int(self._run(_op, default=0, label='mark_interrupted') or 0)

    def delete_analysis(self, session_id: str) -> bool:
        def _op(conn):
            conn.execute('DELETE FROM bb_analyses WHERE session_id = %s', (session_id,))
            conn.execute('DELETE FROM bb_smart_analyses WHERE session_id = %s', (session_id,))
            return True
        return bool(self._run(_op, default=False, label='delete_analysis'))

    def purge_expired(self) -> int:
        """Housekeeping sweep — runs alongside the in-memory cleanup timer.

        Analyses are deleted ONLY when a retention window is explicitly
        configured. With the default (keep forever) this just clears auth tokens
        that have already expired, which are dead weight either way.
        """
        days = retention_days()

        def _op(conn):
            conn.execute('DELETE FROM bb_auth_sessions WHERE expires_at < NOW()')
            if days <= 0:
                return 0  # keep every analysis, forever
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cur = conn.execute('DELETE FROM bb_analyses WHERE updated_at < %s', (cutoff,))
            return cur.rowcount or 0
        return int(self._run(_op, default=0, label='purge_expired') or 0)

    # ---- auth sessions -------------------------------------------------------

    def save_auth_session(self, token: str, record: Dict[str, Any]) -> bool:
        def _op(conn):
            conn.execute(
                """
                INSERT INTO bb_auth_sessions (token, username, name, role, is_beta, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (token) DO UPDATE SET expires_at = EXCLUDED.expires_at
                """,
                (token, record.get('username'), record.get('name'), record.get('role'),
                 bool(record.get('is_beta')), record.get('expires_at')),
            )
            return True
        return bool(self._run(_op, default=False, label='save_auth_session'))

    def delete_auth_session(self, token: str) -> bool:
        def _op(conn):
            conn.execute('DELETE FROM bb_auth_sessions WHERE token = %s', (token,))
            return True
        return bool(self._run(_op, default=False, label='delete_auth_session'))

    def delete_auth_sessions_for(self, username: str) -> int:
        def _op(conn):
            cur = conn.execute('DELETE FROM bb_auth_sessions WHERE username = %s', (username,))
            return cur.rowcount or 0
        return int(self._run(_op, default=0, label='delete_auth_sessions_for') or 0)

    def load_auth_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Unexpired sessions, shaped exactly like app.active_sessions values."""
        def _op(conn):
            rows = conn.execute(
                """
                SELECT token, username, name, role, is_beta, expires_at
                FROM bb_auth_sessions WHERE expires_at > NOW()
                """).fetchall()
            return {r[0]: {'username': r[1], 'name': r[2], 'role': r[3],
                           'is_beta': bool(r[4]), 'expires_at': r[5]} for r in rows}
        return self._run(_op, default={}, label='load_auth_sessions') or {}

    # ---- beta testers --------------------------------------------------------

    def save_beta_tester(self, record: Dict[str, Any]) -> bool:
        def _op(conn):
            conn.execute(
                """
                INSERT INTO bb_beta_testers
                    (username, name, created_at, last_seen, docs_used, doc_limit)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE SET
                    name = EXCLUDED.name, last_seen = EXCLUDED.last_seen,
                    docs_used = EXCLUDED.docs_used, doc_limit = EXCLUDED.doc_limit
                """,
                (record.get('username'), record.get('name'), record.get('created_at'),
                 record.get('last_seen'), int(record.get('docs_used', 0) or 0),
                 int(record.get('doc_limit', 0) or 0)),
            )
            return True
        return bool(self._run(_op, default=False, label='save_beta_tester'))

    def delete_beta_tester(self, username: str) -> bool:
        def _op(conn):
            conn.execute('DELETE FROM bb_beta_testers WHERE username = %s', (username,))
            return True
        return bool(self._run(_op, default=False, label='delete_beta_tester'))

    def load_beta_testers(self) -> List[Dict[str, Any]]:
        def _op(conn):
            rows = conn.execute(
                """
                SELECT username, name, created_at, last_seen, docs_used, doc_limit
                FROM bb_beta_testers
                """).fetchall()
            return [{'username': r[0], 'name': r[1], 'created_at': r[2],
                     'last_seen': r[3], 'docs_used': r[4] or 0,
                     'doc_limit': r[5] or 0} for r in rows]
        return self._run(_op, default=[], label='load_beta_testers') or []

    # ---- bonus features ------------------------------------------------------

    def set_bonus_user(self, email: str, enabled: bool) -> bool:
        def _op(conn):
            if enabled:
                conn.execute(
                    'INSERT INTO bb_bonus_users (email) VALUES (%s) ON CONFLICT DO NOTHING',
                    (email,))
            else:
                conn.execute('DELETE FROM bb_bonus_users WHERE email = %s', (email,))
            return True
        return bool(self._run(_op, default=False, label='set_bonus_user'))

    def load_bonus_users(self) -> List[str]:
        def _op(conn):
            return [r[0] for r in conn.execute('SELECT email FROM bb_bonus_users').fetchall()]
        return self._run(_op, default=[], label='load_bonus_users') or []

    # ---- smart analyses ------------------------------------------------------

    def save_smart_analysis(self, session_id: str, payload: Dict[str, Any]) -> bool:
        def _op(conn):
            conn.execute(
                """
                INSERT INTO bb_smart_analyses (session_id, payload, generated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (session_id) DO UPDATE SET
                    payload = EXCLUDED.payload, generated_at = NOW()
                """,
                (session_id, json.dumps(payload, default=_json_default)))
            return True
        return bool(self._run(_op, default=False, label='save_smart_analysis'))

    def load_smart_analysis(self, session_id: str) -> Optional[Dict[str, Any]]:
        def _op(conn):
            row = conn.execute(
                'SELECT payload FROM bb_smart_analyses WHERE session_id = %s',
                (session_id,)).fetchone()
            if not row:
                return None
            payload = row[0]
            return json.loads(payload) if isinstance(payload, str) else payload
        return self._run(_op, default=None, label='load_smart_analysis')

    # ---- settings ------------------------------------------------------------

    def set_setting(self, key: str, value: Any) -> bool:
        def _op(conn):
            conn.execute(
                """
                INSERT INTO bb_settings (key, value, updated_at) VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                """, (key, json.dumps(value, default=_json_default)))
            return True
        return bool(self._run(_op, default=False, label='set_setting'))

    def get_setting(self, key: str, default: Any = None) -> Any:
        def _op(conn):
            row = conn.execute('SELECT value FROM bb_settings WHERE key = %s',
                               (key,)).fetchone()
            if not row:
                return default
            value = row[0]
            return json.loads(value) if isinstance(value, str) else value
        result = self._run(_op, default=default, label='get_setting')
        return default if result is None else result


store = Store()


# ---- one-command self check -------------------------------------------------
# Run with the real connection string to prove the whole path end to end:
#   DATABASE_URL='postgresql://...' python -m services.persistence
# It creates the schema, round-trips a record, then cleans up after itself.

def _self_check() -> int:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if not database_url():
        print('FAIL: DATABASE_URL is not set in this shell.')
        return 1

    print(f'Connecting... (retention {retention_days()} days)')
    if not store.init():
        print(f'FAIL: could not initialize — {store.last_error}')
        return 1
    print('OK  schema created / already present')

    sid = f'selfcheck_{int(datetime.now().timestamp())}'
    snapshot = {'result': {'sections': [], 'document_name': 'selfcheck.pdf'},
                'statistics': {'questions_answered': 1, 'total_questions': 1}}
    if not store.save_analysis(sid, owner='selfcheck', pdf_filename='selfcheck.pdf',
                               mode='bid_spec', status='completed', snapshot=snapshot,
                               completed_at=datetime.now(timezone.utc)):
        print('FAIL: could not write an analysis row')
        return 1
    print('OK  wrote an analysis snapshot')

    loaded = store.load_analysis(sid)
    if not loaded or loaded.get('statistics', {}).get('questions_answered') != 1:
        print(f'FAIL: round-trip mismatch — got {loaded!r}')
        return 1
    print('OK  read it back identically')

    index = store.list_analysis_index(limit=5)
    print(f'OK  index query returned {len(index)} row(s)')

    store.set_setting('selfcheck', {'ok': True})
    if (store.get_setting('selfcheck') or {}).get('ok') is not True:
        print('FAIL: settings round-trip failed')
        return 1
    print('OK  settings round-trip')

    store.delete_analysis(sid)
    print('OK  cleaned up the test row')
    print('\nPersistence is working. Set DATABASE_URL on Render and redeploy.')
    return 0


if __name__ == '__main__':
    raise SystemExit(_self_check())
