'use strict';
/* The Document Intelligence tab must appear whenever the Excel export would
   render its sheet.

   Excel gates on `if result.get('dynamic_tables')` — a plain truthiness check —
   then iterates. The browser gated on `.length`, which is `undefined` for a
   dict, so the very same payload produced a sheet in Excel and NO tab in the
   browser. That silent divergence is the bug; these tests pin the agreement. */
const test = require('node:test');
const assert = require('node:assert');
const { loadModules, plain } = require('./_harness');

const RESULTS_MODULES = [
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-results.js',
];

const TABLE = {
  title: 'Pipe Schedule',
  columns: [{ key: 'size', label: 'Size' }, { key: 'material', label: 'Material' }],
  rows: [{ size: '8"', material: 'DIP' }],
};

const BASE = { sections: [], total_questions: 0, questions_answered: 0 };

function sheetIds(payload) {
  const { BB } = loadModules(RESULTS_MODULES);
  return plain(BB.sheetList ? BB.sheetList(payload) : BB.results.sheetList(payload))
    .map((s) => s.id);
}

test('an ARRAY of tables earns the Document Intelligence tab', () => {
  const ids = sheetIds(Object.assign({}, BASE, { dynamic_tables: [TABLE] }));
  assert.ok(ids.includes('intelligence'), 'array payload lost the DI tab');
});

test('a DICT of tables earns it too — Excel renders this shape', () => {
  /* The exact divergence: `.length` on an object is undefined, so this payload
     used to produce an Excel sheet and no browser tab. */
  const ids = sheetIds(Object.assign({}, BASE, {
    dynamic_tables: { pipes: TABLE },
  }));
  assert.ok(ids.includes('intelligence'),
    'a dict of tables renders in Excel but was dropped by the browser');
});

test('a single bare table object earns it', () => {
  const ids = sheetIds(Object.assign({}, BASE, { dynamic_tables: TABLE }));
  assert.ok(ids.includes('intelligence'), 'a lone table object was dropped');
});

test('no intelligence of any kind means no tab', () => {
  const ids = sheetIds(Object.assign({}, BASE, { dynamic_tables: [] }));
  assert.ok(!ids.includes('intelligence'), 'an empty payload must not earn a tab');
});

test('a stated failure still earns the tab, so it can explain itself', () => {
  /* Hiding the tab when generation failed is indistinguishable from the feature
     not existing. Showing the reason is an answer. */
  const ids = sheetIds(Object.assign({}, BASE, {
    dynamic_tables: [], intelligence_error: 'RateLimitError: quota exceeded',
  }));
  assert.ok(ids.includes('intelligence'), 'a failed DI pass should say so');
});

test('a focus line alone earns the tab', () => {
  const ids = sheetIds(Object.assign({}, BASE, {
    dynamic_tables: [], intelligence_focus: 'pipe materials and bedding',
  }));
  assert.ok(ids.includes('intelligence'));
});

test('normalising never invents tables out of nothing', () => {
  const { BB } = loadModules(RESULTS_MODULES);
  const fn = BB.results.dynamicTables || BB.dynamicTables;
  if (!fn) return; // not exported; sheetList coverage above is the contract
  assert.deepStrictEqual(plain(fn({})), []);
  assert.deepStrictEqual(plain(fn({ dynamic_tables: null })), []);
  assert.deepStrictEqual(plain(fn(null)), []);
});

/* The completion-view bug, reproduced as the backend's REAL event order.

   app.py emits analysis_complete from inside the orchestrator, THEN spends
   20-60s generating the Document Intelligence tables, THEN appends
   results_ready carrying them. Treating analysis_complete as terminal stopped
   the poll before results_ready ever arrived, so the completion view showed
   every tab except Document Intelligence while the admin view — a fresh fetch
   of the finished session — had it. */
const ENGINE_MODULES = [
  'shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-status.js', 'shared/assets/js/bb-orb.js',
  'shared/assets/js/bb-shell.js', 'shared/assets/js/bb-engine.js',
];

/* Timers are stubbed: the engine arms a 4-minute fallback on analysis_complete,
   and a real one would hold Node's event loop open for four minutes. */
const NO_TIMERS = { setTimeout: () => 1, clearTimeout: () => {}, clearInterval: () => {} };

test('the real event order lands the DI tables in the completion view', () => {
  const { BB } = loadModules(ENGINE_MODULES, NO_TIMERS);
  const handle = BB.engine.handleEvent;
  assert.ok(handle, 'bb-engine must export handleEvent for this contract to be testable');

  // 1. The orchestrator says it is done — packaging has NOT run yet.
  handle({ event: 'analysis_complete' });
  // 2. Packaging finishes and delivers the only payload carrying the tables.
  handle({
    event: 'results_ready',
    result: { sections: [], dynamic_tables: [TABLE], intelligence_focus: 'scope' },
    statistics: { questions_answered: 1, total_questions: 1 },
  });

  const results = plain(BB.state.analysis.results || {});
  assert.ok((results.dynamic_tables || []).length,
    'results_ready never reached the client — analysis_complete stopped the poll early');
  assert.ok(sheetIds(results).includes('intelligence'),
    'the completion view is missing the Document Intelligence tab');
});

/* THE mechanism, asserted directly: the poll must still be running after
   analysis_complete. Asserting only on the final payload cannot catch this —
   a test that hands over results_ready by hand passes even when production
   would never have received it, because the poll had already been cancelled. */
test('polling survives analysis_complete, or results_ready is never received', () => {
  const cleared = [];
  const { BB } = loadModules(ENGINE_MODULES, {
    setTimeout: () => 1,
    clearTimeout: () => {},
    setInterval: () => 42,
    clearInterval: (id) => cleared.push(id),
    fetch: () => Promise.resolve({ json: () => Promise.resolve({ success: true }) }),
  });

  BB.engine.startPolling('sess_test');
  cleared.length = 0; // startPolling clears any previous timer first

  BB.engine.handleEvent({ event: 'analysis_complete' });
  assert.deepStrictEqual(cleared, [],
    'the poll was cancelled on analysis_complete — results_ready, the only event ' +
    'carrying the Document Intelligence tables, could never arrive');

  BB.engine.handleEvent({
    event: 'results_ready',
    result: { sections: [], dynamic_tables: [TABLE] },
  });
  assert.deepStrictEqual(cleared, [42], 'results_ready should end the poll');
});
