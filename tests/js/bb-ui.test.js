'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadModules } = require('./_harness');

const { BB } = loadModules('shared/assets/js/bb-ui.js');

test('escapeHtml neutralises markup', () => {
  assert.strictEqual(
    BB.ui.escapeHtml('<img src=x onerror="alert(1)">&'),
    '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;'
  );
});

test('escapeHtml passes plain text through untouched', () => {
  assert.strictEqual(BB.ui.escapeHtml('Bonds & Insurance'), 'Bonds &amp; Insurance');
});

test('formatFileSize picks the right unit', () => {
  assert.strictEqual(BB.ui.formatFileSize(512), '512 B');
  assert.strictEqual(BB.ui.formatFileSize(2048), '2.00 KB');
  assert.strictEqual(BB.ui.formatFileSize(5 * 1024 * 1024), '5.00 MB');
});

test('html tagged template escapes interpolated values', () => {
  const name = '<script>bad</script>';
  assert.strictEqual(
    BB.ui.html`<p>${name}</p>`,
    '<p>&lt;script&gt;bad&lt;/script&gt;</p>'
  );
});

test('html tagged template leaves BB.ui.raw() values alone', () => {
  const markup = BB.ui.raw('<b>ok</b>');
  assert.strictEqual(BB.ui.html`<p>${markup}</p>`, '<p><b>ok</b></p>');
});

test('html tagged template joins arrays, escaping each entry', () => {
  const rows = ['a & b', BB.ui.raw('<i>c</i>')];
  assert.strictEqual(BB.ui.html`<ul>${rows}</ul>`, '<ul>a &amp; b<i>c</i></ul>');
});
