"""Structural tests for the BidBrief web front-end (2.3.0 iOS-parity shell).

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


def test_health_reports_2_5_2(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.get_json()['version'] == '2.5.2'


@pytest.mark.parametrize('name', [
    'btools-titlelogo-transparent.png',
    'btools-iconlogo-transparent.png',
    'btools-logo.svg',
])
def test_brand_assets_are_served(client, name):
    resp = client.get(f'/pics/brand/{name}')
    assert resp.status_code == 200, f'{name} not served'
    assert len(resp.data) > 200, f'{name} looks empty'


def _png_colour_type(data):
    """Byte 25 of a PNG is the IHDR colour type; 6 == RGBA, 2 == RGB."""
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG'
    return data[25]


@pytest.mark.parametrize('page', ['/', '/login'])
def test_pages_use_the_truly_transparent_logos(client, page):
    """The "nobg" masters are white-backed RGB - using them paints a white box
    over the planet. Only the alpha-keyed twins may be referenced."""
    headers = _auth(client) if page == '/' else {}
    html = client.get(page, headers=headers).data.decode('utf-8')
    assert '-nobg.png' not in html, 'a white-backed logo is referenced'
    for src in re.findall(r'src="(/pics/brand/[^"]+\.png)"', html):
        data = client.get(src).data
        assert _png_colour_type(data) == 6, f'{src} has no alpha channel (white box)'


MODULE_OWNERSHIP = {
    'bb-engine.js': ['BB.engine =', 'startPolling', 'fetchResults'],
    'bb-status.js': ['BB.status =', 'WINDOW_BAND_SPAN'],
    'bb-analyze.js': ['BB.analyze =', 'buildAnalyzePayload', 'enable_visual_analysis'],
    'bb-progress.js': ['BB.progress =', 'phaseTrack'],
    # 2.4.0: the results screen IS the Excel workbook (sheet tabs), including
    # the Visual Intelligence sheet fed by the opt-in vision pass.
    'bb-results.js': ['BB.results =', 'answer_summary', 'sheetList',
                      'Executive Summary', 'Visual Intelligence', 'visual_findings'],
    'bb-scraper.js': ['BB.scraper =', '/api/scraper/research'],
    # 2.4.0: the session dashboard lives in-app (no more legacy new-tab page)
    # and every session row carries a mode-aware Excel export.
    'bb-admin.js': ['BB.admin =', 'entriesFor', '/api/admin/beta', 'betaSummaryText',
                    '/api/admin/sessions', 'exportUrlFor', '/api/export/bestprep-excel/'],
    'bb-settings.js': ['BB.settings =', '/auth/logout'],
    'bb-questionhub.js': ['BB.questionHub =', 'buildSaveBody'],
    'bb-qgen.js': ['BB.qgen =', 'context_file'],
    'bb-libraries.js': ['BB.libraries =', 'seedStarterOnce'],
    'bb-login.js': ['BB.login =', '/auth/beta-login', '/api/beta/status'],
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
    ('/shared/assets/css/bb-screens.css', '.bb-sheet-tabs'),
    ('/shared/assets/css/bb-screens.css', '.bb-visual-finding'),
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


def test_no_light_theme_leftovers_in_the_shipped_shell(client):
    """The overhaul is only done when the old palette is gone from the shell."""
    headers = _auth(client)
    html = client.get('/', headers=headers).data.decode('utf-8')
    for stale in ('#5B7FCC', '#1E3A8A', 'rgba(255, 255, 255, 0.95)'):
        assert stale not in html, f'legacy light-theme value {stale} still in index.html'


def test_every_script_the_shell_references_is_served(client):
    """A 404 on one module silently breaks a whole screen in the browser."""
    headers = _auth(client)
    html = client.get('/', headers=headers).data.decode('utf-8')
    srcs = [s for s in re.findall(r'<script[^>]*\bsrc="([^"]+)"', html) if s.startswith('/')]
    assert len(srcs) >= 10, f'expected the full module set, found {len(srcs)}'
    for src in srcs:
        assert client.get(src).status_code == 200, f'{src} is not served'


def test_starter_question_set_is_served_and_well_formed(client):
    resp = client.get('/shared/assets/data/starter-question-set.json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data.get('sections'), list) and data['sections'], 'starter set is empty'
    first = data['sections'][0]
    assert 'section_id' in first and 'section_name' in first and 'questions' in first
    assert first['questions'], 'starter sections must carry questions'


def test_login_page_wears_the_orb_and_the_btools_lockup(client):
    html = client.get('/login').data.decode('utf-8')
    assert 'bb-orb-host' in html, 'the login page must sit on the planet field'
    assert '/pics/brand/btools-titlelogo-transparent.png' in html, 'btools lockup missing'
    assert '/shared/assets/css/bb-theme.css' in html
    # The form contract the backend depends on must survive the restyle.
    assert 'action="/auth/login"' in html and 'method="POST"' in html
    assert 'name="username"' in html and 'name="password"' in html


def test_login_page_carries_the_beta_path(client):
    """The button ships in the markup but starts hidden; bb-login.js reveals it
    only when /api/beta/status says free beta is open."""
    html = client.get('/login').data.decode('utf-8')
    assert 'id="betaAccess"' in html and 'hidden' in html
    assert 'id="betaButton"' in html
    assert 'Free Beta Testing' in html
    # The terms modal needs a host on this page.
    assert 'id="bb-modal-host"' in html


def test_login_page_drops_the_old_white_card(client):
    html = client.get('/login').data.decode('utf-8')
    assert 'rgba(255, 255, 255, 0.95)' not in html
    assert '/pics/AILLCLogo.png' not in html


def test_every_stylesheet_the_shell_references_is_served(client):
    headers = _auth(client)
    html = client.get('/', headers=headers).data.decode('utf-8')
    hrefs = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', html)
    assert hrefs, 'no stylesheets linked'
    for href in hrefs:
        assert client.get(href).status_code == 200, f'{href} is not served'
