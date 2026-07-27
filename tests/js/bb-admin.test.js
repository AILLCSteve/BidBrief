'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules, plain } = require('./_harness');

const MODULES = [
  'shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-orb.js', 'shared/assets/js/bb-shell.js',
  'shared/assets/js/bb-scraper.js', 'shared/assets/js/bb-admin.js',
];

const ids = (entries) => plain(entries).map((e) => e.id);

test('admins see the sessions dashboard, the bonus manager and CityScraper', () => {
  const { BB } = loadModules(MODULES);
  assert.deepStrictEqual(
    ids(BB.admin.entriesFor({ isAdmin: true, hasPremium: true })),
    ['sessions', 'bonus', 'scraper']
  );
});

test("bonus users see ONLY CityScraper - never other users' work", () => {
  const { BB } = loadModules(MODULES);
  const entries = ids(BB.admin.entriesFor({ isAdmin: false, hasPremium: true }));
  assert.deepStrictEqual(entries, ['scraper']);
  assert.ok(!entries.includes('sessions'),
    "the sessions dashboard exposes other users' analyses - admin only");
  assert.ok(!entries.includes('bonus'));
});

test('plain users get nothing here', () => {
  const { BB } = loadModules(MODULES);
  assert.deepStrictEqual(ids(BB.admin.entriesFor({ isAdmin: false, hasPremium: false })), []);
});

test('the page title follows the role', () => {
  const { BB } = loadModules(MODULES);
  assert.deepStrictEqual(plain(BB.admin.headingFor({ isAdmin: true })),
    { title: 'Admin', subtitle: 'Server operations' });
  assert.deepStrictEqual(plain(BB.admin.headingFor({ isAdmin: false, hasPremium: true })),
    { title: 'Bonus Features', subtitle: 'Premium features unlocked for you' });
});
