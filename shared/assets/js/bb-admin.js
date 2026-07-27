/* Admin hub. True admins see everything; Bonus Features users see ONLY the
   premium features - the sessions dashboard (other users' work) and the Bonus
   Features manager never render for them.
   Ports Sources/Features/Home/HomeView.swift AdminHomeView. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var ENTRIES = {
    sessions: {
      id: 'sessions', title: 'Session Dashboard',
      subtitle: 'All analyses in server memory', icon: '🗄'
    },
    bonus: {
      id: 'bonus', title: 'Bonus Features',
      subtitle: 'Grant premium features to users', icon: '👥'
    },
    scraper: {
      id: 'scraper', title: 'CityScraper',
      subtitle: 'Municipal research & comparison', icon: '🏛'
    }
  };

  var path = [];

  function entriesFor(session) {
    var out = [];
    if (session && session.isAdmin) { out.push(ENTRIES.sessions); out.push(ENTRIES.bonus); }
    if (session && (session.isAdmin || session.hasPremium)) out.push(ENTRIES.scraper);
    return out;
  }

  function headingFor(session) {
    return (session && session.isAdmin)
      ? { title: 'Admin', subtitle: 'Server operations' }
      : { title: 'Bonus Features', subtitle: 'Premium features unlocked for you' };
  }

  function render() {
    var host = ui.qs('#bb-page-admin');
    if (!host) return;
    var here = path.length ? path[path.length - 1] : null;
    if (here === 'scraper') return BB.scraper.render(host, back);
    if (here === 'bonus') return renderBonusManager(host);
    return renderHome(host);
  }

  function back() { path.pop(); render(); }

  function renderHome(host) {
    var session = BB.state.session;
    var heading = headingFor(session);
    var entries = entriesFor(session);

    var children = [ui.stageHeader(heading.title, heading.subtitle)];

    if (!entries.length) {
      children.push(ui.card(null, [
        ui.el('p', { class: 'bb-body' },
          'Nothing here for your account yet. Premium features appear once an admin grants them.')
      ]));
    }

    entries.forEach(function (entry) {
      children.push(ui.hubButton({
        title: entry.title, subtitle: entry.subtitle, icon: entry.icon,
        onClick: function () {
          if (entry.id === 'sessions') window.open('/admin/sessions', '_blank');
          else { path.push(entry.id); render(); }
        }
      }));
    });

    ui.fill(host, children);
  }

  // ---- Bonus Features manager (admin only) --------------------------------

  function renderBonusManager(host) {
    if (!BB.state.session.isAdmin) { path = []; return render(); }

    var children = [
      ui.el('div', { class: 'bb-row' }, [
        ui.el('button', { class: 'bb-back-chip', type: 'button', onclick: back }, '‹  Back')
      ]),
      ui.stageHeader('Bonus Features', 'Grant premium features to users'),
      ui.el('div', { id: 'bb-bonus-list', class: 'bb-stack' }, [
        ui.el('div', { class: 'bb-row' }, [
          ui.el('span', { class: 'bb-spinner' }),
          ui.el('span', { class: 'bb-body' }, 'Loading users...')
        ])
      ])
    ];
    ui.fill(host, children);

    window.fetch('/api/admin/bonus-features')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'Could not load');
        paintBonusList(data);
      })
      .catch(function (error) {
        ui.fill(ui.qs('#bb-bonus-list'), [
          ui.el('p', { class: 'bb-body' }, 'Could not load users: ' + error.message)
        ]);
      });
  }

  function paintBonusList(data) {
    var list = ui.qs('#bb-bonus-list');
    if (!list) return;
    var users = data.users || [];
    if (!users.length) {
      return ui.fill(list, [ui.el('p', { class: 'bb-body' }, 'No users to show.')]);
    }
    ui.fill(list, [ui.card('Users', users.map(function (user) {
      var name = user.username || user.email || '';
      return ui.toggleRow({
        title: name,
        subtitle: user.premium || user.has_bonus
          ? 'Premium features granted' : 'Standard account',
        checked: !!(user.premium || user.has_bonus),
        onChange: function (on) { grant(name, on); }
      });
    }))]);
  }

  function grant(username, enabled) {
    window.fetch('/api/admin/bonus-features', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username, enabled: enabled })
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'Update failed');
        ui.banner('info', enabled
          ? ('Premium features granted to ' + username)
          : ('Premium features removed from ' + username));
      })
      .catch(function (error) {
        ui.banner('error', 'Could not update: ' + error.message);
      });
  }

  BB.admin = {
    render: render, entriesFor: entriesFor, headingFor: headingFor,
    renderBonusManager: renderBonusManager
  };
})(typeof window !== 'undefined' ? window : this);
