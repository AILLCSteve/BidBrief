# BidBrief Web Front-End — iOS Parity Overhaul (2.2.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the BidBrief web front-end (`index.html`, `login.html`) so its visual language, information architecture, and guided flow match the BidBrief iOS app (2.1.3) — dark "suspended planet" space field, glass cards, glowing capsule buttons, a four-item bottom tab bar (Analyze / Questions / Admin|Bonus / Settings), staged screens with back chips, the confirmed-question-set gate, and the Questions → Analyze onboarding cue.

**Architecture:** The web app is today a single 5,514-line `index.html` (590 lines inline CSS + ~350 lines markup + ~4,440 lines inline JS). We split the inline JS into contiguous, byte-preserving modules first (a mechanical, verifiable step), then replace the shell and each screen with iOS-parity modules that reuse the existing, working API/pipeline logic. All new assets are served by the pre-existing Flask route `/shared/<path:filename>` (`app.py:769`) — no new routes are required. State lives in one `BB.state` object that mirrors the iOS `AppModels` (analysis / questionHub / navigation + a derived `onboardingHint`).

**Tech Stack:** Flask (Python 3.13) serving static files; vanilla ES5/ES2017 browser JS (no bundler, no framework — every module attaches to the `BB` global so the existing inline `onclick=` handlers keep working); plain CSS with custom properties; `pytest` for served-structure tests; `node --test` (Node 22, built-in, zero deps) for pure-logic JS unit tests; Playwright MCP for visual verification.

## Global Constraints

- **Repo:** all work happens in the Flask backend repo `C:\Users\pr0ph\Documents\AI LLC\Apps\Doc Analysis Projects\Non-Buildout and Branded\2026\BidBrief`. The iOS repo is READ-ONLY reference for this plan.
- **Branch:** work on `feat/web-ios-parity-2.2.0`, branched from `master`. **Never push `master` without explicitly asking the user first** — a `master` push auto-deploys to Render production (`DEPLOYMENT.md`).
- **Baseline:** `python -m pytest -q` is **76 passed** before this plan starts. It must be ≥76 passed at every commit.
- **No new Flask routes.** New CSS/JS/data live under `shared/assets/` and are served by the existing `/shared/<path:filename>` route. New images live under `pics/` (existing `/pics/<path:filename>` route).
- **No `type="module"` script tags.** The legacy code relies on global functions bound by inline `onclick=` attributes. Every JS file is a classic script attaching to `window.BB` (namespace) or leaving legacy globals intact.
- **No external CDN additions.** The one existing CDN script (`xlsx-0.20.1`) stays.
- **Palette (exact hex, from `Sources/DesignSystem/Theme.swift`):** spaceDeep `#050E24`, spaceNavy `#0A1F55`, brandNavy `#104090`, periwinkle `#5E86D0`, glowIce `#45B4F2`, success `#22C55E`, warn `#FF9800`, danger `#DC2626`, glassFill `rgba(255,255,255,0.08)`, glassStrong `rgba(255,255,255,0.14)`, glassStroke `rgba(255,255,255,0.18)`, textPrimary `#FFFFFF`, textSecondary `rgba(255,255,255,0.65)`, textTertiary `rgba(255,255,255,0.40)`.
- **Version:** this release is `2.2.0`. Both `/health` handlers in `app.py` report `'version': '2.2.0'`.
- **Every animation respects `@media (prefers-reduced-motion: reduce)`** — matching the iOS `accessibilityReduceMotion` guards.
- **Backend behavior is NOT changed by this plan.** Only `app.py`'s two version strings are touched. Question generation, analysis, exports, and scraper endpoints stay exactly as they are.
- **Preserve these hard-won contracts** (from `CLAUDE.md` Part II — regressions here have happened before):
  - `enabled_sections` is WYSIWYG: always send the explicit checked list of section ids; never collapse a full selection to `undefined`/`null`.
  - Q-gen must ALWAYS send the analyzer document for grounding — as the primary `file` (`source_kind=context`) when there is no PDF questions-source, else as `context_file` alongside the questions-source PDF.
  - Question config round-trips losslessly: never strip unknown keys (`required`, `expected_type`, `section_description`, `section_summary`) when PUTting `/api/config/questions`.
  - `answer_summary` renders between the answer and the page citations on every surface.
  - The first `/api/events` poll after `/api/analyze` may 403 — retry ~3× before erroring.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `shared/assets/css/bb-theme.css` | Design tokens + primitives: glass cards, glow/ghost/hub buttons, stage header, eyebrow, back chip, field, banner, tab bar, throb/breathe animations |
| `shared/assets/css/bb-orb.css` | The suspended-planet background: space gradient, halo, planet body, rim light, specular gleam, orbital ring, moon, legibility scrims |
| `shared/assets/css/bb-screens.css` | Screen layout: app column, stages, results tables, modals, scraper, progress ring/track |
| `shared/assets/js/bb-ui.js` | `BB.ui` DOM/format helpers + banner/toast + throb cue helper |
| `shared/assets/js/bb-orb.js` | Deterministic starfield painter + per-tab parallax drift |
| `shared/assets/js/bb-state.js` | `BB.state` — AppModels parity (analysis / questionHub / navigation) + `onboardingHint` + localStorage persistence |
| `shared/assets/js/bb-shell.js` | Tab bar render, page routing, cue rendering, `/api/user/info` (admin + bonus) |
| `shared/assets/js/bb-status.js` | Port of iOS `AnalysisPhase` + `AnalysisStatus` (event → phase/detail/fraction) |
| `shared/assets/js/bb-analyze.js` | Analyze stages: idle → uploading → configure; analyze payload builder |
| `shared/assets/js/bb-progress.js` | Progress orb ring, phase track, Live Activity popup |
| `shared/assets/js/bb-results.js` | Staged results: overview / sections / key details / intelligence / improve / exports / table |
| `shared/assets/js/bb-questionhub.js` | Hub menu, Current Set disclosure, Sections, Questions, Question edit |
| `shared/assets/js/bb-qgen.js` | Create / Add Question Set screen + generate + personas + suggestions |
| `shared/assets/js/bb-libraries.js` | localStorage library store + one-time Starter Set seed |
| `shared/assets/js/bb-admin.js` | Admin / Bonus hub + Bonus Features manager |
| `shared/assets/js/bb-settings.js` | Settings screen (account, sign out, about) |
| `shared/assets/data/starter-question-set.json` | BidBrief Starter Set (copied from iOS `Resources/DefaultQuestionSet.json`) |
| `pics/brand/*` | btools.ai logo assets copied from the iOS repo `branding/` |
| `tests/test_web_ui.py` | pytest: served assets, page structure, no-inline-script invariants |
| `tests/js/*.test.js` | `node --test` unit tests for the pure-logic JS modules |

**Created by mechanical extraction (Task 2), then progressively replaced:**

| Path | Origin |
|---|---|
| `shared/assets/js/bb-engine.js` | index.html script lines 954–2361 (globals, Logger, ProgressTracker, polling, handleEvent, upload, config load, startAnalysis, fetchResults, displayResults, stop, exports, Smart Analysis, admin check) |
| `shared/assets/js/legacy-results.js` | index.html script lines 2362–2945 (unitary table, selection, second pass / RAG, refresh) |
| `shared/assets/js/legacy-questions.js` | index.html script lines 2946–3705 (question manager CRUD, question-set hub, AI generate, About) |
| `shared/assets/js/legacy-modals.js` | index.html script lines 3706–4593 (answer detail modal, full-view modal + tabs) |
| `shared/assets/js/bb-scraper.js` | index.html script lines 4594–5390 (CityScraper) |

**Modified:**

| Path | Change |
|---|---|
| `index.html` | Rewritten as a shell: head + orb layer + app column + four page containers + tab bar + modals; all CSS/JS by `<link>`/`<script src>` |
| `login.html` | Rewritten: orb background, btools lockup, glass login card |
| `app.py` | `/health` version `2.0.0` → `2.2.0` (two handlers: ~line 774 and ~line 5173) |

---

## Task 1: Asset plumbing, brand assets, version bump, test harness

**Files:**
- Create: `pics/brand/btools-titlelogo-nobg.png`, `pics/brand/btools-iconlogo-nobg.png`, `pics/brand/btools-logo.svg` (copies from the iOS repo `branding/`)
- Create: `tests/test_web_ui.py`
- Create: `tests/js/` (directory), `tests/js/README.md`
- Modify: `app.py` (two `'version': '2.0.0'` strings → `'2.2.0'`)

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/test_web_ui.py` with helper `def _auth(client, role='user')` returning request headers for an authenticated session — every later task's pytest additions use it. Brand assets addressable at `/pics/brand/<name>`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_ui.py`:

```python
"""Structural tests for the BidBrief web front-end (2.2.0 iOS-parity shell).

These do not render the page; they assert the served bytes contain the
structures the front-end depends on, so a broken asset path or a dropped
container fails CI instead of failing silently in a browser.
"""
import re
from datetime import datetime, timedelta

import pytest

from app import app, active_sessions

BASE = __import__('pathlib').Path(__file__).resolve().parent.parent


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "C:/Users/pr0ph/Documents/AI LLC/Apps/Doc Analysis Projects/Non-Buildout and Branded/2026/BidBrief" && python -m pytest tests/test_web_ui.py -q`
Expected: FAIL — 4 failed (`version == '2.0.0'`, and three 404s for the brand assets).

- [ ] **Step 3: Copy the brand assets and bump the version**

```bash
cd "C:/Users/pr0ph/Documents/AI LLC/Apps/Doc Analysis Projects/Non-Buildout and Branded/2026/BidBrief"
mkdir -p pics/brand tests/js
cp "C:/Users/pr0ph/Documents/AI LLC/Apps/BidBrief iOS/branding/btools-titlelogo-nobg.png" pics/brand/
cp "C:/Users/pr0ph/Documents/AI LLC/Apps/BidBrief iOS/branding/btools-iconlogo-nobg.png" pics/brand/
cp "C:/Users/pr0ph/Documents/AI LLC/Apps/BidBrief iOS/branding/btools-logo.svg" pics/brand/
```

In `app.py`, both `/health` handlers change their version string:

```python
        'version': '2.2.0'
```

Create `tests/js/README.md`:

```markdown
# JS unit tests

Pure-logic tests for `shared/assets/js/*` using Node's built-in test runner
(no dependencies, Node >= 18):

    node --test tests/js/

Each module under test is a classic browser script that attaches to a global
`BB` namespace. The tests load it with `loadModule()` from `_harness.js`,
which evaluates the file against a minimal fake `window`/`document`.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_web_ui.py -q`
Expected: PASS — 4 passed.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: `80 passed` (76 baseline + 4 new).

- [ ] **Step 6: Commit**

```bash
git checkout -b feat/web-ios-parity-2.2.0
git add pics/brand tests/test_web_ui.py tests/js/README.md app.py
git commit -m "chore(web): brand assets, web-ui test harness, version 2.2.0"
```

---

## Task 2: Split the inline script into contiguous modules (byte-preserving)

The 4,438-line inline `<script>` becomes five files. This step changes **no
JavaScript** — the concatenation of the five files must equal the original
script body exactly. That invariant is what makes it safe.

**Files:**
- Create: `shared/assets/js/bb-engine.js`, `shared/assets/js/legacy-results.js`, `shared/assets/js/legacy-questions.js`, `shared/assets/js/legacy-modals.js`, `shared/assets/js/bb-scraper.js`
- Modify: `index.html` (replace the inline `<script>` block with five `<script src>` tags), `tests/test_web_ui.py`

**Interfaces:**
- Consumes: `_auth` from Task 1.
- Produces: five globally-scoped legacy modules. All previously-global functions (e.g. `startAnalysis`, `handleEvent`, `renderUnitaryTable`, `openQuestionSetHub`, `switchMainTab`, `startCityScraperResearch`) remain `window` globals, unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_ui.py`:

```python
JS_DIR = BASE / 'shared' / 'assets' / 'js'

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
    caching, and the module split — the page may only reference sources."""
    headers = _auth(client)
    resp = client.get('/', headers=headers)
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    inline = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)
    meaningful = [b for b in inline if len(b.strip()) > 0]
    assert meaningful == [], f'{len(meaningful)} inline script block(s) remain in index.html'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_web_ui.py -q`
Expected: FAIL — 5 parametrized 404s plus `1 inline script block(s) remain`.

- [ ] **Step 3: Extract the script into five files, byte-preserving**

The inline script body is `index.html` lines 954–5390 (the line after `<script>`
at 953 through the line before `</script>` at 5391). Cut points are chosen on
the existing section-comment boundaries. Run this from the repo root — it does
the split mechanically so no bytes are retyped:

```bash
cd "C:/Users/pr0ph/Documents/AI LLC/Apps/Doc Analysis Projects/Non-Buildout and Branded/2026/BidBrief"
python - <<'PY'
from pathlib import Path

src = Path('index.html').read_text(encoding='utf-8').split('\n')
# 0-indexed slice bounds, derived from the 1-indexed line numbers above.
body = src[953:5390]          # lines 954..5390 inclusive
cuts = [
    ('shared/assets/js/bb-engine.js',       0,    2361 - 954 + 1),
    ('shared/assets/js/legacy-results.js',  2362 - 954, 2945 - 954 + 1),
    ('shared/assets/js/legacy-questions.js',2946 - 954, 3705 - 954 + 1),
    ('shared/assets/js/legacy-modals.js',   3706 - 954, 4593 - 954 + 1),
    ('shared/assets/js/bb-scraper.js',      4594 - 954, len(body)),
]
joined = []
for path, start, end in cuts:
    chunk = '\n'.join(body[start:end])
    Path(path).write_text(chunk + '\n', encoding='utf-8')
    joined.append(chunk)
assert '\n'.join(joined) == '\n'.join(body), 'SPLIT IS NOT BYTE-PRESERVING'
print('split OK:', sum(len(c.split(chr(10))) for c in joined), 'lines')
PY
```

Expected output: `split OK: 4437 lines` (and no AssertionError).

Then in `index.html`, replace lines 953 and 5391 (`<script>` … `</script>`) so the
block becomes exactly:

```html
    <script src="/shared/assets/js/bb-engine.js"></script>
    <script src="/shared/assets/js/legacy-results.js"></script>
    <script src="/shared/assets/js/legacy-questions.js"></script>
    <script src="/shared/assets/js/legacy-modals.js"></script>
    <script src="/shared/assets/js/bb-scraper.js"></script>
```

Note the tags are NOT `defer`/`module`: they run in order at the point they
appear (after the markup they touch, exactly as the inline block did).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_web_ui.py -q`
Expected: PASS — 10 passed.

- [ ] **Step 5: Verify the page still boots in a real browser**

Start the app with a throwaway login, then drive it with Playwright:

```bash
AUTH_USER1_EMAIL=admin@test.local AUTH_USER1_PASSWORD=testpass123 \
  python -c "from app import app; app.run(port=5111, debug=False)" &
```

With the Playwright MCP tools: navigate to `http://127.0.0.1:5111/login`, fill
`admin@test.local` / `testpass123`, submit, then call
`browser_console_messages`.
Expected: the analyzer page renders as before and the console has **no**
`ReferenceError` / `Uncaught` entries.

- [ ] **Step 6: Commit**

```bash
git add index.html shared/assets/js tests/test_web_ui.py
git commit -m "refactor(web): extract inline script into five modules (byte-preserving)"
```

---

## Task 3: Design-system CSS + UI helpers

**Files:**
- Create: `shared/assets/css/bb-theme.css`
- Create: `shared/assets/js/bb-ui.js`
- Create: `tests/js/_harness.js`, `tests/js/bb-ui.test.js`
- Modify: `tests/test_web_ui.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - CSS classes consumed by every later task: `.bb-glass-card`, `.bb-hub-btn`, `.bb-btn-glow`, `.bb-btn-ghost`, `.bb-stage-header`, `.bb-eyebrow`, `.bb-back-chip`, `.bb-field`, `.bb-banner`, `.bb-tabbar`, `.bb-tab`, `.bb-next-chip`, `.bb-throb`, `.bb-breathe`, `.bb-stage`, `.bb-divider`, `.bb-toggle`.
  - `window.BB.ui` with: `el(tag, attrs, children) -> HTMLElement`, `html(strings, ...values) -> string` (escaping interpolations), `escapeHtml(s) -> string`, `formatFileSize(bytes) -> string`, `banner(kind, text)` (kind `'info'|'error'`), `setThrob(element, active)`, `qs(sel)`, `qsa(sel)`.

- [ ] **Step 1: Write the failing JS test harness + test**

Create `tests/js/_harness.js`:

```js
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..', '..');

/**
 * Evaluate one or more browser scripts against a minimal fake window and
 * return the shared BB namespace they built. `overrides` lets a test supply
 * stubs (localStorage, fetch, document) before the modules run.
 */
function loadModules(relPaths, overrides = {}) {
  const store = new Map();
  const win = {
    BB: {},
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
      clear: () => store.clear(),
    },
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    console,
    setTimeout,
    clearTimeout,
  };
  win.window = win;
  Object.assign(win, overrides);
  const ctx = vm.createContext(win);
  for (const rel of [].concat(relPaths)) {
    const code = fs.readFileSync(path.join(ROOT, rel), 'utf8');
    vm.runInContext(code, ctx, { filename: rel });
  }
  return { BB: ctx.BB || ctx.window.BB, win: ctx };
}

module.exports = { loadModules, ROOT };
```

Create `tests/js/bb-ui.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const { BB } = loadModules('shared/assets/js/bb-ui.js');

test('escapeHtml neutralises markup', () => {
  assert.strictEqual(
    BB.ui.escapeHtml('<img src=x onerror="alert(1)">&'),
    '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;'
  );
});

