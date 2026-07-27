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


MODULE_OWNERSHIP = {
    'bb-engine.js': ['BB.engine =', 'startPolling', 'fetchResults'],
    'bb-status.js': ['BB.status =', 'WINDOW_BAND_SPAN'],
    'bb-analyze.js': ['BB.analyze =', 'buildAnalyzePayload'],
    'bb-progress.js': ['BB.progress =', 'phaseTrack'],
    'bb-results.js': ['BB.results =', 'answer_summary'],
}


@pytest.mark.parametrize('filename,needles', sorted(MODULE_OWNERSHIP.items()))
def test_js_modules_are_served_and_own_their_responsibilities(client, filename, needles):
    resp = client.get(f'/shared/assets/js/{filename}')
    assert resp.status_code == 200, f'{filename} not served'
    body = resp.data.decode('utf-8')
    for needle in needles:
        assert needle in body, f'{needle!r} missing from {filename}'


@pytest.mark.parametrize('path,needle', [
    ('/shared/assets/css/bb-theme.css', '--bb-glow-ice: #45B4F2'),
    ('/shared/assets/js/bb-ui.js', 'BB.ui ='),
    ('/shared/assets/css/bb-orb.css', '.bb-orb-planet'),
    ('/shared/assets/js/bb-orb.js', 'starPoints'),
])
def test_design_system_assets_served(client, path, needle):
    resp = client.get(path)
    assert resp.status_code == 200, f'{path} not served'
    assert needle in resp.data.decode('utf-8')


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


def test_shell_has_the_four_ios_pages_and_a_tab_bar(client):
    headers = _auth(client)
    html = client.get('/', headers=headers).data.decode('utf-8')
    for page in ('bb-page-analyze', 'bb-page-questions', 'bb-page-admin', 'bb-page-settings'):
        assert f'id="{page}"' in html, f'missing page container {page}'
    assert 'id="bb-tabbar"' in html
    assert 'id="bb-orb"' in html
    assert '/shared/assets/css/bb-theme.css' in html
    assert '/shared/assets/js/bb-boot.js' in html


def test_shell_no_longer_ships_the_old_light_navbar(client):
    headers = _auth(client)
    html = client.get('/', headers=headers).data.decode('utf-8')
    assert 'mpt-navbar' not in html, 'the legacy light-theme navbar must be gone'


def test_every_stylesheet_the_shell_references_is_served(client):
    headers = _auth(client)
    html = client.get('/', headers=headers).data.decode('utf-8')
    hrefs = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', html)
    assert hrefs, 'no stylesheets linked'
    for href in hrefs:
        assert client.get(href).status_code == 200, f'{href} is not served'
