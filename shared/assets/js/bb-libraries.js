/* Named question-set snapshots kept in this browser.
   Ports Sources/Features/QuestionHub/QuestionLibraryStore.swift.

   Two kinds of entry live here:
   - USER libraries: explicitly saved and named by the user. Never touched.
   - AUTO backups: taken automatically before a Replace-mode generation so an
     overwrite is always undoable.

   Auto backups used to pile up: every generation saved another copy, and before
   a set is confirmed the "current" config is the backend default — so iterating
   on generation produced four or five identical copies of the same stock set,
   each named with a raw timestamp. They are now deduplicated by content, capped,
   and named after what they contain. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var KEY = 'bb.questionLibraries';
  var SEED_KEY = 'bb.starterSeeded';
  var TIDY_KEY = 'bb.librariesTidied';

  /* How many automatic pre-generation backups to keep. Undo needs a couple of
     steps, not an archive. User-saved libraries are never capped. */
  var MAX_AUTO_BACKUPS = 3;

  function storage() { try { return window.localStorage; } catch (e) { return null; } }

  function read() {
    var s = storage(); if (!s) return [];
    try {
      var parsed = JSON.parse(s.getItem(KEY) || '[]');
      return (Object.prototype.toString.call(parsed) === '[object Array]') ? parsed : [];
    } catch (e) { return []; }
  }

  function write(list) {
    var s = storage(); if (s) s.setItem(KEY, JSON.stringify(list));
  }

  function counts(config) {
    var sections = (config && config.sections) || [];
    return {
      sectionCount: sections.length,
      questionCount: sections.reduce(function (n, sec) {
        return n + ((sec.questions && sec.questions.length) || 0);
      }, 0)
    };
  }

  /** Content identity for a question set: same sections and same question text
      means the same set, whatever it happens to be called. Pure - unit tested. */
  function fingerprint(config) {
    var sections = (config && config.sections) || [];
    return sections.map(function (sec) {
      var questions = (sec.questions || []).map(function (q) {
        return String(q.text || q.question || '').trim().toLowerCase();
      });
      return String(sec.section_name || sec.section_id || '').trim().toLowerCase()
        + '::' + questions.join('|');
    }).join('~~');
  }

  /** "10 sections · 100 questions" — what a set actually is, for a label. */
  function describe(config) {
    var c = counts(config);
    return c.sectionCount + (c.sectionCount === 1 ? ' section' : ' sections')
      + ' · ' + c.questionCount + (c.questionCount === 1 ? ' question' : ' questions');
  }

  function shortStamp(date) {
    var d = date || new Date();
    try {
      return d.toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
      });
    } catch (e) {
      return d.toISOString().slice(0, 16).replace('T', ' ');
    }
  }

  function makeEntry(name, config, auto) {
    var c = counts(config);
    return {
      id: 'lib_' + Date.now().toString(36) + '_' + Math.floor(Math.random() * 1e6).toString(36),
      name: String(name || '').trim() || 'Untitled set',
      savedAt: new Date().toISOString(),
      sectionCount: c.sectionCount,
      questionCount: c.questionCount,
      auto: !!auto,
      fingerprint: fingerprint(config),
      /* Deep copy - later edits to the live config must not leak in. */
      config: JSON.parse(JSON.stringify(config || { sections: [] }))
    };
  }

  /** Explicit, user-named save. Always kept, never deduplicated - if someone
      saves the same set under two names, they meant to. */
  function save(name, config) {
    var entry = makeEntry(name, config, false);
    var list = read();
    list.unshift(entry);
    write(list);
    return entry;
  }

  /**
   * Automatic pre-generation backup.
   *
   * Skipped entirely when a library already holds this exact set — that is what
   * produced the stack of identical stock sets. Otherwise saved with a name that
   * says what it is, and the oldest auto backups beyond MAX_AUTO_BACKUPS are
   * dropped. Returns the entry, or null when nothing needed saving.
   */
  function autoBackup(config, label) {
    if (!config || !((config.sections || []).length)) return null;

    var print = fingerprint(config);
    var list = read();

    var duplicate = list.some(function (lib) {
      return (lib.fingerprint || fingerprint(lib.config)) === print;
    });
    if (duplicate) return null;

    var entry = makeEntry(
      (label || 'Backup') + ' · ' + describe(config) + ' · ' + shortStamp(),
      config, true);
    list.unshift(entry);

    var autoSeen = 0;
    list = list.filter(function (lib) {
      if (!lib.auto) return true;
      autoSeen += 1;
      return autoSeen <= MAX_AUTO_BACKUPS;
    });

    write(list);
    return entry;
  }

  function list() { return read(); }

  function get(id) {
    return read().filter(function (l) { return l.id === id; })[0] || null;
  }

  function remove(id) {
    write(read().filter(function (l) { return l.id !== id; }));
  }

  /**
   * One-time cleanup of libraries saved before this fix.
   *
   * Collapses entries that hold identical sets (keeping the oldest, which is the
   * one the user is most likely to have named themselves), renames the legacy
   * "Before AI generation - <timestamp>" entries, and caps what is left. Runs
   * once per browser. Returns how many entries were removed.
   */
  function tidyOnce() {
    var s = storage();
    if (s && s.getItem(TIDY_KEY) === 'true') return 0;
    if (s) s.setItem(TIDY_KEY, 'true');

    var list = read();
    if (!list.length) return 0;

    var before = list.length;
    var seen = {};
    var kept = [];

    /* Oldest first so the earliest copy of a set survives the collapse. */
    list.slice().reverse().forEach(function (lib) {
      var print = lib.fingerprint || fingerprint(lib.config);
      if (seen[print]) return;
      seen[print] = true;

      var isLegacyAuto = /^Before AI generation/i.test(lib.name || '');
      kept.push({
        id: lib.id,
        name: isLegacyAuto
          ? ('Backup · ' + describe(lib.config) + ' · ' + shortStamp(new Date(lib.savedAt)))
          : (lib.name || 'Untitled set'),
        savedAt: lib.savedAt,
        sectionCount: lib.sectionCount,
        questionCount: lib.questionCount,
        auto: isLegacyAuto || !!lib.auto,
        fingerprint: print,
        config: lib.config
      });
    });

    kept.reverse();  /* back to newest first */
    write(kept);
    return before - kept.length;
  }

  /** Seed the bundled Sample Set ONCE. It is a Library, never auto-applied. */
  function seedStarterOnce(config) {
    var s = storage();
    if (s && s.getItem(SEED_KEY) === 'true') return null;
    if (s) s.setItem(SEED_KEY, 'true');
    if (!config) return null;

    /* If an identical set is already saved (e.g. it was captured by an old
       auto-backup before this fix), don't add a second copy of it. */
    var print = fingerprint(config);
    var existing = read().some(function (lib) {
      return (lib.fingerprint || fingerprint(lib.config)) === print;
    });
    if (existing) return null;

    return save(config.config_name || 'BidBrief Sample Set', config);
  }

  BB.libraries = {
    list: list, get: get, save: save, remove: remove,
    autoBackup: autoBackup, seedStarterOnce: seedStarterOnce, tidyOnce: tidyOnce,
    fingerprint: fingerprint, describe: describe,
    MAX_AUTO_BACKUPS: MAX_AUTO_BACKUPS
  };
})(typeof window !== 'undefined' ? window : this);