test('escapeHtml passes plain text through untouched', () => {
  assert.strictEqual(BB.ui.escapeHtml('Bonds & Insurance'), 'Bonds &amp; Insurance');
});

test('formatFileSize picks the right unit', () => {
  assert.strictEqual(BB.ui.formatFileSize(512), '512 B');
  assert.strictEqual(BB.ui.formatFileSize(2048), '2.00 KB');
  assert.strictEqual(BB.ui.formatFileSize(5 * 1024 * 1024), '5.00 MB');
});

test('html tagged template escapes interpolated values', () => {
  const name = '<script>bad</script>';
  assert.strictEqual(
    BB.ui.html`<p>${name}</p>`,
    '<p>&lt;script&gt;bad&lt;/script&gt;</p>'
  );
});

test('html tagged template leaves BB.ui.raw() values alone', () => {
  const markup = BB.ui.raw('<b>ok</b>');
  assert.strictEqual(BB.ui.html`<p>${markup}</p>`, '<p><b>ok</b></p>');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/`
Expected: FAIL — `ENOENT: no such file or directory ... shared/assets/js/bb-ui.js`.

- [ ] **Step 3: Write `bb-ui.js`**

Create `shared/assets/js/bb-ui.js`:

```js
/* BidBrief UI primitives — shared DOM + formatting helpers.
   Classic script: attaches to window.BB.ui, no module system. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var RAW = '__bb_raw__';

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /** Mark a string as already-safe markup for the html`` template. */
  function raw(markup) {
    return { type: RAW, value: String(markup == null ? '' : markup) };
  }

  /** Tagged template that escapes every interpolation except raw() values. */
  function html(strings) {
    var out = strings[0];
    for (var i = 1; i < arguments.length; i++) {
      var v = arguments[i];
      if (v && v.type === RAW) out += v.value;
      else if (Array.isArray(v)) out += v.map(function (x) {
        return (x && x.type === RAW) ? x.value : escapeHtml(x);
      }).join('');
      else out += escapeHtml(v);
      out += strings[i];
    }
    return out;
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  }

  function qs(sel, root) { return (root || window.document).querySelector(sel); }
  function qsa(sel, root) {
    return Array.prototype.slice.call((root || window.document).querySelectorAll(sel));
  }

  function el(tag, attrs, children) {
    var node = window.document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'class') node.className = attrs[k];
      else if (k === 'html') node.innerHTML = attrs[k];
      else if (k.slice(0, 2) === 'on') node.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] != null) node.setAttribute(k, attrs[k]);
    });
    [].concat(children || []).forEach(function (child) {
      if (child == null) return;
      node.appendChild(typeof child === 'string'
        ? window.document.createTextNode(child) : child);
    });
    return node;
  }

  /** Bottom toast. kind: 'info' (green) | 'error' (red). Auto-dismisses. */
  function banner(kind, text) {
    var host = qs('#bb-banner-host');
    if (!host) return;
    var node = el('div', { class: 'bb-banner bb-banner-' + kind }, text);
    host.appendChild(node);
    window.setTimeout(function () {
      node.classList.add('bb-banner-out');
      window.setTimeout(function () { node.remove(); }, 300);
    }, kind === 'info' ? 2500 : 4000);
  }

  /** The onboarding cue: grow/throb + flashing glow (iOS throbbingCue). */
  function setThrob(node, active) {
    if (!node) return;
    node.classList.toggle('bb-throb', !!active);
  }

  BB.ui = {
    escapeHtml: escapeHtml, raw: raw, html: html,
    formatFileSize: formatFileSize,
    qs: qs, qsa: qsa, el: el, banner: banner, setThrob: setThrob
  };
})(typeof window !== 'undefined' ? window : this);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/`
Expected: PASS — `# pass 5`.

- [ ] **Step 5: Write `bb-theme.css`**

Create `shared/assets/css/bb-theme.css`. Tokens first, then the primitives — a
direct port of `Sources/DesignSystem/Theme.swift` and `Components.swift`:

```css
/* BidBrief design system — ported from the iOS app (BBTheme + Components).
   Every colour here is the exact hex used by Sources/DesignSystem/Theme.swift. */
:root {
  --bb-space-deep: #050E24;
  --bb-space-navy: #0A1F55;
  --bb-brand-navy: #104090;
  --bb-periwinkle: #5E86D0;
  --bb-glow-ice: #45B4F2;
  --bb-success: #22C55E;
  --bb-warn: #FF9800;
  --bb-danger: #DC2626;
  --bb-glass-fill: rgba(255, 255, 255, 0.08);
  --bb-glass-strong: rgba(255, 255, 255, 0.14);
  --bb-glass-stroke: rgba(255, 255, 255, 0.18);
  --bb-text-primary: #FFFFFF;
  --bb-text-secondary: rgba(255, 255, 255, 0.65);
  --bb-text-tertiary: rgba(255, 255, 255, 0.40);
  --bb-radius-card: 18px;
  --bb-radius-hub: 20px;
  --bb-font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: var(--bb-font);
  background: var(--bb-space-deep);
  color: var(--bb-text-primary);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

/* ---- Glass surfaces ---- */
.bb-glass-card {
  padding: 16px;
  border-radius: var(--bb-radius-card);
  background:
    linear-gradient(rgba(16, 64, 144, 0.18), rgba(16, 64, 144, 0.18)),
    rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(18px) saturate(140%);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  border: 1px solid transparent;
  border-image: linear-gradient(135deg,
      rgba(255, 255, 255, 0.35),
      var(--bb-glass-stroke),
      rgba(94, 134, 208, 0.30)) 1;
  box-shadow: 0 10px 16px rgba(5, 14, 36, 0.60),
              0 4px 24px rgba(94, 134, 208, 0.18);
}

.bb-eyebrow {
  font-size: 11px; font-weight: 700; letter-spacing: 1.6px;
  text-transform: uppercase; color: var(--bb-text-tertiary);
  display: block; margin-bottom: 8px;
}

.bb-divider { height: 1px; background: var(--bb-glass-stroke); border: 0; }

/* ---- Buttons ---- */
.bb-btn-glow {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  width: 100%; padding: 14px 22px; border: 1px solid rgba(255, 255, 255, 0.55);
  border-radius: 999px; cursor: pointer;
  font: 600 16px/1.2 var(--bb-font); color: #fff;
  background: linear-gradient(135deg, rgba(69, 180, 242, 0.9), var(--bb-periwinkle), var(--bb-brand-navy));
  box-shadow: 0 6px 18px rgba(94, 134, 208, 0.6);
  transition: transform .12s ease, box-shadow .2s ease, opacity .2s ease;
}
.bb-btn-glow:hover:not(:disabled) { box-shadow: 0 8px 30px rgba(94, 134, 208, 0.8); }
.bb-btn-glow:active:not(:disabled) { transform: scale(.97); }
.bb-btn-glow:disabled { opacity: .5; cursor: not-allowed; }
.bb-btn-glow.bb-pulses:not(:disabled) { animation: bb-breathe 2.2s ease-in-out infinite; }

.bb-btn-ghost {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 11px 18px; border-radius: 999px; cursor: pointer;
  font: 500 14px/1.2 var(--bb-font);
  color: var(--bb-glow-ice); background: var(--bb-glass-fill);
  border: 1px solid rgba(69, 180, 242, 0.35);
  transition: transform .12s ease, background .2s ease;
}
.bb-btn-ghost:active { transform: scale(.97); }
.bb-btn-ghost:disabled { opacity: .5; cursor: not-allowed; }
.bb-btn-ghost.bb-success { color: var(--bb-success); border-color: rgba(34, 197, 94, .35); }
.bb-btn-ghost.bb-danger  { color: var(--bb-danger);  border-color: rgba(220, 38, 38, .35); }

/* Hub button — the glowing entry point of a stage. */
.bb-hub-btn {
  display: flex; align-items: center; gap: 16px; width: 100%; text-align: left;
  padding: 18px; border-radius: var(--bb-radius-hub); cursor: pointer;
  background:
    linear-gradient(rgba(16, 64, 144, 0.22), rgba(16, 64, 144, 0.22)),
    rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(18px);
  border: 1px solid rgba(69, 180, 242, 0.45);
  box-shadow: 0 9px 14px rgba(5, 14, 36, 0.6);
  color: var(--bb-text-primary);
  animation: bb-breathe 2.2s ease-in-out infinite;
}
.bb-hub-btn .bb-hub-icon {
  flex: 0 0 44px; height: 44px; border-radius: 50%;
  display: grid; place-items: center; font-size: 20px;
  color: var(--bb-glow-ice); background: rgba(16, 64, 144, 0.6);
  border: 1px solid rgba(69, 180, 242, 0.45);
}
.bb-hub-btn .bb-hub-title { font-size: 16px; font-weight: 600; }
.bb-hub-btn .bb-hub-sub { font-size: 12px; color: var(--bb-text-secondary); margin-top: 3px; }
.bb-hub-btn .bb-hub-chevron { margin-left: auto; color: var(--bb-text-tertiary); }
.bb-hub-btn.bb-primary { transform: scale(1.04); box-shadow: 0 0 22px rgba(69, 180, 242, 0.55); }

/* ---- Stage chrome ---- */
.bb-stage-header { text-align: center; animation: bb-rise .6s ease-out both; }
.bb-stage-header h1 {
  font-size: 34px; font-weight: 700; letter-spacing: -0.5px;
  text-shadow: 0 0 18px rgba(94, 134, 208, 0.55);
}
.bb-stage-header p {
  margin-top: 6px; font-size: 14px; color: var(--bb-text-secondary);
}
.bb-back-chip {
  display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
  padding: 8px 14px; border-radius: 999px; font: 600 13px/1 var(--bb-font);
  color: var(--bb-glow-ice); background: var(--bb-glass-strong);
  border: 1px solid var(--bb-glass-stroke);
}

/* ---- Fields ---- */
.bb-field, .bb-field textarea, .bb-field input, .bb-field select {
  font-family: var(--bb-font);
}
.bb-field {
  padding: 13px; border-radius: 12px;
  background: var(--bb-glass-strong); border: 1px solid var(--bb-glass-stroke);
}
.bb-field textarea, .bb-field input, .bb-field select {
  width: 100%; border: 0; background: transparent; outline: none; resize: vertical;
  color: var(--bb-text-primary); font-size: 14px;
}
.bb-field textarea::placeholder, .bb-field input::placeholder { color: var(--bb-text-tertiary); }
.bb-field select option { background: var(--bb-space-navy); color: #fff; }

/* ---- Toggle (iOS switch) ---- */
.bb-toggle { display: flex; align-items: center; gap: 12px; cursor: pointer; }
.bb-toggle input { appearance: none; width: 46px; height: 28px; flex: 0 0 46px;
  border-radius: 999px; background: var(--bb-glass-strong);
  border: 1px solid var(--bb-glass-stroke); position: relative;
  cursor: pointer; transition: background .2s ease; }
.bb-toggle input::after {
  content: ''; position: absolute; top: 2px; left: 2px; width: 22px; height: 22px;
  border-radius: 50%; background: #fff; transition: transform .2s ease;
}
.bb-toggle input:checked { background: var(--bb-periwinkle); border-color: var(--bb-periwinkle); }
.bb-toggle input:checked::after { transform: translateX(18px); }

/* ---- Banner ---- */
#bb-banner-host {
  position: fixed; left: 50%; transform: translateX(-50%);
  bottom: 92px; z-index: 3000; display: flex; flex-direction: column; gap: 8px;
  align-items: center; pointer-events: none;
}
.bb-banner {
  padding: 10px 16px; border-radius: 999px; font: 700 13px/1 var(--bb-font);
  color: #fff; animation: bb-rise .25s ease-out both;
}
.bb-banner-info  { background: rgba(34, 197, 94, .92);  box-shadow: 0 0 10px rgba(34,197,94,.6); }
.bb-banner-error { background: rgba(220, 38, 38, .92);  box-shadow: 0 0 10px rgba(220,38,38,.6); }
.bb-banner-out { opacity: 0; transition: opacity .3s ease; }

/* ---- Tab bar ---- */
.bb-tabbar {
  position: fixed; left: 50%; transform: translateX(-50%); bottom: 10px;
  z-index: 2500; display: flex; gap: 4px; padding: 5px;
  border-radius: 999px; background: rgba(10, 31, 85, 0.72);
  border: 1px solid var(--bb-glass-stroke);
  backdrop-filter: blur(18px); width: min(520px, calc(100% - 48px));
}
.bb-tab {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 9px 4px; border: 0; border-radius: 999px; cursor: pointer;
  background: transparent; color: var(--bb-text-tertiary);
  font: 600 10px/1 var(--bb-font); position: relative;
}
.bb-tab .bb-tab-icon { font-size: 17px; line-height: 1; }
.bb-tab.bb-active {
  color: var(--bb-glow-ice); background: rgba(94, 134, 208, 0.22);
  box-shadow: 0 0 10px rgba(94, 134, 208, 0.55);
}
.bb-tab.bb-nudged { color: var(--bb-glow-ice); }
.bb-next-chip {
  position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
  padding: 2px 7px; border-radius: 999px; background: var(--bb-glow-ice);
  color: var(--bb-space-deep); font: 700 9px/1.4 var(--bb-font);
}

/* ---- Animations ---- */
@keyframes bb-breathe {
  0%, 100% { transform: scale(1);     box-shadow: 0 0 14px rgba(94, 134, 208, .30); }
  50%      { transform: scale(1.035); box-shadow: 0 0 30px rgba(94, 134, 208, .75); }
}
@keyframes bb-throb {
  0%, 100% { transform: scale(1);    opacity: .86;
             box-shadow: 0 0 8px rgba(69, 180, 242, .35); }
  50%      { transform: scale(1.09); opacity: 1;
             box-shadow: 0 0 22px rgba(69, 180, 242, .95), 0 0 40px rgba(69, 180, 242, .5); }
}
@keyframes bb-rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes bb-fade-scale { from { opacity: 0; transform: scale(.94); } to { opacity: 1; transform: none; } }

.bb-throb { animation: bb-throb .9s ease-in-out infinite; }
.bb-breathe { animation: bb-breathe 2.2s ease-in-out infinite; }
.bb-stage { animation: bb-fade-scale .35s ease-out both; }

@media (prefers-reduced-motion: reduce) {
  .bb-throb, .bb-breathe, .bb-hub-btn, .bb-btn-glow.bb-pulses,
  .bb-stage, .bb-stage-header, .bb-banner { animation: none !important; }
  .bb-hub-btn.bb-primary { transform: none; }
}
```

- [ ] **Step 6: Add the served-asset assertion**

Append to `tests/test_web_ui.py`:

```python
@pytest.mark.parametrize('path,needle', [
    ('/shared/assets/css/bb-theme.css', '--bb-glow-ice: #45B4F2'),
    ('/shared/assets/js/bb-ui.js', 'BB.ui ='),
])
def test_design_system_assets_served(client, path, needle):
    resp = client.get(path)
    assert resp.status_code == 200, f'{path} not served'
    assert needle in resp.data.decode('utf-8')
```

- [ ] **Step 7: Run both suites**

Run: `python -m pytest tests/test_web_ui.py -q && node --test tests/js/`
Expected: pytest `12 passed`; node `# pass 5`.

- [ ] **Step 8: Commit**

```bash
git add shared/assets/css/bb-theme.css shared/assets/js/bb-ui.js tests/
git commit -m "feat(web): iOS design system in CSS + UI primitives"
```

---

## Task 4: The suspended-planet background

Ports `Sources/DesignSystem/OrbBackground.swift`: graded space field, deterministic
starfield, atmospheric halo, planet body lit from the upper-left, rim light,
btools mark high-centred, specular gleam, orbital ring at −14°, distant moon, and
top/bottom legibility scrims. `drift` shifts the planet against the active tab so
switching tabs reads as orbiting it.

**Files:**
- Create: `shared/assets/css/bb-orb.css`, `shared/assets/js/bb-orb.js`
- Create: `tests/js/bb-orb.test.js`
- Modify: `tests/test_web_ui.py`

**Interfaces:**
- Consumes: tokens from `bb-theme.css`.
- Produces: `window.BB.orb` with `mount(hostElement)` (paints the starfield canvas once) and `setDrift(driftUnits)` (number, typically −1.5…1.5; moves the planet and its lighting). Markup contract: the host element must contain `.bb-orb-planet`, `.bb-orb-halo`, `.bb-orb-mark`, `.bb-orb-gleam`, `.bb-orb-ring`, `.bb-orb-moon`, `canvas.bb-orb-stars`. `BB.orb.starPoints(count, w, h)` is the pure, deterministic star generator (exported for the test).

- [ ] **Step 1: Write the failing test**

Create `tests/js/bb-orb.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const { BB } = loadModules(['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-orb.js']);

test('starPoints is deterministic — same input, same field', () => {
  const a = BB.orb.starPoints(90, 800, 600);
  const b = BB.orb.starPoints(90, 800, 600);
  assert.deepStrictEqual(a, b);
});

test('starPoints returns the requested count inside the canvas bounds', () => {
  const pts = BB.orb.starPoints(90, 800, 600);
  assert.strictEqual(pts.length, 90);
  for (const p of pts) {
    assert.ok(p.x >= 0 && p.x <= 800, `x out of bounds: ${p.x}`);
    assert.ok(p.y >= 0 && p.y <= 600, `y out of bounds: ${p.y}`);
    assert.ok(p.r > 0 && p.r < 3, `radius out of range: ${p.r}`);
    assert.ok(p.opacity > 0 && p.opacity <= 1, `opacity out of range: ${p.opacity}`);
  }
});

test('driftFor spaces tabs symmetrically around centre (iOS HomeView.drift)', () => {
  // 4 tabs -> -1.5, -0.5, 0.5, 1.5
  assert.deepStrictEqual(
    [0, 1, 2, 3].map((i) => BB.orb.driftFor(i, 4)),
    [-1.5, -0.5, 0.5, 1.5]
  );
  // 3 tabs -> -1, 0, 1
  assert.deepStrictEqual([0, 1, 2].map((i) => BB.orb.driftFor(i, 3)), [-1, 0, 1]);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/bb-orb.test.js`
