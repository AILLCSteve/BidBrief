'use strict';
/* 2.4.0 — Visual Intelligence flag + the results workbook + the in-app
   admin session dashboard. Pure-logic coverage of the new surface. */
const test = require('node:test');
const assert = require('node:assert');
const { loadModules, plain } = require('./_harness');

const ANALYZE_MODULES = [
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-orb.js',
  'shared/assets/js/bb-status.js',
  'shared/assets/js/bb-shell.js',
  'shared/assets/js/bb-analyze.js',
];

const RESULTS_MODULES = [
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-results.js',
];

const ADMIN_MODULES = [
  'shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-orb.js', 'shared/assets/js/bb-shell.js',
  'shared/assets/js/bb-scraper.js', 'shared/assets/js/bb-admin.js',
];

// ---- the /api/analyze flag --------------------------------------------------

test('visual analysis toggle rides the analyze payload as enable_visual_analysis', () => {
  const { BB } = loadModules(ANALYZE_MODULES);
  BB.state.questionHub.config = { sections: [{ section_id: 's1', questions: [] }] };
  BB.state.analysis.visualAnalysis = true;
  const body = plain(BB.analyze.buildAnalyzePayload(BB.state, 'up-1', 'plans.pdf'));
  assert.strictEqual(body.enable_visual_analysis, true);
});

test('visual analysis is OFF by default - the standard pipeline is untouched', () => {
  const { BB } = loadModules(ANALYZE_MODULES);
  BB.state.questionHub.config = { sections: [{ section_id: 's1', questions: [] }] };
  const body = plain(BB.analyze.buildAnalyzePayload(BB.state, 'up-1', 'plans.pdf'));
  assert.strictEqual(body.enable_visual_analysis, false);
});

test('reset clears the visual toggle with the rest of the analysis state', () => {
  const { BB } = loadModules(ANALYZE_MODULES);
  BB.state.analysis.visualAnalysis = true;
  BB.state.reset();
  assert.strictEqual(BB.state.analysis.visualAnalysis, false);
});

// ---- the results workbook ---------------------------------------------------

const PAYLOAD = {
  document_name: 'Spec.pdf',
  total_pages: 12,
  sections: [{
    section_id: 'a', section_name: 'General',
    questions: [
      { question_id: 'q1', question: 'Name?', answer: 'Oak St CIPP', confidence: 0.9,
        page_citations: [1], answer_summary: 'Oak Street project.' },
      { question_id: 'q2', question: 'Bond?', answer: null, confidence: 0, page_citations: [] },
    ],
  }],
  footnotes: ['Page 1: "Oak St CIPP"'],
};

test('sheet tabs mirror the Excel workbook - core sheets always, extras when earned', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  const core = plain(BB.results.sheetList(PAYLOAD)).map((s) => s.id);
  assert.deepStrictEqual(core, ['summary', 'detailed', 'bySection', 'footnotes']);

  const rich = plain(BB.results.sheetList(Object.assign({}, PAYLOAD, {
    dynamic_tables: [{ title: 'T', columns: [], rows: [] }],
    visual_findings: [{ page: 3, kind: 'drawing', description: 'd' }],
  }))).map((s) => s.id);
  assert.deepStrictEqual(rich,
    ['summary', 'detailed', 'bySection', 'intelligence', 'visual', 'footnotes']);
});

test('executive summary rows mirror the Excel statistics block', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  const rows = plain(BB.results.execSummaryRows(PAYLOAD));
  const byLabel = Object.fromEntries(rows);
  assert.strictEqual(byLabel['Total Questions'], '2');
  assert.strictEqual(byLabel['Questions Answered'], '1');
  assert.strictEqual(byLabel['Answer Rate'], '50%');
  assert.strictEqual(byLabel['Average Confidence'], '90%');
  assert.ok(byLabel['Analysis Date']);
});

