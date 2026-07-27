"""Structural tests for the BidBrief web front-end (2.2.0 iOS-parity shell).

These do not render the page; they assert the served bytes contain the
structures the front-end depends on, so a broken asset path or a dropped
container fails CI instead of failing silently in a browser.
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app import app, active_sessions

BASE = Path(__file__).resolve().parent.parent


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _auth(client, role='user', username='webtester'):
    """Register an in-memory session and attach its cookie to the client."""
    token = f'web-ui-test-{role}'
    active_sessions[token] = {
        'username': username,
        'name': 'Web Tester',
        'role': role,
        'expires_at': datetime.now() + timedelta(hours=1),
    }
    try:
        client.set_cookie('bidbrief_auth', token)
        return {}
    except TypeError:
        return {'Cookie': f'bidbrief_auth={token}'}


def test_health_reports_2_2_0(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.get_json()['version'] == '2.2.0'


@pytest.mark.parametrize('name', [
    'btools-titlelogo-nobg.png',
    'btools-iconlogo-nobg.png',
    'btools-logo.svg',
])
def test_brand_assets_are_served(client, name):
    resp = client.get(f'/pics/brand/{name}')
    assert resp.status_code == 200, f'{name} not served'
    assert len(resp.data) > 200, f'{name} looks empty'


LEGACY_MODULES = {
    'bb-engine.js': ['function startAnalysis', 'function handleEvent', 'function pollForEvents'],
    'legacy-results.js': ['function renderUnitaryTable', 'function runSecondPassOnSelected'],
    'legacy-questions.js': ['function renderQuestionManager', 'function generateAIQuestions'],
    'legacy-modals.js': ['function openAnswerDetailModal', 'function switchFullViewTab'],
    'bb-scraper.js': ['function startCityScraperResearch', 'function updateCSProgress'],
}


@pytest.mark.parametrize('filename,needles', sorted(LEGACY_MODULES.items()))
def test_extracted_js_modules_are_served_and_own_their_functions(client, filename, needles):
    resp = client.get(f'/shared/assets/js/{filename}')
    assert resp.status_code == 200, f'{filename} not served'
    body = resp.data.decode('utf-8')
    for needle in needles:
        assert needle in body, f'{needle!r} missing from {filename}'


def test_index_html_has_no_inline_application_script(client):
    """All JS lives in files. Inline <script> blocks hide code from review,
    caching, and the module split - the page may only reference sources."""
    headers = _auth(client)
    resp = client.get('/', headers=headers)
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    inline = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)
    meaningful = [b for b in inline if len(b.strip()) > 0]
    assert meaningful == [], f'{len(meaningful)} inline script block(s) remain in index.html'