Expected: FAIL — `ENOENT ... bb-orb.js`.

- [ ] **Step 3: Write `bb-orb.js`**

```js
/* The signature element: a luminous planet suspended in deep space behind every
   screen. Ported from Sources/DesignSystem/OrbBackground.swift — the star field
   uses the same deterministic sin-hash so it never shimmers between renders. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  function frac(x) { var v = x % 1; return v < 0 ? -v : v; }

  /** Deterministic star specks — no randomness, stable across renders. */
  function starPoints(count, width, height) {
    var pts = [];
    for (var i = 0; i < count; i++) {
      var n = i;
      var x = frac(Math.sin(n * 12.9898) * 43758.5453);
      var y = frac(Math.sin(n * 78.233) * 96321.9134);
      pts.push({
        x: x * width,
        y: y * height,
        r: 0.6 + Math.abs(x * y) * 1.6,
        opacity: 0.2 + y * 0.45
      });
    }
    return pts;
  }

  /** Drift in page units for tab `index` of `count` (iOS HomeView.drift). */
  function driftFor(index, count) {
    return index - (count - 1) / 2;
  }

  var host = null;

  function paintStars() {
    if (!host) return;
    var canvas = host.querySelector('canvas.bb-orb-stars');
    if (!canvas || !canvas.getContext) return;
    var w = canvas.width = host.offsetWidth;
    var h = canvas.height = host.offsetHeight;
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    starPoints(90, w, h).forEach(function (p) {
      ctx.fillStyle = 'rgba(255,255,255,' + p.opacity.toFixed(3) + ')';
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function mount(hostElement) {
    host = hostElement;
    paintStars();
    window.addEventListener('resize', paintStars);
    setDrift(0);
  }

  /** Shift the planet and its lighting; CSS custom properties do the work. */
  function setDrift(units) {
    if (!host) return;
    host.style.setProperty('--bb-drift', String(units));
  }

  BB.orb = { mount: mount, setDrift: setDrift, starPoints: starPoints, driftFor: driftFor };
})(typeof window !== 'undefined' ? window : this);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/bb-orb.test.js`
Expected: PASS — `# pass 3`.

- [ ] **Step 5: Write `bb-orb.css`**

```css
/* The suspended planet. Fixed behind everything; --bb-drift (page units, set by
   BB.orb.setDrift) slides the planet and its lighting when the tab changes. */
.bb-orb-host {
  position: fixed; inset: 0; z-index: -1; overflow: hidden;
  --bb-drift: 0;
  --bb-orb-size: min(100vw, 760px);
  --bb-orb-x: calc(50% - var(--bb-drift) * 12vw);
  --bb-orb-y: 30vh;
  background: radial-gradient(circle at 50% 20%, var(--bb-space-navy) 0%, var(--bb-space-deep) 85%);
  transition: none;
}
.bb-orb-host > * { position: absolute; transition: left .45s ease, transform .45s ease; }

.bb-orb-stars { inset: 0; width: 100%; height: 100%; pointer-events: none; }

.bb-orb-halo {
  width: calc(var(--bb-orb-size) * 1.3); height: calc(var(--bb-orb-size) * 1.3);
  left: var(--bb-orb-x); top: var(--bb-orb-y); transform: translate(-50%, -50%);
  border-radius: 50%; background: var(--bb-periwinkle);
  filter: blur(70px); opacity: .33;
  animation: bb-orb-breathe 3.4s ease-in-out infinite;
}

.bb-orb-planet {
  width: var(--bb-orb-size); height: var(--bb-orb-size);
  left: var(--bb-orb-x); top: var(--bb-orb-y); transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle at calc(34% - var(--bb-drift) * 8%) 26%,
    var(--bb-glow-ice) 4%, var(--bb-periwinkle) 34%, var(--bb-brand-navy) 62%, #050C24 100%);
  box-shadow: 0 0 45px rgba(94, 134, 208, .45),
              inset 2px 2px 0 -1px rgba(69, 180, 242, .9);
  animation: bb-orb-breathe 3.4s ease-in-out infinite;
}

.bb-orb-mark {
  width: calc(var(--bb-orb-size) * .34); height: auto;
  left: var(--bb-orb-x);
  top: calc(var(--bb-orb-y) - var(--bb-orb-size) * .10);
  transform: translate(-50%, -50%);
  opacity: .88; filter: drop-shadow(0 0 22px rgba(69, 180, 242, .55));
  pointer-events: none;
}

.bb-orb-gleam {
  width: calc(var(--bb-orb-size) * .5); height: calc(var(--bb-orb-size) * .34);
  left: calc(var(--bb-orb-x) - var(--bb-orb-size) * .17 - var(--bb-drift) * 18px);
  top: calc(var(--bb-orb-y) - var(--bb-orb-size) * .24);
  transform: translate(-50%, -50%);
  border-radius: 50%; filter: blur(14px);
  background: radial-gradient(circle, rgba(255,255,255,.55) 0%, transparent 70%);
}

.bb-orb-ring {
  width: calc(var(--bb-orb-size) * 1.5); height: calc(var(--bb-orb-size) * .44);
  left: var(--bb-orb-x);
  top: calc(var(--bb-orb-y) + var(--bb-orb-size) * .06);
  transform: translate(-50%, -50%) rotate(-14deg);
  border-radius: 50%; opacity: .75; background: transparent;
  border: 1.6px solid transparent;
  border-image: linear-gradient(to right,
    rgba(69,180,242,.55), rgba(94,134,208,.10), rgba(69,180,242,.35)) 1;
}

.bb-orb-moon {
  width: 26px; height: 26px; border-radius: 50%; opacity: .85;
  left: calc(86% + var(--bb-drift) * 12px); top: 66vh;
  background: radial-gradient(circle at 35% 30%,
    rgba(255,255,255,.6) 0%, rgba(94,134,208,.3) 45%, transparent 75%);
}

/* Legibility scrims: gentle at the top (titles), stronger at the bottom. */
.bb-orb-scrim-top {
  inset: 0 0 auto 0; height: 30vh;
  background: linear-gradient(to bottom, rgba(5,14,36,.55), transparent);
}
.bb-orb-scrim-bottom {
  inset: auto 0 0 0; height: 58vh;
  background: linear-gradient(to bottom, transparent, rgba(5,14,36,.72));
}

@keyframes bb-orb-breathe {
  0%, 100% { transform: translate(-50%, -50%) scale(1); }
  50%      { transform: translate(-50%, -50%) scale(1.02); }
}

@media (prefers-reduced-motion: reduce) {
  .bb-orb-halo, .bb-orb-planet { animation: none; }
  .bb-orb-host > * { transition: none; }
}
```

- [ ] **Step 6: Add the served-asset assertion and run everything**

Add `('/shared/assets/css/bb-orb.css', '.bb-orb-planet')` and
`('/shared/assets/js/bb-orb.js', 'starPoints')` to the
`test_design_system_assets_served` parametrize list.

Run: `python -m pytest tests/test_web_ui.py -q && node --test tests/js/`
Expected: pytest `14 passed`; node `# pass 8`.

- [ ] **Step 7: Commit**

```bash
git add shared/assets/css/bb-orb.css shared/assets/js/bb-orb.js tests/
git commit -m "feat(web): suspended-planet background with per-tab parallax"
```

---

## Task 5: `BB.state` — AppModels parity

The single source of truth for the guided flow, mirroring
`Sources/App/AppModels.swift` + `QuestionHubModel.isConfirmed`. The
`onboardingHint` rules — including the 2.1.3 regression fix — live here.

**Files:**
- Create: `shared/assets/js/bb-state.js`
- Create: `tests/js/bb-state.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `window.BB.state` with:
  - `analysis`: `{ phase, uploadId, filename, file, sessionId, hasPendingDocument, needsQuestionChoice, enabledSections (array|null), contextGuardrails, mode, highPower, enableSecondPass, recheckEmptyWindows, enableDeepRAG, results, events }`
  - `questionHub`: `{ config, isConfirmed, currentSetSummary(), loadedSetSummary() }`
  - `session`: `{ username, role, isAdmin, hasPremium }`
  - `navigation`: `{ selectedTab }` (`'analyze' | 'questions' | 'admin' | 'settings'`)
  - `onboardingHint()` → `'none' | 'chooseQuestions' | 'goAnalyze' | 'startAnalysis'`
  - `setConfirmed(bool)` — persists to `localStorage['bb.questionSetConfirmed']` and, when `true`, clears `analysis.needsQuestionChoice` (the iOS `onConfirmSet` hook)
  - `beginChoosing()` — sets `isConfirmed = false`
  - `noteFreshUpload(file)` — sets `hasPendingDocument = true`, `needsQuestionChoice = true`
  - `subscribe(fn)` / `notify()` — re-render hook
  - `reset()` — clears analysis state back to idle

- [ ] **Step 1: Write the failing test**

Create `tests/js/bb-state.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

function fresh() {
  return loadModules(['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js']).BB.state;
}

test('no document waiting -> no cue', () => {
  const s = fresh();
  assert.strictEqual(s.onboardingHint(), 'none');
});

test('a fresh upload cues Questions', () => {
  const s = fresh();
  s.noteFreshUpload({ name: 'bid.pdf' });
  assert.strictEqual(s.onboardingHint(), 'chooseQuestions');
});

test('an unconfirmed set cues Questions even with a document', () => {
  const s = fresh();
  s.noteFreshUpload({ name: 'bid.pdf' });
  s.analysis.needsQuestionChoice = false;
  assert.strictEqual(s.onboardingHint(), 'chooseQuestions');
});

test('REGRESSION 2.1.3: creating a set clears the pending choice and advances to Analyze', () => {
  const s = fresh();
  s.noteFreshUpload({ name: 'bid.pdf' });
  s.navigation.selectedTab = 'questions';
  s.setConfirmed(true);                       // confirm from the Questions tab
  assert.strictEqual(s.analysis.needsQuestionChoice, false,
    'confirming a set must resolve the upload question-choice');
  assert.strictEqual(s.onboardingHint(), 'goAnalyze');
});

test('on the Analyze tab with a confirmed set the cue becomes startAnalysis', () => {
  const s = fresh();
  s.noteFreshUpload({ name: 'bid.pdf' });
  s.setConfirmed(true);
  s.navigation.selectedTab = 'analyze';
  assert.strictEqual(s.onboardingHint(), 'startAnalysis');
});

test('a NEW upload re-cues Questions even after a set was confirmed', () => {
  const s = fresh();
  s.setConfirmed(true);
  s.noteFreshUpload({ name: 'second.pdf' });
  assert.strictEqual(s.onboardingHint(), 'chooseQuestions');
});

test('beginChoosing un-confirms the set', () => {
  const s = fresh();
  s.setConfirmed(true);
  s.beginChoosing();
  assert.strictEqual(s.questionHub.isConfirmed, false);
});

test('confirmation persists across reloads via localStorage', () => {
  const store = new Map();
  const fakeStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  const first = loadModules(
    ['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js'],
    { localStorage: fakeStorage }
  ).BB.state;
  first.setConfirmed(true);

  const second = loadModules(
    ['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js'],
    { localStorage: fakeStorage }
  ).BB.state;
  assert.strictEqual(second.questionHub.isConfirmed, true);
});

test('currentSetSummary counts only a confirmed set; loadedSetSummary always counts', () => {
  const s = fresh();
  s.questionHub.config = {
    sections: [
      { section_id: 'a', section_name: 'A', questions: [{ id: 'q1' }, { id: 'q2' }] },
      { section_id: 'b', section_name: 'B', questions: [{ id: 'q3' }] },
    ],
  };
  assert.strictEqual(s.questionHub.currentSetSummary(), null);
  assert.deepStrictEqual(s.questionHub.loadedSetSummary(), { sections: 2, questions: 3 });
  s.setConfirmed(true);
  assert.deepStrictEqual(s.questionHub.currentSetSummary(), { sections: 2, questions: 3 });
});

test('subscribers are notified on state changes', () => {
  const s = fresh();
  let calls = 0;
  s.subscribe(() => { calls += 1; });
  s.setConfirmed(true);
  assert.ok(calls > 0, 'setConfirmed must notify subscribers');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/bb-state.test.js`
Expected: FAIL — `ENOENT ... bb-state.js`.

- [ ] **Step 3: Write `bb-state.js`**

```js
/* BB.state — the web mirror of the iOS AppModels (analysis + questionHub +
   navigation). The onboarding cue rules live here and nowhere else. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var CONFIRMED_KEY = 'bb.questionSetConfirmed';

  function storage() {
    try { return window.localStorage; } catch (e) { return null; }
  }

  function readConfirmed() {
    var s = storage();
    return !!(s && s.getItem(CONFIRMED_KEY) === 'true');
  }

  function countSections(config) {
    if (!config || !config.sections || !config.sections.length) return null;
    return {
      sections: config.sections.length,
      questions: config.sections.reduce(function (sum, sec) {
        return sum + ((sec.questions && sec.questions.length) || 0);
      }, 0)
    };
  }

  var listeners = [];

  var state = {
    session: { username: '', role: 'user', isAdmin: false, hasPremium: false },

    navigation: { selectedTab: 'analyze' },

    analysis: {
      phase: 'idle',            // idle | uploading | configuring | analyzing | done | failed
      file: null,               // the File object chosen in the browser
      filename: '',
      uploadId: null,
      sessionId: null,
      hasPendingDocument: false,
      needsQuestionChoice: false,
      enabledSections: null,    // null = "not yet chosen"; otherwise an explicit array
      contextGuardrails: '',
      mode: 'bid_spec',
      highPower: false,
      enableSecondPass: false,
      recheckEmptyWindows: false,
      enableDeepRAG: false,
      pipelineMode: 'classic',
      results: null,
      events: [],
      errorMessage: null
    },

    questionHub: {
      config: null,
      isConfirmed: readConfirmed(),
      currentSetSummary: function () {
        return state.questionHub.isConfirmed ? countSections(state.questionHub.config) : null;
      },
      loadedSetSummary: function () {
        return countSections(state.questionHub.config);
      }
    },

    subscribe: function (fn) { listeners.push(fn); return fn; },

    notify: function () {
      listeners.forEach(function (fn) {
        try { fn(state); } catch (e) { (window.console || {}).error && window.console.error(e); }
      });
    },

    /** A freshly attached PDF: the "which questions?" decision reopens. */
    noteFreshUpload: function (file) {
      state.analysis.file = file || null;
      state.analysis.filename = (file && file.name) || '';
      state.analysis.hasPendingDocument = true;
      state.analysis.needsQuestionChoice = true;
      state.notify();
    },

    /** Confirming a set resolves that decision — the iOS onConfirmSet hook.
        Never gate the Analyze cue on isConfirmed alone (regression 2.1.3). */
    setConfirmed: function (confirmed) {
      state.questionHub.isConfirmed = !!confirmed;
      var s = storage();
      if (s) s.setItem(CONFIRMED_KEY, confirmed ? 'true' : 'false');
      if (confirmed) state.analysis.needsQuestionChoice = false;
      state.notify();
    },

    beginChoosing: function () { state.setConfirmed(false); },

    reset: function () {
      var a = state.analysis;
      a.phase = 'idle'; a.file = null; a.filename = ''; a.uploadId = null;
      a.sessionId = null; a.hasPendingDocument = false; a.needsQuestionChoice = false;
      a.enabledSections = null; a.results = null; a.events = []; a.errorMessage = null;
      state.notify();
    },

    /** Only nudge once a document is waiting to be analyzed. */
    onboardingHint: function () {
      if (!state.analysis.hasPendingDocument) return 'none';
      if (state.analysis.needsQuestionChoice || !state.questionHub.isConfirmed) {
        return 'chooseQuestions';
      }
      return state.navigation.selectedTab === 'analyze' ? 'startAnalysis' : 'goAnalyze';
    },

    /** Prune a stored selection against the section ids that actually exist. */
    prunedSelection: function (selection, validIds) {
      if (!selection) return null;
      var valid = {};
      validIds.forEach(function (id) { valid[id] = true; });
      var kept = selection.filter(function (id) { return valid[id]; });
      return kept.length ? kept : null;
    }
  };

  BB.state = state;
})(typeof window !== 'undefined' ? window : this);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/bb-state.test.js`
Expected: PASS — `# pass 10`.

- [ ] **Step 5: Commit**

```bash
git add shared/assets/js/bb-state.js tests/js/bb-state.test.js
git commit -m "feat(web): BB.state — AppModels parity incl. 2.1.3 cue rules"
```

---

## Task 6: The app shell — tab bar, routing, onboarding cue

Replaces the navbar + two-tab layout with the iOS shell: a centred app column
over the orb, four pages, and a floating capsule tab bar that shows a throbbing
"Next" chip on the tab the user should visit.

**Files:**
- Modify: `index.html` (head + body shell; the analyzer/cityscraper markup moves into pages)
- Create: `shared/assets/js/bb-shell.js`
- Create: `tests/js/bb-shell.test.js`
- Modify: `tests/test_web_ui.py`

**Interfaces:**
- Consumes: `BB.ui`, `BB.orb`, `BB.state`.
- Produces: `window.BB.shell` with `init()`, `go(tabId)`, `renderTabBar()`, `tabsFor(session)` → array of `{ id, label, icon }`, `registerPage(tabId, renderFn)`. Page containers in the DOM: `#bb-page-analyze`, `#bb-page-questions`, `#bb-page-admin`, `#bb-page-settings`. `BB.shell.loadUserInfo()` fetches `/api/user/info` and fills `BB.state.session` (`is_admin`, `premium`/`bonus_features`).

