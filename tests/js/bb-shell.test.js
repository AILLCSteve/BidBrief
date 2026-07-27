'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules, plain } = require('./_harness');

const MODULES = [
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-orb.js',
  'shared/assets/js/bb-shell.js',
];

function ids(tabs) { return plain(tabs).map((t) => t.id); }

test('plain users get three tabs - no Admin slot', () => {
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

test('applyUserInfo treats admin, premium and bonus grants as premium', () => {
  const { BB } = loadModules(MODULES);
  BB.shell.applyUserInfo({ success: true, username: 'bob', role: 'user', is_admin: false });
  assert.strictEqual(BB.state.session.hasPremium, false);

  BB.shell.applyUserInfo({ success: true, username: 'bob', premium: true });
  assert.strictEqual(BB.state.session.hasPremium, true);

  BB.shell.applyUserInfo({ success: true, username: 'bob', bonus_features: ['cityscraper'] });
  assert.strictEqual(BB.state.session.hasPremium, true);

  BB.shell.applyUserInfo({ success: true, username: 'root', is_admin: true });
  assert.strictEqual(BB.state.session.isAdmin, true);
  assert.strictEqual(BB.state.session.hasPremium, true, 'admins hold every premium feature');
});

test('a failed user-info response leaves the user a plain user', () => {
  const { BB } = loadModules(MODULES);
  BB.shell.applyUserInfo({ success: false });
  assert.strictEqual(BB.state.session.isAdmin, false);
  assert.strictEqual(BB.state.session.hasPremium, false);
});
