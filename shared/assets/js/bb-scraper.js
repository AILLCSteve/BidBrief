/* CityScraper - municipal research, on glass. Same endpoints and same
   one-shot research flow as before (/api/scraper/research, events polled with
   `since`, results from /api/scraper/research/<sid>); only the presentation
   changed. Never calls /api/admin/sessions. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var session = {
    id: null,
    municipality: '',
    tableMode: 'systems_info',
    running: false,
    eventIndex: 0,
    events: [],
    progress: { phase: 'Initializing...', percent: 0 },
    preflight: null,
    fields: {},
    result: null,
    error: null,
    timer: null
  };

  var host = null;
  var onBack = null;

  function render(pageHost, backFn) {
    host = pageHost;
    onBack = backFn;
    paint();
  }

  function paint() {
    if (!host) return;
    var children = [];

    if (onBack) {
      children.push(ui.el('div', { class: 'bb-row' }, [
        ui.el('button', { class: 'bb-back-chip', type: 'button', onclick: onBack }, '‹  Back')
      ]));
    }
    children.push(ui.stageHeader('CityScraper',
      'AI-powered municipal infrastructure and bid research'));

    /* Input card */
    var input = ui.el('input', { type: 'text', placeholder: 'e.g. Springfield, IL' });
    input.value = session.municipality;
    input.addEventListener('input', function () { session.municipality = input.value; });

    var select = ui.el('select', {});
    [
      ['systems_info', 'Municipal Systems Information'],
      ['public_bids', 'Municipal Public Bids'],
      ['both', 'Both Tables']
    ].forEach(function (opt) {
      var o = ui.el('option', { value: opt[0] }, opt[1]);
      if (session.tableMode === opt[0]) o.selected = true;
      select.appendChild(o);
    });
    select.addEventListener('change', function () { session.tableMode = select.value; });

    var startBtn = ui.el('button', {
      class: 'bb-btn-glow', type: 'button', onclick: start
    }, '🔎  Start Research');
    startBtn.disabled = session.running;

    var stopBtn = ui.el('button', {
      class: 'bb-btn-ghost bb-danger', type: 'button', onclick: stop
    }, '■  Stop');
    stopBtn.disabled = !session.running;

    children.push(ui.card('Municipality', [
      ui.el('div', { class: 'bb-field' }, [input]),
      ui.el('span', { class: 'bb-eyebrow', style: 'margin-top:14px' }, 'Research Mode'),
      ui.el('div', { class: 'bb-field' }, [select]),
      ui.el('div', { class: 'bb-row', style: 'margin-top:14px' }, [startBtn, stopBtn])
    ]));

    if (session.error) {
      children.push(ui.card(null, [ui.el('p', { class: 'bb-body' }, session.error)]));
    }

    if (session.running || session.progress.percent > 0) children.push(progressCard());
    if (session.preflight) children.push(preflightCard());
    if (Object.keys(session.fields).length) children.push(liveFieldsCard());
    if (session.result) resultCards().forEach(function (c) { children.push(c); });

    ui.fill(host, children);
  }

  function progressCard() {
    var bar = ui.el('div', { class: 'bb-progressbar' },
      [ui.el('span', { style: 'width:' + Math.round(session.progress.percent) + '%' })]);
    var feed = session.events.slice(-40).map(function (e) {
      return ui.el('div', { class: 'bb-feed-row' }, [
        ui.el('div', { class: 'bb-feed-icon' }, e.status === 'failed' ? '⚠' : '🤖'),
        ui.el('div', { class: 'bb-feed-text' },
          (e.agent_name || e.agent_id || 'agent') + ' — ' + (e.status_message || e.status || '')),
        ui.el('div', { class: 'bb-feed-time' }, e.timestamp
          ? new Date(e.timestamp).toLocaleTimeString() : '')
      ]);
    });
    return ui.card('Progress', [
      ui.el('div', { class: 'bb-row' }, [
        ui.el('span', { class: 'bb-body bb-grow' }, session.progress.phase),
        ui.el('span', { class: 'bb-body' }, Math.round(session.progress.percent) + '%')
      ]),
      ui.el('div', { style: 'margin:10px 0 16px' }, [bar]),
      ui.el('span', { class: 'bb-eyebrow' }, 'Agent Activity'),
      ui.el('div', { class: 'bb-feed' }, feed.length ? feed
        : [ui.el('p', { class: 'bb-caption' }, 'Waiting for the first agent to report...')])
    ]);
  }

  function preflightCard() {
    var pf = session.preflight || {};
    var rows = [
      ['Municipality', pf.municipality_full_name || pf.municipality || '—'],
      ['County', pf.county || '—'],
      ['Region', pf.region || '—'],
      ['Sanitary Sewer Owner', pf.sanitary_sewer_owner || '—'],
      ['Storm Sewer Owner', pf.storm_sewer_owner || '—'],
      ['Official Website', pf.official_url || '—'],
      ['Sources Found', pf.sources_count == null ? '—' : String(pf.sources_count)],
      ['Readiness', pf.readiness || '—']
    ];
    return ui.card('Pre-Flight Validation', [
      ui.el('div', { class: 'bb-pf-grid' }, rows.map(function (r) {
        return ui.el('div', {}, [
          ui.el('div', { class: 'bb-pf-label' }, r[0]),
          ui.el('div', { class: 'bb-pf-value' }, String(r[1]))
        ]);
      }))
    ]);
  }

  function liveFieldsCard() {
    var ids = Object.keys(session.fields);
    return ui.card('Extracted Data (' + ids.length + ' fields)', [
      ui.el('div', { class: 'bb-table-wrap' }, [
        ui.el('table', { class: 'bb-table' }, [
          ui.el('thead', {}, [ui.el('tr', {},
            ['Field', 'Value', 'Confidence', 'Source'].map(function (h) {
              return ui.el('th', {}, h);
            }))]),
          ui.el('tbody', {}, ids.map(function (id) {
            var f = session.fields[id];
            return ui.el('tr', {}, [
              ui.el('td', { class: 'bb-td-strong' }, id.replace(/_/g, ' ')),
              ui.el('td', {}, String(f.value == null ? '' : f.value)),
              ui.el('td', {}, [
                ui.el('span', { class: 'bb-pill bb-pill-' + pillFor(f.confidence) },
                  String(f.confidence || 'unknown'))
              ]),
              ui.el('td', {}, String(f.source || ''))
            ]);
          }))
        ])
      ])
    ]);
  }

  function pillFor(confidence) {
    var c = String(confidence || '').toLowerCase();
    if (c === 'high') return 'high';
    if (c === 'medium') return 'medium';
    return 'low';
  }

  function resultCards() {
    var result = session.result || {};
    var presentation = result.presentation_result || {};
    var extraction = result.extraction_result || {};
    var municipality = result.municipality || {};
    var stats = result.statistics || {};
    var cards = [];

    cards.push(ui.card(null, [
      ui.el('div', { class: 'bb-stats' }, [
        statCell('Municipality', municipality.full_name || municipality.city || 'Unknown'),
        ui.el('div', { class: 'bb-stat-sep' }),
        statCell('Sources', String(stats.sources_found || 0)),
        ui.el('div', { class: 'bb-stat-sep' }),
        statCell('Data Points', String(stats.fields_extracted || 0))
      ])
    ]));

    var rows = extraction.systems_info_rows || extraction.public_bid_rows || [];
    if (rows.length) {
      var columns = Object.keys(rows[0]);
      cards.push(ui.card('Data Table', [
        ui.el('div', { class: 'bb-table-wrap' }, [
          ui.el('table', { class: 'bb-table' }, [
            ui.el('thead', {}, [ui.el('tr', {}, columns.map(function (c) {
              return ui.el('th', {}, c.replace(/_/g, ' '));
            }))]),
            ui.el('tbody', {}, rows.map(function (row) {
              return ui.el('tr', {}, columns.map(function (c) {
                var v = row[c];
                if (v && typeof v === 'object') v = JSON.stringify(v);
                return ui.el('td', {}, String(v == null ? '' : v));
              }));
            }))
          ])
        ])
      ]));
    }

    if ((presentation.data_gaps || []).length) {
      cards.push(ui.card('Data Gaps', presentation.data_gaps.slice(0, 8).map(function (g) {
        return ui.el('p', { class: 'bb-body' }, '• ' + String(g));
      })));
    }

    if ((presentation.warnings || []).length) {
      cards.push(ui.card('Warnings', presentation.warnings.map(function (w) {
        return ui.el('p', { class: 'bb-body' }, '• ' + String(w));
      })));
    }

    cards.push(ui.card('Export', [
      ui.el('div', { class: 'bb-row' }, [
        ui.el('button', {
          class: 'bb-btn-ghost', type: 'button',
          onclick: function () { exportAs('excel'); }
        }, '📊  Excel'),
        ui.el('button', {
          class: 'bb-btn-ghost', type: 'button',
          onclick: function () { exportAs('markdown'); }
        }, '📝  Markdown')
      ])
    ]));

    return cards;
  }

  function statCell(label, value) {
    return ui.el('div', { class: 'bb-stat' }, [
      ui.el('div', { class: 'bb-stat-value', style: 'font-size:15px' }, value),
      ui.el('div', { class: 'bb-stat-label' }, label)
    ]);
  }

  // ---- Flow ---------------------------------------------------------------

  function start() {
    if (session.running) return;
    if (!session.municipality.trim()) {
      ui.banner('error', 'Enter a municipality first.');
      return;
    }
    session.running = true;
    session.error = null;
    session.eventIndex = 0;
    session.events = [];
    session.fields = {};
    session.preflight = null;
    session.result = null;
    session.progress = { phase: 'Initializing...', percent: 0 };
    paint();

    window.fetch('/api/scraper/research', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        municipality: session.municipality.trim(),
        table_mode: session.tableMode
      })
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'Failed to start research');
        session.id = data.session_id;
        session.timer = window.setInterval(poll, 1000);
        paint();
      })
      .catch(function (error) {
        session.running = false;
        session.error = 'Could not start research: ' + error.message;
        paint();
      });
  }

  function poll() {
    if (!session.id) return;
    /* The scraper events param is `since`, NOT last_index. */
    window.fetch('/api/scraper/events/' + session.id + '?since=' + session.eventIndex,
      { credentials: 'same-origin' })
      .then(function (resp) {
        if (resp.status === 401 || resp.status === 404) {
          finishPolling();
          return loadResults();
        }
        return resp.json().then(function (data) {
          session.eventIndex = data.total_events || session.eventIndex;
          (data.events || []).forEach(function (event) {
            session.events.push(event);
            var du = event.data_update;
            if (!du) return;
            if (du.type === 'preflight') session.preflight = du.preflight_data;
            else if (du.type === 'field_extracted') {
              session.fields[du.field_id] = {
                value: du.value, confidence: du.confidence, source: du.source_url
              };
            }
          });
          if (data.progress) {
            session.progress = {
              phase: data.progress.phase || data.progress.current_phase || session.progress.phase,
              percent: data.progress.percent != null ? data.progress.percent
                : (data.progress.progress_percent || session.progress.percent)
            };
          }
          if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
            finishPolling();
            if (data.status === 'completed') {
              session.progress = { phase: 'Complete', percent: 100 };
              return loadResults();
            }
            session.error = data.status === 'failed'
              ? 'Research failed.' : 'Research cancelled.';
          }
          paint();
        });
      })
      .catch(function () { /* transient */ });
  }

  function finishPolling() {
    if (session.timer) { window.clearInterval(session.timer); session.timer = null; }
    session.running = false;
  }

  function loadResults() {
    return window.fetch('/api/scraper/research/' + session.id, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.result) session.result = data.result;
        else session.error = 'No results were returned.';
        paint();
      })
      .catch(function (error) {
        session.error = 'Could not load results: ' + error.message;
        paint();
      });
  }

  function stop() {
    if (!session.id) return;
    window.fetch('/api/scraper/stop/' + session.id, {
      method: 'POST', credentials: 'same-origin'
    }).then(function () {
      finishPolling();
      paint();
    }).catch(function () { finishPolling(); paint(); });
  }

  function exportAs(format) {
    if (!session.id) return;
    window.open('/api/scraper/export/' + format + '/' + session.id, '_blank');
  }

  BB.scraper = { render: render, start: start, stop: stop, session: session };
})(typeof window !== 'undefined' ? window : this);