- [ ] **Step 1: Write the failing test**

Create `tests/js/bb-shell.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const MODULES = [
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-orb.js',
  'shared/assets/js/bb-shell.js',
];

function ids(tabs) { return tabs.map((t) => t.id); }

test('plain users get three tabs — no Admin slot', () => {
  const { BB } = loadModules(MODULES);
  assert.deepStrictEqual(
    ids(BB.shell.tabsFor({ isAdmin: false, hasPremium: false })),
    ['analyze', 'questions', 'settings']
  );
});

test('admins get the Admin tab', () => {
  const { BB } = loadModules(MODULES);
  const tabs = BB.shell.tabsFor({ isAdmin: true, hasPremium: false });
  assert.deepStrictEqual(ids(tabs), ['analyze', 'questions', 'admin', 'settings']);
  assert.strictEqual(tabs[2].label, 'Admin');
});

test('bonus-features users get the same slot relabelled Bonus', () => {
  const { BB } = loadModules(MODULES);
  const tabs = BB.shell.tabsFor({ isAdmin: false, hasPremium: true });
  assert.deepStrictEqual(ids(tabs), ['analyze', 'questions', 'admin', 'settings']);
  assert.strictEqual(tabs[2].label, 'Bonus');
});

test('nudgedTab maps the hint to a tab and never nudges the current tab', () => {
  const { BB } = loadModules(MODULES);
  BB.state.noteFreshUpload({ name: 'x.pdf' });
  BB.state.navigation.selectedTab = 'analyze';
  assert.strictEqual(BB.shell.nudgedTab(), 'questions');

  BB.state.navigation.selectedTab = 'questions';
  assert.strictEqual(BB.shell.nudgedTab(), null, 'never nudge the tab you are on');

  BB.state.setConfirmed(true);
  assert.strictEqual(BB.shell.nudgedTab(), 'analyze');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/bb-shell.test.js`
Expected: FAIL — `ENOENT ... bb-shell.js`.

- [ ] **Step 3: Write `bb-shell.js`**

```js
/* The app shell: four pages over the orb + a floating capsule tab bar that
   throbs a "Next" chip on the tab the guided flow wants next.
   Mirrors Sources/Features/Home/HomeView.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var ALL_TABS = {
    analyze:   { id: 'analyze',   label: 'Analyze',  icon: '\uD83D\uDD0D' }, /* magnifier */
    questions: { id: 'questions', label: 'Questions', icon: '\uD83D\uDCCB' }, /* clipboard */
    admin:     { id: 'admin',     label: 'Admin',    icon: '\uD83D\uDD11' }, /* key */
    bonus:     { id: 'admin',     label: 'Bonus',    icon: '\u2728' },        /* sparkles */
    settings:  { id: 'settings',  label: 'Settings', icon: '\u2699\uFE0F' }   /* gear */
  };

  var pages = {};

  /** Admins get Admin; Bonus users get the same slot relabelled. */
  function tabsFor(session) {
    var tabs = [ALL_TABS.analyze, ALL_TABS.questions];
    if (session && session.isAdmin) tabs.push(ALL_TABS.admin);
    else if (session && session.hasPremium) tabs.push(ALL_TABS.bonus);
    tabs.push(ALL_TABS.settings);
    return tabs;
  }

  var HINT_TAB = { chooseQuestions: 'questions', goAnalyze: 'analyze' };

  function nudgedTab() {
    var target = HINT_TAB[BB.state.onboardingHint()] || null;
    if (!target) return null;
    return target === BB.state.navigation.selectedTab ? null : target;
  }

  function renderTabBar() {
    var host = ui.qs('#bb-tabbar');
    if (!host) return;
    var tabs = tabsFor(BB.state.session);
    var nudge = nudgedTab();
    host.innerHTML = '';
    tabs.forEach(function (tab, index) {
      var active = BB.state.navigation.selectedTab === tab.id;
      var nudged = nudge === tab.id;
      var btn = ui.el('button', {
        class: 'bb-tab' + (active ? ' bb-active' : '') + (nudged ? ' bb-nudged bb-throb' : ''),
        type: 'button',
        'data-tab': tab.id,
        'aria-current': active ? 'page' : null,
        onclick: function () { go(tab.id); }
      }, [
        nudged ? ui.el('span', { class: 'bb-next-chip' }, 'Next') : null,
        ui.el('span', { class: 'bb-tab-icon' }, tab.icon),
        ui.el('span', {}, tab.label)
      ]);
      btn.dataset.index = String(index);
      host.appendChild(btn);
    });
  }

  function go(tabId) {
    BB.state.navigation.selectedTab = tabId;
    var tabs = tabsFor(BB.state.session);
    var index = 0;
    tabs.forEach(function (t, i) { if (t.id === tabId) index = i; });
    BB.orb.setDrift(BB.orb.driftFor(index, tabs.length));

    ui.qsa('.bb-page').forEach(function (page) {
      var mine = page.id === 'bb-page-' + tabId;
      page.hidden = !mine;
      if (mine) { page.classList.remove('bb-stage'); void page.offsetWidth; page.classList.add('bb-stage'); }
    });
    if (pages[tabId]) pages[tabId]();
    renderTabBar();
    BB.state.notify();
  }

  function registerPage(tabId, renderFn) { pages[tabId] = renderFn; }

  /** Fill BB.state.session from /api/user/info (is_admin + premium/bonus). */
  function loadUserInfo() {
    return window.fetch('/api/user/info')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) return;
        BB.state.session.username = data.username || data.email || '';
        BB.state.session.role = data.role || 'user';
        BB.state.session.isAdmin = !!data.is_admin;
        BB.state.session.hasPremium = !!(data.is_admin || data.premium ||
          (data.bonus_features && data.bonus_features.length));
        renderTabBar();
        BB.state.notify();
      })
      .catch(function () { /* stay a plain user */ });
  }

  function init() {
    BB.orb.mount(ui.qs('#bb-orb'));
    BB.state.subscribe(renderTabBar);
    renderTabBar();
    go('analyze');
    loadUserInfo();
  }

  BB.shell = {
    init: init, go: go, registerPage: registerPage,
    renderTabBar: renderTabBar, tabsFor: tabsFor, nudgedTab: nudgedTab,
    loadUserInfo: loadUserInfo
  };
})(typeof window !== 'undefined' ? window : this);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/bb-shell.test.js`
Expected: PASS — `# pass 4`.

- [ ] **Step 5: Rewrite `index.html` as the shell**

The whole file becomes (legacy screen markup moves inside the page containers;
`#bb-page-analyze` keeps the ids the legacy engine writes to until Tasks 7–9
replace them):

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="color-scheme" content="dark">
    <title>BidBrief — AI Document Analysis</title>
    <link rel="icon" type="image/png" href="/pics/AILLCfavicon.png">
    <link rel="stylesheet" href="/shared/assets/css/bb-theme.css">
    <link rel="stylesheet" href="/shared/assets/css/bb-orb.css">
    <link rel="stylesheet" href="/shared/assets/css/bb-screens.css">
    <script src="https://cdn.sheetjs.com/xlsx-0.20.1/package/dist/xlsx.full.min.js"></script>
</head>
<body>
    <!-- The suspended planet, behind everything. -->
    <div id="bb-orb" class="bb-orb-host" aria-hidden="true">
        <canvas class="bb-orb-stars"></canvas>
        <div class="bb-orb-halo"></div>
        <div class="bb-orb-planet"></div>
        <img class="bb-orb-mark" src="/pics/brand/btools-iconlogo-nobg.png" alt="">
        <div class="bb-orb-gleam"></div>
        <div class="bb-orb-ring"></div>
        <div class="bb-orb-moon"></div>
        <div class="bb-orb-scrim-top"></div>
        <div class="bb-orb-scrim-bottom"></div>
    </div>

    <main class="bb-app">
        <section id="bb-page-analyze"   class="bb-page"></section>
        <section id="bb-page-questions" class="bb-page" hidden></section>
        <section id="bb-page-admin"     class="bb-page" hidden></section>
        <section id="bb-page-settings"  class="bb-page" hidden></section>
    </main>

    <nav id="bb-tabbar" class="bb-tabbar" aria-label="Primary"></nav>
    <div id="bb-banner-host"></div>

    <!-- Modals (hidden until opened) -->
    <div id="bb-modal-host"></div>
    <!-- ... existing modal containers: questionManagerModal, answerDetailModal,
         fullViewModal, aboutModal — markup unchanged, restyled by CSS ... -->

    <script src="/shared/assets/js/bb-ui.js"></script>
    <script src="/shared/assets/js/bb-orb.js"></script>
    <script src="/shared/assets/js/bb-state.js"></script>
    <script src="/shared/assets/js/bb-status.js"></script>
    <script src="/shared/assets/js/bb-shell.js"></script>
    <script src="/shared/assets/js/bb-engine.js"></script>
    <script src="/shared/assets/js/legacy-results.js"></script>
    <script src="/shared/assets/js/legacy-questions.js"></script>
    <script src="/shared/assets/js/legacy-modals.js"></script>
    <script src="/shared/assets/js/bb-analyze.js"></script>
    <script src="/shared/assets/js/bb-progress.js"></script>
    <script src="/shared/assets/js/bb-results.js"></script>
    <script src="/shared/assets/js/bb-libraries.js"></script>
    <script src="/shared/assets/js/bb-questionhub.js"></script>
    <script src="/shared/assets/js/bb-qgen.js"></script>
    <script src="/shared/assets/js/bb-admin.js"></script>
    <script src="/shared/assets/js/bb-settings.js"></script>
    <script src="/shared/assets/js/bb-scraper.js"></script>
    <script src="/shared/assets/js/bb-boot.js"></script>
</body>
</html>
```

Create `shared/assets/js/bb-boot.js` (the only entry point):

```js
/* Entry point: wire the pages into the shell, then start it. */
(function (window) {
  'use strict';
  var BB = window.BB;
  window.document.addEventListener('DOMContentLoaded', function () {
    BB.shell.registerPage('analyze', BB.analyze.render);
    BB.shell.registerPage('questions', BB.questionHub.render);
    BB.shell.registerPage('admin', BB.admin.render);
    BB.shell.registerPage('settings', BB.settings.render);
    BB.shell.init();
  });
})(window);
```

Add the app-column layout to `shared/assets/css/bb-screens.css` (created here,
extended by later tasks):

```css
.bb-app {
  max-width: 900px; margin: 0 auto;
  padding: 28px 20px 120px;   /* bottom clears the floating tab bar */
  min-height: 100vh;
}
.bb-page { display: flex; flex-direction: column; gap: 18px; }
.bb-page[hidden] { display: none; }
.bb-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.bb-stack { display: flex; flex-direction: column; gap: 14px; }
@media (max-width: 640px) { .bb-app { padding: 18px 14px 120px; } }
```

- [ ] **Step 6: Extend the pytest structure test**

Append to `tests/test_web_ui.py`:

```python
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
```

- [ ] **Step 7: Run everything**

Run: `python -m pytest -q && node --test tests/js/`
Expected: pytest `≥82 passed`; node `# pass 22`.

- [ ] **Step 8: Commit**

```bash
git add index.html shared/assets tests/
git commit -m "feat(web): iOS app shell — orb pages, capsule tab bar, Next cue"
```

---

## Task 7: Analyze screen — idle, uploading, configure

Ports `Sources/Features/Analyze/UploadConfigureView.swift`. Note the deliberate
ordering: **Start Analysis sits directly below Context Guardrails and above the
section list**, and is disabled until a question set is confirmed.

**Files:**
- Create: `shared/assets/js/bb-analyze.js`
- Create: `tests/js/bb-analyze.test.js`
- Modify: `shared/assets/css/bb-screens.css` (upload orb, configure layout)
- Modify: `shared/assets/js/bb-engine.js` (delete the superseded `handleFileSelect`, `displayQuestionSections`, `toggleSection`, `updateActiveQuestionCount`, `startAnalysis` DOM wiring; keep the network calls, now called by `BB.analyze`)

**Interfaces:**
- Consumes: `BB.state`, `BB.ui`, `BB.shell`.
- Produces: `window.BB.analyze` with:
  - `render()` — draws the stage for `BB.state.analysis.phase` into `#bb-page-analyze`
  - `buildAnalyzePayload(state, uploadId, filename)` → the exact `/api/analyze` JSON body
  - `chooseFile(file)`, `start()`, `reset()`
  - `loadSections()` — GETs `/api/config/questions`, prunes `enabledSections`

- [ ] **Step 1: Write the failing test**

Create `tests/js/bb-analyze.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const MODULES = [
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-orb.js',
  'shared/assets/js/bb-shell.js',
  'shared/assets/js/bb-analyze.js',
];

function setup() {
  const { BB } = loadModules(MODULES);
  BB.state.questionHub.config = {
    sections: [
      { section_id: 's1', section_name: 'Bonds', questions: [{ id: 'q1' }] },
      { section_id: 's2', section_name: 'Schedule', questions: [{ id: 'q2' }] },
      { section_id: 's3', section_name: 'Insurance', questions: [{ id: 'q3' }] },
    ],
  };
  return BB;
}

test('WYSIWYG: an explicit selection is sent verbatim', () => {
  const BB = setup();
  BB.state.analysis.enabledSections = ['s1', 's3'];
  const body = BB.analyze.buildAnalyzePayload(BB.state, 'up-1', 'bid.pdf');
  assert.deepStrictEqual(body.enabled_sections, ['s1', 's3']);
});

test('WYSIWYG: a FULL selection is still sent explicitly, never collapsed to null', () => {
  const BB = setup();
  BB.state.analysis.enabledSections = ['s1', 's2', 's3'];
  const body = BB.analyze.buildAnalyzePayload(BB.state, 'up-1', 'bid.pdf');
  assert.deepStrictEqual(body.enabled_sections, ['s1', 's2', 's3'],
    'collapsing a full selection is the bug that leaked deselections into analysis');
});

test('no selection yet means every section in the loaded config', () => {
  const BB = setup();
  BB.state.analysis.enabledSections = null;
  const body = BB.analyze.buildAnalyzePayload(BB.state, 'up-1', 'bid.pdf');
  assert.deepStrictEqual(body.enabled_sections, ['s1', 's2', 's3']);
});

test('payload carries upload id, filename, guardrails, mode and the advanced flags', () => {
  const BB = setup();
  BB.state.analysis.contextGuardrails = '  Only CIPP lining  ';
  BB.state.analysis.mode = 'bestprep';
  BB.state.analysis.enableSecondPass = true;
  BB.state.analysis.recheckEmptyWindows = true;
  BB.state.analysis.enableDeepRAG = false;
  const body = BB.analyze.buildAnalyzePayload(BB.state, 'up-9', 'spec.pdf');
  assert.strictEqual(body.upload_id, 'up-9');
  assert.strictEqual(body.pdf_filename, 'spec.pdf');
  assert.strictEqual(body.context_guardrails, 'Only CIPP lining');
  assert.strictEqual(body.mode, 'bestprep');
  assert.strictEqual(body.enable_second_pass, true);
  assert.strictEqual(body.recheck_empty_windows, true);
  assert.strictEqual(body.enable_deep_rag, false);
  assert.strictEqual(body.pipeline_mode, 'classic');
});

test('empty guardrails are omitted, not sent as an empty string', () => {
  const BB = setup();
  BB.state.analysis.contextGuardrails = '   ';
  const body = BB.analyze.buildAnalyzePayload(BB.state, 'up-1', 'bid.pdf');
  assert.strictEqual('context_guardrails' in body, false);
});

test('high_power is only sent when the user actually has premium', () => {
  const BB = setup();
  BB.state.analysis.highPower = true;
  BB.state.session.hasPremium = false;
  assert.strictEqual('high_power' in BB.analyze.buildAnalyzePayload(BB.state, 'u', 'f.pdf'), false,
    'sending high_power without premium earns a 403');
  BB.state.session.hasPremium = true;
  assert.strictEqual(BB.analyze.buildAnalyzePayload(BB.state, 'u', 'f.pdf').high_power, true);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/bb-analyze.test.js`
Expected: FAIL — `ENOENT ... bb-analyze.js`.

- [ ] **Step 3: Write `bb-analyze.js`**

The payload builder is the tested core; the renderers draw the stages described
below it.

```js
/* Analyze tab: idle -> uploading -> configuring -> analyzing -> done | failed.
   Ports Sources/Features/Analyze/UploadConfigureView.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  /** The exact /api/analyze body. enabled_sections is ALWAYS explicit. */
  function buildAnalyzePayload(state, uploadId, filename) {
    var a = state.analysis;
    var allIds = ((state.questionHub.config || {}).sections || []).map(function (s) {
      return s.section_id;
    });
    var enabled = a.enabledSections && a.enabledSections.length
      ? a.enabledSections.slice()
      : allIds;

    var body = {
      upload_id: uploadId,
      pdf_filename: filename,
      enabled_sections: enabled,
      mode: a.mode,
      recheck_empty_windows: !!a.recheckEmptyWindows,
      enable_second_pass: !!a.enableSecondPass,
      enable_deep_rag: !!a.enableDeepRAG,
      pipeline_mode: a.pipelineMode || 'classic'
    };
    var guard = (a.contextGuardrails || '').trim();
    if (guard) body.context_guardrails = guard;
    // High Power is entitlement-gated server-side (403) — only send it when held.
    if (a.highPower && state.session.hasPremium) body.high_power = true;
    return body;
  }

  BB.analyze = {
    buildAnalyzePayload: buildAnalyzePayload,
    render: render, chooseFile: chooseFile, start: start,
    reset: reset, loadSections: loadSections
  };
  /* ... render/chooseFile/start/reset/loadSections defined below ... */
})(typeof window !== 'undefined' ? window : this);
```