test('key details rows use the Excel display names, order and citation stripping', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  const rows = plain(BB.results.keyDetailRows({
    warranty: '2 years <PDF pg 44>',
    project_name: 'Oak St CIPP',
    zzz_custom: 'thing',
    owner: 'City of Oakton',
  }));
  assert.deepStrictEqual(rows, [
    ['Project Name', 'Oak St CIPP'],
    ['Owner/Agency', 'City of Oakton'],
    ['Warranty', '2 years'],
    ['Zzz Custom', 'thing'],
  ]);
});

test('key details drop not-found placeholders and merge same-label values', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  const rows = plain(BB.results.keyDetailRows({
    bid_bond: '5%', performance_bond: '100%', engineer: 'Not found',
  }));
  assert.deepStrictEqual(rows, [['Bonding', '5%; 100%']]);
});

test('statusOf distinguishes found from missing exactly like the Excel Status column', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  assert.strictEqual(BB.results.statusOf({ answer: 'yes' }), 'found');
  assert.strictEqual(BB.results.statusOf({ answer: '   ' }), 'missing');
  assert.strictEqual(BB.results.statusOf({}), 'missing');
});

// ---- the in-app admin session dashboard --------------------------------------

test('exportUrlFor routes bestprep sessions to the bestprep Excel endpoint', () => {
  const { BB } = loadModules(ADMIN_MODULES);
  assert.strictEqual(
    BB.admin.exportUrlFor({ session_id: 'sess_1', mode: 'bestprep' }),
    '/api/export/bestprep-excel/sess_1');
  assert.strictEqual(
    BB.admin.exportUrlFor({ session_id: 'sess_2', mode: 'bid_spec' }),
    '/api/export/excel-dashboard/sess_2');
  assert.strictEqual(
    BB.admin.exportUrlFor({ session_id: 'sess_3' }),
    '/api/export/excel-dashboard/sess_3',
    'missing mode defaults to the bid/spec dashboard export');
});

test('sessionGroups keeps lifecycle order and drops empty buckets', () => {
  const { BB } = loadModules(ADMIN_MODULES);
  const groups = plain(BB.admin.sessionGroups({
    active: [], completed: [{ session_id: 'a' }],
    partial: [{ session_id: 'b' }], legacy: [],
  }));
  assert.deepStrictEqual(groups.map((g) => g.key), ['completed', 'partial']);
});

test('sessionsSummaryText reads like the dashboard header', () => {
  const { BB } = loadModules(ADMIN_MODULES);
  assert.strictEqual(
    BB.admin.sessionsSummaryText({
      total_sessions: 3, active_count: 1, completed_count: 2, partial_count: 0,
    }),
    '3 total  ·  1 active  ·  2 completed  ·  0 partial');
});

// ---- visual provenance on answers (2.4.0 interweave) ----------------------

const VIS_PAYLOAD = {
  sections: [{
    section_id: 'a', section_name: 'Scope',
    questions: [
      { question_id: 'q1', question: 'Pipe size?', answer: '8 inch <PDF pg 7>',
        page_citations: [7], visual_sources: [{ page: 7, kind: 'drawing' }] },
      { question_id: 'q2', question: 'Route?', answer: 'Along Oak <PDF pg 9>',
        page_citations: [9],
        visual_sources: [{ page: 9, kind: 'map' }, { page: 7, kind: 'drawing' }] },
      { question_id: 'q3', question: 'Bond?', answer: 'Yes <PDF pg 2>', page_citations: [2] },
    ],
  }],
  visual_findings: [{ page: 7, kind: 'drawing', description: 'Plan sheet' }],
};

test('visualSourceLabel matches the Excel Visual Source cell', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  const qs = VIS_PAYLOAD.sections[0].questions;
  assert.strictEqual(BB.results.visualSourceLabel(qs[0]), 'Drawing p.7');
  assert.strictEqual(BB.results.visualSourceLabel(qs[1]), 'Map p.9; Drawing p.7');
});

test('a text-only answer has no visual label and no badge', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  const q = VIS_PAYLOAD.sections[0].questions[2];
  assert.strictEqual(BB.results.visualSourceLabel(q), '');
  assert.deepStrictEqual(plain(BB.results.visualSourcesOf(q)), []);
});

