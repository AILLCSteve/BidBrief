/* Login page behaviour: mount the orb, surface the ?error= reason, block an
   empty submit before it round-trips, and — when the server says free beta is
   open — offer the Free Beta Testing path behind its terms modal. */
(function (window) {
  'use strict';
  var document = window.document;

  var MESSAGES = {
    invalid: 'Invalid username or password. Please try again.',
    session: 'Your session has expired. Please log in again.',
    beta_closed: 'Free beta access has closed. Please sign in to continue.',
    beta_ended: 'Your free beta session has ended. Subscribe to keep using BidBrief.'
  };

  /** The beta terms, in the user's words rather than the server's. Pure so the
      copy can be asserted in a test without a DOM. */
  function betaTerms(docLimit) {
    var limit = docLimit > 0 ? docLimit : 5;
    var docs = limit + (limit === 1 ? ' document' : ' documents');
    return {
      title: 'Free Beta Testing',
      lede: 'BidBrief is free to try while the beta is open.',
      points: [
        'Your free pass covers up to ' + docs + ' — full analysis, full results, full exports.',
        'No account, no card, no commitment. Your session lasts 24 hours.',
        'Free beta is available for a limited time only.'
      ],
      fine: 'When the beta closes, or once you have used your ' + docs +
            ', a paid subscription is required to continue using BidBrief and ' +
            'to access full functionality.',
      confirm: 'Start Free Beta',
      cancel: 'Not now'
    };
  }

  function showError(text) {
    var box = document.getElementById('errorMessage');
    if (!box) return;
    box.textContent = text;
    box.classList.add('show');
  }

  function openBetaModal(docLimit) {
    var ui = window.BB.ui;
    var copy = betaTerms(docLimit);

    var confirmBtn = ui.el('button',
      { class: 'bb-btn-glow', type: 'button' }, copy.confirm);
    var cancelBtn = ui.el('button',
      { class: 'bb-btn-ghost', type: 'button', onclick: function () { window.BB.modal.close(); } },
      copy.cancel);

    confirmBtn.addEventListener('click', function () {
      confirmBtn.disabled = true;
      cancelBtn.disabled = true;
      confirmBtn.textContent = 'Starting...';
      startBetaSession(function (message) {
        window.BB.modal.close();
        showError(message);
      });
    });

    var card = window.BB.modal.open([
      ui.el('div', { class: 'bb-modal-head' }, [ui.el('h2', {}, copy.title)]),
      ui.el('div', { class: 'bb-modal-body' }, [
        ui.el('p', { class: 'bb-beta-lede' }, copy.lede),
        ui.el('ul', { class: 'bb-beta-terms' }, copy.points.map(function (point) {
          return ui.el('li', {}, [
            ui.el('span', { class: 'bb-beta-bullet' }, '✦'),
            ui.el('span', {}, point)
          ]);
        })),
        ui.el('p', { class: 'bb-beta-fine' }, copy.fine),
        ui.el('div', { class: 'bb-beta-actions' }, [cancelBtn, confirmBtn])
      ])
    ]);
    if (card) card.classList.add('bb-beta-modal');
  }

  function startBetaSession(onError) {
    window.fetch('/auth/beta-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        if (!res.ok || !res.data.success) {
          throw new Error(res.data.error || 'Could not start a free beta session.');
        }
        window.location.href = res.data.redirect || '/';
      })
      .catch(function (error) { onError(error.message); });
  }

  function mountBetaButton() {
    var host = document.getElementById('betaAccess');
    var button = document.getElementById('betaButton');
    if (!host || !button) return;

    // The button stays hidden unless the server says beta access is open, so a
    // disabled beta leaves no trace of itself on the login page.
    window.fetch('/api/beta/status')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.enabled) return;
        host.hidden = false;
        button.addEventListener('click', function () { openBetaModal(data.doc_limit); });
      })
      .catch(function () { /* beta stays hidden — never block normal sign-in */ });
  }

  document.addEventListener('DOMContentLoaded', function () {
    window.BB.orb.mount(document.getElementById('bb-orb'));

    var error = new window.URLSearchParams(window.location.search).get('error');
    if (error) showError(MESSAGES[error] || 'An error occurred. Please try again.');

    document.getElementById('loginForm').addEventListener('submit', function (e) {
      var user = document.getElementById('username').value.trim();
      var pass = document.getElementById('password').value;
      if (user && pass) return;
      e.preventDefault();
      showError('Please enter both username and password.');
    });

    mountBetaButton();
  });

  window.BB = window.BB || {};
  window.BB.login = { betaTerms: betaTerms, MESSAGES: MESSAGES };
})(window);