The renderers produce this structure (all classes from Task 3):

- **idle** — centred `.bb-stage-header` ("Analyze" / "Upload a bid specification
  PDF to begin."), then a 132px circular gradient button
  (`.bb-upload-orb.bb-breathe`, same radial gradient as the planet) wrapping a
  hidden `<input type="file" accept=".pdf">`, then "Choose PDF" in `--bb-glow-ice`.
  Selecting a file calls `chooseFile(file)` → `BB.state.noteFreshUpload(file)`,
  POSTs `/api/upload`, and moves to `configuring`.
- **uploading** — `.bb-stage-header` "Uploading" + a `.bb-glass-card` holding a
  determinate progress bar with a monospaced percentage.
- **configuring** — in this exact order:
  1. `.bb-back-chip` "Different file" → `reset()`
  2. `.bb-stage-header` "Configure"
  3. the question-choice card, when `analysis.needsQuestionChoice` (three
     branches, copy verbatim from `UploadConfigureView.questionChoiceCard`):
     - confirmed set → "Use your current set (N sections · M questions) for this
       document, or choose a different one?" + **Keep current set** (ghost,
       success tint; clears `needsQuestionChoice`) / **Create / choose new**
       (ghost; clears the flag, `BB.state.beginChoosing()`, `BB.shell.go('questions')`)
     - only the loaded default → "Default questions are loaded (N sections · M
       questions). Proceed with the defaults, or create your own question set?" +
       **Proceed with defaults** (`BB.state.setConfirmed(true)`) / **Create a question set**
     - nothing loaded → "Pick or create a question set to analyze this document
       against." + **Choose questions** (`.bb-btn-glow`)
  4. Document card — `.bb-eyebrow` "Document" + the filename
  5. Analysis Mode segmented control — **only when `session.hasPremium`**
     (`Contracts/RFPs/Spec` vs `BestPrep/TestPrep`)
  6. `.bb-eyebrow` "Context Guardrails (Optional)" + a `.bb-field` textarea bound
     to `analysis.contextGuardrails` + the caption "Steer the analysis toward what
     matters for this document."
  7. **Start Analysis** — `.bb-btn-glow`, `disabled` + 0.5 opacity unless
     `questionHub.isConfirmed`; carries `.bb-pulses` when
     `BB.state.onboardingHint() === 'startAnalysis'`
  8. when confirmed: the Sections card — one `.bb-toggle` per section showing
     "N questions", caption "Only checked sections are analyzed."; toggling writes
     the **explicit** set into `analysis.enabledSections` (never nulls a full
     selection). When not confirmed: a `.bb-hub-btn` "Choose your questions /
     Pick or create the set to analyze this document against" → `BB.shell.go('questions')`
  9. Advanced card — three `.bb-toggle`s: "Second pass for unanswered questions",
     "Re-check empty windows", "Deep RAG (external search)"
  10. High Power card — only when `session.hasPremium`
- **failed** — warning glyph, "Analysis Problem" + message, "Start Over" (`.bb-btn-glow`).

`loadSections()` re-GETs `/api/config/questions` on every entry to the configure
stage and on every change of `questionHub.isConfirmed`, then
`analysis.enabledSections = BB.state.prunedSelection(analysis.enabledSections, ids)`
— a stale section list here is exactly how deselections used to leak into analysis.

`start()` POSTs `/api/upload` (if not already uploaded), then `/api/analyze` with
`buildAnalyzePayload(...)`, stores `session_id`, sets `phase = 'analyzing'`, and
hands off to `BB.progress.begin(sessionId)`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/bb-analyze.test.js`
Expected: PASS — `# pass 6`.

- [ ] **Step 5: Prune the superseded legacy code**

Delete from `shared/assets/js/bb-engine.js`: `handleFileSelect`,
`displayQuestionSections`, `toggleSection`, `updateActiveQuestionCount`,
`toggleAdvancedOptions`, and the DOM manipulation inside `startAnalysis`
(`analyzeBtn` / `stopBtn` / `fileInfo` / `liveResults` element writes). Keep
`Logger`, `ProgressTracker` (re-pointed at the new progress DOM in Task 8),
`startPolling`, `stopPolling`, `pollForEvents`, `handleEvent`, `fetchResults`,
`fetchPartialResults`, `stopAnalysis`, `checkAdminStatus` (now delegating to
`BB.shell.loadUserInfo`).

Verify nothing still calls the deleted names:

Run: `grep -rn "displayQuestionSections\|updateActiveQuestionCount\|handleFileSelect\|toggleAdvancedOptions" shared/assets/js index.html`
Expected: no output.

- [ ] **Step 6: Browser check**

With the local server running, use Playwright: log in, confirm the Analyze idle
stage renders the upload orb, upload a small PDF, and confirm the configure stage
shows Start Analysis **above** the sections card and disabled while unconfirmed.
Take a screenshot. Check `browser_console_messages` for errors.

- [ ] **Step 7: Commit**

```bash
git add shared/assets tests/js/bb-analyze.test.js
git commit -m "feat(web): Analyze stages — upload orb, guided configure, WYSIWYG sections"
```

---

## Task 8: Analysis progress — orb ring, phase track, Live Activity

Ports `AnalysisPhase.swift` + `AnalysisStatus` + `AnalysisProgressView.swift`.
This replaces the flat percentage bar and the always-visible debug log.

**Files:**
- Create: `shared/assets/js/bb-status.js`, `shared/assets/js/bb-progress.js`
- Create: `tests/js/bb-status.test.js`
- Modify: `shared/assets/css/bb-screens.css`
- Modify: `shared/assets/js/bb-engine.js` (`handleEvent` pushes into `BB.state.analysis.events` and calls `BB.progress.update()`)

**Interfaces:**
- Consumes: `BB.state`, `BB.ui`.
- Produces:
  - `window.BB.status` with `PHASES` (ordered array of `{ key, title, stepLabel, icon }`), `TRACK_STEPS` (the five track phases), `fromEvents(events)` → `{ phase, detail, fraction, windowNum, totalWindows }`, `friendlyLine(event)` → string|null.
  - `window.BB.progress` with `begin(sessionId)`, `update()`, `render()`, `openLiveActivity()`, `stop()`.

- [ ] **Step 1: Write the failing test**

Create `tests/js/bb-status.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const { BB } = loadModules(['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-status.js']);

const ev = (event, payload) => Object.assign({ event, timestamp: '' }, payload || {});

test('a fresh stream starts in preparing at a low fraction', () => {
  const s = BB.status.fromEvents([ev('analysis_started')]);
  assert.strictEqual(s.phase, 'preparing');
  assert.ok(s.fraction > 0 && s.fraction < 0.1);
});

test('experts_complete moves to analyzing at the window-band start', () => {
  const s = BB.status.fromEvents([ev('analysis_started'), ev('experts_complete')]);
  assert.strictEqual(s.phase, 'analyzing');
  assert.strictEqual(s.fraction, 0.12);
});

test('REGRESSION: key_requirements fires EARLY and must not jump the bar to 94%', () => {
  const s = BB.status.fromEvents([
    ev('analysis_started'),
    ev('key_requirements_start'),
    ev('key_requirements_complete'),
  ]);
  assert.ok(s.fraction <= 0.12,
    `key details must stay under the window band, got ${s.fraction}`);
});

test('windows own 12% -> 90% as equal slices', () => {
  const half = BB.status.fromEvents([
    ev('window_complete', { payload: { window_num: 5, total_windows: 10 } }),
  ]);
  assert.ok(Math.abs(half.fraction - (0.12 + 0.78 * 0.5)) < 1e-9,
    `expected 0.51, got ${half.fraction}`);

  const last = BB.status.fromEvents([
    ev('window_complete', { payload: { window_num: 10, total_windows: 10 } }),
  ]);
  assert.ok(Math.abs(last.fraction - 0.90) < 1e-9, `expected 0.90, got ${last.fraction}`);
});

test('analysis_complete is NOT the end — only results_ready completes', () => {
  const mid = BB.status.fromEvents([ev('analysis_complete')]);
  assert.ok(mid.fraction < 1, 'analysis_complete fires before results are packaged');
  assert.notStrictEqual(mid.phase, 'complete');

  const done = BB.status.fromEvents([ev('analysis_complete'), ev('results_ready')]);
  assert.strictEqual(done.phase, 'complete');
  assert.strictEqual(done.fraction, 1);
});

test('phase and fraction only ever move forward, whatever the event order', () => {
  const s = BB.status.fromEvents([
    ev('window_complete', { payload: { window_num: 9, total_windows: 10 } }),
    ev('prescan_start'),
  ]);
  assert.strictEqual(s.phase, 'analyzing');
  assert.ok(s.fraction > 0.5, 'a late-arriving early event must not rewind the bar');
});

test('friendlyLine narrates real events and stays silent on internals', () => {
  assert.match(
    BB.status.friendlyLine(ev('window_processing', { payload: { window_num: 2, total_windows: 8 } })),
    /window 2 of 8/i
  );
  assert.strictEqual(BB.status.friendlyLine(ev('layer_3_internal_thing')), null);
});

test('the track shows five steps, ending before "complete"', () => {
  assert.deepStrictEqual(
    BB.status.TRACK_STEPS.map((p) => p.key),
    ['preparing', 'experts', 'analyzing', 'verifying', 'finalizing']
  );
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/bb-status.test.js`
Expected: FAIL — `ENOENT ... bb-status.js`.

- [ ] **Step 3: Write `bb-status.js`**

A direct transcription of `AnalysisStatus.ingest` — every case, the same
fractions and the same copy:

```js
/* Rolls the raw event stream up into phase + friendly detail + progress.
   Pure and order-tolerant: fraction and phase only move forward.
   Transcribed from Sources/Features/Analyze/AnalysisPhase.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var WINDOW_BAND_START = 0.12;
  var WINDOW_BAND_SPAN = 0.78;   /* 12% -> 90% */

  var PHASES = [
    { key: 'preparing',  title: 'Reading Document',   stepLabel: 'Read',    icon: '\uD83D\uDCC4' },
    { key: 'experts',    title: 'Creating Experts',   stepLabel: 'Experts', icon: '\uD83D\uDC65' },
    { key: 'analyzing',  title: 'Analyzing',          stepLabel: 'Analyze', icon: '\uD83D\uDD0E' },
    { key: 'verifying',  title: 'Double-Checking',    stepLabel: 'Verify',  icon: '\uD83D\uDEE1\uFE0F' },
    { key: 'finalizing', title: 'Assembling Results', stepLabel: 'Finish',  icon: '\uD83D\uDCE6' },
    { key: 'complete',   title: 'Complete',           stepLabel: 'Done',    icon: '\u2705' }
  ];
  var RANK = {};
  PHASES.forEach(function (p, i) { RANK[p.key] = i; });

  function payloadOf(event) { return (event && event.payload) || {}; }
  function num(v) { return typeof v === 'number' ? v : (v == null ? null : parseInt(v, 10)); }

  function ingest(status, event) {
    var p = payloadOf(event);

    function advance(phase, fraction, detail) {
      if (RANK[phase] > RANK[status.phase]) status.phase = phase;
      if (fraction > status.fraction) status.fraction = Math.min(fraction, 1);
      if (detail != null) status.detail = detail;
    }

    switch (event.event) {
      case 'analysis_started': case 'processing_start': case 'pipeline_start':
        advance('preparing', 0.03, 'Starting the analysis pipeline'); break;
      case 'config_loaded':
        advance('preparing', 0.04, 'Question set loaded'); break;
      case 'prescan_start':
        advance('preparing', 0.05, 'Scanning the document'); break;
      case 'prescan_complete': case 'document_ingested': case 'layer_0_start':
        advance('preparing', 0.07, 'Reading the PDF'); break;
      case 'layer_1_start':
        advance('preparing', 0.08, 'Mapping the document structure'); break;
      case 'layer_2_start':
        advance('preparing', 0.09, 'Splitting into analysis windows'); break;

      case 'expert_generated': {
        var name = p.expert_name || 'expert';
        advance('experts', 0.09, p.section ? ('Created ' + name + ' for ' + p.section)
                                           : ('Created ' + name));
        break;
      }
      case 'experts_dispatched': {
        var count = num(p.expert_count);
        advance('experts', 0.10, count != null ? ('Dispatched ' + count + ' expert agents')
                                               : 'Expert agents dispatched');
        break;
      }
      case 'experts_complete':
        advance('analyzing', 0.12, 'Experts ready — analysis underway'); break;

      /* Key details run EARLY. Mapping them high was the old
         "jumps to 94% and stalls" bug — they must never outrank the window band. */
      case 'key_requirements_start':
        advance('experts', 0.10, 'Extracting key document details'); break;
      case 'key_requirements_complete': case 'key_requirements_failed':
        advance('experts', 0.12, 'Key details captured'); break;

      case 'window_processing': {
        var n = num(p.window_num), total = num(p.total_windows);
        if (n != null && total) {
          status.windowNum = n; status.totalWindows = total;
          var pages = p.pages ? String(p.pages) : '';
          advance('analyzing',
            WINDOW_BAND_START + WINDOW_BAND_SPAN * (n - 1) / total,
            pages ? ('Analyzing window ' + n + ' of ' + total + ' — pages ' + pages)
                  : ('Analyzing window ' + n + ' of ' + total));
        } else {
          advance('analyzing', status.fraction, 'Analyzing the document');
        }
        break;
      }
      case 'window_complete': case 'progress_milestone': {
        var done = num(p.window_num); if (done == null) done = num(p.windows_processed);
        var tot = num(p.total_windows); if (tot == null) tot = status.totalWindows;
        if (done != null && tot) {
          status.windowNum = done; status.totalWindows = tot;
          advance('analyzing', WINDOW_BAND_START + WINDOW_BAND_SPAN * done / tot,
                  done + ' of ' + tot + ' windows finished');
        }
        break;
      }

      case 'recheck_start':
        advance('verifying', 0.905, 'Re-checking windows that came back empty'); break;
      case 'recheck_window_processing': {
        var rn = num(p.recheck_num), rt = num(p.total_rechecks);
        if (rn != null && rt) {
          advance('verifying', 0.905 + 0.02 * rn / rt, 'Re-checking window ' + rn + ' of ' + rt);
        }
        break;
      }
      case 'recheck_complete':
        advance('verifying', 0.925, 'Re-check finished'); break;
      case 'second_pass_started': case 'second_pass_processing': {
        var un = num(p.unanswered_count);
        advance('verifying', 0.93, un != null
          ? ('Second pass on ' + un + ' unanswered questions')
          : 'Second pass on unanswered questions');
        break;
      }
      case 'second_pass_complete':
        advance('verifying', 0.955, 'Second pass complete'); break;
      case 'second_pass_failed':
        advance('verifying', 0.955, 'Second pass skipped'); break;

      case 'layer_6_start':
        advance('finalizing', 0.96, 'Cross-checking answers'); break;
      case 'layer_7_start': case 'stage_4_start':
        advance('finalizing', 0.965, 'Assembling the final report'); break;

      /* The orchestrator's completion fires BEFORE results are packaged. */
      case 'analysis_complete': case 'pipeline_complete':
      case 'stage_4_complete': case 'layer_7_complete':
        advance('finalizing', 0.97, 'Wrapping up — assembling final results'); break;
      case 'status':
        if (p.message) {
          advance('finalizing',
            String(p.message).toLowerCase().indexOf('intelligence') >= 0 ? 0.98 : status.fraction,
            p.message);
        }
        break;
      case 'results_ready': case 'done':
        advance('complete', 1.0, 'Analysis complete'); break;

      default: break;   /* stage_*/layer_* internals never move the story */
    }
  }

  function fromEvents(events) {
    var status = {
      phase: 'preparing', detail: 'Warming up the pipeline…',
      fraction: 0.02, windowNum: null, totalWindows: null
    };
    (events || []).forEach(function (e) { ingest(status, e); });
    return status;
  }

  /** One friendly feed line per event, or null for technical noise. */
  function friendlyLine(event) {
    var probe = { phase: 'preparing', detail: '', fraction: 0, windowNum: null, totalWindows: null };
    ingest(probe, event);
    return probe.detail === '' ? null : probe.detail;
  }

  BB.status = {
    PHASES: PHASES,
    TRACK_STEPS: PHASES.slice(0, 5),
    fromEvents: fromEvents,
    friendlyLine: friendlyLine,
    phaseInfo: function (key) { return PHASES[RANK[key]]; }
  };
})(typeof window !== 'undefined' ? window : this);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/bb-status.test.js`
Expected: PASS — `# pass 8`.

- [ ] **Step 5: Write `bb-progress.js` + its CSS**

`BB.progress.render()` draws, into `#bb-page-analyze`:
1. a 190px **progress orb ring**: an SVG circle (`stroke: var(--bb-glass-stroke)`)
   plus a trimmed arc using `stroke-dasharray`/`stroke-dashoffset` on an angular
   periwinkle→ice gradient (`stroke-linecap: round`, rotated −90°), a breathing
   planet disc inside it, and the percentage in the centre with a `.6s` ease
   transition on the offset
2. the phase title (`status.phase.title`), the detail line, and a live
   "M:SS elapsed" ticker
3. the **phase track** — five dots joined by 2px rules, past ones filled
   `--bb-periwinkle`, the current one `.bb-breathe` with a
   `rgba(94,134,208,.35)` disc, labels under each
4. **Live Activity** (`.bb-btn-glow`, non-pulsing) → a modal with the friendly
   narration feed (`BB.status.friendlyLine`, one glass row per line with icon +
   time), and — for admins only — an "Overview / Raw Events" segmented control
   that flips to the raw `event` + payload stream
