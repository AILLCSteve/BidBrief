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
import time
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

# The analysis upsert lives here rather than inline so save_analysis() and the
# write probe in self_test() cannot drift apart. A probe that exercises a
# DIFFERENT statement than production proves nothing about production: this one
# was reporting storage healthy (via a bb_settings round-trip) for six releases
# while every analysis write failed on malformed SQL.
_INSERT_ANALYSIS = """
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
    """Max concurrent connections. Default 10, matching gunicorn's thread count.

    It was 4 while gunicorn runs `threads = 10`, so six request threads could be
    waiting on a connection that the pool was not allowed to create — and the
    wait ends in the same PoolTimeout ("couldn't get a connection") that a
    genuine connection failure produces, with nothing to tell them apart.
    Sizing the pool to the threads that can ask for one removes that whole
    failure mode. Neon's pooled endpoint is PgBouncer; ten is nothing to it.
    """
    try:
        return max(1, int(os.environ.get('BIDBRIEF_DB_POOL_MAX', '10')))
    except ValueError:
        return 10


def _naive_local(value):
    """Postgres TIMESTAMPTZ round-trips as a timezone-AWARE datetime.

    The app compares expiries against a naive datetime.now(), and comparing the
    two raises TypeError — which, thrown inside the auth check, 500s every
    authenticated page. So nothing timezone-aware may escape this module: every
    datetime handed back to the app is converted to naive LOCAL time, matching
    what the rest of the process uses.
    """
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def _aware_utc(value):
    """Naive local datetimes are stored as explicit UTC, so the value in the
    database is correct no matter what timezone the host runs in."""
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.astimezone(timezone.utc)
    return value


def _json_default(value):
    """datetimes and stray objects must never break a snapshot write."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class _PoolErrorCapture(logging.Handler):
    """Keep the REAL reason connections are failing.

    psycopg_pool opens connections on a background worker. When that fails it
    logs the actual cause — "password authentication failed", "too many
    connections for role", "SSL SYSCALL error", "connection timeout expired" —
    to its OWN logger, and then hands the caller a bare
    PoolTimeout("couldn't get a connection after N sec").

    So the exception a caller sees never contains the diagnosis. That is why a
    week of "cannot write" produced no actionable error: the cause was being
    logged to a logger nobody listened to. This handler listens.
    """

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.last_message: Optional[str] = None

    def emit(self, record):
        try:
            self.last_message = record.getMessage()
        except Exception:
            pass


_pool_errors = _PoolErrorCapture()
logging.getLogger('psycopg_pool').addHandler(_pool_errors)


def endpoint_kind() -> str:
    """'pooled' | 'direct' | 'unset' — never the credentials.

    Neon exposes two hosts. The POOLED one (…-pooler.…) is PgBouncer and is
    built for many short-lived connections; the DIRECT one has a small hard
    connection cap and refuses new connections once it is reached, which looks
    exactly like this failure. Worth stating plainly in the admin panel, since
    pasting the wrong one is a two-character difference in the URL.
    """
    url = database_url()
    if not url:
        return 'unset'
    host = url.split('@')[-1].split('/')[0].lower()
    return 'pooled' if '-pooler.' in host else 'direct'


