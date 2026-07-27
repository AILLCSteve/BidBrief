"""
Free Beta Testing tests.

Hard rules verified here:
  1. The beta button is invisible and the login route closed while the switch is off.
  2. Every beta login mints its OWN identity — never a shared account.
  3. A beta tester is an ordinary user: no admin, no premium, no High Power.
  4. The document quota is enforced, is only spent on a valid request, and is
     atomic under concurrency.
  5. Only admins can see or change beta access, testers and quotas.
  6. The admin dashboard shows each tester's analyses in the same shape
     /api/admin/sessions serves (one formatter, one contract).
"""
import threading
from datetime import datetime, timedelta

import pytest

from app import (
    AUTHORIZED_USERS,
    active_analyses,
    active_sessions,
    app,
    beta_access,
    bonus_feature_users,
)
from services.beta_access import BetaAccess, is_beta_username


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_state():
    beta_access.set_enabled(False)
    for record in beta_access.all():
        beta_access.delete(record['username'])
    bonus_feature_users.clear()
    AUTHORIZED_USERS.setdefault('admin@test.local', {
        'password_hash': 'x', 'name': 'Admin', 'role': 'admin'})
    AUTHORIZED_USERS.setdefault('user@test.local', {
        'password_hash': 'x', 'name': 'User', 'role': 'user'})
    yield
    beta_access.set_enabled(False)
    for record in beta_access.all():
        beta_access.delete(record['username'])
    for token in ('tok-admin', 'tok-user'):
        active_sessions.pop(token, None)


def _login(client, token, username, role, is_beta=False):
    active_sessions[token] = {
        'username': username,
        'name': username,
        'role': role,
        'is_beta': is_beta,
        'expires_at': datetime.now() + timedelta(hours=1),
    }
    client.set_cookie('bidbrief_auth', token)


def _start_beta_session(client):
    """Take the real beta login path and return the tester's username."""
    beta_access.set_enabled(True)
    resp = client.post('/auth/beta-login')
    assert resp.status_code == 200
    return resp.get_json()['username']


# ---- the switch ------------------------------------------------------------

def test_status_reports_the_switch(client):
    data = client.get('/api/beta/status').get_json()
    assert data['enabled'] is False

    beta_access.set_enabled(True)
    data = client.get('/api/beta/status').get_json()
    assert data['enabled'] is True
    assert data['doc_limit'] >= 1


def test_beta_login_closed_while_disabled(client):
    resp = client.post('/auth/beta-login')
    assert resp.status_code == 403
    assert resp.get_json()['success'] is False
    assert not beta_access.all(), 'a denied login must not mint a tester'


def test_status_is_public(client):
    """The login page is pre-auth, so this endpoint must answer without a cookie."""
    assert client.get('/api/beta/status').status_code == 200


# ---- identity --------------------------------------------------------------

def test_each_beta_login_mints_its_own_identity(client):
    beta_access.set_enabled(True)
    first = client.post('/auth/beta-login').get_json()['username']
    client.delete_cookie('bidbrief_auth')
    second = client.post('/auth/beta-login').get_json()['username']

    assert first != second, (
        'a shared beta account would let any tester read any other tester\'s '
        'results — analyses are owner-scoped by username'
    )
    assert is_beta_username(first) and is_beta_username(second)
    assert len(beta_access.all()) == 2


def test_beta_login_sets_the_auth_cookie(client):
    beta_access.set_enabled(True)
    resp = client.post('/auth/beta-login')
    cookie = resp.headers.get('Set-Cookie', '')
    assert 'bidbrief_auth=' in cookie
    assert 'HttpOnly' in cookie
    # The session works immediately.
    assert client.get('/api/user/info').status_code == 200


def test_beta_tester_is_an_ordinary_user(client):
    _start_beta_session(client)
    info = client.get('/api/user/info').get_json()

    assert info['is_beta'] is True
    assert info['is_admin'] is False
    assert info['premium'] is False
    assert info['beta']['docs_remaining'] == info['beta']['doc_limit']

    # No admin surface, and no High Power.
    assert client.get('/api/admin/sessions').status_code == 403
    assert client.get('/api/admin/beta').status_code == 403
    resp = client.post('/api/analyze', json={'upload_id': 'nope', 'high_power': True})
    assert resp.status_code == 403


# ---- the document quota ----------------------------------------------------