5. **Stop and keep partial results** (`.bb-btn-ghost` warn tint) → `stopAnalysis()`

`BB.progress.update()` re-derives the status from `BB.state.analysis.events` and
patches only the numbers/labels (no full re-render, so the ring animates).

`bb-engine.js`'s `handleEvent` gains, at the top: `BB.state.analysis.events.push(event); BB.progress.update();`
and its `results_ready` branch sets `BB.state.analysis.phase = 'done'` then calls
`BB.results.render()`.

- [ ] **Step 6: Browser check**

Run a real analysis against the local server with a small PDF (or replay: in the
console, push synthetic events into `BB.state.analysis.events` and call
`BB.progress.update()`), screenshot the ring at ~50%, and confirm the phase track
lights up in order.

- [ ] **Step 7: Commit**

```bash
git add shared/assets tests/js/bb-status.test.js
git commit -m "feat(web): progress orb ring, phase track, Live Activity feed"
```

---

## Task 9: Results — staged overview and detail layers

Ports `Sources/Features/Analyze/ResultsView.swift`, keeping the web-only
full-width **Table** view (genuinely better on a desktop) as one more stage
rather than dropping it.

**Files:**
- Create: `shared/assets/js/bb-results.js`
- Create: `tests/js/bb-results.test.js`
- Modify: `shared/assets/css/bb-screens.css`
- Delete (after porting): `shared/assets/js/legacy-results.js`, `shared/assets/js/legacy-modals.js` — their unitary-table renderer and answer-detail/full-view modals move into `bb-results.js`, restyled onto glass

**Interfaces:**
- Consumes: `BB.state`, `BB.ui`, `BB.exportsMenu` (kept inside `bb-engine.js`).
- Produces: `window.BB.results` with `render()`, `push(stage)`, `back()`,
  `summarize(results)` → `{ answered, total, rate, pages, unanswered: [...] }`,
  `stages`: `overview | sections | sectionDetail | keyDetails | intelligence | bestprep | improve | actions | table`.

- [ ] **Step 1: Write the failing test**

Create `tests/js/bb-results.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const { BB } = loadModules([
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-results.js',
]);

const RESULTS = {
  document_name: 'Sewer Lining Spec.pdf',
  total_pages: 120,
  sections: [
    {
      section_id: 's1', section_name: 'Bonds',
      questions: [
        { question_id: 'q1', question: 'Bid bond %?', answer: '10%',
          answer_summary: 'A 10% bid bond is required.', page_citations: [4, 9],
          confidence: 'high' },
        { question_id: 'q2', question: 'Payment bond?', answer: '', page_citations: [] },
      ],
    },
    {
      section_id: 's2', section_name: 'Schedule',
      questions: [
        { question_id: 'q3', question: 'Completion date?', answer: 'June 1',
          page_citations: [22], confidence: 'medium' },
      ],
    },
  ],
};

test('summarize counts answered questions across sections', () => {
  const s = BB.results.summarize(RESULTS);
  assert.strictEqual(s.total, 3);
  assert.strictEqual(s.answered, 2);
  assert.strictEqual(s.rate, '67%');
  assert.strictEqual(s.pages, 120);
});

test('summarize lists the unanswered questions for the Improve stage', () => {
  const s = BB.results.summarize(RESULTS);
  assert.deepStrictEqual(s.unanswered.map((q) => q.question_id), ['q2']);
});

test('a question with a blank answer is not "answered"', () => {
  const s = BB.results.summarize({ sections: [{ questions: [{ answer: '   ' }] }] });
  assert.strictEqual(s.answered, 0);
});

test('answerSummaryOf returns the L6.5 summary, tolerating old cached results', () => {
  assert.strictEqual(
    BB.results.answerSummaryOf(RESULTS.sections[0].questions[0]),
    'A 10% bid bond is required.'
  );
  assert.strictEqual(BB.results.answerSummaryOf({ answer: 'x' }), null,
    'results cached before L6.5 have no answer_summary — decode tolerantly');
});

test('zero questions does not divide by zero', () => {
  const s = BB.results.summarize({ sections: [] });
  assert.strictEqual(s.total, 0);
  assert.strictEqual(s.rate, '—');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/bb-results.test.js`
Expected: FAIL — `ENOENT ... bb-results.js`.

- [ ] **Step 3: Write `bb-results.js`**

The tested core:

```js
/* Results — staged like the iOS ResultsView: an overview of glowing entry
   points, each fading into a focused layer with a back chip. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  function isAnswered(q) {
    return !!(q && typeof q.answer === 'string' && q.answer.trim().length);
  }

  /** L6.5 AnswerSummarizer output; absent on results cached before 2.1.0. */
  function answerSummaryOf(q) {
    var s = q && q.answer_summary;
    return (typeof s === 'string' && s.trim().length) ? s : null;
  }

  function summarize(results) {
    var questions = ((results && results.sections) || []).reduce(function (acc, sec) {
      return acc.concat(sec.questions || []);
    }, []);
    var answered = questions.filter(isAnswered).length;
    return {
      total: questions.length,
      answered: answered,
      rate: questions.length ? Math.round(answered / questions.length * 100) + '%' : '—',
      pages: (results && results.total_pages) || 0,
      unanswered: questions.filter(function (q) { return !isAnswered(q); })
    };
  }

  BB.results = {
    summarize: summarize, answerSummaryOf: answerSummaryOf, isAnswered: isAnswered,
    render: render, push: push, back: back
  };
  /* ... stage renderers below ... */
})(typeof window !== 'undefined' ? window : this);
```

Stages (each preceded by `.bb-back-chip` + `.bb-stage-header`, except the overview):

- **overview** — `.bb-eyebrow` "Results" + the document name in a glowing title;
  a three-cell stat card (`Answered N/M` · `Pages P` · `Rate R%`); then hub
  buttons, each rendered only when it has content:
  `Sections` (N sections of answers) · `Key Details` (when `key_requirements` or
  `footnotes`) · `Document Intelligence` (when `dynamic_tables`) · `BestPrep Detail`
  (bestprep mode with fragments) · `Improve Results` (N unanswered) ·
  `Table View` (every question in one sortable table — the web-only stage) ·
  `Exports & Analysis`; then "New Analysis" (`.bb-btn-ghost` danger).
- **sections** — one glass row per section, "N/M answered", chevron.
- **sectionDetail** — one `.bb-glass-card` per question: question text; answer
  (clamped to 3 lines, click to expand); the **Answer Summary** block —
  `.bb-answer-summary`, `rgba(94,134,208,.12)` fill with a
  `rgba(94,134,208,.35)` border, label "Answer Summary" in `--bb-glow-ice` —
  positioned **between the answer and the page citations**; then the confidence
  pill (high green / medium orange / low red) and "p. 4, 9"; unanswered questions
  read "Not found in document" in italic tertiary.
- **keyDetails** — "Document Facts" (key humanised, value) + "Footnotes".
- **intelligence** — one glass table per entry of `dynamic_tables`, with the
  focus caption above.
- **improve** — hub buttons "Second Pass" and "Deep RAG", each opening a
  multi-select modal listing the unanswered questions with **Select All**, then
  POSTing `/api/analyze/second-pass/<sid>` or `/api/analyze/rag/<sid>` with the
  chosen `question_ids` and re-fetching results.
- **actions** — the export menu (Excel Report Package / CSV / HTML / JSON, plus
  BestPrep Excel in bestprep mode) and **Smart Analysis** (`.bb-btn-glow`), which
  opens the existing Smart Analysis flow rendered onto glass.
- **table** — the ported unitary table on a dark glass surface: sticky header,
  `Section | Question | Answer | Answer Summary | Pages | Confidence`, row
  selection checkboxes feeding the same second-pass/RAG runs, and the existing
  answer-detail modal restyled.

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/bb-results.test.js`
Expected: PASS — `# pass 5`.

- [ ] **Step 5: Delete the superseded legacy modules**

```bash
git rm shared/assets/js/legacy-results.js shared/assets/js/legacy-modals.js
```

Remove their `<script>` tags from `index.html`, then verify no orphan callers:

Run: `grep -rn "renderUnitaryTable\|openAnswerDetailModal\|switchFullViewTab\|legacy-results\|legacy-modals" index.html shared/assets/js`
Expected: no output (or only definitions inside `bb-results.js`).

- [ ] **Step 6: Browser check + full suites**

Run: `python -m pytest -q && node --test tests/js/`
Expected: pytest `≥82 passed`; node all green.
Playwright: open a completed analysis (or stub `BB.state.analysis.results` in the
console and call `BB.results.render()`), walk overview → sections → a section,
and confirm the Answer Summary block sits between the answer and the citations.
Screenshot.

- [ ] **Step 7: Commit**

```bash
git add -A shared/assets index.html tests/js/bb-results.test.js
git commit -m "feat(web): staged results with answer summaries, intelligence, improve passes"
```

---

## Task 10: Question Hub — menu, current set, sections, questions, edit

Ports `QuestionHubView.swift` (menu, Sections, All Questions, Question edit) and
the confirmed-set gate from `QuestionHubModel`.

**Files:**
- Create: `shared/assets/js/bb-questionhub.js`
- Create: `tests/js/bb-questionhub.test.js`
- Modify: `shared/assets/css/bb-screens.css`
- Modify: `shared/assets/js/legacy-questions.js` (strip the old hub/manager UI; keep only the CRUD fetch helpers until they are absorbed)

**Interfaces:**
- Consumes: `BB.state`, `BB.ui`, `BB.libraries` (Task 12), `BB.qgen` (Task 11).
- Produces: `window.BB.questionHub` with `render()`, `push(stage)`, `back()`,
  `load()` (GET `/api/config/questions`), `save()` (PUT — **lossless**),
  `apply(config)`, `addSection(name)`, `renameSection(id, name)`,
  `addQuestion(sectionId, text)`, `updateQuestion(sectionId, id, text, enabled)`,
  `toggleQuestion(sectionId, id)`, `setSectionEnabled(sectionId, enabled)`,
  `proceedWithDefaults()`. Stages: `menu | sections | sectionDetail | allQuestions | questionEdit | generate | libraries`.

- [ ] **Step 1: Write the failing test**

Create `tests/js/bb-questionhub.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const MODULES = [
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-questionhub.js',
];

function withConfig() {
  const { BB } = loadModules(MODULES);
  BB.state.questionHub.config = {
    sections: [{
      section_id: 's1',
      section_name: 'Bonds',
      section_description: 'Surety requirements',
      section_summary: 'Bonding drives who can bid.',
      questions: [
        { id: 'q1', text: 'Bid bond %?', enabled: true, required: true, expected_type: 'percent' },
        { id: 'q2', text: 'Payment bond?', enabled: false },
      ],
    }],
  };
  return BB;
}

test('the PUT body round-trips unknown keys losslessly', () => {
  const BB = withConfig();
  const body = BB.questionHub.buildSaveBody(BB.state.questionHub.config);
  const section = body.sections[0];
  assert.strictEqual(section.section_description, 'Surety requirements',
    'section_description drives backend expert generation — never strip it');
  assert.strictEqual(section.section_summary, 'Bonding drives who can bid.');
  assert.strictEqual(section.questions[0].required, true);
  assert.strictEqual(section.questions[0].expected_type, 'percent',
    'expected_type drives backend expert generation — never strip it');
});

test('toggleQuestion flips only the named question', () => {
  const BB = withConfig();
  BB.questionHub.toggleQuestion('s1', 'q1');
  const qs = BB.state.questionHub.config.sections[0].questions;
  assert.strictEqual(qs[0].enabled, false);
  assert.strictEqual(qs[1].enabled, false);
});

test('setSectionEnabled turns every question in the section on or off', () => {
  const BB = withConfig();
  BB.questionHub.setSectionEnabled('s1', true);
  assert.deepStrictEqual(
    BB.state.questionHub.config.sections[0].questions.map((q) => q.enabled), [true, true]);
  BB.questionHub.setSectionEnabled('s1', false);
  assert.deepStrictEqual(
    BB.state.questionHub.config.sections[0].questions.map((q) => q.enabled), [false, false]);
});

test('addSection appends a section and confirms the set', () => {
  const BB = withConfig();
  BB.questionHub.addSection('Insurance');
  const sections = BB.state.questionHub.config.sections;
  assert.strictEqual(sections.length, 2);
  assert.strictEqual(sections[1].section_name, 'Insurance');
  assert.ok(sections[1].section_id, 'a new section needs an id');
  assert.strictEqual(BB.state.questionHub.isConfirmed, true,
    'adding a section is a genuine confirm path');
});

test('addSection ignores blank names', () => {
  const BB = withConfig();
  BB.questionHub.addSection('   ');
  assert.strictEqual(BB.state.questionHub.config.sections.length, 1);
});

test('addQuestion appends to the right section with a unique id', () => {
  const BB = withConfig();
  BB.questionHub.addQuestion('s1', 'Warranty period?');
  const qs = BB.state.questionHub.config.sections[0].questions;
  assert.strictEqual(qs.length, 3);
  assert.strictEqual(qs[2].text, 'Warranty period?');
  assert.strictEqual(qs[2].enabled, true);
  assert.notStrictEqual(qs[2].id, qs[0].id);
});

test('applying a config confirms the set (a genuine confirm path)', () => {
  const BB = withConfig();
  BB.state.setConfirmed(false);
  BB.questionHub.apply({ sections: [{ section_id: 'x', section_name: 'X', questions: [] }] });
  assert.strictEqual(BB.state.questionHub.isConfirmed, true);
});

test('proceedWithDefaults confirms without changing the loaded config', () => {
  const BB = withConfig();
  BB.state.setConfirmed(false);
  const before = JSON.stringify(BB.state.questionHub.config);
  BB.questionHub.proceedWithDefaults();
  assert.strictEqual(BB.state.questionHub.isConfirmed, true);
  assert.strictEqual(JSON.stringify(BB.state.questionHub.config), before);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/bb-questionhub.test.js`
Expected: FAIL — `ENOENT ... bb-questionhub.js`.

- [ ] **Step 3: Write `bb-questionhub.js`**

Core mutators (the tested surface):

```js
/* Question Hub — staged navigation over the orb.
   Ports Sources/Features/QuestionHub/QuestionHubView.swift + QuestionHubModel. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  function sectionById(id) {
    return ((BB.state.questionHub.config || {}).sections || []).filter(function (s) {
      return s.section_id === id;
    })[0];
  }

  function uid(prefix) {
    return prefix + '_' + Date.now().toString(36) + '_' +
      Math.floor(Math.random() * 1e6).toString(36);
  }

  /** The PUT body. Question config is a LOSSLESS round-tripper: unknown keys
      (required / expected_type / section_description / section_summary) drive
      backend expert generation, so we send the sections back untouched. */
  function buildSaveBody(config) {
    return { sections: (config && config.sections) || [] };
  }

  function toggleQuestion(sectionId, questionId) {
    var sec = sectionById(sectionId); if (!sec) return;
    (sec.questions || []).forEach(function (q) {
      if (q.id === questionId) q.enabled = !q.enabled;
    });
    BB.state.notify();
  }

  function setSectionEnabled(sectionId, enabled) {
    var sec = sectionById(sectionId); if (!sec) return;
    (sec.questions || []).forEach(function (q) { q.enabled = !!enabled; });
    BB.state.notify();
  }

  function addSection(name) {
    var clean = (name || '').trim(); if (!clean) return;
    var config = BB.state.questionHub.config || (BB.state.questionHub.config = { sections: [] });
    config.sections.push({ section_id: uid('sec'), section_name: clean, questions: [] });
    BB.state.setConfirmed(true);   /* a genuine confirm path */
  }

  function addQuestion(sectionId, text) {
    var clean = (text || '').trim(); if (!clean) return;
    var sec = sectionById(sectionId); if (!sec) return;
    (sec.questions = sec.questions || []).push({ id: uid('q'), text: clean, enabled: true });
    BB.state.notify();
  }

  function updateQuestion(sectionId, questionId, text, enabled) {
    var sec = sectionById(sectionId); if (!sec) return;
    (sec.questions || []).forEach(function (q) {
      if (q.id !== questionId) return;
      q.text = text; q.enabled = !!enabled;
    });
    BB.state.notify();
  }

  function renameSection(sectionId, name) {
    var clean = (name || '').trim(); if (!clean) return;
    var sec = sectionById(sectionId); if (sec) { sec.section_name = clean; BB.state.notify(); }
  }

  /** Replace the whole set — generate, library apply, upload. Confirms. */
  function apply(config) {
    BB.state.questionHub.config = config;
    (config.sections || []).forEach(function (s) {
      s.questions = s.questions || [];
      s.questions.forEach(function (q) { if (q.enabled === undefined) q.enabled = true; });
    });
    BB.state.setConfirmed(true);
  }

  /** The backend always physically holds a set; adopting it is the user's call. */
  function proceedWithDefaults() { BB.state.setConfirmed(true); }

  BB.questionHub = {
    buildSaveBody: buildSaveBody, toggleQuestion: toggleQuestion,
    setSectionEnabled: setSectionEnabled, addSection: addSection,
    addQuestion: addQuestion, updateQuestion: updateQuestion,
    renameSection: renameSection, apply: apply,
    proceedWithDefaults: proceedWithDefaults,
    render: render, push: push, back: back, load: load, save: save
  };
  /* ... load/save/render + stage renderers below ... */
})(typeof window !== 'undefined' ? window : this);
```

Stage renderers:

