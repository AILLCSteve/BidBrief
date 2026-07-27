/* Settings: account, sign out, and the About text that used to live in a modal.
   Ports Sources/Features/Settings/SettingsView.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var VERSION = '2.2.0';

  function render() {
    var host = ui.qs('#bb-page-settings');
    if (!host) return;
    var session = BB.state.session;

    ui.fill(host, [
      ui.stageHeader('Settings'),

      ui.card('Account', [
        row('Signed in as', session.username || '—'),
        row('Role', session.isAdmin ? 'Admin' : (session.hasPremium ? 'Premium' : 'User')),
        ui.el('a', {
          class: 'bb-btn-ghost bb-danger', href: '/auth/logout', style: 'margin-top:12px'
        }, 'Sign Out')
      ]),

      ui.card('About', [
        row('Version', VERSION),
        ui.el('p', { class: 'bb-body', style: 'margin-top:10px' },
          'BidBrief is an AI document-analysis system by Additional Intelligence LLC. ' +
          'It reads long bid specifications, contracts, and RFPs, builds a bespoke panel of ' +
          'expert readers for your question set, and returns cited answers you can export.'),
        ui.el('p', { class: 'bb-caption', style: 'margin-top:10px' },
          'Patent Pending — Additional Intelligence, LLC'),
        ui.el('p', { class: 'bb-caption', style: 'margin-top:6px' }, [
          'Powered by ',
          ui.el('a', { href: 'https://additionalintel.com', target: '_blank', rel: 'noopener' },
            'Additional Intelligence LLC')
        ])
      ])
    ]);
  }

  function row(label, value) {
    return ui.el('div', { class: 'bb-row', style: 'justify-content:space-between' }, [
      ui.el('span', { class: 'bb-body' }, label),
      ui.el('span', {}, String(value))
    ]);
  }

  BB.settings = { render: render, VERSION: VERSION };
})(typeof window !== 'undefined' ? window : this);
