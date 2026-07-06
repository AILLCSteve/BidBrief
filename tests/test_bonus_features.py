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


def test_question_gen_always_high_power_for_plain_user(client, monkeypatch):
    """Question generation is high-power for EVERY user — no entitlement gate,
    no 403 (product decision 2026-07-05)."""
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _login(client, 'tok-user', 'user@test.local', 'user')

    captured = {}

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'message': {'content':
                '{"sections": [{"section_id": "s1", "section_name": "S1", '
                '"section_description": "d", "questions": [{"id": "Q1", "text": "t", '
                '"required": false, "expected_type": "string", "enabled": true}]}]}'}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured['model'] = json['model']
        return _FakeResp()

    import requests as _requests
    monkeypatch.setattr(_requests, 'post', fake_post)

    resp = client.post('/api/config/questions/generate',
                       json={'user_input': 'test questions'})
    assert resp.status_code == 200

    from services.ai_models import high_power_model
    assert captured['model'] == high_power_model()


def test_generate_questions_source_frames_derivation(client, monkeypatch):
    """A questions-source upload frames the prompt to DERIVE questions from the
    material, and non-PDF text is read and injected."""
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _login(client, 'tok-user', 'user@test.local', 'user')

    captured = {}

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'message': {'content':
                '{"sections": [{"section_id": "s1", "section_name": "S1", '
                '"section_description": "d", "questions": [{"id": "Q1", "text": "t", '
                '"required": false, "expected_type": "string", "enabled": true}]}]}'}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured['system'] = json['messages'][0]['content']
        return _FakeResp()

    import requests as _requests
    from io import BytesIO
    monkeypatch.setattr(_requests, 'post', fake_post)

    resp = client.post(
        '/api/config/questions/generate',
        data={'user_input': 'derive questions', 'source_kind': 'questions_source',
              'file': (BytesIO(b'Compare vendor SLA against our uptime standard.'), 'notes.txt')},
        content_type='multipart/form-data')
    assert resp.status_code == 200
    assert 'derive' in captured['system'].lower()
    assert 'uptime standard' in captured['system'].lower()


def test_generate_questions_source_and_context_file_both_used(client, monkeypatch):
    """A questions-source file AND a separate context_file (the analyzer/bid
    document) are BOTH incorporated: the derive-from block frames the questions
    source, and the document-context grounding block carries the context_file —
    so a questions source never displaces the analyzer document (bug 2026-07-06).
    Both also reach the Persona Architect."""
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _login(client, 'tok-user', 'user@test.local', 'user')

    calls = []
    payloads = [
        ('{"panel": [{"name": "Sewer Rehab Spec Analyst", "expertise": "CIPP", '
         '"focus": "liners"}], "document_reading": "A CIPP rehab RFP"}'),
        ('{"sections": [{"section_id": "s1", "section_name": "S1", '
         '"section_description": "d", "section_summary": "why", '
         '"questions": [{"id": "Q1", "text": "t", "required": false, '
         '"expected_type": "string", "enabled": true}]}]}'),
    ]

    class _FakeResp:
        def __init__(self, content):
            self._content = content

        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'message': {'content': self._content}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _FakeResp(payloads[min(len(calls) - 1, len(payloads) - 1)])

    import requests as _requests
    from io import BytesIO
    monkeypatch.setattr(_requests, 'post', fake_post)

    resp = client.post(
        '/api/config/questions/generate',
        data={'user_input': 'derive questions', 'source_kind': 'questions_source',
              'file': (BytesIO(b'Compare vendor SLA against our uptime standard.'), 'notes.txt'),
              'context_file': (BytesIO(b'Bidder must line 4200 linear feet of sewer main.'),
                               'bid_spec.txt')},
        content_type='multipart/form-data')
    assert resp.status_code == 200

    # Generation system prompt (calls[1] = generation, calls[0] = architect).
    gen_system = calls[1]['messages'][0]['content']
    # Questions-source derivation block present, with its material.
    assert 'derive questions from' in gen_system.lower()
    assert 'uptime standard' in gen_system.lower()
    # Document-context grounding block present, with the context_file's material.
    assert 'document context' in gen_system.lower()
    assert '4200 linear feet' in gen_system.lower()

    # Both materials reached the Persona Architect too.
    architect_user = calls[0]['messages'][1]['content'].lower()
    assert 'uptime standard' in architect_user
    assert '4200 linear feet' in architect_user