- **menu** — `.bb-stage-header` "Question Hub" / "Start here: build the set of
  questions to analyze your document against."; then
  1. **Create / Add Question Set** — `.bb-hub-btn.bb-primary` (enlarged, extra
     glow), subtitle "Paste questions, describe what to ask, or upload —
     BidBrief builds the set" → `push('generate')`
  2. **Libraries** — "Choose or save a question set" → `push('libraries')`
  3. **Current Question Set** — a disclosure whose subtitle is
     "N sections · M questions" from `currentSetSummary()`, or
     **"No set currently loaded"**. Expanded and confirmed → hub buttons
     **Sections** and **Questions**; expanded and unconfirmed → "Create or choose
     a set first."
- **sections** — one row per section (name, "E/T questions on", the AI
  `section_summary` in italic `--bb-glow-ice` when present) with a whole-section
  toggle; plus an "Add a Section" card (field + `.bb-btn-ghost`).
- **sectionDetail** — rename affordance, one `QuestionToggleRow` per question
  (click text to edit, switch to enable/disable), plus "Add a Question".
- **allQuestions** — every section's questions grouped under `.bb-eyebrow` labels.
- **questionEdit** — textarea + "Included in analyses" toggle + "Apply Changes".
- A bottom overlay shows **Save Question Set** (`.bb-btn-glow`) whenever the
  config is dirty, and hosts the info/error banners.

`load()` GETs `/api/config/questions`, defaults `enabled` to `true` per question,
and stores it **without** confirming (the backend always ships a set; adopting it
is the user's decision). `save()` PUTs `buildSaveBody(config)`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/bb-questionhub.test.js`
Expected: PASS — `# pass 8`.

- [ ] **Step 5: Browser check**

Playwright: open the Questions tab on a fresh profile → "No set currently
loaded"; expand Current Question Set → the "Create or choose a set first."
hint; add a section → the subtitle becomes "1 sections · 0 questions" and the
tab-bar cue moves off Questions. Screenshot.

- [ ] **Step 6: Commit**

```bash
git add shared/assets tests/js/bb-questionhub.test.js
git commit -m "feat(web): Question Hub — menu, current-set gate, sections, questions"
```

---

## Task 11: Create / Add Question Set — full iOS-parity generation

The biggest functional gap. The web today sends one file and prompts for
`source_intent` with `window.prompt`. This brings it to iOS 2.1.1/2.1.2 parity:
a Questions Source slot, a Document Context slot that **auto-adopts the analyzer
document**, Replace/Merge modes with an automatic library snapshot, the expert
panel card, and per-section suggestion selection.

**Files:**
- Create: `shared/assets/js/bb-qgen.js`
- Create: `tests/js/bb-qgen.test.js`
- Modify: `shared/assets/js/legacy-questions.js` → delete `showAIGenerateView`, `generateAIQuestions`, `fetchAdditionalQuestions`, `applyAdditionalQuestions`, `openQuestionSetHub`, `showHubHome`, `loadCIPPQuestionSet` (all superseded)

**Interfaces:**
- Consumes: `BB.state`, `BB.questionHub`, `BB.libraries`, `BB.ui`.
- Produces: `window.BB.qgen` with:
  - `buildGeneratePayload({ userText, contextFile, questionsSourceFile, sourceIntent, questionsSourceText })` → `{ kind: 'json'|'multipart', fields: {...}, files: { file?, context_file? } }`
  - `render()`, `generate()`, `suggestAdditional()`, `acceptSuggestions(ids)`

- [ ] **Step 1: Write the failing test**

Create `tests/js/bb-qgen.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const { BB } = loadModules([
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-qgen.js',
]);

const pdf = (name) => ({ name, type: 'application/pdf' });
const txt = (name) => ({ name, type: 'text/plain' });

test('text only -> a plain JSON request', () => {
  const p = BB.qgen.buildGeneratePayload({ userText: 'Cover bonds and insurance' });
  assert.strictEqual(p.kind, 'json');
  assert.strictEqual(p.fields.user_input, 'Cover bonds and insurance');
  assert.deepStrictEqual(p.files, {});
});

test('the analyzer document alone rides the primary file slot as context', () => {
  const doc = pdf('bid.pdf');
  const p = BB.qgen.buildGeneratePayload({ userText: 'give me 3 questions', contextFile: doc });
  assert.strictEqual(p.kind, 'multipart');
  assert.strictEqual(p.files.file, doc);
  assert.strictEqual(p.fields.source_kind, 'context');
  assert.strictEqual('context_file' in p.files, false);
});

test('REGRESSION 2.1.1: a PDF questions-source must NOT displace the document context', () => {
  const doc = pdf('bid.pdf');
  const source = pdf('standard.pdf');
  const p = BB.qgen.buildGeneratePayload({
    userText: '', contextFile: doc, questionsSourceFile: source,
  });
  assert.strictEqual(p.files.file, source, 'the questions-source takes the primary slot');
  assert.strictEqual(p.files.context_file, doc,
    'the analyzer doc MUST still be sent as context_file — dropping it un-grounds Q-gen');
  assert.strictEqual(p.fields.source_kind, 'questions_source');
});

test('a text questions-source is folded into user_input locally, not uploaded', () => {
  const p = BB.qgen.buildGeneratePayload({
    userText: 'Focus on schedule',
    questionsSourceFile: txt('notes.txt'),
    questionsSourceText: 'Q: When does work start?',
    contextFile: pdf('bid.pdf'),
  });
  assert.strictEqual(p.files.file, undefined, 'text sources are read locally');
  assert.match(p.fields.user_input, /Focus on schedule/);
  assert.match(p.fields.user_input, /When does work start/);
  assert.ok(p.files.context_file || p.fields.source_kind === 'context');
});

test('source_intent is sent when given and omitted when blank', () => {
  const doc = pdf('bid.pdf');
  const withIntent = BB.qgen.buildGeneratePayload({
    userText: 'x', contextFile: doc, sourceIntent: '  derive from this standard  ',
  });
  assert.strictEqual(withIntent.fields.source_intent, 'derive from this standard');

  const without = BB.qgen.buildGeneratePayload({ userText: 'x', contextFile: doc, sourceIntent: '  ' });
  assert.strictEqual('source_intent' in without.fields, false);
});

test('high_power is NEVER sent for Q-gen — the backend forces it for everyone', () => {
  const p = BB.qgen.buildGeneratePayload({ userText: 'x', contextFile: pdf('bid.pdf') });
  assert.strictEqual('high_power' in p.fields, false,
    'sending high_power here re-introduces the 403 gate for non-premium users');
});

test('document-only generation synthesises a default instruction', () => {
  const p = BB.qgen.buildGeneratePayload({ userText: '', contextFile: pdf('bid.pdf') });
  assert.ok(p.fields.user_input && p.fields.user_input.length > 10,
    'a blank field plus a doc must still carry an instruction');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/bb-qgen.test.js`
Expected: FAIL — `ENOENT ... bb-qgen.js`.

- [ ] **Step 3: Write `bb-qgen.js`**

```js
/* Create / Add Question Set. Ports the iOS GenerateStage + QuestionHubModel.generate.
   THE RULE (2.1.1/2.1.2): the Document Context is ALWAYS sent for grounding —
   as the primary `file` when there is no PDF questions-source, else as
   `context_file` alongside it. Never let a questions-source displace it. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var DOC_ONLY_INSTRUCTION =
    'Derive the most important document-analysis questions from the attached document.';

  function isPdf(file) {
    if (!file) return false;
    return file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');
  }

  function buildGeneratePayload(opts) {
    opts = opts || {};
    var fields = {};
    var files = {};

    var text = (opts.userText || '').trim();
    // Text-based questions sources are read locally and folded into the prompt.
    var sourceText = (opts.questionsSourceText || '').trim();
    if (sourceText) {
      text = text
        ? text + '\n\n--- Questions source (' + (opts.questionsSourceFile || {}).name + ') ---\n' + sourceText
        : sourceText;
    }

    var contextFile = opts.contextFile || null;
    var sourcePdf = isPdf(opts.questionsSourceFile) ? opts.questionsSourceFile : null;

    if (!text && (contextFile || sourcePdf)) text = DOC_ONLY_INSTRUCTION;
    fields.user_input = text;

    var intent = (opts.sourceIntent || '').trim();
    if (intent) fields.source_intent = intent;

    if (sourcePdf) {
      files.file = sourcePdf;
      fields.source_kind = 'questions_source';
      if (contextFile) files.context_file = contextFile;   /* ALWAYS grounded */
    } else if (contextFile) {
      files.file = contextFile;
      fields.source_kind = 'context';
    }

    // NOTE: no high_power. Question generation is high-power for every user
    // server-side; sending the flag would hit the entitlement gate (403).
    return {
      kind: (files.file || files.context_file) ? 'multipart' : 'json',
      fields: fields,
      files: files
    };
  }

  BB.qgen = {
    buildGeneratePayload: buildGeneratePayload,
    render: render, generate: generate,
    suggestAdditional: suggestAdditional, acceptSuggestions: acceptSuggestions
  };
  /* ... renderers + fetch wrappers below ... */
})(typeof window !== 'undefined' ? window : this);
```

The screen (all copy verbatim from the iOS `GenerateStage`):

1. `.bb-back-chip`, `.bb-stage-header` "Create / Add Question Set" with the
   subtitle "Paste any questions you already have, tell BidBrief what to ask, or
   both — then generate. Everything you paste is kept word-for-word; anything you
   describe becomes tailored document-analysis questions."
2. **Your Questions & Instructions** — a 4–10 row `.bb-field` textarea.
3. **Questions Source (Optional)** — file picker accepting
   `.pdf,.txt,.text,.csv,.md`. Text types are read with `FileReader` and folded
   into `user_input`; PDFs are uploaded. When attached: the filename, a ✕ to
   remove, and "BidBrief will work out what this is and derive the questions
   from it."
4. **Document Context** — **auto-adopts `BB.state.analysis.file` on entry** when
   the user hasn't chosen one (this is the 2.1.2 fix: without it, the common flow
   sends no document and Q-gen produces ungrounded questions). Shows a "Use
   <name>" shortcut and an "Attach the bid document (PDF)" picker; attaching here
   also adopts the file as the Analyzer's pending upload
   (`BB.state.noteFreshUpload(file)`), so the user never uploads twice.
5. **Mode** — segmented Replace / Merge. Replace snapshots the current set into
   Libraries first ("Before AI generation — <timestamp>") so nothing is lost.
6. **What's this file for? (Recommended)** — shown as soon as any file is
   attached; an inline `.bb-field` (never `window.prompt`), sent as `source_intent`.
7. **Generate Question Set** (`.bb-btn-glow`) — disabled until there is text or a
   file; while running the label reads "Reading your material & generating…"
   (or "BidBrief is generating…" with no files).
8. After success: `BB.questionHub.apply(config)` + PUT, then the **Built By Your
   Expert Panel** card (`document_reading` caption + each persona's name and
   expertise — tolerate `generation_personas: []`, the Architect can fall back),
   and per-section previews carrying each `section_summary` as italic rationale.
9. Then "Want more? BidBrief can suggest up to 3 complementary sections…" →
   `generate-additional`, rendering each suggested section with a checkbox, its
   rationale, and the first four questions; **Add Selected** merges them.

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/bb-qgen.test.js`
Expected: PASS — `# pass 7`.

- [ ] **Step 5: End-to-end check against the real endpoint**

With the local server running (needs `OPENAI_API_KEY` in the environment):
upload a PDF on Analyze → Questions → Create → type "give me 3 questions" →
Generate. Confirm via the network panel that the request is multipart with a
`file` part, and that the three questions returned are specific to the document.
Then attach a second PDF as the Questions Source and confirm the request now
carries **both** `file` and `context_file`.

- [ ] **Step 6: Commit**

```bash
git add shared/assets tests/js/bb-qgen.test.js
git commit -m "feat(web): iOS-parity question generation — questions source, context_file, personas"
```

---

## Task 12: Libraries + the BidBrief Starter Set

**Files:**
- Create: `shared/assets/js/bb-libraries.js`
- Create: `shared/assets/data/starter-question-set.json` (copy of the iOS `Sources/Resources/DefaultQuestionSet.json`; if that file is absent, generate it from the backend's `config/default_questions.json`)
- Create: `tests/js/bb-libraries.test.js`
- Modify: `tests/test_web_ui.py`

**Interfaces:**
- Consumes: `BB.state`, `BB.ui`.
- Produces: `window.BB.libraries` with `list()`, `save(name, config)`, `remove(id)`, `get(id)`, `seedStarterOnce()` — all backed by `localStorage['bb.questionLibraries']`. Library shape: `{ id, name, savedAt (ISO), sectionCount, questionCount, config }`.

- [ ] **Step 1: Write the failing test**

Create `tests/js/bb-libraries.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const MODULES = ['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js',
                 'shared/assets/js/bb-libraries.js'];

const CONFIG = {
  sections: [
    { section_id: 'a', section_name: 'A', questions: [{ id: 'q1' }, { id: 'q2' }] },
    { section_id: 'b', section_name: 'B', questions: [{ id: 'q3' }] },
  ],
};

test('save stores a named snapshot with counts and a timestamp', () => {
  const { BB } = loadModules(MODULES);
  const lib = BB.libraries.save('CIPP lining bids', CONFIG);
  assert.strictEqual(lib.name, 'CIPP lining bids');
  assert.strictEqual(lib.sectionCount, 2);
  assert.strictEqual(lib.questionCount, 3);
  assert.ok(Date.parse(lib.savedAt), 'savedAt must be an ISO timestamp');
  assert.strictEqual(BB.libraries.list().length, 1);
});

test('the snapshot is a deep copy — later edits do not mutate it', () => {
  const { BB } = loadModules(MODULES);
  const source = JSON.parse(JSON.stringify(CONFIG));
  BB.libraries.save('snap', source);
  source.sections[0].section_name = 'MUTATED';
  assert.strictEqual(BB.libraries.list()[0].config.sections[0].section_name, 'A');
});

test('remove deletes only the named library', () => {
  const { BB } = loadModules(MODULES);
  const one = BB.libraries.save('one', CONFIG);
  BB.libraries.save('two', CONFIG);
  BB.libraries.remove(one.id);
  assert.deepStrictEqual(BB.libraries.list().map((l) => l.name), ['two']);
});

test('libraries survive a reload', () => {
  const store = new Map();
  const fakeStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  loadModules(MODULES, { localStorage: fakeStorage }).BB.libraries.save('kept', CONFIG);
  const reloaded = loadModules(MODULES, { localStorage: fakeStorage }).BB;
  assert.deepStrictEqual(reloaded.libraries.list().map((l) => l.name), ['kept']);
});

test('the Starter Set seeds exactly once and is never auto-applied', () => {
  const store = new Map();
  const fakeStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  const first = loadModules(MODULES, { localStorage: fakeStorage }).BB;
  first.libraries.seedStarterOnce(CONFIG);
  first.libraries.seedStarterOnce(CONFIG);
  assert.strictEqual(first.libraries.list().length, 1, 'seeding twice must not duplicate');
  assert.strictEqual(first.state.questionHub.isConfirmed, false,
    'the starter set is a Library, never an auto-applied set');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/bb-libraries.test.js`
Expected: FAIL — `ENOENT ... bb-libraries.js`.

- [ ] **Step 3: Write `bb-libraries.js`**

```js
/* Named question-set snapshots kept in this browser.
   Ports Sources/Features/QuestionHub/QuestionLibraryStore.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var KEY = 'bb.questionLibraries';
  var SEED_KEY = 'bb.starterSeeded';

  function storage() { try { return window.localStorage; } catch (e) { return null; } }

  function read() {
    var s = storage(); if (!s) return [];
    try { return JSON.parse(s.getItem(KEY) || '[]'); } catch (e) { return []; }
  }

  function write(list) {
    var s = storage(); if (s) s.setItem(KEY, JSON.stringify(list));
  }

  function counts(config) {
    var sections = (config && config.sections) || [];
    return {
      sectionCount: sections.length,
      questionCount: sections.reduce(function (n, sec) {
        return n + ((sec.questions && sec.questions.length) || 0);
      }, 0)
    };
  }

  function save(name, config) {
    var c = counts(config);
    var lib = {
      id: 'lib_' + Date.now().toString(36) + '_' + Math.floor(Math.random() * 1e6).toString(36),
      name: String(name || '').trim() || 'Untitled set',
      savedAt: new Date().toISOString(),
      sectionCount: c.sectionCount,
      questionCount: c.questionCount,
      config: JSON.parse(JSON.stringify(config))   /* deep copy — later edits must not leak in */
    };
    var list = read(); list.unshift(lib); write(list);
    return lib;
  }

  function list() { return read(); }
  function get(id) { return read().filter(function (l) { return l.id === id; })[0] || null; }
  function remove(id) {
    write(read().filter(function (l) { return l.id !== id; }));
  }

  /** Seed the BidBrief Starter Set ONCE. It is a Library, never auto-applied. */
  function seedStarterOnce(config) {
    var s = storage();
    if (s && s.getItem(SEED_KEY) === 'true') return null;
    if (s) s.setItem(SEED_KEY, 'true');
    if (!config) return null;
    return save('BidBrief Starter Set', config);
  }

  BB.libraries = { list: list, get: get, save: save, remove: remove, seedStarterOnce: seedStarterOnce };
})(typeof window !== 'undefined' ? window : this);
```

- [ ] **Step 4: Ship the starter set and wire the Libraries stage**

```bash
cd "C:/Users/pr0ph/Documents/AI LLC/Apps/Doc Analysis Projects/Non-Buildout and Branded/2026/BidBrief"
mkdir -p shared/assets/data
cp "C:/Users/pr0ph/Documents/AI LLC/Apps/BidBrief iOS/Sources/Resources/DefaultQuestionSet.json" \
   shared/assets/data/starter-question-set.json
```

If that path does not exist, find the iOS copy first
(`ls "C:/Users/pr0ph/Documents/AI LLC/Apps/BidBrief iOS/Sources/Resources/"`) and,
failing that, build it from the backend default:
`cp config/default_questions.json shared/assets/data/starter-question-set.json` —
then normalise it to the `{ "sections": [...] }` shape the hub expects.

`BB.questionHub`'s `libraries` stage renders: a "Save Current Set" card (name
field + `.bb-btn-ghost` "Save as Library"), then each saved library as a glass row
with "N sections · M questions · <date>" and **Use** (success ghost —
`BB.questionHub.apply(lib.config)` then `save()`) / **Delete** (danger ghost).
Empty state: "No libraries yet. Save the current set to start one."
`bb-boot.js` calls `BB.libraries.seedStarterOnce(starterConfig)` after fetching
`/shared/assets/data/starter-question-set.json`.

