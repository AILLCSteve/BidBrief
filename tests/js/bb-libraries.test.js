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

// ---- auto backups no longer stack up (2.5.0) --------------------------------

const SET_A = {
  sections: [{ section_id: 'a', section_name: 'A',
               questions: [{ text: 'What size pipe?' }, { text: 'What material?' }] }],
};
const SET_A_RENAMED = {  // same content, different section id/casing
  sections: [{ section_id: 'zzz', section_name: 'a',
               questions: [{ text: '  what size pipe? ' }, { text: 'WHAT MATERIAL?' }] }],
};
const SET_B = {
  sections: [{ section_id: 'b', section_name: 'B', questions: [{ text: 'Bond amount?' }] }],
};

test('fingerprint identifies a set by content, not by its name or ids', () => {
  const { BB } = loadModules(MODULES);
  assert.strictEqual(BB.libraries.fingerprint(SET_A), BB.libraries.fingerprint(SET_A_RENAMED));
  assert.notStrictEqual(BB.libraries.fingerprint(SET_A), BB.libraries.fingerprint(SET_B));
});

test('repeated generations never stack duplicate copies of the same set', () => {
  const { BB } = loadModules(MODULES, { localStorage: fakeStorage() });
  // Five iterations against an unchanged set - the exact bug reported.
  for (let i = 0; i < 5; i += 1) BB.libraries.autoBackup(SET_A, 'Backup before generating');
  assert.strictEqual(BB.libraries.list().length, 1,
    'an unchanged set must be backed up once, not once per generation');
});

test('a genuinely different set still gets its own backup', () => {
  const { BB } = loadModules(MODULES, { localStorage: fakeStorage() });
  BB.libraries.autoBackup(SET_A, 'Backup before generating');
  BB.libraries.autoBackup(SET_B, 'Backup before generating');
  assert.strictEqual(BB.libraries.list().length, 2);
});

test('auto backups are capped; user-saved libraries are never dropped', () => {
  const { BB } = loadModules(MODULES, { localStorage: fakeStorage() });
  BB.libraries.save('My named set', SET_A);
  for (let i = 0; i < 6; i += 1) {
    BB.libraries.autoBackup(
      { sections: [{ section_id: 's' + i, section_name: 'S' + i,
                     questions: [{ text: 'q' + i }] }] }, 'Backup before generating');
  }
  const libs = plain(BB.libraries.list());
  const autos = libs.filter((l) => l.auto);
  const users = libs.filter((l) => !l.auto);
  assert.strictEqual(autos.length, BB.libraries.MAX_AUTO_BACKUPS);
  assert.deepStrictEqual(users.map((l) => l.name), ['My named set']);
});

test('backups are named after what they contain, not a raw timestamp', () => {
  const { BB } = loadModules(MODULES, { localStorage: fakeStorage() });
  const entry = BB.libraries.autoBackup(SET_A, 'Backup before generating');
  assert.match(entry.name, /^Backup before generating · 1 section · 2 questions · /);
  assert.ok(!/^Before AI generation/.test(entry.name));
});

test('an empty set is never backed up', () => {
  const { BB } = loadModules(MODULES, { localStorage: fakeStorage() });
  assert.strictEqual(BB.libraries.autoBackup({ sections: [] }, 'x'), null);
  assert.strictEqual(BB.libraries.autoBackup(null, 'x'), null);
  assert.strictEqual(BB.libraries.list().length, 0);
});

test('tidyOnce collapses the duplicates already sitting in a browser', () => {
  const { BB } = loadModules(MODULES, { localStorage: fakeStorage() });
  // Simulate the reported mess: five near-identical legacy auto-snapshots.
  for (let i = 0; i < 5; i += 1) {
    BB.libraries.save('Before AI generation - 8/2/2026, 10:1' + i + ':00 PM', SET_A);
  }
  BB.libraries.save('My real library', SET_B);
  assert.strictEqual(BB.libraries.list().length, 6);

  const removed = BB.libraries.tidyOnce();
  const libs = plain(BB.libraries.list());
  assert.strictEqual(removed, 4);
  assert.strictEqual(libs.length, 2);
  assert.ok(libs.some((l) => l.name === 'My real library'), 'user libraries survive');
  assert.ok(!libs.some((l) => /^Before AI generation/.test(l.name)),
    'legacy timestamp names are rewritten');
});

test('tidyOnce runs only once per browser', () => {
  const { BB } = loadModules(MODULES, { localStorage: fakeStorage() });
  BB.libraries.save('Before AI generation - x', SET_A);
  BB.libraries.save('Before AI generation - y', SET_A);
  assert.strictEqual(BB.libraries.tidyOnce(), 1);
  assert.strictEqual(BB.libraries.tidyOnce(), 0);
});

test('the Sample Set is not seeded when that exact set is already saved', () => {
  const { BB } = loadModules(MODULES, { localStorage: fakeStorage() });
  BB.libraries.save('Backup · whatever', SET_A);
  const seeded = BB.libraries.seedStarterOnce(
    Object.assign({ config_name: 'BidBrief Sample Set' }, SET_A));
  assert.strictEqual(seeded, null, 'seeding must not create a duplicate of a stored set');
  assert.strictEqual(BB.libraries.list().length, 1);
});
