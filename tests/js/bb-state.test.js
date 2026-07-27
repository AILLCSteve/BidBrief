'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules, plain } = require('./_harness');

function fresh() {
  return loadModules(['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js']).BB.state;
}

test('no document waiting -> no cue', () => {
  const s = fresh();
  assert.strictEqual(s.onboardingHint(), 'none');
});

test('a fresh upload cues Questions', () => {
  const s = fresh();
  s.noteFreshUpload({ name: 'bid.pdf' });
  assert.strictEqual(s.onboardingHint(), 'chooseQuestions');
});

test('an unconfirmed set cues Questions even with a document', () => {
  const s = fresh();
  s.noteFreshUpload({ name: 'bid.pdf' });
  s.analysis.needsQuestionChoice = false;
  assert.strictEqual(s.onboardingHint(), 'chooseQuestions');
});

test('REGRESSION 2.1.3: creating a set clears the pending choice and advances to Analyze', () => {
  const s = fresh();
  s.noteFreshUpload({ name: 'bid.pdf' });
  s.navigation.selectedTab = 'questions';
  s.setConfirmed(true);                       // confirm from the Questions tab
  assert.strictEqual(s.analysis.needsQuestionChoice, false,
    'confirming a set must resolve the upload question-choice');
  assert.strictEqual(s.onboardingHint(), 'goAnalyze');
});

test('on the Analyze tab with a confirmed set the cue becomes startAnalysis', () => {
  const s = fresh();
  s.noteFreshUpload({ name: 'bid.pdf' });
  s.setConfirmed(true);
  s.navigation.selectedTab = 'analyze';
  assert.strictEqual(s.onboardingHint(), 'startAnalysis');
});

test('a NEW upload re-cues Questions even after a set was confirmed', () => {
  const s = fresh();
  s.setConfirmed(true);
  s.noteFreshUpload({ name: 'second.pdf' });
  assert.strictEqual(s.onboardingHint(), 'chooseQuestions');
});

test('beginChoosing un-confirms the set', () => {
  const s = fresh();
  s.setConfirmed(true);
  s.beginChoosing();
  assert.strictEqual(s.questionHub.isConfirmed, false);
});

test('confirmation persists across reloads via localStorage', () => {
  const store = new Map();
  const fakeStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  const first = loadModules(
    ['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js'],
    { localStorage: fakeStorage }
  ).BB.state;
  first.setConfirmed(true);

  const second = loadModules(
    ['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js'],
    { localStorage: fakeStorage }
  ).BB.state;
  assert.strictEqual(second.questionHub.isConfirmed, true);
});

test('currentSetSummary counts only a confirmed set; loadedSetSummary always counts', () => {
  const s = fresh();
  s.questionHub.config = {
    sections: [
      { section_id: 'a', section_name: 'A', questions: [{ id: 'q1' }, { id: 'q2' }] },
      { section_id: 'b', section_name: 'B', questions: [{ id: 'q3' }] },
    ],
  };
  assert.strictEqual(s.questionHub.currentSetSummary(), null);
  assert.deepStrictEqual(plain(s.questionHub.loadedSetSummary()), { sections: 2, questions: 3 });
  s.setConfirmed(true);
  assert.deepStrictEqual(plain(s.questionHub.currentSetSummary()), { sections: 2, questions: 3 });
});

test('subscribers are notified on state changes', () => {
  const s = fresh();
  let calls = 0;
  s.subscribe(() => { calls += 1; });
  s.setConfirmed(true);
  assert.ok(calls > 0, 'setConfirmed must notify subscribers');
});

test('prunedSelection drops section ids that no longer exist', () => {
  const s = fresh();
  assert.deepStrictEqual(s.prunedSelection(['a', 'gone', 'b'], ['a', 'b', 'c']), ['a', 'b']);
  assert.strictEqual(s.prunedSelection(['gone'], ['a']), null,
    'a selection with nothing valid left means "not yet chosen"');
  assert.strictEqual(s.prunedSelection(null, ['a']), null);
});

test('reset clears the analysis back to idle', () => {
  const s = fresh();
  s.noteFreshUpload({ name: 'bid.pdf' });
  s.analysis.sessionId = 'sess-1';
  s.analysis.results = { sections: [] };
  s.reset();
  assert.strictEqual(s.analysis.phase, 'idle');
  assert.strictEqual(s.analysis.hasPendingDocument, false);
  assert.strictEqual(s.analysis.sessionId, null);
  assert.strictEqual(s.analysis.results, null);
  assert.strictEqual(s.onboardingHint(), 'none');
});
