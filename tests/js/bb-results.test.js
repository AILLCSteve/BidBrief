'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules, plain } = require('./_harness');

function load() {
  return loadModules([
    'shared/assets/js/bb-ui.js',
    'shared/assets/js/bb-state.js',
    'shared/assets/js/bb-status.js',
    'shared/assets/js/bb-results.js',
  ]).BB;
}

const RESULTS = {
  document_name: 'Sewer Lining Spec.pdf',
  total_pages: 120,
  sections: [
    {
      section_id: 's1', section_name: 'Bonds',
      questions: [
        { question_id: 'q1', question: 'Bid bond %?', answer: '10%',
          answer_summary: 'A 10% bid bond is required.', page_citations: [4, 9],
          confidence: 'high' },
        { question_id: 'q2', question: 'Payment bond?', answer: '', page_citations: [] },
      ],
    },
    {
      section_id: 's2', section_name: 'Schedule',
      questions: [
        { question_id: 'q3', question: 'Completion date?', answer: 'June 1',
          page_citations: [22], confidence: 'medium' },
      ],
    },
  ],
};

test('summarize counts answered questions across sections', () => {
  const BB = load();
  const s = BB.results.summarize(RESULTS);
  assert.strictEqual(s.total, 3);
  assert.strictEqual(s.answered, 2);
  assert.strictEqual(s.rate, '67%');
  assert.strictEqual(s.pages, 120);
});

test('summarize lists the unanswered questions for the Improve stage', () => {
  const BB = load();
  const s = BB.results.summarize(RESULTS);
  assert.deepStrictEqual(plain(s.unanswered).map((q) => q.question_id), ['q2']);
});

test('a question with a blank answer is not "answered"', () => {
  const BB = load();
  const s = BB.results.summarize({ sections: [{ questions: [{ answer: '   ' }] }] });
  assert.strictEqual(s.answered, 0);
});

test('answerSummaryOf returns the L6.5 summary, tolerating old cached results', () => {
  const BB = load();
  assert.strictEqual(
    BB.results.answerSummaryOf(RESULTS.sections[0].questions[0]),
    'A 10% bid bond is required.'
  );
  assert.strictEqual(BB.results.answerSummaryOf({ answer: 'x' }), null,
    'results cached before L6.5 have no answer_summary - decode tolerantly');
});

test('zero questions does not divide by zero', () => {
  const BB = load();
  const s = BB.results.summarize({ sections: [] });
  assert.strictEqual(s.total, 0);
  assert.strictEqual(s.rate, '—');
});

test('confidence maps to the badge class, defaulting to low', () => {
  const BB = load();
  assert.strictEqual(BB.results.confidenceOf({ confidence: 'high' }), 'high');
  assert.strictEqual(BB.results.confidenceOf({ confidence: 'MEDIUM' }), 'medium');
  assert.strictEqual(BB.results.confidenceOf({}), 'low');
});

test('flatten yields every question with its section name for the table view', () => {
  const BB = load();
  const rows = plain(BB.results.flatten(RESULTS));
  assert.strictEqual(rows.length, 3);
  assert.strictEqual(rows[0].section_name, 'Bonds');
  assert.strictEqual(rows[2].section_name, 'Schedule');
  assert.strictEqual(rows[2].question_id, 'q3');
});

test('csv rows carry the answer summary between answer and pages', () => {
  const BB = load();
  const csv = BB.results.toCsv(RESULTS);
  const header = csv.split('\n')[0];
  assert.strictEqual(header, 'Section,#,Question,Answer,Answer Summary,PDF Pages');
  assert.match(csv, /A 10% bid bond is required\./);
  assert.match(csv, /"4;9"/);
});
