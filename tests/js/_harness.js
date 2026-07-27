'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..', '..');

/**
 * Evaluate one or more browser scripts against a minimal fake window and
 * return the shared BB namespace they built. `overrides` lets a test supply
 * stubs (localStorage, fetch, document) before the modules run.
 */
function loadModules(relPaths, overrides = {}) {
  const store = new Map();
  const win = {
    BB: {},
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
      clear: () => store.clear(),
    },
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {},
    console,
    setTimeout,
    clearTimeout,
    document: {
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener() {},
      createElement: () => ({
        style: {}, dataset: {}, classList: { add() {}, remove() {}, toggle() {} },
        setAttribute() {}, appendChild() {}, addEventListener() {}, remove() {},
      }),
      createTextNode: (t) => ({ text: t }),
    },
  };
  win.window = win;
  Object.assign(win, overrides);
  const ctx = vm.createContext(win);
  for (const rel of [].concat(relPaths)) {
    const code = fs.readFileSync(path.join(ROOT, rel), 'utf8');
    vm.runInContext(code, ctx, { filename: rel });
  }
  return { BB: ctx.BB || ctx.window.BB, win: ctx };
}

module.exports = { loadModules, ROOT };
