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

test('admins see the sessions dashboard, beta, the bonus manager and CityScraper', () => {
  const { BB } = loadModules(MODULES);
  assert.deepStrictEqual(
    ids(BB.admin.entriesFor({ isAdmin: true, hasPremium: true })),
    ['sessions', 'beta', 'bonus', 'scraper']
  );
});

test("bonus users see ONLY CityScraper - never other users' work", () => {
  const { BB } = loadModules(MODULES);
  const entries = ids(BB.admin.entriesFor({ isAdmin: false, hasPremium: true }));
  assert.deepStrictEqual(entries, ['scraper']);
  assert.ok(!entries.includes('sessions'),
    "the sessions dashboard exposes other users' analyses - admin only");
  assert.ok(!entries.includes('bonus'));
  assert.ok(!entries.includes('beta'),
    'the beta manager can delete testers and lift quotas - admin only');
});

test('plain users get nothing here', () => {
  const { BB } = loadModules(MODULES);
  assert.deepStrictEqual(ids(BB.admin.entriesFor({ isAdmin: false, hasPremium: false })), []);
});

test('the quota line states usage and what is left', () => {
  const { BB } = loadModules(MODULES);
  assert.strictEqual(
    BB.admin.quotaText({ docs_used: 3, doc_limit: 5, docs_remaining: 2 }),
    '3 of 5 documents used  ·  2 left'
  );
});

test('a tester at their limit reads as limit reached, never "0 left"', () => {
  const { BB } = loadModules(MODULES);
  assert.strictEqual(
    BB.admin.quotaText({ docs_used: 5, doc_limit: 5, docs_remaining: 0 }),
    '5 of 5 documents used  ·  limit reached'
  );
});

test('the beta summary counts testers, sign-ins, documents and exhaustion', () => {
  const { BB } = loadModules(MODULES);
  const text = BB.admin.betaSummaryText(
    { tester_count: 2, signed_in_count: 1, docs_used: 7, exhausted_count: 1 }, 5);
  assert.match(text, /2 testers/);
  assert.match(text, /1 signed in/);
  assert.match(text, /7 documents processed/);
  assert.match(text, /1 at their limit/);
  assert.match(text, /5 free documents each/);
});

test('the beta summary handles an empty population', () => {
  const { BB } = loadModules(MODULES);
  assert.match(BB.admin.betaSummaryText({}, 5), /^0 testers/);
  assert.match(BB.admin.betaSummaryText(null, 5), /^0 testers/);
});

test('a session line carries mode, answers, pages and a short id', () => {
  const { BB } = loadModules(MODULES);
  const meta = BB.admin.sessionMeta({
    session_id: 'sess_abcdef0123456789', mode: 'bid_spec',
    questions_answered: 12, total_pages: 40, completed_at: null
  });
  assert.match(meta, /Bid Spec/);
  assert.match(meta, /12 answered/);
  assert.match(meta, /40 pages/);
  assert.match(meta, /sess_abcdef012/);
});

test('a session line survives the "N/A" stats the server sends for active runs', () => {
  const { BB } = loadModules(MODULES);
  const meta = BB.admin.sessionMeta({
    session_id: 'sess_x', mode: 'bestprep',
    questions_answered: 'N/A', total_pages: 'N/A'
  });
  assert.match(meta, /BestPrep/);
  assert.ok(!meta.includes('N/A'), 'placeholder stats must not reach the admin');
});

test('status maps to the chip vocabulary', () => {
  const { BB } = loadModules(MODULES);
  assert.strictEqual(BB.admin.statusKind('active'), 'live');
  assert.strictEqual(BB.admin.statusKind('completed'), 'ok');
  assert.strictEqual(BB.admin.statusKind('legacy_completed'), 'ok');
  assert.strictEqual(BB.admin.statusKind('partial'), 'warn');
  assert.strictEqual(BB.admin.statusKind('anything_else'), 'idle');
});

test('the page title follows the role', () => {
  const { BB } = loadModules(MODULES);
  assert.deepStrictEqual(plain(BB.admin.headingFor({ isAdmin: true })),
    { title: 'Admin', subtitle: 'Server operations' });
  assert.deepStrictEqual(plain(BB.admin.headingFor({ isAdmin: false, hasPremium: true })),
    { title: 'Bonus Features', subtitle: 'Premium features unlocked for you' });
});
