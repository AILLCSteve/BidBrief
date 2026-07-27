/* Live analysis: a high-level, visual story of what the pipeline is doing -
   no raw call/return jargon on screen. The scrolling live feed lives in a
   popup; non-admins get friendly narration only, admins can flip to the raw
   technical stream. Ports Sources/Features/Analyze/AnalysisProgressView.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var RADIUS = 88;
  var CIRCUMFERENCE = 2 * Math.PI * RADIUS;
  var startedAt = null;
  var tickTimer = null;
  var showRaw = false;

  function begin() {
    startedAt = new Date();
    if (tickTimer) window.clearInterval(tickTimer);
    tickTimer = window.setInterval(paintElapsed, 1000);
  }

  function end() {
    if (tickTimer) { window.clearInterval(tickTimer); tickTimer = null; }
  }

  function elapsedText() {
    if (!startedAt) return '';
    var seconds = Math.max(0, Math.round((new Date() - startedAt) / 1000));
    var mm = Math.floor(seconds / 60);
    var ss = seconds % 60;
    return mm + ':' + (ss < 10 ? '0' : '') + ss + ' elapsed';
  }

  function paintElapsed() {
    var node = ui.qs('#bb-progress-elapsed');
    if (node) node.textContent = elapsedText();
  }

  /** The progress orb ring: a trimmed arc around a breathing planet. */
  function ring(fraction) {
    var svgNS = 'http://www.w3.org/2000/svg';
    var svg = window.document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 190 190');

    var defs = window.document.createElementNS(svgNS, 'defs');
    var grad = window.document.createElementNS(svgNS, 'linearGradient');
    grad.setAttribute('id', 'bb-ring-grad');
    grad.setAttribute('x1', '0'); grad.setAttribute('y1', '0');
    grad.setAttribute('x2', '1'); grad.setAttribute('y2', '1');
    [['0%', '#5E86D0'], ['100%', '#45B4F2']].forEach(function (stop) {
      var s = window.document.createElementNS(svgNS, 'stop');
      s.setAttribute('offset', stop[0]);
      s.setAttribute('stop-color', stop[1]);
      grad.appendChild(s);
    });
    defs.appendChild(grad);
    svg.appendChild(defs);

    var track = window.document.createElementNS(svgNS, 'circle');
    track.setAttribute('class', 'bb-orb-ring-track');
    track.setAttribute('cx', '95'); track.setAttribute('cy', '95');
    track.setAttribute('r', String(RADIUS));
    svg.appendChild(track);

    var fill = window.document.createElementNS(svgNS, 'circle');
    fill.setAttribute('class', 'bb-orb-ring-fill');
    fill.setAttribute('id', 'bb-ring-fill');
    fill.setAttribute('cx', '95'); fill.setAttribute('cy', '95');
    fill.setAttribute('r', String(RADIUS));
    fill.setAttribute('stroke-dasharray', String(CIRCUMFERENCE));
    fill.setAttribute('stroke-dashoffset',
      String(CIRCUMFERENCE * (1 - Math.max(0.02, fraction))));
    svg.appendChild(fill);

    return ui.el('div', { class: 'bb-orb-ring-wrap' }, [
      svg,
      ui.el('div', { class: 'bb-orb-ring-core' }),
      ui.el('div', { class: 'bb-orb-ring-pct', id: 'bb-ring-pct' },
        Math.round(fraction * 100) + '%')
    ]);
  }

  /** The journey line: five steps, past ones lit, the current one pulsing. */
  function phaseTrack(currentKey) {
    var current = BB.status.rank(currentKey);
    var children = [];
    BB.status.TRACK_STEPS.forEach(function (step, index) {
      var rank = BB.status.rank(step.key);
      var isDone = rank < current;
      var isCurrent = rank === current ||
        (step.key === 'finalizing' && currentKey === 'complete');
      if (index > 0) {
        children.push(ui.el('div', {
          class: 'bb-phase-rule' + (rank <= current ? ' bb-lit' : '')
        }));
      }
      children.push(ui.el('div', {
        class: 'bb-phase-step' + (isDone ? ' bb-done' : '') + (isCurrent ? ' bb-current' : '')
      }, [
        ui.el('div', { class: 'bb-phase-dot' }, step.icon),
        ui.el('div', { class: 'bb-phase-label' }, step.stepLabel)
      ]));
    });
    return ui.el('div', { class: 'bb-phase-track' }, children);
  }

  function render(host) {
    var status = BB.status.fromEvents(BB.state.analysis.events);
    if (!startedAt) begin();

    ui.fill(host, [
      ui.el('div', { class: 'bb-progress-stage' }, [
        ring(status.fraction),
        ui.el('div', { class: 'bb-progress-title', id: 'bb-progress-title' },
          BB.status.phaseInfo(status.phase).title),
        ui.el('div', { class: 'bb-progress-detail', id: 'bb-progress-detail' }, status.detail),
        ui.el('div', { class: 'bb-progress-elapsed', id: 'bb-progress-elapsed' }, elapsedText()),
        phaseTrack(status.phase)
      ]),
      ui.el('div', { class: 'bb-stack' }, [
        ui.el('button', {
          class: 'bb-btn-glow', type: 'button',
          onclick: function () { openLiveActivity(); }
        }, '📡  Live Activity'),
        ui.el('button', {
          class: 'bb-btn-ghost bb-warn', type: 'button',
          onclick: function () { BB.engine.stop(); }
        }, '■  Stop and keep partial results')
      ])
    ]);
  }

  /** Patch the numbers in place so the ring animates instead of jumping. */
  function update() {
    if (BB.state.analysis.phase !== 'analyzing') return;
    var status = BB.status.fromEvents(BB.state.analysis.events);

    var fill = ui.qs('#bb-ring-fill');
    if (fill) {
      fill.setAttribute('stroke-dashoffset',
        String(CIRCUMFERENCE * (1 - Math.max(0.02, status.fraction))));
    }
    var pct = ui.qs('#bb-ring-pct');
    if (pct) pct.textContent = Math.round(status.fraction * 100) + '%';
    var title = ui.qs('#bb-progress-title');
    if (title) title.textContent = BB.status.phaseInfo(status.phase).title;
    var detail = ui.qs('#bb-progress-detail');
    if (detail) detail.textContent = status.detail;

    var track = ui.qs('.bb-phase-track');
    if (track && track.parentNode) {
      track.parentNode.replaceChild(phaseTrack(status.phase), track);
    }
    if (ui.qs('#bb-feed-body')) paintFeed();
  }

  // ---- Live Activity popup ------------------------------------------------

  function friendlyRows() {
    return BB.state.analysis.events.map(function (event) {
      var line = BB.status.friendlyLine(event);
      if (!line) return null;
      return ui.el('div', { class: 'bb-feed-row' }, [
        ui.el('div', { class: 'bb-feed-icon' },
          BB.status.phaseInfo(BB.status.phaseOf(event)).icon),
        ui.el('div', { class: 'bb-feed-text' }, line),
        ui.el('div', { class: 'bb-feed-time' }, timeOnly(event.timestamp))
      ]);
    }).filter(Boolean);
  }

  function rawRows() {
    return BB.state.analysis.events.map(function (event) {
      var payload = {};
      Object.keys(event.payload || {}).forEach(function (k) {
        if (k !== 'event' && k !== 'timestamp') payload[k] = event.payload[k];
      });
      var text = JSON.stringify(payload);
      return ui.el('div', { class: 'bb-feed-raw' }, [
        ui.el('div', { class: 'bb-row' }, [
          ui.el('span', { class: 'bb-feed-name' }, event.event),
          ui.el('span', { class: 'bb-feed-time bb-grow bb-row-end' }, timeOnly(event.timestamp))
        ]),
        text && text !== '{}'
          ? ui.el('div', { class: 'bb-feed-payload' }, text.slice(0, 400))
          : null
      ]);
    });
  }

  function paintFeed() {
    var body = ui.qs('#bb-feed-body');
    if (!body) return;
    var atBottom = body.scrollTop + body.clientHeight >= body.scrollHeight - 40;
    ui.fill(body, ui.el('div', { class: 'bb-feed' },
      (showRaw && BB.state.session.isAdmin) ? rawRows() : friendlyRows()));
    if (atBottom) body.scrollTop = body.scrollHeight;
  }

  function openLiveActivity() {
    var body = ui.el('div', { class: 'bb-modal-body', id: 'bb-feed-body' });
    var head = [
      ui.el('h2', {}, 'Live Activity'),
      ui.el('button', {
        class: 'bb-modal-close', type: 'button', 'aria-label': 'Close',
        onclick: function () { BB.modal.close(); }
      }, '✕')
    ];

    var children = [ui.el('div', { class: 'bb-modal-head' }, head)];
    /* Everyone gets the friendly narration; admins can flip to the raw
       event stream - a view that exists nowhere else. */
    if (BB.state.session.isAdmin) {
      var seg = ui.el('div', { class: 'bb-segmented' }, [
        ui.el('button', {
          class: showRaw ? '' : 'bb-active', type: 'button',
          onclick: function () { showRaw = false; refreshSegments(seg); paintFeed(); }
        }, 'Overview'),
        ui.el('button', {
          class: showRaw ? 'bb-active' : '', type: 'button',
          onclick: function () { showRaw = true; refreshSegments(seg); paintFeed(); }
        }, 'Raw Events')
      ]);
      children.push(ui.el('div', { style: 'padding: 14px 20px 0;' }, [seg]));
    }
    children.push(body);

    BB.modal.open(children);
    paintFeed();
    body.scrollTop = body.scrollHeight;
  }

  function refreshSegments(seg) {
    var buttons = seg.querySelectorAll('button');
    buttons[0].className = showRaw ? '' : 'bb-active';
    buttons[1].className = showRaw ? 'bb-active' : '';
  }

  function timeOnly(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString();
  }

  BB.progress = {
    render: render, update: update, begin: begin, end: end,
    openLiveActivity: openLiveActivity
  };
})(typeof window !== 'undefined' ? window : this);
