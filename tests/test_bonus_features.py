"""
Bonus Features + High Power gating tests.

Hard rules verified here:
  1. Only admins can view/change Bonus Features grants.
  2. Bonus users NEVER gain /api/admin/sessions (the sessions dashboard).
  3. high_power requests are 403 for plain users, allowed for admin/bonus.
  4. Scraper access opens to bonus users; scraper session list stays own-only for them.
"""
from datetime import datetime, timedelta

import pytest

from app import (
    AUTHORIZED_USERS,
    active_sessions,
    app,
    bonus_feature_users,
)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_state():
    bonus_feature_users.clear()
    # Ensure two known users exist regardless of env configuration
    AUTHORIZED_USERS.setdefault('admin@test.local', {
        'password_hash': 'x', 'name': 'Admin', 'role': 'admin'})
    AUTHORIZED_USERS.setdefault('user@test.local', {
        'password_hash': 'x', 'name': 'User', 'role': 'user'})
    yield
    bonus_feature_users.clear()
    active_sessions.pop('tok-admin', None)
    active_sessions.pop('tok-user', None)


def _login(client, token, username, role):
    active_sessions[token] = {
        'username': username,
        'name': username,
        'role': role,
        'expires_at': datetime.now() + timedelta(hours=1),
    }
    client.set_cookie('bidbrief_auth', token)


def test_user_info_includes_bonus_and_premium(client):
    _login(client, 'tok-user', 'user@test.local', 'user')
    data = client.get('/api/user/info').get_json()
    assert data['bonus_features'] is False
    assert data['premium'] is False

    bonus_feature_users.add('user@test.local')
    data = client.get('/api/user/info').get_json()
    assert data['bonus_features'] is True
    assert data['premium'] is True


def test_admin_always_premium(client):
    _login(client, 'tok-admin', 'admin@test.local', 'admin')
    data = client.get('/api/user/info').get_json()
    assert data['is_admin'] is True
    assert data['premium'] is True


def test_bonus_routes_admin_only(client):
    _login(client, 'tok-user', 'user@test.local', 'user')
    assert client.get('/api/admin/bonus-features').status_code == 403
    assert client.post('/api/admin/bonus-features',
                       json={'email': 'user@test.local', 'enabled': True}).status_code == 403
    # And granting bonus does NOT change that
    bonus_feature_users.add('user@test.local')
    assert client.get('/api/admin/bonus-features').status_code == 403


def test_admin_grants_and_revokes(client):
    _login(client, 'tok-admin', 'admin@test.local', 'admin')

    resp = client.post('/api/admin/bonus-features',
                       json={'email': 'user@test.local', 'enabled': True})
    assert resp.status_code == 200
    assert resp.get_json()['bonus_features'] is True
    assert 'user@test.local' in bonus_feature_users

    listing = client.get('/api/admin/bonus-features').get_json()
    target = next(u for u in listing['users'] if u['email'] == 'user@test.local')
    assert target['bonus_features'] is True
    assert 'password_hash' not in target

    resp = client.post('/api/admin/bonus-features',
                       json={'email': 'user@test.local', 'enabled': False})
    assert resp.status_code == 200
    assert 'user@test.local' not in bonus_feature_users


def test_unknown_user_404(client):
    _login(client, 'tok-admin', 'admin@test.local', 'admin')
    resp = client.post('/api/admin/bonus-features',
                       json={'email': 'ghost@nowhere.local', 'enabled': True})
    assert resp.status_code == 404


def test_bonus_never_unlocks_admin_sessions(client):
    """THE hard rule: sessions dashboard stays invisible to bonus users."""
    _login(client, 'tok-user', 'user@test.local', 'user')
    bonus_feature_users.add('user@test.local')
    resp = client.get('/api/admin/sessions')
    assert resp.status_code == 403


def test_high_power_analyze_403_for_plain_user(client):
    _login(client, 'tok-user', 'user@test.local', 'user')
    resp = client.post('/api/analyze', json={'upload_id': 'nope', 'high_power': True})
    assert resp.status_code == 403
    assert 'High Power' in resp.get_json()['error']


def test_high_power_analyze_passes_gate_for_bonus_user(client):
    _login(client, 'tok-user', 'user@test.local', 'user')
    bonus_feature_users.add('user@test.local')
    resp = client.post('/api/analyze', json={'upload_id': 'nope', 'high_power': True})
    # Gate passed; fails later on the bogus upload id instead (404, not 403)
    assert resp.status_code == 404


def test_high_power_question_gen_403_for_plain_user(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _login(client, 'tok-user', 'user@test.local', 'user')
    resp = client.post('/api/config/questions/generate',
                       json={'user_input': 'test questions', 'high_power': True})
    assert resp.status_code == 403


def test_high_power_smart_analysis_403_for_plain_user(client):
    _login(client, 'tok-user', 'user@test.local', 'user')
    resp = client.post('/api/smart-analysis/sess_doesnotexist',
                       json={'high_power': True})
    assert resp.status_code == 403


def test_scraper_admin_check_opens_for_bonus_user(client):
    _login(client, 'tok-user', 'user@test.local', 'user')
    data = client.get('/api/scraper/admin-check').get_json()
    assert data['is_admin'] is False

    bonus_feature_users.add('user@test.local')
    data = client.get('/api/scraper/admin-check').get_json()
    assert data['is_admin'] is True


def test_scraper_sessions_own_only_for_bonus_user(client):
    from app import cityscraper_sessions
    cityscraper_sessions['scraper_other'] = {
        'status': 'completed', 'municipality': 'Elsewhere', 'user': 'admin@test.local',
        'started_at': datetime.now().isoformat()}
    cityscraper_sessions['scraper_mine'] = {
        'status': 'completed', 'municipality': 'Mytown', 'user': 'user@test.local',
        'started_at': datetime.now().isoformat()}
    try:
        _login(client, 'tok-user', 'user@test.local', 'user')
        bonus_feature_users.add('user@test.local')
        data = client.get('/api/scraper/sessions').get_json()
        ids = [s['session_id'] for s in data['sessions']]
        assert 'scraper_mine' in ids
        assert 'scraper_other' not in ids

        _login(client, 'tok-admin', 'admin@test.local', 'admin')
        data = client.get('/api/scraper/sessions').get_json()
        ids = [s['session_id'] for s in data['sessions']]
        assert 'scraper_other' in ids and 'scraper_mine' in ids
    finally:
        cityscraper_sessions.pop('scraper_other', None)
        cityscraper_sessions.pop('scraper_mine', None)


def test_preflight_rejects_bad_focus(client):
    _login(client, 'tok-admin', 'admin@test.local', 'admin')
    resp = client.post('/api/scraper/preflight',
                       json={'municipality': 'Round Rock, TX',
                             'table_mode': 'systems_info',
                             'research_focus': 'bogus_focus'})
    # Either a focus validation 400, or a 503 when scraper modules are unavailable
    assert resp.status_code in (400, 503)
    if resp.status_code == 400:
        assert 'research_focus' in resp.get_json()['error']
