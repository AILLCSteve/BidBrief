/* Results - staged like the iOS ResultsView: an overview of glowing entry
   points, each fading into a focused layer with a back chip. The full-width
   Table view is the one web-only stage (a desktop screen earns it).
   Ports Sources/Features/Analyze/ResultsView.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var path = [];                 /* stage stack; empty = overview */
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

  /** Every question with its section name - the table view and CSV. */
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

  function csvCell(value) {
    return '"' + String(value == null ? '' : value).replace(/"/g, '""') + '"';
  }

  function toCsv(payload) {
    var lines = ['Section,#,Question,Answer,Answer Summary,PDF Pages'];
    ((payload && payload.sections) || []).forEach(function (sec) {
      (sec.questions || []).forEach(function (q, index) {
        lines.push([
          csvCell(sec.section_name),
          csvCell(index + 1),
          csvCell(q.question),
          csvCell(isAnswered(q) ? q.answer : 'Not found'),
          csvCell(answerSummaryOf(q) || ''),
          csvCell((q.page_citations || []).join(';'))
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

  // ---- Navigation ---------------------------------------------------------

  function push(stage, arg) { path.push({ stage: stage, arg: arg }); render(); }
  function back() { path.pop(); render(); }
  function top() { return path.length ? path[path.length - 1] : null; }

  function render(host) {
    host = host || ui.qs('#bb-page-analyze');
    if (!host) return;
    var here = top();
    if (!here) return renderOverview(host);
    switch (here.stage) {
      case 'sections':      return renderSections(host);
      case 'sectionDetail': return renderSectionDetail(host, here.arg);
      case 'keyDetails':    return renderKeyDetails(host);
      case 'intelligence':  return renderIntelligence(host);
      case 'improve':       return renderImprove(host);
      case 'actions':       return renderActions(host);
      case 'table':         return renderTable(host);
      default:              return renderOverview(host);
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

  // ---- Overview -----------------------------------------------------------

  function renderOverview(host) {
    var payload = results();
    var s = summarize(payload);
    var children = [];

    children.push(ui.el('div', { class: 'bb-center' }, [
      ui.el('span', { class: 'bb-eyebrow' }, 'Results'),
      ui.el('h1', { style: 'font-size:24px;font-weight:700;text-shadow:0 0 14px rgba(94,134,208,.55)' },
        payload.document_name || BB.state.analysis.filename || 'Results')
    ]));

    if (BB.state.analysis.isPartial) {
      children.push(ui.card(null, [
        ui.el('p', { class: 'bb-body' },
          'These are partial results - the analysis was stopped before it finished.')
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

    var hubs = [];
    hubs.push(ui.hubButton({
      title: 'Sections', icon: '🗂',
      subtitle: (payload.sections || []).length + ' sections of answers',
      onClick: function () { push('sections'); }
    }));
    if (hasKeyDetails(payload)) {
      hubs.push(ui.hubButton({
        title: 'Key Details', icon: '⭐',
        subtitle: "The document's essential facts",
        onClick: function () { push('keyDetails'); }
      }));
    }
    if (dynamicTables(payload).length) {
      hubs.push(ui.hubButton({
        title: 'Document Intelligence', icon: '🧠',
        subtitle: dynamicTables(payload).length + ' dynamic tables built for this document',
        onClick: function () { push('intelligence'); }
      }));
    }
    if (s.unanswered.length) {
      hubs.push(ui.hubButton({
        title: 'Improve Results', icon: '🪄',
        subtitle: s.unanswered.length + ' unanswered - run another pass',
        onClick: function () { push('improve'); }
      }));
    }
    hubs.push(ui.hubButton({
      title: 'Table View', icon: '▦',
      subtitle: 'Every question and answer in one table',
      onClick: function () { push('table'); }
    }));
    hubs.push(ui.hubButton({
      title: 'Exports & Analysis', icon: '⬆',
      subtitle: 'Excel dashboard, CSV, HTML, Smart Analysis',
      onClick: function () { push('actions'); }
    }));
    children.push(ui.el('div', { class: 'bb-stack' }, hubs));

    children.push(ui.el('button', {
      class: 'bb-btn-ghost bb-danger', type: 'button',
      onclick: function () { path = []; BB.analyze.reset(); }
    }, 'New Analysis'));

    ui.fill(host, children);
  }

  function stat(label, value) {
    return ui.el('div', { class: 'bb-stat' }, [
      ui.el('div', { class: 'bb-stat-value' }, value),
      ui.el('div', { class: 'bb-stat-label' }, label)
    ]);
  }

  function hasKeyDetails(payload) {
    var kr = payload.key_requirements || BB.state.analysis.keyRequirements;
    return !!((kr && Object.keys(kr).length) || (payload.footnotes || []).length);
  }

  function dynamicTables(payload) {
    return payload.dynamic_tables || payload.dynamicTables || [];
  }

  // ---- Sections -----------------------------------------------------------

  function renderSections(host) {
    var payload = results();
    var rows = (payload.sections || []).map(function (section) {
      var answered = (section.questions || []).filter(isAnswered).length;
      return ui.el('button', {
        class: 'bb-list-row', type: 'button',
        onclick: function () { push('sectionDetail', section.section_id); }
      }, [
        ui.el('span', {}, [
          ui.el('span', { class: 'bb-list-title' }, section.section_name),
          ui.el('span', { class: 'bb-list-sub', style: 'display:block' },
            answered + '/' + (section.questions || []).length + ' answered')
        ]),
        ui.el('span', { class: 'bb-list-chevron' }, '›')
      ]);
    });
    ui.fill(host, chrome('Sections').concat([ui.card(null, rows)]));
  }

  function renderSectionDetail(host, sectionId) {
    var payload = results();
    var section = (payload.sections || []).filter(function (s) {
      return s.section_id === sectionId;
    })[0];
    if (!section) return renderSections(host);

    var answered = (section.questions || []).filter(isAnswered).length;
    var cards = (section.questions || []).map(function (q) {
      return ui.card(null, [questionBlock(q)]);
    });
    ui.fill(host, chrome(section.section_name,
      answered + ' of ' + (section.questions || []).length + ' answered').concat(cards));
  }

  /** One question: text, answer, the L6.5 summary, then confidence + pages. */
  function questionBlock(q) {
    var parts = [ui.el('div', { class: 'bb-question-text' }, q.question || q.text || '')];

    if (isAnswered(q)) {
      var answer = ui.el('div', { class: 'bb-question-answer bb-clamped' }, q.answer);
      answer.addEventListener('click', function () {
        answer.classList.toggle('bb-clamped');
      });
      parts.push(answer);

      var summary = answerSummaryOf(q);
      if (summary) {
        parts.push(ui.el('div', { class: 'bb-answer-summary' }, [
          ui.el('span', { class: 'bb-answer-summary-label' }, 'Answer Summary'),
          ui.el('span', {}, summary)
        ]));
      }

      var meta = [ui.el('span', { class: 'bb-pill bb-pill-' + confidenceOf(q) }, confidenceOf(q))];
      if ((q.page_citations || []).length) {
        meta.push(ui.el('span', { class: 'bb-pages' }, 'p. ' + q.page_citations.join(', ')));
      }
      parts.push(ui.el('div', { class: 'bb-row' }, meta));

      if (q.footnote) {
        parts.push(ui.el('div', { class: 'bb-caption' }, q.footnote));
      }
    } else {
      parts.push(ui.el('div', { class: 'bb-question-missing' }, 'Not found in document'));
    }

    return ui.el('div', { class: 'bb-question' }, parts);
  }

  // ---- Key details --------------------------------------------------------

  function renderKeyDetails(host) {
    var payload = results();
    var kr = payload.key_requirements || BB.state.analysis.keyRequirements || {};
    var children = chrome('Key Details');

    var factRows = Object.keys(kr).sort().map(function (key) {
      var value = kr[key];
      if (value && typeof value === 'object') value = JSON.stringify(value);
      return ui.el('div', { style: 'margin-bottom:10px' }, [
        ui.el('div', { class: 'bb-caption' },
          key.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); })),
        ui.el('div', {}, String(value == null ? '' : value))
      ]);
    });
    if (factRows.length) children.push(ui.card('Document Facts', factRows));

    var footnotes = payload.footnotes || [];
    if (footnotes.length) {
      children.push(ui.card('Footnotes', footnotes.map(function (f) {
        return ui.el('div', { class: 'bb-body', style: 'margin-bottom:6px' }, String(f));
      })));
    }
    ui.fill(host, children);
  }

  // ---- Document intelligence ---------------------------------------------

  function renderIntelligence(host) {
    var payload = results();
    var children = chrome('Document Intelligence',
      'Tables the AI chose for this specific document');

    if (payload.intelligence_focus) {
      children.push(ui.el('p', { class: 'bb-caption-lit bb-center' }, payload.intelligence_focus));
    }

    dynamicTables(payload).forEach(function (table) {
      var columns = table.columns || (table.rows && table.rows[0] ? Object.keys(table.rows[0]) : []);
      children.push(ui.card(table.title || table.name || 'Table', [
        table.description ? ui.el('p', { class: 'bb-body', style: 'margin-bottom:10px' }, table.description) : null,
        ui.el('div', { class: 'bb-table-wrap' }, [
          ui.el('table', { class: 'bb-table' }, [
            ui.el('thead', {}, [ui.el('tr', {}, columns.map(function (c) {
              return ui.el('th', {}, String(c));
            }))]),
            ui.el('tbody', {}, (table.rows || []).map(function (row) {
              return ui.el('tr', {}, columns.map(function (c) {
                return ui.el('td', {}, String(row[c] == null ? '' : row[c]));
              }));
            }))
          ])
        ])
      ]));
    });
    ui.fill(host, children);
  }

  // ---- Improve ------------------------------------------------------------

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

  // ---- Exports & Smart Analysis ------------------------------------------

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
      onclick: function () { path = []; BB.analyze.reset(); }
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
        '<td>' + ui.escapeHtml((q.page_citations || []).join(', ')) + '</td></tr>';
    }).join('');
    var html = '<!DOCTYPE html><html><head><meta charset="UTF-8">' +
      '<title>BidBrief Analysis Report</title><style>' +
      'body{font-family:Calibri,Arial,sans-serif;font-size:12pt;margin:40px;}' +
      'h1{color:#104090;border-bottom:4px solid #5E86D0;padding-bottom:12px;}' +
      'table{width:100%;border-collapse:collapse;margin-top:20px;}' +
      'th{background:#104090;color:#fff;padding:10px;text-align:left;}' +
      'td{padding:9px;border:1px solid #ddd;vertical-align:top;}' +
      '</style></head><body><h1>' + ui.escapeHtml(payload.document_name || 'Document Analysis') +
      '</h1><p>Generated: ' + new Date().toLocaleString() + '</p><table><thead><tr>' +
      '<th>Section</th><th>Question</th><th>Answer</th><th>Answer Summary</th><th>PDF Pages</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></body></html>';
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

  // ---- Table view (web-only) ---------------------------------------------

  function renderTable(host) {
    var rows = flatten(results());
    var body = ui.el('tbody', {}, rows.map(function (q) {
      return ui.el('tr', {}, [
        ui.el('td', {}, q.section_name || ''),
        ui.el('td', { class: 'bb-td-strong' }, q.question || ''),
        ui.el('td', isAnswered(q) ? {} : { class: 'bb-td-pending' },
          isAnswered(q) ? q.answer : 'Not found in document'),
        ui.el('td', {}, answerSummaryOf(q) || ''),
        ui.el('td', {}, (q.page_citations || []).join(', ')),
        ui.el('td', {}, [
          ui.el('span', { class: 'bb-pill bb-pill-' + confidenceOf(q) }, confidenceOf(q))
        ])
      ]);
    }));

    ui.fill(host, chrome('Table View', rows.length + ' questions').concat([
      ui.card(null, [
        ui.el('div', { class: 'bb-table-wrap' }, [
          ui.el('table', { class: 'bb-table' }, [
            ui.el('thead', {}, [ui.el('tr', {},
              ['Section', 'Question', 'Answer', 'Answer Summary', 'Pages', 'Confidence']
                .map(function (h) { return ui.el('th', {}, h); }))]),
            body
          ])
        ])
      ])
    ]));
  }

  BB.results = {
    render: render, push: push, back: back,
    summarize: summarize, answerSummaryOf: answerSummaryOf, isAnswered: isAnswered,
    confidenceOf: confidenceOf, flatten: flatten, toCsv: toCsv,
    ingestLiveAnswers: ingestLiveAnswers,
    reset: function () { path = []; liveAnswers = {}; }
  };
})(typeof window !== 'undefined' ? window : this);