test('results cached before 2.4.0 decode without visual_sources', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  assert.deepStrictEqual(plain(BB.results.visualSourcesOf({ answer: 'old' })), []);
  assert.strictEqual(BB.results.visualSourceLabel({ answer: 'old' }), '');
});

test('questionsFedBy proves which questions a graphic actually answered', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  const fed = plain(BB.results.questionsFedBy(VIS_PAYLOAD, 7));
  assert.deepStrictEqual(fed.map((q) => q.question_id), ['q1', 'q2']);
  assert.deepStrictEqual(plain(BB.results.questionsFedBy(VIS_PAYLOAD, 99)), []);
});

test('CSV carries the visual source column', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  const csv = BB.results.toCsv(VIS_PAYLOAD);
  assert.ok(csv.split('\n')[0].endsWith('Visual Source'));
  assert.ok(csv.includes('"Drawing p.7"'));
});

// ---- visual events in the progress story --------------------------------------

test('visual scan events narrate under the 12% window band and never outrank it', () => {
  const { BB } = loadModules(['shared/assets/js/bb-status.js']);
  const status = BB.status.fromEvents([
    { event: 'analysis_started', payload: {} },
    { event: 'visual_scan_start', payload: { candidate_pages: [3, 7] } },
    { event: 'visual_page_complete', payload: { page: 3, scanned: 1, total_candidates: 2 } },
    { event: 'visual_scan_complete', payload: { findings_count: 2 } },
  ]);
  assert.strictEqual(status.phase, 'preparing');
  assert.ok(status.fraction <= 0.12, 'visual scan must stay under the window band');
  assert.match(status.detail, /Visual intelligence captured from 2 pages/);
});

test('a failed visual scan reads as skipped, not as an analysis error', () => {
  const { BB } = loadModules(['shared/assets/js/bb-status.js']);
  const line = BB.status.friendlyLine({ event: 'visual_scan_failed', payload: {} });
  assert.match(line, /skipped/i);
});

// ---- Document Intelligence must survive the results handoff (2.5.1) --------
// A completed analysis emits results_ready WITH dynamic_tables, then the engine
// fetches /api/results and calls finish() with that payload. When the fetch
// landed on a branch that rebuilt the payload without the tables, finish()
// overwrote the good one and the DI tab vanished - while the Excel export,
// which reads the session dict directly, still had the sheet.

const ENGINE_MODULES = [
  'shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-status.js', 'shared/assets/js/bb-orb.js',
  'shared/assets/js/bb-shell.js', 'shared/assets/js/bb-engine.js',
];

const RICH = {
  sections: [], dynamic_tables: [{ title: 'Pipe Segments', columns: [], rows: [] }],
  intelligence_focus: 'Scope and quantities', visual_findings: [{ page: 3, kind: 'drawing' }],
};

test('finish() never downgrades a payload that already has DI tables', () => {
  const { BB } = loadModules(ENGINE_MODULES);
  const thin = { sections: [], dynamic_tables: [], intelligence_focus: '' };
  const merged = plain(BB.engine.mergeResults(RICH, thin));
  assert.strictEqual(merged.dynamic_tables.length, 1,
    'the DI tab disappears if a thinner payload is allowed to win');
  assert.strictEqual(merged.intelligence_focus, 'Scope and quantities');
  assert.strictEqual(merged.visual_findings.length, 1);
});

test('a richer incoming payload still wins', () => {
  const { BB } = loadModules(ENGINE_MODULES);
  const merged = plain(BB.engine.mergeResults(
    { sections: [], dynamic_tables: [] },
    { sections: [], dynamic_tables: [{ title: 'New' }] }));
  assert.strictEqual(merged.dynamic_tables.length, 1);
  assert.strictEqual(merged.dynamic_tables[0].title, 'New');
});

test('merge tolerates a missing previous payload', () => {
  const { BB } = loadModules(ENGINE_MODULES);
  assert.deepStrictEqual(plain(BB.engine.mergeResults(null, RICH)).dynamic_tables.length, 1);
  assert.deepStrictEqual(plain(BB.engine.mergeResults(RICH, null)).dynamic_tables.length, 1);
});

