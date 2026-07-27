'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules, plain } = require('./_harness');

const { BB } = loadModules(['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-status.js']);

const ev = (event, payload) => ({ event, timestamp: '', payload: payload || {} });

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
    ev('window_complete', { window_num: 5, total_windows: 10 }),
  ]);
  assert.ok(Math.abs(half.fraction - (0.12 + 0.78 * 0.5)) < 1e-9,
    `expected 0.51, got ${half.fraction}`);

  const last = BB.status.fromEvents([
    ev('window_complete', { window_num: 10, total_windows: 10 }),
  ]);
  assert.ok(Math.abs(last.fraction - 0.90) < 1e-9, `expected 0.90, got ${last.fraction}`);
});

test('analysis_complete is NOT the end - only results_ready completes', () => {
  const mid = BB.status.fromEvents([ev('analysis_complete')]);
  assert.ok(mid.fraction < 1, 'analysis_complete fires before results are packaged');
  assert.notStrictEqual(mid.phase, 'complete');

  const done = BB.status.fromEvents([ev('analysis_complete'), ev('results_ready')]);
  assert.strictEqual(done.phase, 'complete');
  assert.strictEqual(done.fraction, 1);
});

test('phase and fraction only ever move forward, whatever the event order', () => {
  const s = BB.status.fromEvents([
    ev('window_complete', { window_num: 9, total_windows: 10 }),
    ev('prescan_start'),
  ]);
  assert.strictEqual(s.phase, 'analyzing');
  assert.ok(s.fraction > 0.5, 'a late-arriving early event must not rewind the bar');
});

test('friendlyLine narrates real events and stays silent on internals', () => {
  assert.match(
    BB.status.friendlyLine(ev('window_processing', { window_num: 2, total_windows: 8 })),
    /window 2 of 8/i
  );
  assert.strictEqual(BB.status.friendlyLine(ev('layer_3_internal_thing')), null);
});

test('the track shows five steps, ending before "complete"', () => {
  assert.deepStrictEqual(
    plain(BB.status.TRACK_STEPS).map((p) => p.key),
    ['preparing', 'experts', 'analyzing', 'verifying', 'finalizing']
  );
});

test('window_processing narrates the page range when the backend sends one', () => {
  const s = BB.status.fromEvents([
    ev('window_processing', { window_num: 3, total_windows: 12, pages: '41-60' }),
  ]);
  assert.match(s.detail, /window 3 of 12/i);
  assert.match(s.detail, /41-60/);
});

test('a server packaging note about intelligence pushes the bar to 98%', () => {
  const s = BB.status.fromEvents([
    ev('analysis_complete'),
    ev('status', { message: 'Building document intelligence tables' }),
  ]);
  assert.ok(Math.abs(s.fraction - 0.98) < 1e-9, `expected 0.98, got ${s.fraction}`);
  assert.match(s.detail, /intelligence/i);
});