def test_generate_context_only_grounds_in_document(client, monkeypatch):
    """The user's core path: a single Document-Context file (source_kind=context,
    the default) makes the generation prompt carry the document's actual content
    under a grounding directive — so 'give me N questions' produces questions
    grounded in the document, not generic ones."""
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _login(client, 'tok-user', 'user@test.local', 'user')

    calls = []

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'message': {'content':
                '{"sections": [{"section_id": "s1", "section_name": "S1", '
                '"section_description": "d", "section_summary": "why", '
                '"questions": [{"id": "Q1", "text": "t", "required": false, '
                '"expected_type": "string", "enabled": true}]}]}'}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _FakeResp()

    import requests as _requests
    from io import BytesIO
    monkeypatch.setattr(_requests, 'post', fake_post)

    resp = client.post(
        '/api/config/questions/generate',
        data={'user_input': 'give me 3 questions',
              'file': (BytesIO(b'Section 3: Contractor shall reline 4200 linear feet of '
                               b'8-inch sanitary sewer main using CIPP.'), 'bid_spec.txt')},
        content_type='multipart/form-data')
    assert resp.status_code == 200

    gen_system = calls[-1]['messages'][0]['content'].lower()
    # Grounding directive + the document's actual content both present.
    assert 'document to be analyzed' in gen_system
    assert '4200 linear feet' in gen_system


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


def test_generate_builds_dynamic_persona_panel(client, monkeypatch):
    """Two-stage generation: a Persona Architect derives a bespoke expert panel
    from the document/user input, the panel generates the set, and every
    section carries a section_summary rationale. source_intent threads into
    both prompts."""
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _login(client, 'tok-user', 'user@test.local', 'user')

    calls = []
    payloads = [
        # Call 1: persona architect
        ('{"panel": [{"name": "CIPP Rehab Standards Analyst", '
         '"expertise": "Trenchless rehab specs", "focus": "materials"}], '
         '"document_reading": "A sewer rehab RFP"}'),
        # Call 2: generation with rationale
        ('{"sections": [{"section_id": "s1", "section_name": "Liner Materials", '
         '"section_description": "d", '
         '"section_summary": "Created because the doc centers on CIPP liner specs.", '
         '"questions": [{"id": "Q1", "text": "t", "required": false, '
         '"expected_type": "string", "enabled": true}]}]}'),
    ]

    class _FakeResp:
        def __init__(self, content):
            self._content = content

        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'message': {'content': self._content}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _FakeResp(payloads[min(len(calls) - 1, len(payloads) - 1)])

    import requests as _requests
    monkeypatch.setattr(_requests, 'post', fake_post)

    resp = client.post('/api/config/questions/generate',
                       json={'user_input': 'sewer lining bid questions',
                             'source_intent': 'derive questions from this rehab standard'})
    assert resp.status_code == 200
    data = resp.get_json()

    # Two calls: architect then generation
    assert len(calls) == 2
    # source_intent reached both prompts
    assert 'rehab standard' in calls[0]['messages'][1]['content']
    joined_gen = calls[1]['messages'][0]['content'] + calls[1]['messages'][1]['content']
    assert 'rehab standard' in joined_gen
    # The bespoke panel steers generation and is returned to the client
    assert 'CIPP Rehab Standards Analyst' in calls[1]['messages'][0]['content']
    assert data['generation_personas'][0]['name'] == 'CIPP Rehab Standards Analyst'
    # Every section carries its rationale
    assert data['config']['sections'][0]['section_summary'].startswith('Created because')


def test_generate_architect_failure_falls_back(client, monkeypatch):
    """If the persona-architect stage fails, generation still succeeds without
    personas (never 500 on a cosmetics stage)."""
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    _login(client, 'tok-user', 'user@test.local', 'user')

    calls = []

    class _FakeResp:
        def __init__(self, content):
            self._content = content

        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'message': {'content': self._content}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            raise RuntimeError('architect down')
        return _FakeResp(
            '{"sections": [{"section_id": "s1", "section_name": "S1", '
            '"section_description": "d", "questions": [{"id": "Q1", "text": "t", '
            '"required": false, "expected_type": "string", "enabled": true}]}]}')

    import requests as _requests
    monkeypatch.setattr(_requests, 'post', fake_post)

    resp = client.post('/api/config/questions/generate',
                       json={'user_input': 'test questions'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['generation_personas'] == []
    assert len(data['config']['sections']) == 1