def _is_connection_problem(exc: Exception) -> bool:
    """True when we could not REACH the database, as opposed to bad SQL.

    Neon suspends idle compute, so the first request after a quiet spell has to
    wake it. That surfaces as a pool timeout ("couldn't get a connection after
    N sec") — a transient worth one retry, unlike a syntax error, which will
    fail identically forever and must not be retried.
    """
    if type(exc).__name__ in ('PoolTimeout', 'PoolClosed', 'OperationalError',
                              'InterfaceError'):
        return True
    return "couldn't get a connection" in str(exc).lower()


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
        self._init_lock = threading.RLock()
        self.enabled = False
        self.last_error: Optional[str] = None
        self._last_init_attempt = 0.0
        self._self_test_cache = None
        self._consecutive_failures = 0

    # ---- lifecycle -----------------------------------------------------------

    def _discard_pool(self):
        """Tear a pool down completely. Never just drop the reference."""
        pool, self._pool = self._pool, None
        self.enabled = False
        if pool is not None:
            try:
                pool.close()
            except Exception as e:
                logger.warning(f"💾 Pool close failed (continuing): {e}")

    def init(self) -> bool:
        """Open the pool and ensure the schema. Returns True when usable.

        Serialized: two threads retrying at once would build two pools and leak
        one of them.
        """
        with self._init_lock:
            return self._init_locked()

    def _init_locked(self) -> bool:
        # A previous attempt may have left a pool behind; never stack them.
        self._discard_pool()
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
                # timeout/connect_timeout at 20s, not 10: Neon suspends idle
                # compute and the request that wakes it pays the cold start.
                # min_size stays 0 deliberately — holding a connection open to
                # keep the pool warm would keep Neon awake and burn compute
                # hours, which is a worse problem than a slow first query.
                # num_workers=3, not 1: the workers are what actually OPEN
                # connections, so a single one serializes every new connection
                # behind the slowest connect_timeout. Ten request threads then
                # queue behind one cold start and all time out together.
                conninfo=url, min_size=0, max_size=_pool_max(),
                timeout=15, max_idle=120, num_workers=3, open=True,
                check=ConnectionPool.check_connection,
                # Only libpq CONNECTION parameters here. Neon's pooled endpoint
                # is PgBouncer, which rejects unknown startup parameters — an
                # `options='-c statement_timeout=...'` string makes every
                # connection fail and the pool time out ("couldn't get a
                # connection after 30.00 sec"). TCP keepalives achieve the same
                # protection against a dead half-open socket and are safe
                # through a pooler.
                kwargs={
                    'autocommit': True,
                    'connect_timeout': 15,
                    'keepalives': 1,
                    'keepalives_idle': 30,
                    'keepalives_interval': 10,
                    'keepalives_count': 3,
                },
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
            # Same blindness as _run: a PoolTimeout here says nothing about WHY.
            # The pool logged the real cause; carry it.
            self.last_error = str(e)
            if _is_connection_problem(e) and _pool_errors.last_message:
                self.last_error += f' [pool: {_pool_errors.last_message}]'
            # CLOSE the pool before dropping it. A ConnectionPool runs a
            # background worker that keeps opening connections; discarding the
            # reference leaks that thread AND its server-side connections. With
            # a retry loop that leaks a whole pool per attempt, which exhausts
            # the database's connection allowance and turns a transient blip
            # into a permanent "couldn't get a connection" failure.
            self._discard_pool()
            logger.error(f"💾 Could not initialize persistence ({e}) — running in-memory. "
                         "Analyses and logins will NOT survive a restart.")
            return False

    def close(self):
        self._discard_pool()

    # ---- plumbing ------------------------------------------------------------

    def _try_reinit(self) -> bool:
        """Re-attempt startup if the boot attempt failed, at most once a minute.

        Neon suspends idle compute, so a deploy can land while the database is
        still waking and init() fails. Without this the store would stay dead
        for the whole life of the process — persistence silently off until
        somebody happened to restart it again.
        """
        if not database_url():
            return False
        now = time.monotonic()
        with self._lock:
            if self.enabled:
                return True
            if now - self._last_init_attempt < 60:
                return False
            self._last_init_attempt = now
        logger.info("💾 Retrying durable storage startup...")
        return self.init()

    def _run(self, fn, default=None, label='db'):
        """Execute fn(conn), swallowing every failure. The app must survive a
        database outage — degraded persistence beats a failed analysis."""
        if not self.enabled or self._pool is None:
            if not self._try_reinit():
                return default
        # Two attempts: Neon suspends idle compute, and the request that wakes
        # it can lose the race. A second try turns that into a slow success
        # instead of a silent no-op. Only ever retried for CONNECTION problems —
        # bad SQL would fail identically forever.
        attempts = 2
        for attempt in range(1, attempts + 1):
            try:
                with self._pool.connection() as conn:
                    result = fn(conn)
            except Exception as e:
                if attempt < attempts and _is_connection_problem(e):
                    logger.info(f"💾 {label}: {e} — retry {attempt}/{attempts - 1} "
                                "(the database may be waking)")
                    time.sleep(1.5 * attempt)
                    continue
                # Name the operation, and attach the REAL cause. A bare
                # "couldn't get a connection after 10.00 sec" is the pool's
                # generic timeout; the actual reason was logged by psycopg_pool
                # and captured above. Without it this message is undiagnosable.
                detail = f'{label}: {e}'
                if _is_connection_problem(e) and _pool_errors.last_message:
                    detail += f' [pool: {_pool_errors.last_message}]'
                self.last_error = detail
                self._consecutive_failures += 1
                logger.warning(f"💾 {detail} (non-fatal)")
                if self._consecutive_failures >= 3:
                    # A pool that keeps refusing never recovers on its own:
                    # nothing else clears `enabled`, so _try_reinit() can never
                    # fire and storage stays dead until the next deploy. Drop it
                    # and let the next call build a fresh one.
                    logger.warning("💾 Discarding the connection pool after "
                                   f"{self._consecutive_failures} consecutive failures "
                                   "— the next call will rebuild it")
                    self._discard_pool()
                    self._consecutive_failures = 0
                    self._last_init_attempt = 0.0  # allow an immediate rebuild
                return default
            # Clear on success. A sticky last_error reports one transient blip
            # forever, so the admin status line contradicts a store that is
            # healthy right now — which is how a permanent failure came to look
            # intermittent.
            self.last_error = None
            self._consecutive_failures = 0
            return result
        return default

    def pool_stats(self) -> Dict[str, Any]:
        """The pool's own counters — the only way to tell WHY a checkout failed.

        A PoolTimeout has two completely different causes that read identically
        in the error text:
          * connections cannot be ESTABLISHED — `connections_errors` climbs and
            psycopg_pool logs the real reason (captured in last_error).
          * the pool is STARVED — `pool_size` is at max, `pool_available` is 0
            and `requests_waiting` is high, with no connection errors at all.
        Without these numbers the two are indistinguishable, which is how this
        went a week without a diagnosis.
        """
        pool = self._pool
        if pool is None:
            return {}
        try:
            raw = pool.get_stats()
        except Exception:
            return {}
        keep = ('pool_size', 'pool_available', 'requests_waiting', 'requests_errors',
                'connections_num', 'connections_errors', 'connections_lost',
                'requests_num', 'requests_queued')
        stats = {k: raw[k] for k in keep if k in raw}
        stats['pool_max'] = _pool_max()
        return stats

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
                _INSERT_ANALYSIS,
                (session_id, owner, pdf_filename, mode, status, _aware_utc(completed_at),
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

    def _analysis_write_probe(self) -> bool:
        """Run the REAL analysis upsert, then roll it back.

        Rolled back, so it can never pollute history — but the statement it
        exercises is byte-for-byte the one an analysis writes, which is the only
        way this check can speak for that write path.
        """
        def _op(conn):
            import psycopg
            with conn.transaction():
                conn.execute(_INSERT_ANALYSIS, (
                    '__write_probe__', None, 'probe.pdf', 'bid_spec', 'probe',
                    _aware_utc(datetime.now(timezone.utc)),
                    json.dumps({'probe': True})))
                raise psycopg.Rollback  # swallowed by the block; nothing commits
            return True
        return bool(self._run(_op, default=False, label='analysis_write_probe'))

    def self_test(self) -> Dict[str, Any]:
        """Prove the store can actually WRITE and read back, not merely connect.

        'Connected' is not the same as 'working': a wrong database, a read-only
        role or a failed schema create all still connect. Neither is "some table
        works" — this check used to round-trip only a settings row, and settings
        kept working for six releases while every bb_analyses write failed on
        malformed SQL, so the dashboard reported storage healthy the whole time
        history was being silently dropped. It now exercises the analysis write
        as well, because that is the write anyone actually cares about.
        """
        if not self.enabled:
            return {'ok': False, 'reason': 'disabled', 'error': self.last_error}
        # Cache briefly: the admin dashboard calls this on every load, and a
        # write per page view is needless traffic against the connection budget.
        now = time.monotonic()
        cached = self._self_test_cache
        if cached and now - cached[0] < 30:
            return cached[1]
        key = '__write_check__'
        stamp = datetime.now(timezone.utc).isoformat()
        if not self.set_setting(key, {'at': stamp}):
            return {'ok': False, 'reason': 'write_failed', 'error': self.last_error}
        value = self.get_setting(key) or {}
        if value.get('at') != stamp:
            return {'ok': False, 'reason': 'readback_mismatch', 'error': self.last_error}
        if not self._analysis_write_probe():
            return {'ok': False, 'reason': 'analysis_write_failed',
                    'error': self.last_error}
        result = {'ok': True}
        self._self_test_cache = (now, result)
        return result

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
                    'created_at': _naive_local(r[5]),
                    'completed_at': _naive_local(r[6]),
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
                 bool(record.get('is_beta')), _aware_utc(record.get('expires_at'))),
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
                           'is_beta': bool(r[4]), 'expires_at': _naive_local(r[5])}
                    for r in rows}
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
                (record.get('username'), record.get('name'),
                 _aware_utc(record.get('created_at')), _aware_utc(record.get('last_seen')),
                 int(record.get('docs_used', 0) or 0),
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
            return [{'username': r[0], 'name': r[1],
                     'created_at': _naive_local(r[2]), 'last_seen': _naive_local(r[3]),
                     'docs_used': r[4] or 0, 'doc_limit': r[5] or 0} for r in rows]
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

    def delete_setting(self, key: str) -> bool:
        def _op(conn):
            conn.execute('DELETE FROM bb_settings WHERE key = %s', (key,))
            return True
        return bool(self._run(_op, default=False, label='delete_setting'))

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
    store.delete_setting('selfcheck')  # leave no trace of the probe
    print('OK  settings round-trip')

    store.delete_analysis(sid)
    print('OK  cleaned up the test rows')

    stored = store.count_analyses()
    print(f'OK  {stored} analysis(es) currently stored')

    # Shut the pool down explicitly: without this the worker threads outlive the
    # script and psycopg prints "couldn't stop thread" warnings at exit.
    store.close()
    print('OK  connections closed cleanly')

    print('\nPersistence is working. With DATABASE_URL set on Render, session '
          'history survives restarts and accumulates indefinitely.')
    return 0


if __name__ == '__main__':
    raise SystemExit(_self_check())