def test_quota_is_enforced_at_the_limit(client):
    username = _start_beta_session(client)
    limit = beta_access.get(username)['doc_limit']

    # Spend the quota directly — no real analysis needed to prove the wall.
    for _ in range(limit):
        allowed, _ = beta_access.consume_document(username)
        assert allowed

    resp = client.post('/api/analyze', json={'upload_id': 'nope'})
    assert resp.status_code == 402
    body = resp.get_json()
    assert body['beta_quota_exhausted'] is True
    assert body['docs_remaining'] == 0
    assert 'subscribe' in body['error'].lower()


def test_invalid_request_never_costs_a_document(client):
    """A bogus upload id must fail without burning one of the free documents."""
    username = _start_beta_session(client)
    before = beta_access.get(username)['docs_used']

    assert client.post('/api/analyze', json={'upload_id': 'nope'}).status_code == 404
    assert beta_access.get(username)['docs_used'] == before


def test_non_beta_users_are_never_gated():
    """consume_document must wave through anyone it does not know."""
    access = BetaAccess(enabled=True, doc_limit=1)
    allowed, remaining = access.consume_document('user@test.local')
    assert allowed is True
    assert remaining == -1


def test_quota_is_atomic_under_concurrency():
    """Analyses start on background threads: two concurrent starts must never
    both claim the last free document."""
    access = BetaAccess(enabled=True, doc_limit=50)
    tester = access.mint()
    granted = []
    barrier = threading.Barrier(10)

    def claim():
        barrier.wait()
        for _ in range(10):
            allowed, _ = access.consume_document(tester['username'])
            if allowed:
                granted.append(1)

    threads = [threading.Thread(target=claim) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(granted) == 50
    assert access.get(tester['username'])['docs_used'] == 50


# ---- admin control ---------------------------------------------------------

def test_beta_admin_routes_are_admin_only(client):
    _login(client, 'tok-user', 'user@test.local', 'user')
    bonus_feature_users.add('user@test.local')  # premium must not help

    assert client.get('/api/admin/beta').status_code == 403
    assert client.post('/api/admin/beta', json={'enabled': True}).status_code == 403
    assert client.post('/api/admin/beta/testers/beta-abc', json={'reset': True}).status_code == 403
    assert client.delete('/api/admin/beta/testers/beta-abc').status_code == 403


def test_admin_toggles_access(client):
    _login(client, 'tok-admin', 'admin@test.local', 'admin')

    assert client.post('/api/admin/beta', json={'enabled': True}).get_json()['enabled'] is True
    assert beta_access.enabled is True
    assert client.get('/api/beta/status').get_json()['enabled'] is True

    assert client.post('/api/admin/beta', json={'enabled': False}).get_json()['enabled'] is False
    assert beta_access.enabled is False

    # Missing field is a 400, not a silent disable.
    assert client.post('/api/admin/beta', json={}).status_code == 400


def test_admin_sees_testers_and_their_quota(client):
    username = _start_beta_session(client)
    beta_access.consume_document(username)

    _login(client, 'tok-admin', 'admin@test.local', 'admin')
    data = client.get('/api/admin/beta').get_json()

    tester = next(t for t in data['testers'] if t['username'] == username)
    assert tester['docs_used'] == 1
    assert tester['docs_remaining'] == tester['doc_limit'] - 1
    assert tester['exhausted'] is False
    assert tester['signed_in'] is True
    assert data['summary']['tester_count'] == 1
    assert data['summary']['docs_used'] == 1


def test_admin_extends_a_trial(client):
    username = _start_beta_session(client)
    limit = beta_access.get(username)['doc_limit']
    for _ in range(limit):
        beta_access.consume_document(username)

    _login(client, 'tok-admin', 'admin@test.local', 'admin')

    # Grant more headroom.
    resp = client.post(f'/api/admin/beta/testers/{username}', json={'grant': 5})
    assert resp.status_code == 200
    assert resp.get_json()['tester']['doc_limit'] == limit + 5
    assert beta_access.remaining(username) == 5

    # Or reset usage for a clean trial.
    resp = client.post(f'/api/admin/beta/testers/{username}', json={'reset': True})
    assert resp.status_code == 200
    assert resp.get_json()['tester']['docs_used'] == 0

    # Or set the quota outright.
    resp = client.post(f'/api/admin/beta/testers/{username}', json={'doc_limit': 2})
    assert resp.get_json()['tester']['doc_limit'] == 2


def test_extend_rejects_nonsense(client):
    username = _start_beta_session(client)
    _login(client, 'tok-admin', 'admin@test.local', 'admin')

    assert client.post(f'/api/admin/beta/testers/{username}', json={}).status_code == 400
    assert client.post(f'/api/admin/beta/testers/{username}',
                       json={'grant': 'lots'}).status_code == 400
    assert client.post(f'/api/admin/beta/testers/{username}',
                       json={'doc_limit': -1}).status_code == 400
    assert client.post('/api/admin/beta/testers/beta-ghost',
                       json={'reset': True}).status_code == 404


def test_admin_deletes_a_tester_and_signs_them_out(client):
    username = _start_beta_session(client)
    assert client.get('/api/user/info').status_code == 200  # the tester is live

    _login(client, 'tok-admin', 'admin@test.local', 'admin')
    resp = client.delete(f'/api/admin/beta/testers/{username}')
    assert resp.status_code == 200
    assert resp.get_json()['sessions_revoked'] == 1
    assert beta_access.get(username) is None

    # Their token is gone from active_sessions.
    assert not [s for s in active_sessions.values() if s.get('username') == username]
    assert client.delete(f'/api/admin/beta/testers/{username}').status_code == 404


def test_deleted_tester_cannot_start_an_analysis(client):
    username = _start_beta_session(client)
    tester_cookie = client.get_cookie('bidbrief_auth')

    _login(client, 'tok-admin', 'admin@test.local', 'admin')
    client.delete(f'/api/admin/beta/testers/{username}')

    # Back to the tester's revoked cookie.
    client.set_cookie('bidbrief_auth', tester_cookie.value)
    assert client.post('/api/analyze', json={'upload_id': 'nope'}).status_code == 401


def test_admin_sees_a_testers_sessions(client):
    """Sessions must be observable per tester, in the same shape the sessions
    dashboard (and the iOS AdminSessionInfo decoder) already reads."""
    username = _start_beta_session(client)
    active_analyses['sess_betatest'] = {
        'orchestrator': None,
        'pdf_filename': 'beta-spec.pdf',
        'mode': 'bid_spec',
        'owner': username,
        'status': 'initializing',
    }
    try:
        _login(client, 'tok-admin', 'admin@test.local', 'admin')
        data = client.get('/api/admin/beta').get_json()
        tester = next(t for t in data['testers'] if t['username'] == username)

        assert len(tester['sessions']) == 1
        row = tester['sessions'][0]
        assert row['session_id'] == 'sess_betatest'
        assert row['pdf_filename'] == 'beta-spec.pdf'
        assert row['owner'] == username
        assert row['status'] == 'active'
        assert row['pdf_path'] == '[REDACTED]', 'never leak server file paths'
    finally:
        active_analyses.pop('sess_betatest', None)


def test_admin_sessions_serves_the_ios_contract(client):
    """Regression guard for the iOS admin dashboard: every key AdminSessionInfo
    decodes must be present, and buckets must stay named active/completed/
    partial/legacy."""
    active_analyses['sess_contract'] = {
        'orchestrator': None,
        'pdf_filename': 'contract.pdf',
        'mode': 'bestprep',
        'owner': 'user@test.local',
        'status': 'initializing',
    }
    try:
        _login(client, 'tok-admin', 'admin@test.local', 'admin')
        data = client.get('/api/admin/sessions').get_json()

        assert set(data['sessions'].keys()) == {'active', 'completed', 'partial', 'legacy'}
        row = next(r for r in data['sessions']['active'] if r['session_id'] == 'sess_contract')
        for key in ('session_id', 'status', 'pdf_filename', 'owner', 'mode'):
            assert key in row, f'iOS AdminSessionInfo decodes {key}'
        assert data['summary']['active_count'] >= 1
    finally:
        active_analyses.pop('sess_contract', None)


# ---- the registry in isolation ---------------------------------------------

def test_env_default_survives_a_restart():
    """A Render deploy wipes memory. The env var is what restores intent."""
    assert BetaAccess(enabled=True).enabled is True
    assert BetaAccess(enabled=False).enabled is False


def test_registry_operations():
    access = BetaAccess(enabled=True, doc_limit=3)
    tester = access.mint()
    name = tester['username']

    assert access.remaining(name) == 3
    access.consume_document(name)
    assert access.remaining(name) == 2

    assert access.reset_usage(name)['docs_used'] == 0
    assert access.grant_documents(name, 2)['doc_limit'] == 5
    assert access.set_doc_limit(name, 1)['doc_limit'] == 1

    assert access.delete(name) is not None
    assert access.get(name) is None
    assert access.remaining(name) is None
    assert access.reset_usage(name) is None


def test_registry_hands_out_copies_not_live_records():
    access = BetaAccess(enabled=True, doc_limit=3)
    tester = access.mint()
    tester['doc_limit'] = 9999
    assert access.get(tester['username'])['doc_limit'] == 3