- [ ] **Step 5: Add the asset test and run both suites**

Append to `tests/test_web_ui.py`:

```python
def test_starter_question_set_is_served_and_well_formed(client):
    resp = client.get('/shared/assets/data/starter-question-set.json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data.get('sections'), list) and data['sections'], 'starter set is empty'
    first = data['sections'][0]
    assert 'section_id' in first and 'section_name' in first and 'questions' in first
```

Run: `python -m pytest -q && node --test tests/js/`
Expected: pytest all green; node `# pass` includes the 5 new library tests.

- [ ] **Step 6: Commit**

```bash
git add shared/assets tests/
git commit -m "feat(web): question-set Libraries with one-time Starter Set seed"
```

---

## Task 13: Admin / Bonus hub, CityScraper restyle, Settings

**Files:**
- Create: `shared/assets/js/bb-admin.js`, `shared/assets/js/bb-settings.js`
- Modify: `shared/assets/js/bb-scraper.js` (render into `#bb-page-admin`, glass styling, no light-theme markup)
- Modify: `shared/assets/css/bb-screens.css` (scraper tables, agent feed, preflight grid)
- Create: `tests/js/bb-admin.test.js`
- Modify: `tests/test_web_ui.py`

**Interfaces:**
- Consumes: `BB.state`, `BB.ui`, `BB.shell`.
- Produces:
  - `window.BB.admin` with `render()`, `entriesFor(session)` → array of `{ id, title, subtitle, icon }`, `renderBonusManager()`, `renderScraper()`.
  - `window.BB.settings` with `render()`.

- [ ] **Step 1: Write the failing test**

Create `tests/js/bb-admin.test.js`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const MODULES = [
  'shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-orb.js', 'shared/assets/js/bb-shell.js',
  'shared/assets/js/bb-admin.js',
];

const ids = (entries) => entries.map((e) => e.id);

test('admins see the sessions dashboard, the bonus manager and CityScraper', () => {
  const { BB } = loadModules(MODULES);
  assert.deepStrictEqual(
    ids(BB.admin.entriesFor({ isAdmin: true, hasPremium: true })),
    ['sessions', 'bonus', 'scraper']
  );
});

test('bonus users see ONLY CityScraper — never other users\' work', () => {
  const { BB } = loadModules(MODULES);
  const entries = ids(BB.admin.entriesFor({ isAdmin: false, hasPremium: true }));
  assert.deepStrictEqual(entries, ['scraper']);
  assert.ok(!entries.includes('sessions'),
    'the sessions dashboard exposes other users\' analyses — admin only');
  assert.ok(!entries.includes('bonus'));
});

test('plain users get nothing here', () => {
  const { BB } = loadModules(MODULES);
  assert.deepStrictEqual(ids(BB.admin.entriesFor({ isAdmin: false, hasPremium: false })), []);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/bb-admin.test.js`
Expected: FAIL — `ENOENT ... bb-admin.js`.

- [ ] **Step 3: Write `bb-admin.js` and `bb-settings.js`**

```js
/* Admin hub. True admins see everything; Bonus Features users see ONLY the
   premium features — the sessions dashboard and the bonus manager never render
   for them. Ports AdminHomeView. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var ENTRIES = {
    sessions: { id: 'sessions', title: 'Session Dashboard',
                subtitle: 'All analyses in server memory', icon: '\uD83D\uDCC1' },
    bonus:    { id: 'bonus',    title: 'Bonus Features',
                subtitle: 'Grant premium features to users', icon: '\uD83D\uDC65' },
    scraper:  { id: 'scraper',  title: 'CityScraper',
                subtitle: 'Municipal research & comparison', icon: '\uD83C\uDFDB\uFE0F' }
  };

  function entriesFor(session) {
    var out = [];
    if (session && session.isAdmin) { out.push(ENTRIES.sessions, ENTRIES.bonus); }
    if (session && (session.isAdmin || session.hasPremium)) out.push(ENTRIES.scraper);
    return out;
  }

  BB.admin = { entriesFor: entriesFor, render: render,
               renderBonusManager: renderBonusManager, renderScraper: renderScraper };
  /* ... renderers below ... */
})(typeof window !== 'undefined' ? window : this);
```

- **Admin page** — `.bb-stage-header` "Admin" / "Server operations" (or "Bonus
  Features" / "Premium features unlocked for you"), then one `.bb-hub-btn` per
  entry. `sessions` opens `/admin/sessions` in a new tab; `bonus` pushes the
  Bonus Features manager (GET/POST `/api/admin/bonus-features` — list users,
  toggle grants); `scraper` pushes the CityScraper stage.
- **CityScraper** — same flow and endpoints as today, re-rendered on glass:
  municipality field + research-mode select in a `.bb-glass-card`, Start
  (`.bb-btn-glow`) / Stop (`.bb-btn-ghost` danger), a progress card reusing the
  orb ring, the agent feed as glass rows, the pre-flight grid as a two-column
  glass card with confidence pills, and the results tabs as `.bb-btn-ghost`
  segments over a dark table. **Never** call `/api/admin/sessions` from here.
- **Settings page** (`bb-settings.js`) — `.bb-stage-header` "Settings"; an
  Account card (Email, Role, **Sign Out** → `/auth/logout`, danger ghost); an
  About card (Version "2.2.0", "BidBrief — Additional Intelligence LLC", the
  patent-pending line, and the About text that used to live in the modal).

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tests/js/bb-admin.test.js`
Expected: PASS — `# pass 3`.

- [ ] **Step 5: Add the structural test and run everything**

Append to `tests/test_web_ui.py`:

```python
def test_no_light_theme_leftovers_in_the_shipped_front_end(client):
    """The overhaul is only done when the old palette is gone from the shell."""
    headers = _auth(client)
    html = client.get('/', headers=headers).data.decode('utf-8')
    for stale in ('#5B7FCC', '#1E3A8A', 'rgba(255, 255, 255, 0.95)'):
        assert stale not in html, f'legacy light-theme value {stale} still in index.html'
```

Run: `python -m pytest -q && node --test tests/js/`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add shared/assets tests/
git commit -m "feat(web): Admin/Bonus hub, glass CityScraper, Settings tab"
```

---

## Task 14: Login page

**Files:**
- Modify: `login.html`
- Modify: `tests/test_web_ui.py`

**Interfaces:**
- Consumes: `bb-theme.css`, `bb-orb.css`, `bb-orb.js`, `/pics/brand/*`.
- Produces: nothing downstream. The form still POSTs `username`/`password` to `/auth/login` — the backend contract is untouched.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_ui.py`:

```python
def test_login_page_wears_the_orb_and_the_btools_lockup(client):
    html = client.get('/login').data.decode('utf-8')
    assert 'bb-orb-host' in html, 'the login page must sit on the planet field'
    assert '/pics/brand/btools-titlelogo-nobg.png' in html, 'btools lockup missing'
    assert '/shared/assets/css/bb-theme.css' in html
    # The form contract the backend depends on must survive the restyle.
    assert 'action="/auth/login"' in html and 'method="POST"' in html
    assert 'name="username"' in html and 'name="password"' in html


def test_login_page_drops_the_old_white_card(client):
    html = client.get('/login').data.decode('utf-8')
    assert 'rgba(255, 255, 255, 0.95)' not in html
    assert '/pics/AILLCLogo.png' not in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_web_ui.py -q`
Expected: FAIL — both new tests.

- [ ] **Step 3: Rewrite `login.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="color-scheme" content="dark">
    <title>BidBrief — Sign In</title>
    <link rel="icon" type="image/png" href="/pics/AILLCfavicon.png">
    <link rel="stylesheet" href="/shared/assets/css/bb-theme.css">
    <link rel="stylesheet" href="/shared/assets/css/bb-orb.css">
    <style>
        .bb-login-wrap { min-height: 100vh; display: grid; place-items: center; padding: 24px; }
        .bb-login-card { width: 100%; max-width: 420px; text-align: center; }
        .bb-login-card .bb-lockup { height: 42px; margin-bottom: 18px; }
        .bb-login-card h1 { font-size: 32px; font-weight: 700; text-shadow: 0 0 18px rgba(94,134,208,.55); }
        .bb-login-card .bb-sub { color: var(--bb-text-secondary); font-size: 14px; margin-top: 6px; }
        .bb-login-card form { display: flex; flex-direction: column; gap: 14px; margin-top: 26px; text-align: left; }
        .bb-login-card .bb-error {
            display: none; padding: 10px 14px; border-radius: 12px; font-size: 13px;
            background: rgba(220, 38, 38, .16); border: 1px solid rgba(220, 38, 38, .45);
            color: #fff; text-align: center;
        }
        .bb-login-card .bb-error.show { display: block; }
        .bb-login-card footer { margin-top: 26px; font-size: 12px; color: var(--bb-text-tertiary); }
        .bb-login-card footer a { color: var(--bb-glow-ice); text-decoration: none; }
    </style>
</head>
<body>
    <div id="bb-orb" class="bb-orb-host" aria-hidden="true">
        <canvas class="bb-orb-stars"></canvas>
        <div class="bb-orb-halo"></div>
        <div class="bb-orb-planet"></div>
        <img class="bb-orb-mark" src="/pics/brand/btools-iconlogo-nobg.png" alt="">
        <div class="bb-orb-gleam"></div>
        <div class="bb-orb-ring"></div>
        <div class="bb-orb-moon"></div>
        <div class="bb-orb-scrim-top"></div>
        <div class="bb-orb-scrim-bottom"></div>
    </div>

    <div class="bb-login-wrap">
        <div class="bb-login-card bb-glass-card">
            <img class="bb-lockup" src="/pics/brand/btools-titlelogo-nobg.png" alt="btools.ai">
            <h1>BidBrief</h1>
            <p class="bb-sub">AI-powered document analysis</p>

            <form id="loginForm" action="/auth/login" method="POST">
                <div id="errorMessage" class="bb-error"></div>
                <label class="bb-eyebrow" for="username">Username</label>
                <div class="bb-field">
                    <input type="text" id="username" name="username" required
                           autocomplete="username" placeholder="Enter your username">
                </div>
                <label class="bb-eyebrow" for="password">Password</label>
                <div class="bb-field">
                    <input type="password" id="password" name="password" required
                           autocomplete="current-password" placeholder="Enter your password">
                </div>
                <button type="submit" class="bb-btn-glow bb-pulses">Sign In</button>
            </form>

            <footer>
                Powered by <a href="https://additionalintel.com" target="_blank" rel="noopener">Additional Intelligence LLC</a><br>
                Patent Pending
            </footer>
        </div>
    </div>

    <script src="/shared/assets/js/bb-ui.js"></script>
    <script src="/shared/assets/js/bb-orb.js"></script>
    <script src="/shared/assets/js/bb-login.js"></script>
</body>
</html>
```

Create `shared/assets/js/bb-login.js`:

```js
/* Login page behaviour: mount the orb, surface the ?error= reason, and block
   an empty submit before it round-trips. */
(function (window) {
  'use strict';
  var document = window.document;
  var MESSAGES = {
    invalid: 'Invalid username or password. Please try again.',
    session: 'Your session has expired. Please log in again.'
  };

  document.addEventListener('DOMContentLoaded', function () {
    window.BB.orb.mount(document.getElementById('bb-orb'));

    var box = document.getElementById('errorMessage');
    var error = new window.URLSearchParams(window.location.search).get('error');
    if (error) {
      box.textContent = MESSAGES[error] || 'An error occurred. Please try again.';
      box.classList.add('show');
    }

    document.getElementById('loginForm').addEventListener('submit', function (e) {
      var user = document.getElementById('username').value.trim();
      var pass = document.getElementById('password').value;
      if (user && pass) return;
      e.preventDefault();
      box.textContent = 'Please enter both username and password.';
      box.classList.add('show');
    });
  });
})(window);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_web_ui.py -q`
Expected: PASS.

- [ ] **Step 5: Browser check**

Playwright: navigate to `/login`, screenshot, submit blank (inline error), then
submit the real credentials and confirm the redirect to `/` lands on the Analyze
tab.

- [ ] **Step 6: Commit**

```bash
git add login.html shared/assets/js/bb-login.js tests/test_web_ui.py
git commit -m "feat(web): login page on the planet field with the btools lockup"
```

---

## Task 15: Full verification, docs, and hand-off

**Files:**
- Modify: `digestsynopsisSUMMARY.md`, `README.md` (web section), `CLAUDE.md` (backend repo — note the new front-end layout)
- Create: `docs/WEB_FRONTEND.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a green suite, screenshots, and a documented hand-off.

- [ ] **Step 1: Run every automated check**

```bash
cd "C:/Users/pr0ph/Documents/AI LLC/Apps/Doc Analysis Projects/Non-Buildout and Branded/2026/BidBrief"
python -m pytest -q
node --test tests/js/
```

Expected: pytest `≥90 passed` (76 baseline + the new web-ui tests), node all
passing. **Any failure blocks this task** — fix before continuing.

- [ ] **Step 2: Walk the whole app in a browser**

Start the server with test credentials:

```bash
AUTH_USER1_EMAIL=admin@test.local AUTH_USER1_PASSWORD=testpass123 \
AUTH_USER2_EMAIL=user@test.local AUTH_USER2_PASSWORD=testpass123 \
  python -c "from app import app; app.run(port=5111)" &
```

With Playwright, walk and screenshot each of these; check
`browser_console_messages` is clean after every step:

1. `/login` → sign in as the plain user
2. Analyze idle (upload orb) → choose a PDF → the configure stage
3. The tab bar cues **Questions** with a throbbing "Next" chip
4. Questions → Create → generate a small set → the cue moves to **Analyze**
5. Analyze → Start Analysis pulses → run it → the progress ring and phase track
6. Results → overview → a section (Answer Summary in place) → Table view → Exports
7. Settings (account + sign out)
8. Sign in as the admin → the **Admin** tab appears → Bonus Features + CityScraper
9. Resize to 390×844 (phone) and confirm the layout holds and the tab bar clears the content

- [ ] **Step 3: Write the docs**

Create `docs/WEB_FRONTEND.md` covering: the module map (which file owns what),
the `BB` namespace contract, the state model and the cue rules, how to add a new
screen, and the invariants a future change must not break (WYSIWYG
`enabled_sections`; Q-gen always sends the analyzer doc; lossless question-config
round-trip; `answer_summary` between answer and citations; no `high_power` on
Q-gen).

Add a "Web front-end (2.2.0)" section to `digestsynopsisSUMMARY.md` recording the
overhaul and pointing at `docs/WEB_FRONTEND.md`.

- [ ] **Step 4: Commit and merge to master locally**

```bash
git add -A
git commit -m "docs(web): front-end module map, state contract, invariants"
git checkout master
git merge --no-ff feat/web-ios-parity-2.2.0 -m "merge: 2.2.0 — web front-end rebuilt to iOS UX parity"
python -m pytest -q          # confirm master is green after the merge
```

- [ ] **Step 5: STOP — ask before deploying**

**Do not `git push origin master`.** That push auto-deploys to Render
production. Report to the user: what shipped, the screenshots, the test counts,
and ask explicitly whether to push `master` (deploy) now.

---

## Self-Review

**Spec coverage.** The request was "a huge overhaul of the web front-end so that
it is all streamlined with the iOS UX." Mapped: visual identity (Tasks 3–4),
information architecture and the tab shell (Task 6), the guided Analyze flow with
Start Analysis above the sections and the confirmed-set gate (Task 7), the
progress story (Task 8), staged results with answer summaries and dynamic
intelligence (Task 9), the Question Hub and its create/libraries flow at full
2.1.x parity (Tasks 10–12), Admin/Bonus + CityScraper + Settings (Task 13), and
the login page (Task 14). The onboarding cue — including the 2.1.3 rule that
confirming a set advances Questions → Analyze — is specified and tested in Task 5.

**Known gaps, stated deliberately.** (a) The iOS app persists an upload across
app switches via a temp file; the web keeps the `File` object in memory, so a
browser reload requires re-choosing the PDF — matching today's web behaviour, not
a regression. (b) `analyzer_rebuild.html`, `/cipp-analyzer`, and
`/progress-estimator` are dead backend routes noted in `CLAUDE.md`; this plan
leaves them alone. (c) `admin_sessions.html` keeps its own light styling — it is
reached in a new tab and is out of scope; if the user wants it restyled it is a
follow-up.

**Type consistency.** `BB.state`, `BB.ui`, `BB.orb`, `BB.shell`, `BB.status`,
`BB.analyze`, `BB.progress`, `BB.results`, `BB.questionHub`, `BB.qgen`,
`BB.libraries`, `BB.admin`, `BB.settings` are each defined once and referenced
under exactly those names. Section fields are `section_id` / `section_name` and
question fields `id` / `text` / `enabled` throughout (the real backend contract —
using `name`/`question` here is the bug that once rendered blank "Section"
labels). Results fields are `question_id` / `question` / `answer` /
`answer_summary` / `page_citations`, matching the results payload.
