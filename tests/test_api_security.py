import io
import os
import uuid
import secrets
from datetime import datetime, timedelta
import tempfile

import pytest

from app import app, UPLOAD_STORE, completed_analyses, active_analyses, active_sessions, session_events


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _create_auth_cookie(client, token, username, role='user'):
    # Insert into active_sessions and return headers dict to include in requests
    active_sessions[token] = {
        'username': username,
        'role': role,
        'expires_at': datetime.now() + timedelta(hours=1)
    }
    # Try to use client.set_cookie with the simpler signature; if unavailable, fall back to header
    try:
        client.set_cookie('bidbrief_auth', token)
        return {}
    except TypeError:
        client.environ_base['HTTP_COOKIE'] = f'bidbrief_auth={token}'
        return {'Cookie': f'bidbrief_auth={token}'}


def test_config_apikey_admin_protected(client, monkeypatch):
    # Ensure env has API key
    monkeypatch.setenv('OPENAI_API_KEY', 'sk_test_admin123456')

    token = 'admin-token'
    headers = _create_auth_cookie(client, token, 'adminuser', role='admin')

    resp = client.get('/api/config/apikey', headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'masked' in data


def test_config_apikey_non_admin_returns_403(client):
    """Test that non-admin users get 403 JSON error for admin API routes."""
    token = 'user-token'
    headers = _create_auth_cookie(client, token, 'bob', role='user')

    resp = client.get('/api/config/apikey', headers=headers)
    # API routes return JSON 403, not redirect
    assert resp.status_code == 403
    data = resp.get_json()
    assert data['success'] is False
    assert 'Admin access required' in data['error']


def test_upload_requires_auth(client):
    """Test that upload endpoint requires authentication."""
    data = {
        'file': (io.BytesIO(b'%PDF-1.4\n%EOF\n'), 'test_upload.pdf')
    }
    # API routes return JSON 401, not redirect
    resp = client.post('/api/upload', data=data, content_type='multipart/form-data')
    assert resp.status_code == 401
    body = resp.get_json()
    assert body['success'] is False
    assert 'Authentication required' in body['error']


def test_upload_returns_upload_id_and_no_path(client):
    """Test that authenticated upload returns opaque upload_id and no file path."""
    # Authenticate first
    token = 'upload-test-token'
    headers = _create_auth_cookie(client, token, 'testuser', role='user')

    data = {
        'file': (io.BytesIO(b'%PDF-1.4\n%EOF\n'), 'test_upload.pdf')
    }
    resp = client.post('/api/upload', data=data, content_type='multipart/form-data', headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert 'upload_id' in body
    assert 'filepath' not in body
    assert 'path' not in body  # Server path should never be exposed

    uid = body['upload_id']
    assert uid in UPLOAD_STORE
    info = UPLOAD_STORE[uid]
    assert os.path.exists(info['path'])
    assert info.get('encrypted') is True  # File should be encrypted
    assert info.get('owner') == 'testuser'  # Owner should be set

    # Clean up file and store
    try:
        os.unlink(info['path'])
    except Exception:
        pass
    UPLOAD_STORE.pop(uid, None)


def test_upload_id_is_cryptographically_random(client):
    """Test that upload_id is cryptographically random, not predictable."""
    token = 'crypto-test-token'
    headers = _create_auth_cookie(client, token, 'testuser', role='user')

    data = {
        'file': (io.BytesIO(b'%PDF-1.4\n%EOF\n'), 'test_upload.pdf')
    }
    resp = client.post('/api/upload', data=data, content_type='multipart/form-data', headers=headers)
    body = resp.get_json()

    uid = body['upload_id']
    # Should be 32 hex chars (16 bytes = 128 bits of entropy)
    assert len(uid) == 32
    assert all(c in '0123456789abcdef' for c in uid)

    # Clean up
    info = UPLOAD_STORE.get(uid)
    if info:
        try:
            os.unlink(info['path'])
        except Exception:
            pass
    UPLOAD_STORE.pop(uid, None)


def test_analyze_enforces_upload_ownership(client):
    """Test that analysis enforces upload ownership."""
    # Create a temporary file and upload record owned by alice
    fd, p = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    with open(p, 'wb') as f:
        f.write(b'%PDF-1.4\n%EOF\n')

    uid = secrets.token_hex(16)
    UPLOAD_STORE[uid] = {
        'path': p,
        'filename': 'owned.pdf',
        'uploaded_at': datetime.now(),
        'expires_at': datetime.now() + timedelta(hours=1),
        'owner': 'alice',
        'encrypted': False  # Legacy unencrypted for test
    }

    # Bob (non-owner) attempts to start analysis
    headers_bob = _create_auth_cookie(client, 'bob-token', 'bob', role='user')
    resp = client.post('/api/analyze', json={'upload_id': uid}, headers=headers_bob)
    assert resp.status_code == 403

    # Admin can start (but may later return API key error)
    headers_admin = _create_auth_cookie(client, 'admin2', 'admin', role='admin')
    resp2 = client.post('/api/analyze', json={'upload_id': uid}, headers=headers_admin)
    # Should not be a 403 (authorization passed). Accept 200 or 500 depending on env
    assert resp2.status_code != 403

    # Cleanup
    try:
        os.unlink(p)
    except Exception:
        pass
    UPLOAD_STORE.pop(uid, None)


def test_session_id_is_cryptographically_secure(client, monkeypatch):
    """Test that session_id is generated server-side and cryptographically secure."""
    monkeypatch.setenv('OPENAI_API_KEY', 'sk_test_123')

    # Create upload
    fd, p = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    with open(p, 'wb') as f:
        f.write(b'%PDF-1.4\n%EOF\n')

    uid = secrets.token_hex(16)
    UPLOAD_STORE[uid] = {
        'path': p,
        'filename': 'test.pdf',
        'uploaded_at': datetime.now(),
        'expires_at': datetime.now() + timedelta(hours=1),
        'owner': 'alice',
        'encrypted': False
    }

    headers = _create_auth_cookie(client, 'alice-token', 'alice', role='user')

    # Client tries to specify session_id - should be ignored
    resp = client.post('/api/analyze', json={
        'upload_id': uid,
        'session_id': 'client_provided_session'  # This should be ignored
    }, headers=headers)

    # May fail due to missing API key, but check session_id pattern if it succeeds
    if resp.status_code == 200:
        body = resp.get_json()
        session_id = body.get('session_id', '')
        # Should start with 'sess_' and have 32 hex chars
        assert session_id.startswith('sess_')
        assert len(session_id) == 37  # 'sess_' (5) + 32 hex chars
        assert session_id != 'client_provided_session'  # Client-provided should be ignored

    # Cleanup
    try:
        os.unlink(p)
    except Exception:
        pass
    UPLOAD_STORE.pop(uid, None)


def test_results_and_exports_enforce_ownership(client):
    """Test that results and exports enforce session ownership."""
    sid = 'sess_' + secrets.token_hex(16)
    # Add a completed_analyses entry with owner alice
    completed_analyses[sid] = {
        'owner': 'alice'
    }

    headers_bob = _create_auth_cookie(client, 'bob2', 'bob', role='user')

    # Bob should not access results
    resp = client.get(f'/api/results/{sid}', headers=headers_bob)
    assert resp.status_code == 403

    # Bob should not access export
    resp2 = client.get(f'/api/export/excel-dashboard/{sid}', headers=headers_bob)
    assert resp2.status_code == 403

    # Alice can access (may 404/500 if content missing) - assert not 403
    headers_alice = _create_auth_cookie(client, 'alice-token', 'alice', role='user')
    resp3 = client.get(f'/api/results/{sid}', headers=headers_alice)
    assert resp3.status_code != 403

    # Cleanup
    completed_analyses.pop(sid, None)


def test_events_endpoint_enforces_ownership(client):
    """Test that /api/events/<session_id> enforces session ownership."""
    sid = 'sess_' + secrets.token_hex(16)

    # Create session owned by alice
    active_analyses[sid] = {
        'owner': 'alice'
    }
    session_events[sid] = [{'event': 'test', 'data': 'test data'}]

    headers_bob = _create_auth_cookie(client, 'bob3', 'bob', role='user')

    # Bob should not access events
    resp = client.get(f'/api/events/{sid}', headers=headers_bob)
    assert resp.status_code == 403

    # Alice can access
    headers_alice = _create_auth_cookie(client, 'alice2-token', 'alice', role='user')
    resp2 = client.get(f'/api/events/{sid}', headers=headers_alice)
    assert resp2.status_code != 403

    # Admin can access
    headers_admin = _create_auth_cookie(client, 'admin3', 'admin', role='admin')
    resp3 = client.get(f'/api/events/{sid}', headers=headers_admin)
    assert resp3.status_code != 403

    # Cleanup
    active_analyses.pop(sid, None)
    session_events.pop(sid, None)


def test_progress_endpoint_enforces_ownership(client):
    """Test that /api/progress/<session_id> enforces session ownership."""
    sid = 'sess_' + secrets.token_hex(16)

    # Create session owned by alice
    active_analyses[sid] = {
        'owner': 'alice'
    }

    headers_bob = _create_auth_cookie(client, 'bob4', 'bob', role='user')

    # Bob should not access progress
    resp = client.get(f'/api/progress/{sid}', headers=headers_bob)
    assert resp.status_code == 403

    # Cleanup
    active_analyses.pop(sid, None)


def test_stop_endpoint_enforces_ownership(client):
    """Test that /api/stop/<session_id> enforces session ownership."""
    sid = 'sess_' + secrets.token_hex(16)

    # Create session owned by alice
    active_analyses[sid] = {
        'owner': 'alice'
    }

    headers_bob = _create_auth_cookie(client, 'bob5', 'bob', role='user')

    # Bob should not be able to stop alice's session
    resp = client.post(f'/api/stop/{sid}', headers=headers_bob)
    assert resp.status_code == 403

    # Cleanup
    active_analyses.pop(sid, None)