test('the Document Intelligence tab appears whenever tables exist', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  const ids = plain(BB.results.sheetList(RICH)).map((s) => s.id);
  assert.ok(ids.includes('intelligence'),
    'tables present must always yield a Document Intelligence tab');
});

test('the admin session view mounts the SAME workbook as the user sees', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  assert.strictEqual(typeof BB.results.buildWorkbook, 'function',
    'admin renders sessions through buildWorkbook so the sheets can never diverge');
});

// ---- storage status must be legible at a glance (2.5.4) --------------------
// "Connected but empty" and "not connected at all" produce an identical session
// list, which is exactly how a silent storage failure hides from an admin.

test('storage line names the specific failure, not just "not working"', () => {
  const { BB } = loadModules(ADMIN_MODULES);
  const line = (info) => BB.admin.storageStatusText(info).text;

  assert.match(line({ database_url_set: false }), /DATABASE_URL is not set/);
  assert.match(line({ database_url_set: true, persistence: { enabled: false, error: 'bad password' } }),
    /FAILED to start .*bad password/);
  assert.match(line({ database_url_set: true, persistence: { enabled: true, reachable: true },
                      write_test: { ok: false, reason: 'write_failed', error: 'read-only role' } }),
    /connected but NOT writable .*read-only role/);
});

test('a healthy store reports what is actually stored', () => {
  const { BB } = loadModules(ADMIN_MODULES);
  const status = BB.admin.storageStatusText({
    database_url_set: true, persistence: { enabled: true, reachable: true },
    write_test: { ok: true }, stored_analyses: 7, indexed_in_memory: 7,
    retention: 'indefinite',
  });
  assert.strictEqual(status.ok, true);
  const text = status.text;
  assert.match(text, /active/);
  assert.match(text, /7 analysis\(es\) stored/);
  assert.match(text, /retention indefinite/);
});

// ---- Settings version must come from the server (2.5.6) --------------------
// A hardcoded literal sat at 2.3.0 through five releases. The About card now
// reads /health, so it cannot drift from the running build again.

const SETTINGS_MODULES = [
  'shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-settings.js',
];

test('settings does not ship a hardcoded version literal', () => {
  const fs = require('fs');
  const src = fs.readFileSync('shared/assets/js/bb-settings.js', 'utf8');
  assert.ok(!/VERSION\s*=\s*'\d+\.\d+\.\d+'/.test(src),
    'a literal version here silently drifts from the real build');
  assert.match(src, /fetch\('\/health'\)/, 'version must be read from the server');
});

test('the version placeholder is replaced once /health answers', async () => {
  const { BB } = loadModules(SETTINGS_MODULES, {
    fetch: () => Promise.resolve({ json: () => Promise.resolve({ version: '9.9.9' }) }),
  });
  assert.strictEqual(BB.settings.version(), '—', 'placeholder before the fetch');
  BB.settings.loadVersion();
  await new Promise((r) => setTimeout(r, 10));
  assert.strictEqual(BB.settings.version(), '9.9.9', 'must show the running build');
});

test('patent attribution names the filer, company credit stays', () => {
  const fs = require('fs');
  const settings = fs.readFileSync('shared/assets/js/bb-settings.js', 'utf8');
  const login = fs.readFileSync('login.html', 'utf8');
  assert.match(settings, /Patent Pending — Stephen Bartlett/);
  assert.match(login, /Patent Pending — Stephen Bartlett/);
  assert.ok(!/Patent Pending — Additional Intelligence/.test(settings));
  // Comma-tolerant: the login footer writes the legal name "Additional
  // Intelligence, LLC" while Settings writes it without the comma. The credit
  // is what must survive, not one file's punctuation.
  assert.match(settings, /Additional Intelligence,? LLC/, 'company credit remains');
  assert.match(login, /Additional Intelligence,? LLC/, 'company credit remains');
});
