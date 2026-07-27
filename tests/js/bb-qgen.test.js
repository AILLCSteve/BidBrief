'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const { BB } = loadModules([
  'shared/assets/js/bb-ui.js',
  'shared/assets/js/bb-state.js',
  'shared/assets/js/bb-qgen.js',
]);

const pdf = (name) => ({ name, type: 'application/pdf' });
const txt = (name) => ({ name, type: 'text/plain' });

test('text only -> a plain JSON request', () => {
  const p = BB.qgen.buildGeneratePayload({ userText: 'Cover bonds and insurance' });
  assert.strictEqual(p.kind, 'json');
  assert.strictEqual(p.fields.user_input, 'Cover bonds and insurance');
  assert.deepStrictEqual(Object.keys(p.files), []);
});

test('the analyzer document alone rides the primary file slot as context', () => {
  const doc = pdf('bid.pdf');
  const p = BB.qgen.buildGeneratePayload({ userText: 'give me 3 questions', contextFile: doc });
  assert.strictEqual(p.kind, 'multipart');
  assert.strictEqual(p.files.file, doc);
  assert.strictEqual(p.fields.source_kind, 'context');
  assert.strictEqual('context_file' in p.files, false);
});

test('REGRESSION 2.1.1: a PDF questions-source must NOT displace the document context', () => {
  const doc = pdf('bid.pdf');
  const source = pdf('standard.pdf');
  const p = BB.qgen.buildGeneratePayload({
    userText: '', contextFile: doc, questionsSourceFile: source,
  });
  assert.strictEqual(p.files.file, source, 'the questions-source takes the primary slot');
  assert.strictEqual(p.files.context_file, doc,
    'the analyzer doc MUST still be sent as context_file - dropping it un-grounds Q-gen');
  assert.strictEqual(p.fields.source_kind, 'questions_source');
});

test('a text questions-source is folded into user_input locally, not uploaded', () => {
  const p = BB.qgen.buildGeneratePayload({
    userText: 'Focus on schedule',
    questionsSourceFile: txt('notes.txt'),
    questionsSourceText: 'Q: When does work start?',
    contextFile: pdf('bid.pdf'),
  });
  assert.strictEqual(p.files.file.name, 'bid.pdf',
    'with no PDF questions-source the analyzer doc keeps the primary slot');
  assert.strictEqual(p.fields.source_kind, 'context');
  assert.match(p.fields.user_input, /Focus on schedule/);
  assert.match(p.fields.user_input, /When does work start/);
});

test('source_intent is sent when given and omitted when blank', () => {
  const doc = pdf('bid.pdf');
  const withIntent = BB.qgen.buildGeneratePayload({
    userText: 'x', contextFile: doc, sourceIntent: '  derive from this standard  ',
  });
  assert.strictEqual(withIntent.fields.source_intent, 'derive from this standard');

  const without = BB.qgen.buildGeneratePayload({ userText: 'x', contextFile: doc, sourceIntent: '  ' });
  assert.strictEqual('source_intent' in without.fields, false);
});

test('high_power is NEVER sent for Q-gen - the backend forces it for everyone', () => {
  const p = BB.qgen.buildGeneratePayload({ userText: 'x', contextFile: pdf('bid.pdf') });
  assert.strictEqual('high_power' in p.fields, false,
    're-introducing high_power here re-introduces the 403 gate for non-premium users');
});

test('document-only generation synthesises a default instruction', () => {
  const p = BB.qgen.buildGeneratePayload({ userText: '', contextFile: pdf('bid.pdf') });
  assert.ok(p.fields.user_input && p.fields.user_input.length > 10,
    'a blank field plus a doc must still carry an instruction');
});

test('canGenerate needs text or a file', () => {
  assert.strictEqual(BB.qgen.canGenerate({ userText: '   ' }), false);
  assert.strictEqual(BB.qgen.canGenerate({ userText: 'ask about bonds' }), true);
  assert.strictEqual(BB.qgen.canGenerate({ contextFile: pdf('a.pdf') }), true);
  assert.strictEqual(BB.qgen.canGenerate({ questionsSourceFile: txt('a.txt') }), true);
});

test('isTextSource identifies the files we read locally', () => {
  assert.strictEqual(BB.qgen.isTextSource(txt('notes.txt')), true);
  assert.strictEqual(BB.qgen.isTextSource({ name: 'list.csv', type: 'text/csv' }), true);
  assert.strictEqual(BB.qgen.isTextSource({ name: 'notes.md', type: '' }), true);
  assert.strictEqual(BB.qgen.isTextSource(pdf('spec.pdf')), false);
});

test('mergeSuggestions appends new sections and never duplicates a question', () => {
  const config = {
    sections: [{ section_id: 's1', section_name: 'Bonds', questions: [{ id: 'q1', text: 'A' }] }],
  };
  const suggestions = [
    { section_id: 's1', section_name: 'Bonds', questions: [{ id: 'q1', text: 'A' }, { id: 'q9', text: 'B' }] },
    { section_id: 's2', section_name: 'Safety', questions: [{ id: 'q5', text: 'C' }] },
  ];
  BB.qgen.mergeSuggestions(config, suggestions, ['s1', 's2']);
  assert.strictEqual(config.sections.length, 2);
  assert.deepStrictEqual(config.sections[0].questions.map((q) => q.id), ['q1', 'q9']);
  assert.strictEqual(config.sections[1].section_name, 'Safety');
});

test('mergeSuggestions honours the user selection', () => {
  const config = { sections: [] };
  const suggestions = [
    { section_id: 'a', section_name: 'A', questions: [{ id: '1' }] },
    { section_id: 'b', section_name: 'B', questions: [{ id: '2' }] },
  ];
  BB.qgen.mergeSuggestions(config, suggestions, ['b']);
  assert.deepStrictEqual(config.sections.map((s) => s.section_id), ['b']);
});
