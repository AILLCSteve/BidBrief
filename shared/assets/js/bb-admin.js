/* Admin hub. True admins see everything; Bonus Features users see ONLY the
   premium features - the sessions dashboard (other users' work), the Bonus
   Features manager and the Free Beta manager never render for them.
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
    beta: {
      id: 'beta', title: 'Free Beta Testing',
      subtitle: 'Open access, testers and document limits', icon: '✦'
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
  var storageInfo = null;   /* last /api/admin/storage result */

  function entriesFor(session) {
    var out = [];
    if (session && session.isAdmin) {
      out.push(ENTRIES.sessions); out.push(ENTRIES.beta); out.push(ENTRIES.bonus);
    }
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
    if (here === 'beta') return renderBetaManager(host);
    if (here === 'sessions') return renderSessionsManager(host);
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
        onClick: function () { path.push(entry.id); render(); }
      }));
    });

    ui.fill(host, children);
  }

  /** Admin-only guard for a sub-screen: bounce to the hub rather than render. */
  function guardAdmin() {
    if (BB.state.session.isAdmin) return true;
    path = [];
    render();
    return false;
  }

  function loadingBlock(text) {
    return ui.el('div', { class: 'bb-row' }, [
      ui.el('span', { class: 'bb-spinner' }),
      ui.el('span', { class: 'bb-body' }, text)
    ]);
  }

  function postJson(url, body, method) {
    return window.fetch(url, {
      method: method || 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'Request failed');
        return data;
      });
  }

  // ---- Session Dashboard (admin only, 2.4.0: in-app on the design system) --

  /** Mode-aware Excel export URL for one session row. Pure - unit tested.
      The Excel button lives on every session card; this is the restored
      per-session export the legacy dashboard used to carry. */
  function exportUrlFor(info) {
    return (info && info.mode === 'bestprep')
      ? '/api/export/bestprep-excel/' + info.session_id
      : '/api/export/excel-dashboard/' + info.session_id;
  }

  /** Flatten the /api/admin/sessions buckets into ordered groups. Pure. */
  function sessionGroups(buckets) {
    var b = buckets || {};
    return [
      { key: 'active', title: 'Active', rows: b.active || [] },
      { key: 'completed', title: 'Completed', rows: b.completed || [] },
      { key: 'partial', title: 'Partial / Stopped', rows: b.partial || [] },
      { key: 'legacy', title: 'Legacy', rows: b.legacy || [] }
    ].filter(function (g) { return g.rows.length; });
  }

  /** "3 total · 1 active · 2 completed" from the summary payload. Pure. */
  function sessionsSummaryText(summary) {
    var s = summary || {};
    return [
      (s.total_sessions || 0) + ' total',
      (s.active_count || 0) + ' active',
      (s.completed_count || 0) + ' completed',
      (s.partial_count || 0) + ' partial'
    ].join('  ·  ');
  }

  function renderSessionsManager(host) {
    if (!guardAdmin()) return;

    ui.fill(host, [
      ui.backChip('Back', back),
      ui.stageHeader('Session Dashboard', 'All analyses in server memory'),
      ui.el('div', { id: 'bb-sessions-body', class: 'bb-stack' },
        [loadingBlock('Loading sessions...')])
    ]);
    loadSessions();
  }

  /** One line telling an admin whether history is really being kept.
      "Connected but empty" and "not connected at all" look identical from the
      session list, which is exactly how a silent storage failure hides. */
  function storageStatusText(info) {
    var p = (info && info.persistence) || {};
    var write = (info && info.write_test) || {};
    var ok = !!(p.enabled && p.reachable && write.ok);

    if (!info || !info.database_url_set) {
      return { ok: false, text: 'Durable storage OFF — DATABASE_URL is not set on this ' +
        'server. Sessions live in memory only and are lost on restart.' };
    }
    if (!p.enabled) {
      return { ok: false, text: 'Durable storage FAILED to start — ' +
        (p.error || 'unknown error') + '. Sessions are in memory only.' };
    }
    if (!write.ok) {
      return { ok: false, text: 'Durable storage connected but NOT writable (' +
        (write.reason || 'unknown') + (write.error ? ': ' + write.error : '') +
        '). Nothing is being saved.' };
    }
    return { ok: ok, text: 'Durable storage active · ' + (info.stored_analyses || 0) +
      ' analysis(es) stored · ' + (info.indexed_in_memory || 0) + ' listed here · retention ' +
      (info.retention || 'indefinite') };
  }

  function storageLine(info) {
    if (!info) return null;
    var status = storageStatusText(info);
    return ui.el('p', {
      class: status.ok ? 'bb-caption' : 'bb-beta-quota-full',
      style: 'margin-top:8px'
    }, (status.ok ? '● ' : '▲ ') + status.text);
  }

  /** The storage check is a DIAGNOSTIC and must never gate the data.
      Chaining it in front of the session list meant one slow database call left
      the whole dashboard stuck on "Loading sessions..." forever. It now runs
      alongside, and repaints the status line only if and when it answers. */
  function loadStorageStatus() {
    window.fetch('/api/admin/storage')
      .then(function (r) { return r.json(); })
      .then(function (info) {
        storageInfo = info;
        var host = ui.qs('#bb-storage-line');
        if (host) ui.fill(host, [storageLine(info)]);
      })
      .catch(function () { /* the session list stands on its own */ });
  }

  function loadSessions() {
    loadStorageStatus();
    window.fetch('/api/admin/sessions')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'Could not load');
        paintSessions(data);
      })
      .catch(function (error) {
        var body = ui.qs('#bb-sessions-body');
        if (body) ui.fill(body, [
          ui.el('p', { class: 'bb-body' }, 'Could not load sessions: ' + error.message)
        ]);
      });
  }

  function paintSessions(data) {
    var body = ui.qs('#bb-sessions-body');
    if (!body) return;

    var children = [
      ui.card(null, [
        ui.el('div', { class: 'bb-row' }, [
          ui.el('p', { class: 'bb-body bb-grow' }, sessionsSummaryText(data.summary)),
          ui.el('button', {
            class: 'bb-btn-ghost', type: 'button', onclick: loadSessions
          }, '↻  Refresh')
        ]),
        ui.el('div', { id: 'bb-storage-line' }, [storageLine(storageInfo)])
      ])
    ];

    var groups = sessionGroups(data.sessions);
    if (!groups.length) {
      children.push(ui.card(null, [
        ui.el('p', { class: 'bb-body' },
          'No analyses in server memory. Sessions appear here while they run ' +
          'and after they complete (until a server restart).')
      ]));
    }

    groups.forEach(function (group) {
      children.push(ui.card(group.title + ' (' + group.rows.length + ')',
        group.rows.map(function (info) { return sessionCard(info); })));
    });

    ui.fill(body, children);
  }

  function sessionCard(info) {
    var actions = [
      ui.el('button', {
        class: 'bb-btn-ghost', type: 'button',
        onclick: function () { openSession(info); }
      }, 'View results'),
      ui.el('button', {
        class: 'bb-btn-ghost', type: 'button',
        onclick: function () { window.open(exportUrlFor(info), '_blank'); }
      }, '📊 Excel')
    ];
    if (info.status === 'active') {
      actions.push(ui.el('button', {
        class: 'bb-btn-ghost bb-danger', type: 'button',
        onclick: function () { stopSession(info); }
      }, 'Stop'));
    }
    actions.push(ui.el('button', {
      class: 'bb-btn-ghost bb-danger', type: 'button',
      onclick: function () { confirmDeleteSession(info); }
    }, 'Delete'));

    return ui.el('div', { class: 'bb-beta-session' }, [
      ui.el('div', { class: 'bb-beta-session-main' }, [
        ui.el('span', { class: 'bb-beta-session-file' }, info.pdf_filename || 'Unknown.pdf'),
        ui.el('span', { class: 'bb-chip bb-chip-' + statusKind(info.status) },
          String(info.status || '').replace(/_/g, ' '))
      ]),
      ui.el('div', { class: 'bb-beta-meta' },
        (info.owner ? info.owner + '  ·  ' : '') + sessionMeta(info)),
      ui.el('div', { class: 'bb-beta-session-actions' }, actions)
    ]);
  }

  /** Deleting an analysis is irreversible and wipes it from storage too, so it
      always asks first. Admin-only screen. */
  function confirmDeleteSession(info) {
    BB.modal.open([
      ui.el('div', { class: 'bb-modal-head' }, [ui.el('h2', {}, 'Delete this analysis?')]),
      ui.el('div', { class: 'bb-modal-body' }, [
        ui.el('p', { class: 'bb-body' },
          (info.pdf_filename || 'This analysis') + ' will be removed permanently, ' +
          'including its results, exports and any Smart Analysis. This cannot be undone.'),
        ui.el('div', { class: 'bb-beta-actions' }, [
          ui.el('button', {
            class: 'bb-btn-ghost bb-grow', type: 'button', onclick: BB.modal.close
          }, 'Cancel'),
          ui.el('button', {
            class: 'bb-btn-ghost bb-danger bb-grow', type: 'button',
            onclick: function () { BB.modal.close(); deleteSession(info); }
          }, 'Delete permanently')
        ])
      ])
    ]);
  }

  function deleteSession(info) {
    postJson('/api/admin/analyses/' + window.encodeURIComponent(info.session_id),
             null, 'DELETE')
      .then(function () { ui.banner('info', 'Analysis deleted.'); loadSessions(); })
      .catch(function (error) { ui.banner('error', 'Could not delete: ' + error.message); });
  }

  function stopSession(info) {
    postJson('/api/stop/' + window.encodeURIComponent(info.session_id), null)
      .then(function () { ui.banner('info', 'Stop requested'); loadSessions(); })
      .catch(function (error) { ui.banner('error', 'Could not stop: ' + error.message); });
  }

  // ---- Bonus Features manager (admin only) --------------------------------

  function renderBonusManager(host) {
    if (!guardAdmin()) return;

    ui.fill(host, [
      ui.backChip('Back', back),
      ui.stageHeader('Bonus Features', 'Grant premium features to users'),
      ui.el('div', { id: 'bb-bonus-list', class: 'bb-stack' },
        [loadingBlock('Loading users...')])
    ]);

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
      // The API speaks `email` and `bonus_features` - match it exactly or every
      // row renders off and every grant 400s on an unknown user.
      return ui.toggleRow({
        title: user.name ? (user.name + ' · ' + user.email) : user.email,
        subtitle: user.role === 'admin'
          ? 'Admin - always has premium'
          : (user.bonus_features ? 'Premium features granted' : 'Standard account'),
        checked: !!user.bonus_features || user.role === 'admin',
        onChange: function (on) { grant(user.email, on); }
      });
    }))]);
  }

  function grant(email, enabled) {
    postJson('/api/admin/bonus-features', { email: email, enabled: enabled })
      .then(function () {
        ui.banner('info', enabled
          ? ('Premium features granted to ' + email)
          : ('Premium features removed from ' + email));
      })
      .catch(function (error) { ui.banner('error', 'Could not update: ' + error.message); });
  }

  // ---- Free Beta Testing manager (admin only) -----------------------------

  function renderBetaManager(host) {
    if (!guardAdmin()) return;

    ui.fill(host, [
      ui.backChip('Back', back),
      ui.stageHeader('Free Beta Testing', 'Open access, testers and document limits'),
      ui.el('div', { id: 'bb-beta-body', class: 'bb-stack' },
        [loadingBlock('Loading beta access...')])
    ]);
    loadBeta();
  }

  function loadBeta() {
    window.fetch('/api/admin/beta')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'Could not load');
        paintBeta(data);
      })
      .catch(function (error) {
        var body = ui.qs('#bb-beta-body');
        if (body) ui.fill(body, [
          ui.el('p', { class: 'bb-body' }, 'Could not load beta access: ' + error.message)
        ]);
      });
  }

  /** One-line summary of the beta population. Pure - unit tested. */
  function betaSummaryText(summary, defaultLimit) {
    var s = summary || {};
    var testers = s.tester_count || 0;
    return [
      testers + (testers === 1 ? ' tester' : ' testers'),
      (s.signed_in_count || 0) + ' signed in',
      (s.docs_used || 0) + ' documents processed',
      (s.exhausted_count || 0) + ' at their limit'
    ].join('  ·  ') + '  ·  ' + (defaultLimit || 0) + ' free documents each';
  }

  /** "3 of 5 used · 2 left", or the exhausted wording. Pure - unit tested. */
  function quotaText(tester) {
    var used = tester.docs_used || 0;
    var limit = tester.doc_limit || 0;
    var left = tester.docs_remaining || 0;
    if (used >= limit) return used + ' of ' + limit + ' documents used  ·  limit reached';
    return used + ' of ' + limit + ' documents used  ·  ' + left + ' left';
  }

  function paintBeta(data) {
    var body = ui.qs('#bb-beta-body');
    if (!body) return;

    var children = [
      ui.card('Access', [
        ui.toggleRow({
          title: 'Free Beta Testing',
          subtitle: data.enabled
            ? 'The Free Beta Testing button is live on the sign-in page'
            : 'Hidden from the sign-in page - nobody can start a free session',
          checked: !!data.enabled,
          onChange: setBetaEnabled
        }),
        ui.el('p', { class: 'bb-beta-hint' },
          'Testers get ' + data.default_doc_limit + ' documents and no premium features. ' +
          'A server restart returns this switch to its BETA_LOGIN_ENABLED default.')
      ]),
      ui.card('Testers', [
        ui.el('p', { class: 'bb-body' }, betaSummaryText(data.summary, data.default_doc_limit))
      ])
    ];

    var testers = data.testers || [];
    if (!testers.length) {
      children.push(ui.card(null, [
        ui.el('p', { class: 'bb-body' },
          'No beta testers yet. Each visitor who takes the free beta appears here with their own identity.')
      ]));
    }
    testers.forEach(function (tester) { children.push(testerCard(tester)); });

    ui.fill(body, children);
  }

  function setBetaEnabled(enabled) {
    postJson('/api/admin/beta', { enabled: enabled })
      .then(function () {
        ui.banner('info', enabled
          ? 'Free Beta Testing is now open'
          : 'Free Beta Testing is now closed');
        loadBeta();
      })
      .catch(function (error) {
        ui.banner('error', 'Could not update: ' + error.message);
        loadBeta();
      });
  }

  function testerCard(tester) {
    var used = tester.docs_used || 0;
    var limit = tester.doc_limit || 0;
    var pct = limit > 0 ? Math.min(100, Math.round(used / limit * 100)) : 100;

    var meter = ui.el('div', { class: 'bb-meter' + (tester.exhausted ? ' bb-meter-full' : '') }, [
      ui.el('span', { class: 'bb-meter-fill', style: 'width:' + pct + '%' })
    ]);

    var head = ui.el('div', { class: 'bb-beta-head' }, [
      ui.el('div', {}, [
        ui.el('div', { class: 'bb-beta-name' }, tester.name || tester.username),
        ui.el('div', { class: 'bb-beta-meta' }, tester.username)
      ]),
      ui.el('span', {
        class: 'bb-chip ' + (tester.signed_in ? 'bb-chip-live' : 'bb-chip-idle')
      }, tester.signed_in ? 'Signed in' : 'Signed out')
    ]);

    var children = [
      head,
      ui.el('p', { class: 'bb-beta-meta' },
        'Started ' + formatStamp(tester.created_at) + '  ·  last seen ' + formatStamp(tester.last_seen)),
      ui.el('p', { class: 'bb-beta-quota' + (tester.exhausted ? ' bb-beta-quota-full' : '') },
        quotaText(tester)),
      meter,
      sessionsBlock(tester),
      ui.el('div', { class: 'bb-beta-actions' }, [
        ui.el('button', {
          class: 'bb-btn-ghost bb-grow', type: 'button',
          onclick: function () { updateTester(tester.username, { grant: 5 }, '+5 documents granted'); }
        }, '+5 documents'),
        ui.el('button', {
          class: 'bb-btn-ghost bb-grow', type: 'button',
          onclick: function () { updateTester(tester.username, { reset: true }, 'Document usage reset'); }
        }, 'Reset usage'),
        ui.el('button', {
          class: 'bb-btn-ghost bb-danger', type: 'button',
          onclick: function () { confirmDelete(tester); }
        }, 'Delete')
      ])
    ];

    return ui.card(null, children, 'bb-beta-card');
  }

  function sessionsBlock(tester) {
    var sessions = tester.sessions || [];
    if (!sessions.length) {
      return ui.el('p', { class: 'bb-beta-meta' }, 'No documents analyzed yet.');
    }
    return ui.el('div', { class: 'bb-beta-sessions' }, sessions.map(function (info) {
      return ui.el('div', { class: 'bb-beta-session' }, [
        ui.el('div', { class: 'bb-beta-session-main' }, [
          ui.el('span', { class: 'bb-beta-session-file' }, info.pdf_filename || 'Unknown.pdf'),
          ui.el('span', { class: 'bb-chip bb-chip-' + statusKind(info.status) },
            String(info.status || '').replace(/_/g, ' '))
        ]),
        ui.el('div', { class: 'bb-beta-meta' }, sessionMeta(info)),
        ui.el('div', { class: 'bb-beta-session-actions' }, [
          ui.el('button', {
            class: 'bb-btn-ghost', type: 'button',
            onclick: function () { openSession(info); }
          }, 'View results'),
          ui.el('button', {
            class: 'bb-btn-ghost', type: 'button',
            onclick: function () {
              window.open('/api/export/excel-dashboard/' + info.session_id, '_blank');
            }
          }, 'Excel')
        ])
      ]);
    }));
  }

  /** Stats line for one session. Pure - unit tested. */
  function sessionMeta(info) {
    var bits = [];
    if (info.mode) bits.push(info.mode === 'bestprep' ? 'BestPrep' : 'Bid Spec');
    if (typeof info.questions_answered === 'number') {
      bits.push(info.questions_answered + ' answered');
    }
    if (typeof info.total_pages === 'number') bits.push(info.total_pages + ' pages');
    var stamp = info.completed_at || info.stopped_at || info.started_at;
    if (stamp) bits.push(formatStamp(stamp));
    bits.push(String(info.session_id || '').slice(0, 14));
    return bits.join('  ·  ');
  }

  function statusKind(status) {
    if (status === 'active') return 'live';
    if (status === 'completed' || status === 'legacy_completed') return 'ok';
    if (status === 'partial') return 'warn';
    return 'idle';
  }

  function formatStamp(iso) {
    if (!iso) return 'unknown';
    var d = new window.Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    return d.toLocaleString();
  }

  /** Read-only inspection of any tester's analysis, without touching the
      Analyze tab's live state - an admin looking at someone else's run must
      never clobber their own in-flight analysis. */
  function openSession(info) {
    var host = BB.modal.open([
      ui.el('div', { class: 'bb-modal-head' }, [
        ui.el('h2', {}, info.pdf_filename || 'Session'),
        ui.el('button', {
          class: 'bb-modal-close', type: 'button', onclick: BB.modal.close
        }, '✕')
      ]),
      ui.el('div', { class: 'bb-modal-body', id: 'bb-beta-session-body' },
        [loadingBlock('Loading results...')])
    ]);
    if (!host) return;

    window.fetch('/api/results/' + info.session_id)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'Results not available');
        paintSessionResults(data.result || {}, info);
      })
      .catch(function (error) {
        var body = ui.qs('#bb-beta-session-body');
        if (body) ui.fill(body, [
          ui.el('p', { class: 'bb-body' }, 'Could not load results: ' + error.message)
        ]);
      });
  }

  /** Render a session exactly as its owner sees it: the full workbook, every
      sheet — Executive Summary, Detailed Results, By Section, Document
      Intelligence, Visual Intelligence, Footnotes. This used to be a flat list
      of answers, which quietly hid the dynamic Document Intelligence tables an
      admin most wants when reviewing a run. */
  function paintSessionResults(payload, info) {
    var body = ui.qs('#bb-beta-session-body');
    if (!body) return;
    var stats = BB.results.summarize(payload);

    var children = [
      ui.el('div', { class: 'bb-stats', style: 'margin-bottom:14px' }, [
        ui.el('div', { class: 'bb-stat' }, [
          ui.el('div', { class: 'bb-stat-value' }, stats.answered + '/' + stats.total),
          ui.el('div', { class: 'bb-stat-label' }, 'Answered')
        ]),
        ui.el('div', { class: 'bb-stat-sep' }),
        ui.el('div', { class: 'bb-stat' }, [
          ui.el('div', { class: 'bb-stat-value' }, String(stats.pages)),
          ui.el('div', { class: 'bb-stat-label' }, 'Pages')
        ]),
        ui.el('div', { class: 'bb-stat-sep' }),
        ui.el('div', { class: 'bb-stat' }, [
          ui.el('div', { class: 'bb-stat-value' }, stats.rate),
          ui.el('div', { class: 'bb-stat-label' }, 'Rate')
        ])
      ]),
      BB.results.buildWorkbook(payload)
    ];

    if (info && info.session_id) {
      children.push(ui.el('div', { class: 'bb-row', style: 'margin-top:14px' }, [
        ui.el('button', {
          class: 'bb-btn-ghost', type: 'button',
          onclick: function () { window.open(exportUrlFor(info), '_blank'); }
        }, '📊  Excel Report Package')
      ]));
    }

    ui.fill(body, children);
  }

  function updateTester(username, body, successText) {
    postJson('/api/admin/beta/testers/' + window.encodeURIComponent(username), body)
      .then(function () { ui.banner('info', successText); loadBeta(); })
      .catch(function (error) { ui.banner('error', 'Could not update: ' + error.message); });
  }

  function confirmDelete(tester) {
    BB.modal.open([
      ui.el('div', { class: 'bb-modal-head' }, [ui.el('h2', {}, 'Delete beta tester?')]),
      ui.el('div', { class: 'bb-modal-body' }, [
        ui.el('p', { class: 'bb-body' },
          (tester.name || tester.username) + ' will be signed out immediately and will not be ' +
          'able to return with this identity. Their analyses stay in the session dashboard.'),
        ui.el('div', { class: 'bb-beta-actions' }, [
          ui.el('button', {
            class: 'bb-btn-ghost bb-grow', type: 'button', onclick: BB.modal.close
          }, 'Cancel'),
          ui.el('button', {
            class: 'bb-btn-ghost bb-danger bb-grow', type: 'button',
            onclick: function () { BB.modal.close(); deleteTester(tester.username); }
          }, 'Delete')
        ])
      ])
    ]);
  }

  function deleteTester(username) {
    postJson('/api/admin/beta/testers/' + window.encodeURIComponent(username), null, 'DELETE')
      .then(function () { ui.banner('info', 'Beta tester deleted'); loadBeta(); })
      .catch(function (error) { ui.banner('error', 'Could not delete: ' + error.message); });
  }

  BB.admin = {
    render: render, entriesFor: entriesFor, headingFor: headingFor,
    renderBonusManager: renderBonusManager, renderBetaManager: renderBetaManager,
    renderSessionsManager: renderSessionsManager,
    betaSummaryText: betaSummaryText, quotaText: quotaText,
    sessionMeta: sessionMeta, statusKind: statusKind,
    exportUrlFor: exportUrlFor, sessionGroups: sessionGroups,
    storageLine: storageLine, storageStatusText: storageStatusText,
    sessionsSummaryText: sessionsSummaryText
  };
})(typeof window !== 'undefined' ? window : this);
