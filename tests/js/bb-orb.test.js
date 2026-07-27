'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const { BB } = loadModules(['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-orb.js']);

test('starPoints is deterministic - same input, same field', () => {
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
  assert.deepStrictEqual(
    [0, 1, 2, 3].map((i) => BB.orb.driftFor(i, 4)),
    [-1.5, -0.5, 0.5, 1.5]
  );
  assert.deepStrictEqual([0, 1, 2].map((i) => BB.orb.driftFor(i, 3)), [-1, 0, 1]);
});
