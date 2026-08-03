/* Create / Add Question Set. Ports the iOS GenerateStage + QuestionHubModel.generate.

   THE RULE (2.1.1 / 2.1.2): the Document Context is ALWAYS sent for grounding -
   as the primary `file` when there is no PDF questions-source, else as
   `context_file` alongside it. Never let a questions-source displace it, and
   never make the user tap "use this document" for it to happen. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var DOC_ONLY_INSTRUCTION =
    'Derive the most important document-analysis questions from the attached document.';

  var TEXT_EXTENSIONS = /\.(txt|text|csv|md|markdown|json|rtf)$/i;

  /* Screen state (survives re-renders while the user is on the screen). */
  var draft = {
    userText: '',
    contextFile: null,
    questionsSourceFile: null,
    questionsSourceText: '',
    sourceIntent: '',
    mode: 'replace',
    generating: false,
    generatedOnce: false,
    personas: [],
    documentReading: '',
    suggestions: [],
    selectedSuggestions: {},
    suggesting: false
  };

  function isPdf(file) {
    if (!file) return false;
    return file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');
  }

  /** Files we read locally and fold into the prompt instead of uploading. */
  function isTextSource(file) {
    if (!file) return false;
    if (isPdf(file)) return false;
    if (file.type && file.type.indexOf('text/') === 0) return true;
    return TEXT_EXTENSIONS.test(file.name || '');
  }

  function canGenerate(opts) {
    opts = opts || draft;
    return !!((opts.userText || '').trim() || opts.contextFile || opts.questionsSourceFile);
  }

  function buildGeneratePayload(opts) {
    opts = opts || {};
    var fields = {};
    var files = {};

    var text = (opts.userText || '').trim();
    var sourceText = (opts.questionsSourceText || '').trim();
    if (sourceText) {
      var label = (opts.questionsSourceFile && opts.questionsSourceFile.name) || 'attached material';
      text = text
        ? text + '\n\n--- Questions source (' + label + ') ---\n' + sourceText
        : sourceText;
    }

    var contextFile = opts.contextFile || null;
    var sourcePdf = isPdf(opts.questionsSourceFile) ? opts.questionsSourceFile : null;

    if (!text && (contextFile || sourcePdf)) text = DOC_ONLY_INSTRUCTION;
    fields.user_input = text;

    var intent = (opts.sourceIntent || '').trim();
    if (intent) fields.source_intent = intent;

    if (sourcePdf) {
      files.file = sourcePdf;
      fields.source_kind = 'questions_source';
      if (contextFile) files.context_file = contextFile;   /* ALWAYS grounded */
    } else if (contextFile) {
      files.file = contextFile;
      fields.source_kind = 'context';
    }

    /* NOTE: no high_power. Question generation is high-power for every user
       server-side; sending the flag would hit the entitlement gate (403). */
    return {
      kind: (files.file || files.context_file) ? 'multipart' : 'json',
      fields: fields,
      files: files
    };
  }

  function postGenerate(payload) {
    if (payload.kind === 'json') {
      return window.fetch('/api/config/questions/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload.fields)
      }).then(readJson);
    }
    var form = new window.FormData();
    Object.keys(payload.fields).forEach(function (k) { form.append(k, payload.fields[k]); });
    Object.keys(payload.files).forEach(function (k) { form.append(k, payload.files[k]); });
    return window.fetch('/api/config/questions/generate', { method: 'POST', body: form })
      .then(readJson);
  }

  function readJson(resp) {
    return resp.json().then(function (data) {
      if (!resp.ok || !data.success) throw new Error(data.error || ('HTTP ' + resp.status));
      return data;
    });
  }

  /** Merge accepted suggestions into the live config without duplicating. */
  function mergeSuggestions(config, suggestions, selectedIds) {
    config.sections = config.sections || [];
    (suggestions || []).forEach(function (suggested) {
      if (selectedIds && selectedIds.indexOf(suggested.section_id) < 0) return;
      var existing = config.sections.filter(function (s) {
        return s.section_id === suggested.section_id;
      })[0];
      if (existing) {
        existing.questions = existing.questions || [];
        (suggested.questions || []).forEach(function (q) {
          var already = existing.questions.some(function (eq) { return eq.id === q.id; });
          if (!already) existing.questions.push(q);
        });
      } else {
        var copy = {};
        Object.keys(suggested).forEach(function (k) { copy[k] = suggested[k]; });
        copy.questions = (suggested.questions || []).slice();
        config.sections.push(copy);
      }
    });
    return config;
  }

  // ---- Screen -------------------------------------------------------------

  function reset() {
    draft.userText = '';
    draft.contextFile = null;
    draft.questionsSourceFile = null;
    draft.questionsSourceText = '';
    draft.sourceIntent = '';
    draft.mode = 'replace';
    draft.generating = false;
    draft.generatedOnce = false;
    draft.personas = [];
    draft.documentReading = '';
    draft.suggestions = [];
    draft.selectedSuggestions = {};
    draft.suggesting = false;
  }

  /** The document already uploaded in the Analyzer IS the document to be
      analyzed. Auto-adopt it so generated questions are ALWAYS grounded in it -
      without this the common flow sends no document at all (2.1.2). */
  function adoptAnalyzerDocument() {
    if (!draft.contextFile && BB.state.analysis.file) {
      draft.contextFile = BB.state.analysis.file;
    }
  }

  function render(host, onBack) {
    adoptAnalyzerDocument();
    var children = [];

    children.push(ui.el('div', { class: 'bb-row' }, [
      ui.el('button', { class: 'bb-back-chip', type: 'button', onclick: onBack }, '‹  Back')
    ]));
    children.push(ui.stageHeader('Create / Add Question Set',
      'Paste any questions you already have, tell BidBrief what to ask, or both - then generate. ' +
      'Everything you paste is kept word-for-word; anything you describe becomes tailored ' +
      'document-analysis questions.'));

    /* 1. Your questions & instructions */
    var textarea = ui.el('textarea', {
      rows: '6',
      placeholder: 'Paste your questions here, and/or tell BidBrief what to ask - e.g. ' +
        '"Cover bonds, insurance, schedule, and warranty terms for a municipal sewer-lining bid."'
    });
    textarea.value = draft.userText;
    textarea.addEventListener('input', function () { draft.userText = textarea.value; });
    children.push(ui.card('Your Questions & Instructions', [
      ui.el('div', { class: 'bb-field' }, [textarea])
    ]));

    /* 2. Questions source */
    children.push(ui.card('Questions Source (Optional)', questionsSourceBody(host, onBack)));

    /* 3. Document context (auto-adopted from the Analyzer) */
    children.push(ui.card('Document Context', documentContextBody(host, onBack)));

    /* 4. Mode */
    children.push(ui.card('Mode', [
      ui.el('div', { class: 'bb-segmented' }, [
        modeButton('replace', 'Replace', host, onBack),
        modeButton('merge', 'Merge', host, onBack)
      ]),
      ui.el('span', { class: 'bb-caption', style: 'margin-top:8px' }, draft.mode === 'replace'
        ? 'Your current set is auto-saved to Libraries before it is replaced - nothing is lost.'
        : 'New sections are appended; the current set stays untouched.')
    ]));

    /* 5. Source intent - inline, never a window.prompt */
    if (draft.contextFile || draft.questionsSourceFile) {
      var intent = ui.el('input', {
        type: 'text',
        placeholder: 'e.g. "Derive the questions from this inspection standard"'
      });
      intent.value = draft.sourceIntent;
      intent.addEventListener('input', function () { draft.sourceIntent = intent.value; });
      children.push(ui.card("What's this file for? (Recommended)", [
        ui.el('div', { class: 'bb-field' }, [intent]),
        ui.el('span', { class: 'bb-caption', style: 'margin-top:8px' },
          "Tells BidBrief's expert builder how to use the file when designing your question set.")
      ]));
    }

    /* 6. Generate */
    var generateBtn = ui.el('button', {
      class: 'bb-btn-glow', type: 'button',
      onclick: function () { generate(host, onBack); }
    }, draft.generating
      ? ((draft.contextFile || draft.questionsSourceFile)
          ? 'Reading your material & generating...'
          : 'BidBrief is generating...')
      : '✨  Generate Question Set');
    generateBtn.disabled = !canGenerate() || draft.generating;
    children.push(generateBtn);

    /* 7. The bespoke expert panel that authored the set */
    if (draft.generatedOnce && draft.personas.length) {
      var panel = [];
      if (draft.documentReading) {
        panel.push(ui.el('p', { class: 'bb-caption-lit', style: 'margin-bottom:8px' },
          draft.documentReading));
      }
      draft.personas.forEach(function (p) {
        panel.push(ui.el('div', { class: 'bb-persona' }, [
          ui.el('span', { class: 'bb-persona-name' }, p.name || ''),
          p.expertise ? ui.el('span', { class: 'bb-persona-expertise' }, p.expertise) : null
        ]));
      });
      children.push(ui.card('Built By Your Expert Panel', panel));
    }

    /* 8. Suggest more */
    if (draft.generatedOnce && !draft.suggestions.length && !draft.suggesting) {
      children.push(ui.card(null, [
        ui.el('p', { class: 'bb-body bb-center' },
          'Want more? BidBrief can suggest up to 3 complementary sections that ' +
          "don't repeat anything you have."),
        ui.el('div', { class: 'bb-row', style: 'margin-top:12px' }, [
          ui.el('button', {
            class: 'bb-btn-ghost bb-grow', type: 'button',
            onclick: function () { suggestAdditional(host, onBack); }
          }, 'Suggest more questions'),
          ui.el('button', {
            class: 'bb-btn-ghost bb-success bb-grow', type: 'button', onclick: onBack
          }, 'Done - view the set')
        ])
      ]));
    }

    if (draft.suggesting) {
      children.push(ui.card(null, [
        ui.el('div', { class: 'bb-row' }, [
          ui.el('span', { class: 'bb-spinner' }),
          ui.el('span', { class: 'bb-body' }, 'Finding complementary questions...')
        ])
      ]));
    }

    if (draft.suggestions.length) children.push(suggestionsCard(host, onBack));

    ui.fill(host, children);
  }

  function modeButton(value, label, host, onBack) {
    return ui.el('button', {
      type: 'button',
      class: draft.mode === value ? 'bb-active' : '',
      onclick: function () { draft.mode = value; render(host, onBack); }
    }, label);
  }

  function questionsSourceBody(host, onBack) {
    if (draft.questionsSourceFile) {
      return [
        ui.el('div', { class: 'bb-file-chip' }, [
          ui.el('span', {}, '📑  ' + draft.questionsSourceFile.name),
          ui.el('button', {
            class: 'bb-x', type: 'button', 'aria-label': 'Remove',
            onclick: function () {
              draft.questionsSourceFile = null;
              draft.questionsSourceText = '';
              render(host, onBack);
            }
          }, '✕')
        ]),
        ui.el('span', { class: 'bb-caption-lit', style: 'margin-top:8px' },
          'BidBrief will work out what this is and derive the questions from it.')
      ];
    }

    var input = ui.el('input', {
      type: 'file', accept: '.pdf,.txt,.text,.csv,.md,.markdown', style: 'display:none'
    });
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) return;
      draft.questionsSourceFile = file;
      draft.questionsSourceText = '';
      if (isTextSource(file)) {
        var reader = new window.FileReader();
        reader.onload = function () {
          draft.questionsSourceText = String(reader.result || '');
          render(host, onBack);
        };
        reader.readAsText(file);
      } else {
        render(host, onBack);
      }
    });

    return [
      input,
      ui.el('button', {
        class: 'bb-btn-ghost', type: 'button', onclick: function () { input.click(); }
      }, '⬆  Upload your questions or their basis'),
      ui.el('span', { class: 'bb-caption', style: 'margin-top:8px' },
        'Upload a list of questions - or an email thread, meeting notes, a standard, a syllabus, ' +
        'or any document. BidBrief works out what to ask and derives the questions.')
    ];
  }

  function documentContextBody(host, onBack) {
    if (draft.contextFile) {
      return [
        ui.el('div', { class: 'bb-file-chip' }, [
          ui.el('span', {}, '📄  ' + draft.contextFile.name),
          ui.el('button', {
            class: 'bb-x', type: 'button', 'aria-label': 'Remove',
            onclick: function () { draft.contextFile = null; render(host, onBack); }
          }, '✕')
        ]),
        ui.el('span', { class: 'bb-caption-lit', style: 'margin-top:8px' },
          'BidBrief will ground the questions in this document - and it is loaded into the ' +
          'Analyzer for you, ready to analyze.')
      ];
    }

    var input = ui.el('input', { type: 'file', accept: '.pdf', style: 'display:none' });
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) return;
      draft.contextFile = file;
      /* A document attached for context is also the Analyzer's upload. */
      BB.analyze.chooseFile(file);
      render(host, onBack);
    });

    return [
      input,
      ui.el('button', {
        class: 'bb-btn-ghost', type: 'button', onclick: function () { input.click(); }
      }, '📄  Attach the bid document (PDF)'),
      ui.el('span', { class: 'bb-caption', style: 'margin-top:8px' },
        "Grounds every question in the document's actual contents - and doubles as your " +
        'Analyzer upload.')
    ];
  }

  // ---- Actions ------------------------------------------------------------

  function generate(host, onBack) {
    if (!canGenerate() || draft.generating) return;
    draft.generating = true;
    render(host, onBack);

    /* Replace mode snapshots the current set first - nothing is ever lost.
       autoBackup skips the save when that exact set is already in Libraries,
       so iterating on generation no longer stacks up copies of the same set. */
    if (draft.mode === 'replace' && BB.state.questionHub.config) {
      BB.libraries.autoBackup(BB.state.questionHub.config, 'Backup before generating');
    }

    postGenerate(buildGeneratePayload(draft)).then(function (data) {
      var config = data.config;
      if (draft.mode === 'merge' && BB.state.questionHub.config) {
        var merged = BB.state.questionHub.config;
        mergeSuggestions(merged, config.sections || [], null);
        BB.questionHub.apply(merged);
      } else {
        BB.questionHub.apply(config);
      }
      draft.personas = data.generation_personas || [];
      draft.documentReading = data.document_reading || '';
      draft.generatedOnce = true;
      draft.generating = false;
      return BB.questionHub.save().then(function () {
        var summary = BB.state.questionHub.loadedSetSummary();
        ui.banner('info', 'Imported ' + summary.questions + ' questions across ' +
          summary.sections + ' sections.');
        render(host, onBack);
      });
    }).catch(function (error) {
      draft.generating = false;
      ui.banner('error', 'Generation failed: ' + error.message);
      render(host, onBack);
    });
  }

  function suggestAdditional(host, onBack) {
    draft.suggesting = true;
    render(host, onBack);

    window.fetch('/api/config/questions/generate-additional', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_input: draft.userText || '',
        existing_sections: (BB.state.questionHub.config || {}).sections || []
      })
    }).then(readJson).then(function (data) {
      draft.suggestions = data.additional_sections || [];
      draft.selectedSuggestions = {};
      draft.suggestions.forEach(function (s) { draft.selectedSuggestions[s.section_id] = true; });
      draft.suggesting = false;
      if (!draft.suggestions.length) ui.banner('info', 'No additional questions were suggested.');
      render(host, onBack);
    }).catch(function (error) {
      draft.suggesting = false;
      ui.banner('error', 'Could not suggest more: ' + error.message);
      render(host, onBack);
    });
  }

  function suggestionsCard(host, onBack) {
    var children = [];
    draft.suggestions.forEach(function (section) {
      children.push(ui.toggleRow({
        title: section.section_name,
        subtitle: (section.questions || []).length + ' questions',
        checked: !!draft.selectedSuggestions[section.section_id],
        onChange: function (on) { draft.selectedSuggestions[section.section_id] = on; }
      }));
      if (section.section_summary) {
        children.push(ui.el('div', { class: 'bb-list-why' }, section.section_summary));
      }
      (section.questions || []).slice(0, 4).forEach(function (q) {
        children.push(ui.el('div', { class: 'bb-caption' }, '• ' + (q.text || '')));
      });
      if ((section.questions || []).length > 4) {
        children.push(ui.el('div', { class: 'bb-caption' },
          '...and ' + ((section.questions || []).length - 4) + ' more'));
      }
      children.push(ui.el('hr', { class: 'bb-divider' }));
    });

    children.push(ui.el('div', { class: 'bb-row' }, [
      ui.el('button', {
        class: 'bb-btn-ghost bb-success bb-grow', type: 'button',
        onclick: function () { acceptSuggestions(host, onBack); }
      }, 'Add Selected'),
      ui.el('button', {
        class: 'bb-btn-ghost bb-grow', type: 'button',
        onclick: function () { draft.suggestions = []; onBack(); }
      }, 'No thanks')
    ]));

    return ui.card('Suggested Additions', children);
  }

  function acceptSuggestions(host, onBack) {
    var ids = Object.keys(draft.selectedSuggestions).filter(function (id) {
      return draft.selectedSuggestions[id];
    });
    if (!ids.length) { ui.banner('error', 'Select at least one section.'); return; }

    var config = BB.state.questionHub.config || { sections: [] };
    mergeSuggestions(config, draft.suggestions, ids);
    BB.questionHub.apply(config);
    draft.suggestions = [];
    BB.questionHub.save().then(function () {
      ui.banner('info', 'Questions added.');
      onBack();
    });
  }

  BB.qgen = {
    render: render, reset: reset,
    buildGeneratePayload: buildGeneratePayload,
    mergeSuggestions: mergeSuggestions,
    canGenerate: canGenerate,
    isTextSource: isTextSource,
    draft: draft
  };
})(typeof window !== 'undefined' ? window : this);
