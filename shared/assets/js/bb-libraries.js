/* Named question-set snapshots kept in this browser.
   Ports Sources/Features/QuestionHub/QuestionLibraryStore.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var KEY = 'bb.questionLibraries';
  var SEED_KEY = 'bb.starterSeeded';

  function storage() { try { return window.localStorage; } catch (e) { return null; } }

  function read() {
    var s = storage(); if (!s) return [];
    try { return JSON.parse(s.getItem(KEY) || '[]'); } catch (e) { return []; }
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

  function save(name, config) {
    var c = counts(config);
    var lib = {
      id: 'lib_' + Date.now().toString(36) + '_' + Math.floor(Math.random() * 1e6).toString(36),
      name: String(name || '').trim() || 'Untitled set',
      savedAt: new Date().toISOString(),
      sectionCount: c.sectionCount,
      questionCount: c.questionCount,
      /* Deep copy - later edits to the live config must not leak in. */
      config: JSON.parse(JSON.stringify(config || { sections: [] }))
    };
    var list = read();
    list.unshift(lib);
    write(list);
    return lib;
  }

  function list() { return read(); }

  function get(id) {
    return read().filter(function (l) { return l.id === id; })[0] || null;
  }

  function remove(id) {
    write(read().filter(function (l) { return l.id !== id; }));
  }

  /** Seed the BidBrief Starter Set ONCE. It is a Library, never auto-applied. */
  function seedStarterOnce(config) {
    var s = storage();
    if (s && s.getItem(SEED_KEY) === 'true') return null;
    if (s) s.setItem(SEED_KEY, 'true');
    if (!config) return null;
    return save(config.config_name || 'BidBrief Starter Set', config);
  }

  BB.libraries = {
    list: list, get: get, save: save, remove: remove, seedStarterOnce: seedStarterOnce
  };
})(typeof window !== 'undefined' ? window : this);
