'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules, plain } = require('./_harness');

const MODULES = [
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-orb.js',
  'shared/assets/js/bb-status.js',
  'shared/assets/js/bb-shell.js',
  'shared/assets/js/bb-analyze.js',
];

function setup() {
  const { BB } = loadModules(MODULES);
  BB.state.questionHub.config = {
    sections: [
      { section_id: 's1', section_name: 'Bonds', questions: [{ id: 'q1' }] },
      { section_id: 's2', section_name: 'Schedule', questions: [{ id: 'q2' }] },
      { section_id: 's3', section_name: 'Insurance', questions: [{ id: 'q3' }] },
    ],
  };
  return BB;
}

test('WYSIWYG: an explicit selection is sent verbatim', () => {
  const BB = setup();
  BB.state.analysis.enabledSections = ['s1', 's3'];
  const body = plain(BB.analyze.buildAnalyzePayload(BB.state, 'up-1', 'bid.pdf'));
  assert.deepStrictEqual(body.enabled_sections, ['s1', 's3']);
});

test('WYSIWYG: a FULL selection is still sent explicitly, never collapsed to null', () => {
  const BB = setup();
  BB.state.analysis.enabledSections = ['s1', 's2', 's3'];
  const body = plain(BB.analyze.buildAnalyzePayload(BB.state, 'up-1', 'bid.pdf'));
  assert.deepStrictEqual(body.enabled_sections, ['s1', 's2', 's3'],
    'collapsing a full selection is the bug that leaked deselections into analysis');
});

test('no selection yet means every section in the loaded config', () => {
  const BB = setup();
  BB.state.analysis.enabledSections = null;
  const body = plain(BB.analyze.buildAnalyzePayload(BB.state, 'up-1', 'bid.pdf'));
  assert.deepStrictEqual(body.enabled_sections, ['s1', 's2', 's3']);
});

test('payload carries upload id, filename, guardrails, mode and the advanced flags', () => {
  const BB = setup();
  BB.state.analysis.contextGuardrails = '  Only CIPP lining  ';
  BB.state.analysis.mode = 'bestprep';
  BB.state.analysis.enableSecondPass = true;
  BB.state.analysis.recheckEmptyWindows = true;
  BB.state.analysis.enableDeepRAG = false;
  const body = plain(BB.analyze.buildAnalyzePayload(BB.state, 'up-9', 'spec.pdf'));
  assert.strictEqual(body.upload_id, 'up-9');
  assert.strictEqual(body.pdf_filename, 'spec.pdf');
  assert.strictEqual(body.context_guardrails, 'Only CIPP lining');
  assert.strictEqual(body.mode, 'bestprep');
  assert.strictEqual(body.enable_second_pass, true);
  assert.strictEqual(body.recheck_empty_windows, true);
  assert.strictEqual(body.enable_deep_rag, false);
  assert.strictEqual(body.pipeline_mode, 'classic');
});

test('empty guardrails are omitted, not sent as an empty string', () => {
  const BB = setup();
  BB.state.analysis.contextGuardrails = '   ';
  const body = plain(BB.analyze.buildAnalyzePayload(BB.state, 'up-1', 'bid.pdf'));
  assert.strictEqual('context_guardrails' in body, false);
});

test('high_power is only sent when the user actually has premium', () => {
  const BB = setup();
  BB.state.analysis.highPower = true;
  BB.state.session.hasPremium = false;
  assert.strictEqual(
    'high_power' in plain(BB.analyze.buildAnalyzePayload(BB.state, 'u', 'f.pdf')), false,
    'sending high_power without premium earns a 403');
  BB.state.session.hasPremium = true;
  assert.strictEqual(plain(BB.analyze.buildAnalyzePayload(BB.state, 'u', 'f.pdf')).high_power, true);
});

test('toggling a section writes an explicit set, starting from all-on', () => {
  const BB = setup();
  BB.state.analysis.enabledSections = null;
  BB.analyze.setSectionEnabled('s2', false);
  assert.deepStrictEqual(plain(BB.state.analysis.enabledSections), ['s1', 's3']);
  BB.analyze.setSectionEnabled('s2', true);
  assert.deepStrictEqual(plain(BB.state.analysis.enabledSections).sort(), ['s1', 's2', 's3']);
});

test('canStartAnalysis requires both a document and a confirmed question set', () => {
  const BB = setup();
  assert.strictEqual(BB.analyze.canStart(), false);
  BB.state.noteFreshUpload({ name: 'bid.pdf' });
  assert.strictEqual(BB.analyze.canStart(), false, 'a document alone is not enough');
  BB.state.setConfirmed(true);
  assert.strictEqual(BB.analyze.canStart(), true);
});
