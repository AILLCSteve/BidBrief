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
