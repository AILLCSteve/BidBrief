"""
Free Beta Testing access for BidBrief.

Two things live here, both in memory, both owned by this module:

  1. A switch. Admins flip free beta access on and off at runtime; the boot
     value comes from the BETA_LOGIN_ENABLED env var so a Render deploy (which
     wipes every in-memory dict in this app) restores your intended state
     instead of silently hiding the beta button.

  2. A registry of ephemeral testers. Each click of "Try BidBrief Free" mints
     its OWN identity — beta-<hex> — rather than sharing one account. That is a
     security requirement, not a nicety: analyses are owner-scoped by username
     (`_is_authorized_for_session` in app.py), so a shared beta account would
     let any tester open any other tester's results with just a session id.

Each tester carries a document quota (default 5). The quota is consumed when an
analysis actually starts, never at upload time, so a rejected or malformed
request costs the tester nothing.

Env:
  BETA_LOGIN_ENABLED   '1'/'true'/'yes'/'on' to start enabled (default: off)
  BETA_DOC_LIMIT       documents each new tester may process (default: 5)

Thread safety: analyses run on background threads and admins poll concurrently,
so every mutation takes the module lock. Callers get plain dict copies — never
the live records — so no caller can mutate the registry by accident.
"""

import os
import secrets
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple

DEFAULT_DOC_LIMIT = 5
USERNAME_PREFIX = 'beta-'

_TRUTHY = {'1', 'true', 'yes', 'on'}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _env_int(name: str, default: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def is_beta_username(username: Optional[str]) -> bool:
    """True for identities minted by this module. Cheap enough to call per request."""
    return bool(username) and str(username).startswith(USERNAME_PREFIX)


class BetaAccess:
    """The free-beta switch plus the ephemeral tester registry."""

    def __init__(self, enabled: Optional[bool] = None, doc_limit: Optional[int] = None):
        self._lock = threading.Lock()
        self._env_enabled = _env_flag('BETA_LOGIN_ENABLED') if enabled is None else bool(enabled)
        self._enabled = self._env_enabled
        self._default_doc_limit = (
            _env_int('BETA_DOC_LIMIT', DEFAULT_DOC_LIMIT) if doc_limit is None else int(doc_limit)
        )
        self._testers: Dict[str, dict] = {}

    # ---- the switch ------------------------------------------------------

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> bool:
        with self._lock:
            self._enabled = bool(enabled)
            return self._enabled

    @property
    def default_doc_limit(self) -> int:
        with self._lock:
            return self._default_doc_limit

    # ---- the registry ----------------------------------------------------

    def mint(self, doc_limit: Optional[int] = None) -> dict:
        """Create a brand-new ephemeral tester and return a copy of its record."""
        now = datetime.now()
        with self._lock:
            username = USERNAME_PREFIX + secrets.token_hex(5)
            while username in self._testers:  # collision is ~impossible; correctness is cheap
                username = USERNAME_PREFIX + secrets.token_hex(5)
            record = {
                'username': username,
                'name': 'Beta Tester ' + username[len(USERNAME_PREFIX):][:4].upper(),
                'created_at': now,
                'last_seen': now,
                'docs_used': 0,
                'doc_limit': int(doc_limit) if doc_limit else self._default_doc_limit,
            }
            self._testers[username] = record
            return dict(record)

    def get(self, username: str) -> Optional[dict]:
        with self._lock:
            record = self._testers.get(username)
            return dict(record) if record else None

    def all(self) -> List[dict]:
        """Every tester, newest first."""
        with self._lock:
            records = [dict(r) for r in self._testers.values()]
        records.sort(key=lambda r: r['created_at'], reverse=True)
        return records

    def touch(self, username: str) -> None:
        """Record activity. Silent for unknown users so callers need no guard."""
        with self._lock:
            record = self._testers.get(username)
            if record:
                record['last_seen'] = datetime.now()

    def remaining(self, username: str) -> Optional[int]:
        """Documents left for a tester, or None if this isn't a known tester."""
        with self._lock:
            record = self._testers.get(username)
            if not record:
                return None
            return max(0, record['doc_limit'] - record['docs_used'])

    def consume_document(self, username: str) -> Tuple[bool, int]:
        """
        Claim one document against a tester's quota.

        Returns (allowed, remaining_after). Unknown users are allowed through
        untouched — they are ordinary accounts, not beta testers, and this
        module must never gate them.
        """
        with self._lock:
            record = self._testers.get(username)
            if not record:
                return True, -1
            if record['docs_used'] >= record['doc_limit']:
                return False, 0
            record['docs_used'] += 1
            record['last_seen'] = datetime.now()
            return True, max(0, record['doc_limit'] - record['docs_used'])

    def set_doc_limit(self, username: str, doc_limit: int) -> Optional[dict]:
        """Set an absolute new quota (the 'extend their trial' control)."""
        with self._lock:
            record = self._testers.get(username)
            if not record:
                return None
            record['doc_limit'] = max(0, int(doc_limit))
            return dict(record)

    def grant_documents(self, username: str, extra: int) -> Optional[dict]:
        """Add headroom on top of the current quota."""
        with self._lock:
            record = self._testers.get(username)
            if not record:
                return None
            record['doc_limit'] = max(0, record['doc_limit'] + int(extra))
            return dict(record)

    def reset_usage(self, username: str) -> Optional[dict]:
        """Zero the counter — a full fresh trial at the current quota."""
        with self._lock:
            record = self._testers.get(username)
            if not record:
                return None
            record['docs_used'] = 0
            return dict(record)

    def delete(self, username: str) -> Optional[dict]:
        """Remove a tester. Revoking their live sessions is the caller's job."""
        with self._lock:
            record = self._testers.pop(username, None)
            return dict(record) if record else None


def serialize_tester(record: dict, sessions: Optional[List[dict]] = None) -> dict:
    """Shape one tester for the admin API. Datetimes become ISO strings."""
    used = record.get('docs_used', 0)
    limit = record.get('doc_limit', 0)
    return {
        'username': record.get('username', ''),
        'name': record.get('name', ''),
        'created_at': record['created_at'].isoformat() if record.get('created_at') else None,
        'last_seen': record['last_seen'].isoformat() if record.get('last_seen') else None,
        'docs_used': used,
        'doc_limit': limit,
        'docs_remaining': max(0, limit - used),
        'exhausted': used >= limit,
        'sessions': sessions or [],
    }
