'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules, plain } = require('./_harness');

const MODULES = [
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-orb.js',
  'shared/assets/js/bb-shell.js',
  'shared/assets/js/bb-libraries.js',
  'shared/assets/js/bb-qgen.js',
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
  const body = plain(BB.questionHub.buildSaveBody(BB.state.questionHub.config));
  const section = body.sections[0];
  assert.strictEqual(section.section_description, 'Surety requirements',
    'section_description drives backend expert generation - never strip it');
  assert.strictEqual(section.section_summary, 'Bonding drives who can bid.');
  assert.strictEqual(section.questions[0].required, true);
  assert.strictEqual(section.questions[0].expected_type, 'percent',
    'expected_type drives backend expert generation - never strip it');
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
    plain(BB.state.questionHub.config.sections[0].questions).map((q) => q.enabled), [true, true]);
  BB.questionHub.setSectionEnabled('s1', false);
  assert.deepStrictEqual(
    plain(BB.state.questionHub.config.sections[0].questions).map((q) => q.enabled), [false, false]);
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

test('updateQuestion rewrites text and the enabled flag', () => {
  const BB = withConfig();
  BB.questionHub.updateQuestion('s1', 'q2', 'Payment bond amount?', true);
  const q = BB.state.questionHub.config.sections[0].questions[1];
  assert.strictEqual(q.text, 'Payment bond amount?');
  assert.strictEqual(q.enabled, true);
});

test('renameSection renames without touching questions', () => {
  const BB = withConfig();
  BB.questionHub.renameSection('s1', 'Bonds & Surety');
  assert.strictEqual(BB.state.questionHub.config.sections[0].section_name, 'Bonds & Surety');
  assert.strictEqual(BB.state.questionHub.config.sections[0].questions.length, 2);
});

test('applying a config confirms the set (a genuine confirm path)', () => {
  const BB = withConfig();
  BB.state.setConfirmed(false);
  BB.questionHub.apply({ sections: [{ section_id: 'x', section_name: 'X', questions: [] }] });
  assert.strictEqual(BB.state.questionHub.isConfirmed, true);
});

test('apply defaults every question to enabled without dropping other keys', () => {
  const BB = withConfig();
  BB.questionHub.apply({
    sections: [{
      section_id: 'x', section_name: 'X',
      questions: [{ id: 'q9', text: 'Q', required: false, expected_type: 'text' }],
    }],
  });
  const q = BB.state.questionHub.config.sections[0].questions[0];
  assert.strictEqual(q.enabled, true);
  assert.strictEqual(q.expected_type, 'text');
});

test('proceedWithDefaults confirms without changing the loaded config', () => {
  const BB = withConfig();
  BB.state.setConfirmed(false);
  const before = JSON.stringify(plain(BB.state.questionHub.config));
  BB.questionHub.proceedWithDefaults();
  assert.strictEqual(BB.state.questionHub.isConfirmed, true);
  assert.strictEqual(JSON.stringify(plain(BB.state.questionHub.config)), before);
});
