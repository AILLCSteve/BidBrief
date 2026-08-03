/* Settings: account, sign out, and the About text that used to live in a modal.
   Ports Sources/Features/Settings/SettingsView.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  /* Read from the server, never hardcoded: a literal here silently drifts from
     the real build (it sat at 2.3.0 through five releases). The fallback is
     only what shows for the instant before /health answers. */
  var VERSION = '—';

  function loadVersion() {
    window.fetch('/health')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.version) {
          VERSION = data.version;
          var host = ui.qs('#bb-version-value');
          if (host) ui.fill(host, [window.document.createTextNode(VERSION)]);
        }
      })
      .catch(function () { /* the rest of Settings does not depend on it */ });
  }

  function render() {
    var host = ui.qs('#bb-page-settings');
    if (!host) return;
    var session = BB.state.session;

    ui.fill(host, [
      ui.stageHeader('Settings'),

      ui.card('Account', [
        row('Signed in as', session.username || '—'),
        row('Role', accountKind(session)),
        ui.el('a', {
          class: 'bb-btn-ghost bb-danger', href: '/auth/logout', style: 'margin-top:12px'
        }, 'Sign Out')
      ]),

      session.isBeta ? ui.card('Free Beta', [
        row('Documents left', betaRemainingText(session.beta)),
        ui.el('p', { class: 'bb-body', style: 'margin-top:10px' }, betaNotice(session.beta))
      ]) : null,

      ui.card('About', [
        ui.el('div', { class: 'bb-row', style: 'justify-content:space-between' }, [
          ui.el('span', { class: 'bb-body' }, 'Version'),
          ui.el('span', { id: 'bb-version-value' }, VERSION)
        ]),
        ui.el('p', { class: 'bb-body', style: 'margin-top:10px' },
          'BidBrief is an AI document-analysis system by Additional Intelligence LLC. ' +
          'It reads long bid specifications, contracts, and RFPs, builds a bespoke panel of ' +
          'expert readers for your question set, and returns cited answers you can export.'),
        ui.el('p', { class: 'bb-caption', style: 'margin-top:10px' },
          'Patent Pending — Stephen Bartlett'),
        ui.el('p', { class: 'bb-caption', style: 'margin-top:6px' }, [
          'Powered by ',
          ui.el('a', { href: 'https://additionalintel.com', target: '_blank', rel: 'noopener' },
            'Additional Intelligence LLC')
        ])
      ])
    ]);

    loadVersion();
  }

  function row(label, value) {
    return ui.el('div', { class: 'bb-row', style: 'justify-content:space-between' }, [
      ui.el('span', { class: 'bb-body' }, label),
      ui.el('span', {}, String(value))
    ]);
  }

  function accountKind(session) {
    if (session.isAdmin) return 'Admin';
    if (session.isBeta) return 'Free Beta';
    return session.hasPremium ? 'Premium' : 'User';
  }

  /** "2 of 5" - pure, unit tested. */
  function betaRemainingText(beta) {
    if (!beta) return '—';
    return (beta.docs_remaining || 0) + ' of ' + (beta.doc_limit || 0);
  }

  function betaNotice(beta) {
    var left = beta ? (beta.docs_remaining || 0) : 0;
    if (left > 0) {
      return 'Free beta access is available for a limited time. When the beta ends, or once ' +
             'your free documents are used, a subscription is required to continue using ' +
             'BidBrief and access full functionality.';
    }
    return 'You have used every document in your free beta. Subscribe to keep analyzing ' +
           'documents and unlock full functionality.';
  }

  BB.settings = {
    render: render, loadVersion: loadVersion,
    version: function () { return VERSION; },
    accountKind: accountKind, betaRemainingText: betaRemainingText, betaNotice: betaNotice
  };
})(typeof window !== 'undefined' ? window : this);
