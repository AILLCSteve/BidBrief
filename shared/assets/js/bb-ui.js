/* BidBrief UI primitives - shared DOM + formatting helpers.
   Classic script: attaches to window.BB.ui, no module system. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var RAW = '__bb_raw__';

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /** Mark a string as already-safe markup for the html`` template. */
  function raw(markup) {
    return { type: RAW, value: String(markup == null ? '' : markup) };
  }

  function renderValue(v) {
    if (v && v.type === RAW) return v.value;
    if (Array.isArray(v)) return v.map(renderValue).join('');
    return escapeHtml(v);
  }

  /** Tagged template that escapes every interpolation except raw() values. */
  function html(strings) {
    var out = strings[0];
    for (var i = 1; i < arguments.length; i++) {
      out += renderValue(arguments[i]);
      out += strings[i];
    }
    return out;
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  }

  function qs(sel, root) { return (root || window.document).querySelector(sel); }

  function qsa(sel, root) {
    return Array.prototype.slice.call((root || window.document).querySelectorAll(sel));
  }

  function el(tag, attrs, children) {
    var node = window.document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] == null) return;
      if (k === 'class') node.className = attrs[k];
      else if (k === 'html') node.innerHTML = attrs[k];
      else if (k.slice(0, 2) === 'on') node.addEventListener(k.slice(2), attrs[k]);
      else node.setAttribute(k, attrs[k]);
    });
    [].concat(children || []).forEach(function (child) {
      if (child == null) return;
      node.appendChild(typeof child === 'string'
        ? window.document.createTextNode(child) : child);
    });
    return node;
  }

  /** Replace an element's children with freshly built nodes. */
  function fill(host, children) {
    if (!host) return host;
    host.innerHTML = '';
    [].concat(children || []).forEach(function (child) {
      if (child == null) return;
      host.appendChild(typeof child === 'string'
        ? window.document.createTextNode(child) : child);
    });
    return host;
  }

  /** Bottom toast. kind: 'info' (green) | 'error' (red). Auto-dismisses. */
  function banner(kind, text) {
    var host = qs('#bb-banner-host');
    if (!host) return;
    var node = el('div', { class: 'bb-banner bb-banner-' + kind }, String(text));
    host.appendChild(node);
    window.setTimeout(function () {
      node.classList.add('bb-banner-out');
      window.setTimeout(function () { node.remove(); }, 300);
    }, kind === 'info' ? 2500 : 4000);
  }

  /** The onboarding cue: grow/throb + flashing glow (iOS throbbingCue). */
  function setThrob(node, active) {
    if (!node) return;
    node.classList.toggle('bb-throb', !!active);
  }

  /** A labelled glass card: <section class="bb-glass-card"><span class="bb-eyebrow">..</span>..</section> */
  function card(eyebrow, children, extraClass) {
    return el('section', { class: 'bb-glass-card ' + (extraClass || '') },
      [eyebrow ? el('span', { class: 'bb-eyebrow' }, eyebrow) : null].concat(children || []));
  }

  /** Large screen title that fades into place. */
  function stageHeader(title, subtitle) {
    return el('header', { class: 'bb-stage-header' }, [
      el('h1', {}, title),
      subtitle ? el('p', {}, subtitle) : null
    ]);
  }

  function backChip(label, onClick) {
    return el('div', { class: 'bb-row' }, [
      el('button', { class: 'bb-back-chip', type: 'button', onclick: onClick },
        '‹  ' + (label || 'Back'))
    ]);
  }

  /** Big hub-menu button: the glowing entry point of a stage. */
  function hubButton(opts) {
    return el('button', {
      class: 'bb-hub-btn' + (opts.primary ? ' bb-primary' : ''),
      type: 'button',
      onclick: opts.onClick
    }, [
      el('span', { class: 'bb-hub-icon' }, opts.icon || ''),
      el('span', { class: 'bb-hub-text' }, [
        el('span', { class: 'bb-hub-title' }, opts.title),
        opts.subtitle ? el('span', { class: 'bb-hub-sub' }, opts.subtitle) : null
      ]),
      el('span', { class: 'bb-hub-chevron' }, '›')
    ]);
  }

  /** iOS-style switch row. */
  function toggleRow(opts) {
    var input = el('input', { type: 'checkbox' });
    input.checked = !!opts.checked;
    input.addEventListener('change', function () { opts.onChange(input.checked); });
    return el('label', { class: 'bb-toggle' }, [
      input,
      el('span', { class: 'bb-toggle-text' }, [
        el('span', { class: 'bb-toggle-title' }, opts.title),
        opts.subtitle ? el('span', { class: 'bb-toggle-sub' }, opts.subtitle) : null
      ])
    ]);
  }

  BB.ui = {
    escapeHtml: escapeHtml, raw: raw, html: html,
    formatFileSize: formatFileSize,
    qs: qs, qsa: qsa, el: el, fill: fill,
    banner: banner, setThrob: setThrob,
    card: card, stageHeader: stageHeader, backChip: backChip,
    hubButton: hubButton, toggleRow: toggleRow
  };
})(typeof window !== 'undefined' ? window : this);
