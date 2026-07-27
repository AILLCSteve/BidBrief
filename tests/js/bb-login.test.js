'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const MODULES = [
  'shared/assets/js/bb-ui.js', 'shared/assets/js/bb-orb.js',
  'shared/assets/js/bb-login.js',
];

test('the beta terms state the limit, the time limit and the paywall', () => {
  const { BB } = loadModules(MODULES);
  const copy = BB.login.betaTerms(5);

  assert.strictEqual(copy.title, 'Free Beta Testing');
  assert.match(copy.points.join(' '), /5 documents/);
  assert.match(copy.points.join(' '), /limited time/i);
  assert.match(copy.fine, /paid subscription is required/i);
  assert.match(copy.fine, /full functionality/i);
});

test('the terms pluralise a single-document quota', () => {
  const { BB } = loadModules(MODULES);
  const copy = BB.login.betaTerms(1);
  assert.match(copy.points[0], /1 document\b/);
  assert.ok(!copy.points[0].includes('1 documents'));
});

test('a missing or nonsense quota falls back to 5 rather than showing zero', () => {
  const { BB } = loadModules(MODULES);
  assert.match(BB.login.betaTerms(undefined).fine, /5 documents/);
  assert.match(BB.login.betaTerms(0).fine, /5 documents/);
});

test('the terms name the session length so nobody expects a permanent account', () => {
  const { BB } = loadModules(MODULES);
  const copy = BB.login.betaTerms(5);
  assert.match(copy.points.join(' '), /24 hours/);
  assert.match(copy.points.join(' '), /No account/i);
});

test('the sign-in error vocabulary covers the beta exits', () => {
  const { BB } = loadModules(MODULES);
  assert.ok(BB.login.MESSAGES.beta_closed);
  assert.ok(BB.login.MESSAGES.beta_ended);
  assert.match(BB.login.MESSAGES.beta_ended, /subscribe/i);
});
