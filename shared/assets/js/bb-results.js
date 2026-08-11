/* Results — the Excel workbook, on glass.

   2.4.0: the results screen presents the SAME multi-sheet depth as the Excel
   export (Executive Summary / Detailed Results / By Section / Document
   Intelligence / Visual Intelligence / Footnotes) as a workbook tab strip in
   the bb design system. Improve Results and Exports & Smart Analysis remain
   their own focused layers. Ports services/excel_dashboard.py sheet-for-sheet;
   the public helpers (summarize/flatten/...) are consumed by bb-admin.js. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var path = [];                 /* stage stack; empty = the workbook */
  var activeSheet = null;        /* current workbook tab id */
  var liveAnswers = {};          /* question_id -> answer streamed during analysis */

  function results() { return BB.state.analysis.results || { sections: [] }; }

  function isAnswered(q) {
    return !!(q && typeof q.answer === 'string' && q.answer.trim().length);
  }

  /** L6.5 AnswerSummarizer output; absent on results cached before 2.1.0. */
  function answerSummaryOf(q) {
    var s = q && q.answer_summary;
    return (typeof s === 'string' && s.trim().length) ? s : null;
  }

  function confidenceOf(q) {
    var c = String((q && q.confidence) || '').toLowerCase();
    return (c === 'high' || c === 'medium') ? c : 'low';
  }

  function statusOf(q) { return isAnswered(q) ? 'found' : 'missing'; }

  /* ---- Layer 0.5 provenance ------------------------------------------------
     An answer can be grounded in the written text, in a drawing/map/photo, or
     both. visual_sources says which graphics fed it; absent on results cached
     before 2.4.0, so every reader must tolerate its absence. */

  var VISUAL_KIND_LABELS = {
    drawing: 'Drawing', map: 'Map', photo: 'Photo',
    chart: 'Chart', table: 'Table image', mixed: 'Visual', visual: 'Visual'
  };
  var VISUAL_KIND_ICONS = {
    drawing: '📐', map: '🗺', photo: '📷', chart: '📊', table: '▦', mixed: '🖼', visual: '🖼'
  };

  function visualSourcesOf(q) {
    var list = q && q.visual_sources;
    return (Object.prototype.toString.call(list) === '[object Array]') ? list : [];
  }

  /** "Drawing p.7; Map p.9" - matches the Excel Visual Source column. */
  function visualSourceLabel(q) {
    return visualSourcesOf(q).map(function (s) {
      var kind = String(s.kind || 'visual').toLowerCase();
      return (VISUAL_KIND_LABELS[kind] || 'Visual') + ' p.' + s.page;
    }).join('; ');
  }

  /** Chips marking an answer as sourced from graphics, or null when text-only. */
  function visualBadges(q) {
    var sources = visualSourcesOf(q);
    if (!sources.length) return null;
    return ui.el('span', { class: 'bb-vis-badges' }, sources.map(function (s) {
      var kind = String(s.kind || 'visual').toLowerCase();
      return ui.el('span', {
        class: 'bb-vis-badge',
        title: 'This answer came from the ' + (VISUAL_KIND_LABELS[kind] || 'graphic').toLowerCase() +
               ' on page ' + s.page + ', not from the written text'
      }, (VISUAL_KIND_ICONS[kind] || '🖼') + ' ' +
         (VISUAL_KIND_LABELS[kind] || 'Visual') + ' p.' + s.page);
    }));
  }

  function allQuestions(payload) {
    return ((payload && payload.sections) || []).reduce(function (acc, sec) {
      return acc.concat(sec.questions || []);
    }, []);
  }

  function summarize(payload) {
    var questions = allQuestions(payload);
    var answered = questions.filter(isAnswered).length;
    return {
      total: questions.length,
      answered: answered,
      rate: questions.length ? Math.round(answered / questions.length * 100) + '%' : '—',
      pages: (payload && payload.total_pages) || 0,
      unanswered: questions.filter(function (q) { return !isAnswered(q); })
    };
  }

  /** Every question with its section name - tables, CSV, admin modal. */
  function flatten(payload) {
    var rows = [];
    ((payload && payload.sections) || []).forEach(function (sec) {
      (sec.questions || []).forEach(function (q) {
        var row = {};
        Object.keys(q).forEach(function (k) { row[k] = q[k]; });
        row.section_name = sec.section_name;
        row.section_id = sec.section_id;
        rows.push(row);
      });
    });
    return rows;
  }

  function visualFindings(payload) {
    return (payload && payload.visual_findings) || [];
  }

  function dynamicTables(payload) {
    return (payload && (payload.dynamic_tables || payload.dynamicTables)) || [];
  }

  function hasKeyDetails(payload) {
    var kr = payload.key_requirements || BB.state.analysis.keyRequirements;
    return !!(kr && Object.keys(kr).length);
  }

  // ---- Workbook shape (pure - unit tested) --------------------------------

  /** The sheet tabs this payload earns, in workbook order. */
  function sheetList(payload) {
    var sheets = [
      { id: 'summary', label: 'Executive Summary' },
      { id: 'detailed', label: 'Detailed Results' },
      { id: 'bySection', label: 'By Section' }
    ];
    if (dynamicTables(payload).length) {
      sheets.push({ id: 'intelligence', label: 'Document Intelligence' });
    }
    if (visualFindings(payload).length) {
      sheets.push({ id: 'visual', label: 'Visual Intelligence' });
    }
    sheets.push({ id: 'footnotes', label: 'Footnotes' });
    return sheets;
  }

  /** Executive Summary statistics rows - mirrors the Excel sheet exactly. */
  function execSummaryRows(payload) {
    var questions = allQuestions(payload);
    var answered = questions.filter(isAnswered).length;
    var total = questions.length;
    var confs = questions.map(function (q) { return Number(q.confidence) || 0; })
      .filter(function (c) { return c > 0; });
    var avg = confs.length
      ? Math.round(confs.reduce(function (a, b) { return a + b; }, 0) / confs.length * 100) + '%'
      : 'N/A';
    return [
      ['Total Questions', String(total)],
      ['Questions Answered', String(answered)],
      ['Answer Rate', total ? Math.round(answered / total * 100) + '%' : '—'],
      ['Average Confidence', avg],
      ['Analysis Date', new Date().toLocaleDateString()]
    ];
  }

  /* Key Document Details - the Excel display-name mapping + preferred order. */
  var KEY_LABELS = {
    project_name: 'Project Name', owner: 'Owner/Agency', engineer: 'Engineer',
    location: 'Location', bid_deadline: 'Bid Deadline', completion_date: 'Timeline',
    scope: 'Scope', linear_feet: 'Scope', payment_terms: 'Payment',
    warranty: 'Warranty', liquidated_damages: 'Liquidated Damages',
    bid_bond: 'Bonding', performance_bond: 'Bonding',
    certifications: 'Certifications', insurance: 'Insurance'
  };
  var KEY_ORDER = ['Project Name', 'Owner/Agency', 'Engineer', 'Location', 'Timeline',
    'Scope', 'Bid Deadline', 'Payment', 'Warranty', 'Liquidated Damages',
    'Bonding', 'Certifications', 'Insurance'];

  function cleanDetailValue(value) {
    if (value && typeof value === 'object') value = JSON.stringify(value);
    return String(value == null ? '' : value)
      .replace(/<PDF pg[^>]+>/g, '').replace(/\s+/g, ' ').trim();
  }

  function keyDetailRows(kr) {
    var byLabel = {};
    Object.keys(kr || {}).forEach(function (key) {
      var value = cleanDetailValue(kr[key]);
      if (!value || /^(not found|n\/a|not specified)$/i.test(value)) return;
      var label = KEY_LABELS[key] ||
        key.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
      if (byLabel[label] && byLabel[label].indexOf(value) < 0) {
        byLabel[label] += '; ' + value;
      } else if (!byLabel[label]) {
        byLabel[label] = value;
      }
    });
    var rows = [];
    KEY_ORDER.forEach(function (label) {
      if (byLabel[label]) { rows.push([label, byLabel[label]]); delete byLabel[label]; }
    });
    Object.keys(byLabel).sort().forEach(function (label) {
      rows.push([label, byLabel[label]]);
    });
    return rows;
  }

  // ---- CSV / live ingest ---------------------------------------------------

  function csvCell(value) {
    return '"' + String(value == null ? '' : value).replace(/"/g, '""') + '"';
  }

  function toCsv(payload) {
    var lines = ['Section,#,Question,Answer,Answer Summary,PDF Pages,Visual Source'];
    ((payload && payload.sections) || []).forEach(function (sec) {
      (sec.questions || []).forEach(function (q, index) {
        lines.push([
          csvCell(sec.section_name),
          csvCell(index + 1),
          csvCell(q.question),
          csvCell(isAnswered(q) ? q.answer : 'Not found'),
          csvCell(answerSummaryOf(q) || ''),
          csvCell((q.page_citations || []).join(';')),
          csvCell(visualSourceLabel(q))
        ].join(','));
      });
    });
    return lines.join('\n');
  }

  /** Live answers arriving mid-analysis (window_complete new_answers). */
  function ingestLiveAnswers(answers, stage) {
    (answers || []).forEach(function (item) {
      var id = item.question_id || item.id;
      if (id) liveAnswers[id] = { answer: item.answer, stage: stage, pages: item.page_citations };
    });
  }

  // ---- Navigation ----------------------------------------------------------

  function push(stage, arg) { path.push({ stage: stage, arg: arg }); render(); }
  function back() { path.pop(); render(); }
  function top() { return path.length ? path[path.length - 1] : null; }

  function render(host) {
    host = host || ui.qs('#bb-page-analyze');
    if (!host) return;
    var here = top();
    if (!here) return renderWorkbook(host);
    switch (here.stage) {
      case 'improve': return renderImprove(host);
      case 'actions': return renderActions(host);
      default:        return renderWorkbook(host);
    }
  }

  function chrome(title, subtitle) {
    return [
      ui.el('div', { class: 'bb-row' }, [
        ui.el('button', { class: 'bb-back-chip', type: 'button', onclick: back }, '‹  Back')
      ]),
      ui.stageHeader(title, subtitle)
    ];
  }

  // ---- The workbook --------------------------------------------------------

  /**
   * A self-contained workbook for ANY results payload.
   *
   * Owns its own active-tab state in a closure and repaints only its own body,
   * so the same component can be mounted on the Analyze tab and inside the
   * admin session modal at the same time without the two fighting over which
   * sheet is open. Everything that reads a payload goes through here — that is
   * what guarantees an admin reviewing a session sees exactly the sheets the
   * user who ran it sees, Document Intelligence included.
   */
  function buildWorkbook(payload, opts) {
    var options = opts || {};
    var sheets = sheetList(payload);
    var active = options.sheet && sheets.some(function (t) { return t.id === options.sheet; })
      ? options.sheet
      : sheets[0].id;

    var body = ui.el('div', { class: 'bb-sheet-body' });
    var tabs = ui.el('div', { class: 'bb-sheet-tabs', role: 'tablist' });
    var card = ui.el('div', { class: 'bb-glass-card bb-workbook' }, [tabs, body]);

    function paint() {
      ui.fill(tabs, sheets.map(function (tab) {
        return ui.el('button', {
          class: 'bb-sheet-tab' + (tab.id === active ? ' bb-active' : ''),
          type: 'button', role: 'tab',
          'aria-selected': tab.id === active ? 'true' : 'false',
          onclick: function () { active = tab.id; paint(); }
        }, tab.label);
      }));
      ui.fill(body, sheetBody(active, payload));
    }

    paint();
    return card;
  }

  function renderWorkbook(host) {
    var payload = results();
    var s = summarize(payload);

    var children = [];

    children.push(ui.el('div', { class: 'bb-center' }, [
      ui.el('span', { class: 'bb-eyebrow' }, 'Analysis Report'),
      ui.el('h1', { style: 'font-size:24px;font-weight:700;text-shadow:0 0 14px rgba(201, 162, 39,.55)' },
        payload.document_name || BB.state.analysis.filename || 'Results')
    ]));

    if (BB.state.analysis.isPartial) {
      children.push(ui.card(null, [
        ui.el('p', { class: 'bb-body' },
          '⚠ Partial results - the analysis was stopped before it finished.')
      ]));
    }

    children.push(ui.card(null, [
      ui.el('div', { class: 'bb-stats' }, [
        stat('Answered', s.answered + '/' + s.total),
        ui.el('div', { class: 'bb-stat-sep' }),
        stat('Pages', String(s.pages)),
        ui.el('div', { class: 'bb-stat-sep' }),
        stat('Rate', s.rate)
      ])
    ]));

    children.push(buildWorkbook(payload, { sheet: activeSheet }));

    var hubs = [];
    if (s.unanswered.length) {
      hubs.push(ui.hubButton({
        title: 'Improve Results', icon: '🪄',
        subtitle: s.unanswered.length + ' unanswered - run another pass',
        onClick: function () { push('improve'); }
      }));
    }
    hubs.push(ui.hubButton({
      title: 'Exports & Analysis', icon: '⬆',
      subtitle: 'Excel workbook, CSV, HTML, Smart Analysis',
      onClick: function () { push('actions'); }
    }));
    children.push(ui.el('div', { class: 'bb-stack' }, hubs));

    children.push(ui.el('button', {
      class: 'bb-btn-ghost bb-danger', type: 'button',
      onclick: function () { path = []; activeSheet = null; BB.analyze.reset(); }
    }, 'New Analysis'));

    ui.fill(host, children);
  }

  function stat(label, value) {
    return ui.el('div', { class: 'bb-stat' }, [
      ui.el('div', { class: 'bb-stat-value' }, value),
      ui.el('div', { class: 'bb-stat-label' }, label)
    ]);
  }

  function sheetBody(id, payload) {
    switch (id) {
      case 'summary':      return sheetSummary(payload);
      case 'detailed':     return sheetDetailed(payload);
      case 'bySection':    return sheetBySection(payload);
      case 'intelligence': return sheetIntelligence(payload);
      case 'visual':       return sheetVisual(payload);
      case 'footnotes':    return sheetFootnotes(payload);
      default:             return [];
    }
  }

  // ---- Sheet 1: Executive Summary -----------------------------------------

  function kvTable(rows) {
    return ui.el('div', { class: 'bb-table-wrap' }, [
      ui.el('table', { class: 'bb-table bb-kv-table' }, [
        ui.el('tbody', {}, rows.map(function (pair) {
          return ui.el('tr', {}, [
            ui.el('td', { class: 'bb-td-strong' }, pair[0]),
            ui.el('td', {}, pair[1])
          ]);
        }))
      ])
    ]);
  }

  function sheetSummary(payload) {
    var blocks = [
      sectionBand('Analysis Statistics'),
      kvTable(execSummaryRows(payload))
    ];
    var kr = payload.key_requirements || BB.state.analysis.keyRequirements || {};
    var details = keyDetailRows(kr);
    blocks.push(sectionBand('Key Document Details'));
    if (details.length) {
      blocks.push(kvTable(details));
    } else {
      blocks.push(ui.el('p', { class: 'bb-caption' },
        'Key project details will appear here when extracted from the analysis.'));
    }
    var vis = visualFindings(payload);
    if (vis.length) {
      blocks.push(sectionBand('Visual Intelligence'));
      blocks.push(ui.el('p', { class: 'bb-body' },
        vis.length + ' drawing/map/imagery page' + (vis.length === 1 ? '' : 's') +
        ' deep-processed with AI vision - see the Visual Intelligence sheet.'));
    }
    return blocks;
  }

  function sectionBand(text) {
    return ui.el('div', { class: 'bb-section-band' }, text);
  }

  // ---- Sheet 2: Detailed Results ------------------------------------------

  function expandableAnswer(q) {
    if (!isAnswered(q)) {
      return ui.el('span', { class: 'bb-td-pending' }, 'Not found in document');
    }
    var cell = ui.el('span', { class: 'bb-answer-cell bb-clamped' }, q.answer);
    cell.addEventListener('click', function () { cell.classList.toggle('bb-clamped'); });
    return cell;
  }

  function statusPill(q) {
    var found = isAnswered(q);
    return ui.el('span', {
      class: 'bb-status-pill ' + (found ? 'bb-status-found' : 'bb-status-missing')
    }, found ? 'Found' : 'Not Found');
  }

  function sheetDetailed(payload) {
    var rows = flatten(payload);
    var body = ui.el('tbody', {}, rows.map(function (q, index) {
      return ui.el('tr', {}, [
        ui.el('td', { class: 'bb-td-center' }, String(index + 1)),
        ui.el('td', {}, q.section_name || ''),
        ui.el('td', { class: 'bb-td-strong' }, q.question || ''),
        ui.el('td', {}, [expandableAnswer(q), visualBadges(q)]),
        ui.el('td', {}, answerSummaryOf(q) || '-'),
        ui.el('td', { class: 'bb-td-center' }, (q.page_citations || []).join(', ') || '-'),
        ui.el('td', { class: 'bb-td-center' }, visualSourceLabel(q) || '-'),
        ui.el('td', { class: 'bb-td-center' }, q.footnote ? '✓' : '-'),
        ui.el('td', { class: 'bb-td-center' }, [statusPill(q)])
      ]);
    }));
    return [
      ui.el('p', { class: 'bb-caption', style: 'margin-bottom:10px' },
        rows.length + ' questions - tap an answer to expand it.'),
      ui.el('div', { class: 'bb-table-wrap' }, [
        ui.el('table', { class: 'bb-table' }, [
          ui.el('thead', {}, [ui.el('tr', {},
            ['#', 'Section', 'Question', 'Answer', 'Answer Summary', 'PDF Pages',
             'Visual Source', 'FN', 'Status']
              .map(function (h) { return ui.el('th', {}, h); }))]),
          body
        ])
      ])
    ];
  }

  // ---- Sheet 3: By Section --------------------------------------------------

  function sheetBySection(payload) {
    var blocks = [];
    (payload.sections || []).forEach(function (section) {
      var questions = section.questions || [];
      var answered = questions.filter(isAnswered).length;
      var rate = questions.length ? Math.round(answered / questions.length * 100) : 0;
      blocks.push(sectionBand(
        (section.section_name || 'Section').toUpperCase() +
        '  (' + answered + '/' + questions.length + ' answered - ' + rate + '%)'));
      blocks.push(ui.el('div', { class: 'bb-table-wrap' }, [
        ui.el('table', { class: 'bb-table' }, [
          ui.el('thead', {}, [ui.el('tr', {},
            ['#', 'Question', 'Answer', 'Answer Summary', 'PDF Pages', 'Visual Source', 'Status']
              .map(function (h) { return ui.el('th', {}, h); }))]),
          ui.el('tbody', {}, questions.map(function (q, index) {
            return ui.el('tr', {}, [
              ui.el('td', { class: 'bb-td-center' }, String(index + 1)),
              ui.el('td', { class: 'bb-td-strong' }, q.question || ''),
              ui.el('td', {}, [expandableAnswer(q), visualBadges(q)]),
              ui.el('td', {}, answerSummaryOf(q) || '-'),
              ui.el('td', { class: 'bb-td-center' }, (q.page_citations || []).join(', ') || '-'),
              ui.el('td', { class: 'bb-td-center' }, visualSourceLabel(q) || '-'),
              ui.el('td', { class: 'bb-td-center' }, [
                ui.el('span', {
                  class: 'bb-status-mark ' +
                    (isAnswered(q) ? 'bb-status-found' : 'bb-status-missing')
                }, isAnswered(q) ? '✓' : '✗')
              ])
            ]);
          }))
        ])
      ]));
    });
    return blocks;
  }

  // ---- Sheet: Document Intelligence ----------------------------------------

  function sheetIntelligence(payload) {
    var blocks = [];
    if (payload.intelligence_focus) {
      blocks.push(ui.el('p', { class: 'bb-caption-lit' }, payload.intelligence_focus));
    }
    dynamicTables(payload).forEach(function (table) {
      var columns = table.columns || [];
      var keys, labels;
      if (columns.length && typeof columns[0] === 'object') {
        keys = columns.map(function (c) { return c.key; });
        labels = columns.map(function (c) { return c.label || c.key; });
      } else if (columns.length) {
        keys = labels = columns;
      } else {
        keys = labels = (table.rows && table.rows[0]) ? Object.keys(table.rows[0]) : [];
      }
      blocks.push(sectionBand(table.title || table.name || 'Table'));
      if (table.why_relevant || table.description) {
        blocks.push(ui.el('p', { class: 'bb-caption', style: 'margin-bottom:8px' },
          table.why_relevant || table.description));
      }
      blocks.push(ui.el('div', { class: 'bb-table-wrap' }, [
        ui.el('table', { class: 'bb-table' }, [
          ui.el('thead', {}, [ui.el('tr', {}, labels.map(function (c) {
            return ui.el('th', {}, String(c));
          }))]),
          ui.el('tbody', {}, (table.rows || []).map(function (row) {
            return ui.el('tr', {}, keys.map(function (k) {
              return ui.el('td', {}, String(row[k] == null ? '' : row[k]));
            }));
          }))
        ])
      ]));
      (table.insights || []).forEach(function (insight) {
        blocks.push(ui.el('p', { class: 'bb-caption' }, '💡 ' + insight));
      });
    });
    return blocks;
  }

  // ---- Sheet: Visual Intelligence -------------------------------------------

  /** Questions whose answers cite a given visual page - the proof that the
      visual pass fed the question set rather than sitting beside it. */
  function questionsFedBy(payload, page) {
    return flatten(payload).filter(function (q) {
      return visualSourcesOf(q).some(function (s) { return s.page === page; });
    });
  }

  function sheetVisual(payload) {
    var findings = visualFindings(payload);
    var blocks = [
      ui.el('p', { class: 'bb-caption', style: 'margin-bottom:10px' },
        findings.length + ' visual-heavy page' + (findings.length === 1 ? '' : 's') +
        ' deep-processed with AI vision. Everything read here was fed to the ' +
        'experts as evidence for your question set - answers it produced are ' +
        'marked with a badge throughout the report.')
    ];
    findings.forEach(function (f) {
      var parts = [
        ui.el('div', { class: 'bb-row' }, [
          ui.el('span', { class: 'bb-pill bb-pill-medium' },
            String(f.kind || 'visual').toUpperCase()),
          ui.el('span', { class: 'bb-pages' }, 'p. ' + f.page),
          f.title ? ui.el('span', { class: 'bb-list-title' }, f.title) : null
        ])
      ];
      if (f.description) {
        parts.push(ui.el('p', { class: 'bb-body', style: 'margin-top:6px' }, f.description));
      }
      if (f.extracted_text) {
        parts.push(ui.el('div', { class: 'bb-visual-extract' }, f.extracted_text));
      }
      if ((f.key_facts || []).length) {
        parts.push(ui.el('ul', { class: 'bb-visual-facts' }, f.key_facts.map(function (fact) {
          return ui.el('li', {}, String(fact));
        })));
      }

      /* Close the loop: name the questions this graphic actually answered. */
      var fed = questionsFedBy(payload, f.page);
      if (fed.length) {
        parts.push(ui.el('div', { class: 'bb-visual-fed' }, [
          ui.el('div', { class: 'bb-visual-fed-head' },
            'Answered ' + fed.length + ' question' + (fed.length === 1 ? '' : 's') +
            ' in your set:'),
          ui.el('ul', { class: 'bb-visual-facts' }, fed.map(function (q) {
            return ui.el('li', {}, (q.section_name ? q.section_name + ' — ' : '') +
              (q.question || ''));
          }))
        ]));
      }
      blocks.push(ui.el('div', { class: 'bb-visual-finding' }, parts));
    });
    return blocks;
  }

  // ---- Sheet: Footnotes ------------------------------------------------------

  function sheetFootnotes(payload) {
    var footnotes = payload.footnotes || [];
    if (!footnotes.length) {
      return [ui.el('p', { class: 'bb-caption' }, 'No footnotes were compiled for this analysis.')];
    }
    return [ui.el('div', { class: 'bb-table-wrap' }, [
      ui.el('table', { class: 'bb-table' }, [
        ui.el('thead', {}, [ui.el('tr', {}, [
          ui.el('th', { style: 'width:44px' }, '#'), ui.el('th', {}, 'Footnote')
        ])]),
        ui.el('tbody', {}, footnotes.map(function (fn, index) {
          return ui.el('tr', {}, [
            ui.el('td', { class: 'bb-td-center' }, String(index + 1)),
            ui.el('td', {}, String(fn))
          ]);
        }))
      ])
    ])];
  }

  // ---- Improve ---------------------------------------------------------------

  function renderImprove(host) {
    var s = summarize(results());
    ui.fill(host, chrome('Improve Results',
      s.unanswered.length + ' questions still unanswered.').concat([
      ui.el('div', { class: 'bb-stack' }, [
        ui.hubButton({
          title: 'Second Pass', icon: '🔍',
          subtitle: 'Re-read the document with enhanced scrutiny',
          onClick: function () { openPassPicker('second-pass', 'Second Pass', s.unanswered); }
        }),
        ui.hubButton({
          title: 'Deep RAG', icon: '🌐',
          subtitle: "Search external sources for what the document doesn't say",
          onClick: function () { openPassPicker('rag', 'Deep RAG', s.unanswered); }
        })
      ])
    ]));
  }

  function openPassPicker(kind, title, questions) {
    var selected = {};
    var body = ui.el('div', { class: 'bb-modal-body' });

    function paint() {
      ui.fill(body, [
        ui.el('div', { class: 'bb-row', style: 'margin-bottom:12px' }, [
          ui.el('button', {
            class: 'bb-btn-ghost', type: 'button',
            onclick: function () {
              var all = questions.every(function (q) { return selected[q.question_id]; });
              questions.forEach(function (q) { selected[q.question_id] = !all; });
              paint();
            }
          }, 'Select all / none')
        ])
      ].concat(questions.map(function (q) {
        return ui.toggleRow({
          title: q.question || q.text || '',
          checked: !!selected[q.question_id],
          onChange: function (on) { selected[q.question_id] = on; }
        });
      })).concat([
        ui.el('button', {
          class: 'bb-btn-glow', type: 'button', style: 'margin-top:16px',
          onclick: function () {
            var ids = Object.keys(selected).filter(function (id) { return selected[id]; });
            if (!ids.length) { ui.banner('error', 'Select at least one question.'); return; }
            runPass(kind, title, ids);
          }
        }, 'Run ' + title)
      ]));
    }

    BB.modal.open([
      ui.el('div', { class: 'bb-modal-head' }, [
        ui.el('h2', {}, title),
        ui.el('button', {
          class: 'bb-modal-close', type: 'button', 'aria-label': 'Close',
          onclick: function () { BB.modal.close(); }
        }, '✕')
      ]),
      body
    ]);
    paint();
  }

  function runPass(kind, title, ids) {
    BB.modal.open([
      ui.el('div', { class: 'bb-modal-head' }, [ui.el('h2', {}, title)]),
      ui.el('div', { class: 'bb-modal-body bb-center' }, [
        ui.el('div', { class: 'bb-spinner', style: 'margin-bottom:12px' }),
        ui.el('p', { class: 'bb-body' },
          title + ' running - this can take several minutes...')
      ])
    ], { sticky: true });

    BB.engine.runPass(kind, ids).then(function () {
      BB.modal.close();
      ui.banner('info', title + ' finished.');
      path = [];
      render();
    }).catch(function (error) {
      BB.modal.close();
      ui.banner('error', title + ' failed: ' + error.message);
    });
  }

  // ---- Exports & Smart Analysis ---------------------------------------------

  function renderActions(host) {
    var children = chrome('Exports & Analysis');
    var mode = BB.state.analysis.mode;

    children.push(ui.card('Export', [
      ui.el('div', { class: 'bb-row' }, [
        exportBtn('📊  Excel Report Package', function () {
          var sid = BB.state.analysis.sessionId;
          window.open(mode === 'bestprep'
            ? '/api/export/bestprep-excel/' + sid
            : '/api/export/excel-dashboard/' + sid, '_blank');
        }),
        exportBtn('📄  CSV', function () { downloadCsv(); }),
        exportBtn('🌐  HTML Report', function () { downloadHtml(); }),
        exportBtn('📋  JSON', function () { downloadJson(); })
      ])
    ]));

    var input = ui.el('textarea', {
      rows: '3',
      placeholder: "Optional: ask specific questions about this document (e.g. 'Is this project worth bidding? What are the biggest red flags?')"
    });
    children.push(ui.card('Smart Analysis', [
      ui.el('div', { class: 'bb-field' }, [input]),
      ui.el('button', {
        class: 'bb-btn-glow', type: 'button', style: 'margin-top:12px',
        onclick: function () { runSmartAnalysis(input.value); }
      }, '🧠  Run Smart Analysis'),
      ui.el('div', { id: 'bb-smart-output', class: 'bb-stack', style: 'margin-top:14px' })
    ]));

    children.push(ui.el('button', {
      class: 'bb-btn-ghost bb-danger', type: 'button',
      onclick: function () { path = []; activeSheet = null; BB.analyze.reset(); }
    }, 'New Analysis'));

    ui.fill(host, children);
  }

  function exportBtn(label, onClick) {
    return ui.el('button', { class: 'bb-btn-ghost', type: 'button', onclick: onClick }, label);
  }

  function download(content, filename, mime) {
    var blob = new window.Blob([content], { type: mime });
    var url = window.URL.createObjectURL(blob);
    var a = ui.el('a', { href: url, download: filename });
    a.click();
    window.setTimeout(function () { window.URL.revokeObjectURL(url); }, 1000);
  }

  function downloadJson() {
    download(JSON.stringify(results(), null, 2), 'bidbrief_analysis.json', 'application/json');
  }

  function downloadCsv() {
    download(toCsv(results()), 'bidbrief_analysis.csv', 'text/csv');
  }

  function downloadHtml() {
    var payload = results();
    var rows = flatten(payload).map(function (q) {
      return '<tr><td>' + ui.escapeHtml(q.section_name) + '</td>' +
        '<td>' + ui.escapeHtml(q.question) + '</td>' +
        '<td>' + ui.escapeHtml(isAnswered(q) ? q.answer : 'Not found') + '</td>' +
        '<td>' + ui.escapeHtml(answerSummaryOf(q) || '') + '</td>' +
        '<td>' + ui.escapeHtml((q.page_citations || []).join(', ')) + '</td>' +
        '<td>' + ui.escapeHtml(visualSourceLabel(q)) + '</td></tr>';
    }).join('');
    var visualRows = visualFindings(payload).map(function (f) {
      return '<tr><td>' + ui.escapeHtml(String(f.page)) + '</td>' +
        '<td>' + ui.escapeHtml(String(f.kind || '')) + '</td>' +
        '<td>' + ui.escapeHtml(f.title || '') + '</td>' +
        '<td>' + ui.escapeHtml(f.description || '') + '</td>' +
        '<td>' + ui.escapeHtml(f.extracted_text || '') + '</td>' +
        '<td>' + ui.escapeHtml((f.key_facts || []).join(' • ')) + '</td></tr>';
    }).join('');
    var visualSection = visualRows
      ? '<h2>Visual Intelligence — Drawings, Maps &amp; Imagery</h2><table><thead><tr>' +
        '<th>Page</th><th>Type</th><th>Title</th><th>What It Shows</th>' +
        '<th>Labels &amp; Callouts</th><th>Key Facts</th></tr></thead><tbody>' +
        visualRows + '</tbody></table>'
      : '';
    var html = '<!DOCTYPE html><html><head><meta charset="UTF-8">' +
      '<title>BidBrief Analysis Report</title><style>' +
      'body{font-family:Calibri,Arial,sans-serif;font-size:12pt;margin:40px;}' +
      'h1{color:#2A2312;border-bottom:4px solid #C9A227;padding-bottom:12px;}' +
      'h2{color:#2A2312;margin-top:36px;}' +
      'table{width:100%;border-collapse:collapse;margin-top:20px;}' +
      'th{background:#2A2312;color:#fff;padding:10px;text-align:left;}' +
      'td{padding:9px;border:1px solid #ddd;vertical-align:top;}' +
      '</style></head><body><h1>' + ui.escapeHtml(payload.document_name || 'Document Analysis') +
      '</h1><p>Generated: ' + new Date().toLocaleString() + '</p><table><thead><tr>' +
      '<th>Section</th><th>Question</th><th>Answer</th><th>Answer Summary</th><th>PDF Pages</th>' +
      '<th>Visual Source</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>' + visualSection + '</body></html>';
    download(html, 'bidbrief_analysis.html', 'text/html');
  }

  function runSmartAnalysis(userInput) {
    var out = ui.qs('#bb-smart-output');
    ui.fill(out, [ui.el('div', { class: 'bb-row' }, [
      ui.el('span', { class: 'bb-spinner' }),
      ui.el('span', { class: 'bb-body' }, 'Smart Analysis is underway...')
    ])]);

    BB.engine.smartAnalysis(userInput).then(function (r) {
      ui.fill(out, renderSmart(r));
    }).catch(function (error) {
      ui.fill(out, [ui.el('p', { class: 'bb-body' }, 'Smart Analysis failed: ' + error.message)]);
    });
  }

  function renderSmart(r) {
    var blocks = [];

    function section(title, children) {
      if (!children || !children.length) return;
      blocks.push(ui.card(title, children));
    }

    function items(list) {
      return (list || []).map(function (it) {
        return ui.el('div', { style: 'margin-bottom:12px' }, [
          ui.el('div', { class: 'bb-row' }, [
            ui.el('span', { class: 'bb-pill bb-pill-' + severityClass(it.severity) },
              String(it.severity || 'info')),
            ui.el('span', { class: 'bb-list-title' }, it.title || '')
          ]),
          ui.el('p', { class: 'bb-body', style: 'margin-top:4px' }, it.description || ''),
          (it.evidence || []).length
            ? ui.el('ul', { style: 'margin:6px 0 0 18px' }, (it.evidence || []).map(function (e) {
                return ui.el('li', { class: 'bb-caption' }, String(e));
              }))
            : null
        ]);
      });
    }

    if (r.document_understanding && r.document_understanding.document_overview) {
      section('Document Overview', [
        ui.el('p', { class: 'bb-body' }, r.document_understanding.document_overview)
      ]);
    }
    if ((r.assessments || []).length) {
      section('Professional Assessments', r.assessments.map(function (as) {
        return ui.el('div', { style: 'margin-bottom:8px' }, [
          ui.el('span', { class: 'bb-list-title' }, as.category + ': ' + as.rating),
          ui.el('p', { class: 'bb-body' }, as.rationale || '')
        ]);
      }));
    }
    if (r.executive_summary) {
      section('Executive Summary', [ui.el('p', { class: 'bb-body' }, r.executive_summary)]);
    }
    if ((r.key_insights || []).length) {
      section('Key Insights', r.key_insights.map(function (k, i) {
        return ui.el('p', { class: 'bb-body' }, (i + 1) + '. ' + k);
      }));
    }
    if ((r.user_question_responses || []).length) {
      section('Your Questions', r.user_question_responses.map(function (q) {
        return ui.el('div', { style: 'margin-bottom:10px' }, [
          ui.el('div', { class: 'bb-list-title' }, q.question),
          ui.el('p', { class: 'bb-body' }, q.response),
          ui.el('span', { class: 'bb-caption' }, 'Confidence: ' + q.confidence)
        ]);
      }));
    }
    section('Risks', items(r.risks));
    section('Opportunities', items(r.opportunities));
    section('Ambiguities', items(r.ambiguities));
    section('Contradictions', items(r.contradictions));
    if ((r.strategic_recommendations || []).length) {
      section('Strategic Recommendations', r.strategic_recommendations.map(function (rec, i) {
        return ui.el('p', { class: 'bb-body' }, (i + 1) + '. ' + rec);
      }));
    }
    if ((r.follow_up_questions || []).length) {
      section('Follow-Up Questions', r.follow_up_questions.map(function (q, i) {
        return ui.el('p', { class: 'bb-body' }, (i + 1) + '. ' + q);
      }));
    }

    var sid = BB.state.analysis.sessionId;
    blocks.push(ui.el('div', { class: 'bb-row' }, [
      exportBtn('📊  Smart Excel', function () {
        window.location.href = '/api/smart-analysis/' + sid + '/export/excel';
      }),
      exportBtn('📄  Smart PDF', function () {
        window.location.href = '/api/smart-analysis/' + sid + '/export/pdf';
      })
    ]));
    return blocks;
  }

  function severityClass(severity) {
    var s = String(severity || '').toLowerCase();
    if (s === 'critical' || s === 'high') return 'low';       /* red */
    if (s === 'medium') return 'medium';                       /* amber */
    return 'high';                                             /* green */
  }

  BB.results = {
    render: render, push: push, back: back,
    summarize: summarize, answerSummaryOf: answerSummaryOf, isAnswered: isAnswered,
    confidenceOf: confidenceOf, flatten: flatten, toCsv: toCsv,
    ingestLiveAnswers: ingestLiveAnswers,
    sheetList: sheetList, execSummaryRows: execSummaryRows,
    keyDetailRows: keyDetailRows, statusOf: statusOf,
    /* Mount the full workbook against an arbitrary payload — the admin session
       modal uses this so reviewing a session shows the same sheets the user
       who ran it sees, rather than a second, poorer rendering. */
    buildWorkbook: buildWorkbook,
    visualSourcesOf: visualSourcesOf, visualSourceLabel: visualSourceLabel,
    questionsFedBy: questionsFedBy,
    reset: function () { path = []; activeSheet = null; liveAnswers = {}; }
  };
})(typeof window !== 'undefined' ? window : this);
