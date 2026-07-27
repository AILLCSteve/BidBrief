'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules, plain } = require('./_harness');

const MODULES = ['shared/assets/js/bb-ui.js', 'shared/assets/js/bb-state.js',
                 'shared/assets/js/bb-libraries.js'];

const CONFIG = {
  sections: [
    { section_id: 'a', section_name: 'A', questions: [{ id: 'q1' }, { id: 'q2' }] },
    { section_id: 'b', section_name: 'B', questions: [{ id: 'q3' }] },
  ],
};

function fakeStorage() {
  const store = new Map();
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
}

test('save stores a named snapshot with counts and a timestamp', () => {
  const { BB } = loadModules(MODULES);
  const lib = BB.libraries.save('CIPP lining bids', CONFIG);
  assert.strictEqual(lib.name, 'CIPP lining bids');
  assert.strictEqual(lib.sectionCount, 2);
  assert.strictEqual(lib.questionCount, 3);
  assert.ok(Date.parse(lib.savedAt), 'savedAt must be an ISO timestamp');
  assert.strictEqual(BB.libraries.list().length, 1);
});

test('the snapshot is a deep copy - later edits do not mutate it', () => {
  const { BB } = loadModules(MODULES);
  const source = JSON.parse(JSON.stringify(CONFIG));
  BB.libraries.save('snap', source);
  source.sections[0].section_name = 'MUTATED';
  assert.strictEqual(BB.libraries.list()[0].config.sections[0].section_name, 'A');
});

test('remove deletes only the named library', () => {
  const { BB } = loadModules(MODULES);
  const one = BB.libraries.save('one', CONFIG);
  BB.libraries.save('two', CONFIG);
  BB.libraries.remove(one.id);
  assert.deepStrictEqual(plain(BB.libraries.list()).map((l) => l.name), ['two']);
});

test('libraries survive a reload', () => {
  const storage = fakeStorage();
  loadModules(MODULES, { localStorage: storage }).BB.libraries.save('kept', CONFIG);
  const reloaded = loadModules(MODULES, { localStorage: storage }).BB;
  assert.deepStrictEqual(plain(reloaded.libraries.list()).map((l) => l.name), ['kept']);
});

test('the Starter Set seeds exactly once and is never auto-applied', () => {
  const storage = fakeStorage();
  const BB = loadModules(MODULES, { localStorage: storage }).BB;
  BB.libraries.seedStarterOnce(CONFIG);
  BB.libraries.seedStarterOnce(CONFIG);
  assert.strictEqual(BB.libraries.list().length, 1, 'seeding twice must not duplicate');
  assert.strictEqual(BB.state.questionHub.isConfirmed, false,
    'the starter set is a Library, never an auto-applied set');

  const reloaded = loadModules(MODULES, { localStorage: storage }).BB;
  reloaded.libraries.seedStarterOnce(CONFIG);
  assert.strictEqual(reloaded.libraries.list().length, 1,
    'the seed flag must survive a reload');
});

test('an unnamed save still gets a usable title', () => {
  const { BB } = loadModules(MODULES);
  assert.strictEqual(BB.libraries.save('   ', CONFIG).name, 'Untitled set');
});
