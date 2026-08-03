/* Analyze tab: idle -> uploading -> configuring -> analyzing -> done | failed.
   Ports Sources/Features/Analyze/UploadConfigureView.swift.

   Note the deliberate ordering of the configure stage: Start Analysis sits
   directly below Context Guardrails and ABOVE the section list, and stays
   disabled until a question set is confirmed. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var uploadFraction = 0;

  function a() { return BB.state.analysis; }

  function allSectionIds() {
    return ((BB.state.questionHub.config || {}).sections || []).map(function (s) {
      return s.section_id;
    });
  }

  /** The exact /api/analyze body. enabled_sections is ALWAYS explicit. */
  function buildAnalyzePayload(state, uploadId, filename) {
    var an = state.analysis;
    var all = ((state.questionHub.config || {}).sections || []).map(function (s) {
      return s.section_id;
    });
    var enabled = (an.enabledSections && an.enabledSections.length)
      ? an.enabledSections.slice()
      : all;

    var body = {
      upload_id: uploadId,
      pdf_filename: filename,
      enabled_sections: enabled,
      mode: an.mode,
      recheck_empty_windows: !!an.recheckEmptyWindows,
      enable_second_pass: !!an.enableSecondPass,
      enable_deep_rag: !!an.enableDeepRAG,
      /* Opt-in vision pass over drawing/map/photo-heavy pages. ADDITIVE ONLY:
         the standard text analysis runs unchanged either way. */
      enable_visual_analysis: !!an.visualAnalysis,
      pipeline_mode: an.pipelineMode || 'classic'
    };
    var guard = (an.contextGuardrails || '').trim();
    if (guard) body.context_guardrails = guard;
    /* High Power is entitlement-gated server-side (403) - only send it when held. */
    if (an.highPower && state.session.hasPremium) body.high_power = true;
    return body;
  }

  /** WYSIWYG: always store the EXPLICIT checked set - never collapse back to
      null ("all") based on a count that could be stale. */
  function setSectionEnabled(sectionId, on) {
    var current = a().enabledSections ? a().enabledSections.slice() : allSectionIds();
    var index = current.indexOf(sectionId);
    if (on && index < 0) current.push(sectionId);
    if (!on && index >= 0) current.splice(index, 1);
    a().enabledSections = current;
  }

  function isSectionEnabled(sectionId) {
    if (!a().enabledSections) return true;
    return a().enabledSections.indexOf(sectionId) >= 0;
  }

  function canStart() {
    return !!(a().hasPendingDocument && BB.state.questionHub.isConfirmed);
  }

  // ---- Flow ---------------------------------------------------------------

  function chooseFile(file) {
    if (!file) return;
    BB.state.noteFreshUpload(file);
    a().phase = 'uploading';
    uploadFraction = 0.15;
    render();

    BB.engine.upload(file).then(function (result) {
      a().uploadId = result.uploadId;
      a().filename = result.filename;
      a().phase = 'configuring';
      uploadFraction = 1;
      render();
      loadSections();
    }).catch(function (error) {
      a().phase = 'failed';
      a().errorMessage = error.message;
      render();
    });
  }

  function reset() {
    BB.state.reset();
    BB.progress.end();
    render();
  }

  function start() {
    if (!canStart()) return;
    var body = buildAnalyzePayload(BB.state, a().uploadId, a().filename);
    a().phase = 'analyzing';
    a().events = [];
    a().results = null;
    BB.progress.begin();
    render();

    BB.engine.analyze(body).then(function (data) {
      a().sessionId = data.session_id;
      BB.engine.startPolling(data.session_id);
    }).catch(function (error) {
      a().phase = 'failed';
      a().errorMessage = error.message;
      render();
    });
  }

  /** Always refetch on visit / question-set change: a stale section list here
      is exactly how deselections used to leak into analysis. */
  function loadSections() {
    return window.fetch('/api/config/questions')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) return;
        BB.state.questionHub.config = data.config;
        (data.config.sections || []).forEach(function (s) {
          (s.questions || []).forEach(function (q) {
            if (q.enabled === undefined) q.enabled = true;
          });
        });
        a().enabledSections = BB.state.prunedSelection(a().enabledSections, allSectionIds());
        render();
      })
      .catch(function () { /* the configure screen says so below */ });
  }

  // ---- Render -------------------------------------------------------------

  function render() {
    var host = ui.qs('#bb-page-analyze');
    if (!host) return;

    switch (a().phase) {
      case 'idle':        return renderIdle(host);
      case 'uploading':   return renderUploading(host);
      case 'configuring': return renderConfigure(host);
      case 'analyzing':   return BB.progress.render(host);
      case 'done':        return BB.results.render(host);
      case 'failed':      return renderFailed(host);
      default:            return renderIdle(host);
    }
  }

  function renderIdle(host) {
    var input = ui.el('input', { type: 'file', accept: '.pdf', style: 'display:none' });
    input.addEventListener('change', function () {
      if (input.files && input.files[0]) chooseFile(input.files[0]);
    });

    var orb = ui.el('div', {
      class: 'bb-upload-orb', role: 'button', tabindex: '0',
      'aria-label': 'Choose a PDF',
      onclick: function () { input.click(); },
      onkeydown: function (e) { if (e.key === 'Enter' || e.key === ' ') input.click(); }
    }, '＋');

    ['dragover', 'dragenter'].forEach(function (name) {
      orb.addEventListener(name, function (e) {
        e.preventDefault(); orb.classList.add('bb-dragover');
      });
    });
    ['dragleave', 'drop'].forEach(function (name) {
      orb.addEventListener(name, function (e) {
        e.preventDefault(); orb.classList.remove('bb-dragover');
      });
    });
    orb.addEventListener('drop', function (e) {
      var files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length) chooseFile(files[0]);
    });

    ui.fill(host, [
      ui.stageHeader('Analyze', 'Upload a bid specification PDF to begin.'),
      ui.el('div', { class: 'bb-upload-stage' }, [
        orb, input,
        ui.el('div', { class: 'bb-upload-label' }, 'Choose PDF'),
        ui.el('div', { class: 'bb-caption' }, 'Or drag and drop a PDF here.')
      ])
    ]);
  }

  function renderUploading(host) {
    var bar = ui.el('div', { class: 'bb-progressbar' },
      [ui.el('span', { style: 'width:' + Math.round(uploadFraction * 100) + '%' })]);
    ui.fill(host, [
      ui.stageHeader('Uploading', a().filename),
      ui.card(null, [bar, ui.el('div', { class: 'bb-caption', style: 'margin-top:10px' },
        'Sending the document to BidBrief...')])
    ]);
  }

  function renderFailed(host) {
    ui.fill(host, [
      ui.stageHeader('Analysis Problem', a().errorMessage || 'Something went wrong.'),
      ui.el('button', {
        class: 'bb-btn-glow', type: 'button', onclick: reset
      }, 'Start Over')
    ]);
  }

  function renderConfigure(host) {
    var confirmed = BB.state.questionHub.isConfirmed;
    var hint = BB.state.onboardingHint();
    var children = [];

    children.push(ui.el('div', { class: 'bb-row' }, [
      ui.el('button', { class: 'bb-back-chip', type: 'button', onclick: reset },
        '‹  Different file')
    ]));
    children.push(ui.stageHeader('Configure'));

    if (a().needsQuestionChoice) children.push(questionChoiceCard());

    children.push(ui.card('Document', [
      ui.el('div', { class: 'bb-file-chip' }, ['📄  ' + (a().filename || 'document.pdf')])
    ]));

    /* Mode selection is a premium concept (admin or Bonus Features) - plain
       users always run bid_spec and never see BestPrep exists. */
    if (BB.state.session.hasPremium) {
      children.push(ui.card('Analysis Mode', [modePicker()]));
    }

    var guard = ui.el('textarea', {
      rows: '3',
      placeholder: 'e.g. Focus on CIPP lining requirements...'
    });
    guard.value = a().contextGuardrails || '';
    guard.addEventListener('input', function () { a().contextGuardrails = guard.value; });
    children.push(ui.card('Context Guardrails (Optional)', [
      ui.el('div', { class: 'bb-field' }, [guard]),
      ui.el('span', { class: 'bb-caption', style: 'margin-top:8px' },
        'Steer the analysis toward what matters for this document.')
    ]));

    /* Start Analysis sits directly below the guardrails and above the
       question/section display. Blocked until a set is confirmed. */
    var startBtn = ui.el('button', {
      class: 'bb-btn-glow' + (hint === 'startAnalysis' ? ' bb-pulses' : ''),
      type: 'button', onclick: start
    }, '✨  Start Analysis');
    startBtn.disabled = !confirmed;
    children.push(startBtn);

    if (confirmed) children.push(sectionsCard());
    else {
      children.push(ui.hubButton({
        title: 'Choose your questions',
        subtitle: 'Pick or create the set to analyze this document against',
        icon: '📋',
        onClick: function () { BB.shell.go('questions'); }
      }));
    }

    children.push(ui.card('Visual Intelligence', [
      ui.toggleRow({
        title: 'Analyze drawings, maps & images',
        subtitle: 'AI vision deep-processes drawing-heavy pages - plan sheets, site maps, ' +
          'details, photos - on top of the standard analysis. The standard text ' +
          'processing is unchanged; this only adds what the imagery reveals.',
        checked: a().visualAnalysis,
        onChange: function (on) { a().visualAnalysis = on; }
      })
    ]));

    children.push(ui.card('Advanced', [
      ui.toggleRow({
        title: 'Second pass for unanswered questions',
        checked: a().enableSecondPass,
        onChange: function (on) { a().enableSecondPass = on; }
      }),
      ui.toggleRow({
        title: 'Re-check empty windows',
        checked: a().recheckEmptyWindows,
        onChange: function (on) { a().recheckEmptyWindows = on; }
      }),
      ui.toggleRow({
        title: 'Deep RAG (external search)',
        subtitle: 'Search external sources for what the document does not say.',
        checked: a().enableDeepRAG,
        onChange: function (on) { a().enableDeepRAG = on; }
      })
    ]));

    if (BB.state.session.hasPremium) {
      children.push(ui.card('High Power', [
        ui.toggleRow({
          title: 'Run this analysis at high power',
          subtitle: 'Slower and more thorough. Included with your premium features.',
          checked: a().highPower,
          onChange: function (on) { a().highPower = on; }
        })
      ]));
    }

    ui.fill(host, children);
  }

  function modePicker() {
    var modes = [
      { value: 'bid_spec', label: 'Contracts / RFPs / Spec' },
      { value: 'bestprep', label: 'BestPrep / TestPrep' }
    ];
    return ui.el('div', { class: 'bb-segmented' }, modes.map(function (m) {
      return ui.el('button', {
        type: 'button',
        class: a().mode === m.value ? 'bb-active' : '',
        onclick: function () { a().mode = m.value; render(); }
      }, m.label);
    }));
  }

  /** Prompt shown once per fresh upload. Three cases:
      1. A confirmed set exists -> keep it or choose a different one.
      2. Only the pre-loaded DEFAULT set is present -> proceed or create.
      3. Nothing loaded at all -> go choose. */
  function questionChoiceCard() {
    var current = BB.state.questionHub.currentSetSummary();
    var loaded = BB.state.questionHub.loadedSetSummary();

    function goChoose() {
      a().needsQuestionChoice = false;
      BB.state.beginChoosing();
      BB.shell.go('questions');
    }

    if (current) {
      return ui.card('Question Set', [
        ui.el('p', { class: 'bb-body' },
          'Use your current set (' + current.sections + ' sections · ' +
          current.questions + ' questions) for this document, or choose a different one?'),
        ui.el('div', { class: 'bb-row', style: 'margin-top:10px' }, [
          ui.el('button', {
            class: 'bb-btn-ghost bb-success bb-grow', type: 'button',
            onclick: function () { a().needsQuestionChoice = false; render(); }
          }, 'Keep current set'),
          ui.el('button', {
            class: 'bb-btn-ghost bb-grow', type: 'button', onclick: goChoose
          }, 'Create / choose new')
        ])
      ]);
    }

    if (loaded) {
      return ui.card('Question Set', [
        ui.el('p', { class: 'bb-body' },
          'Default questions are loaded (' + loaded.sections + ' sections · ' +
          loaded.questions + ' questions). Proceed with the defaults, or create your own question set?'),
        ui.el('div', { class: 'bb-row', style: 'margin-top:10px' }, [
          ui.el('button', {
            class: 'bb-btn-ghost bb-success bb-grow', type: 'button',
            onclick: function () {
              a().needsQuestionChoice = false;
              BB.questionHub.proceedWithDefaults();
              render();
            }
          }, 'Proceed with defaults'),
          ui.el('button', {
            class: 'bb-btn-ghost bb-grow', type: 'button', onclick: goChoose
          }, 'Create a question set')
        ])
      ]);
    }

    return ui.card('Question Set', [
      ui.el('p', { class: 'bb-body' },
        'Pick or create a question set to analyze this document against.'),
      ui.el('button', {
        class: 'bb-btn-glow', type: 'button', style: 'margin-top:10px',
        onclick: goChoose
      }, 'Choose questions')
    ]);
  }

  function sectionsCard() {
    var sections = (BB.state.questionHub.config || {}).sections || [];
    if (!sections.length) {
      return ui.card('Sections', [
        ui.el('p', { class: 'bb-body' },
          'Could not load the question set - all sections will run.')
      ]);
    }
    var rows = sections.map(function (section) {
      return ui.toggleRow({
        title: section.section_name,
        subtitle: ((section.questions || []).length) + ' questions',
        checked: isSectionEnabled(section.section_id),
        onChange: function (on) { setSectionEnabled(section.section_id, on); }
      });
    });
    rows.push(ui.el('span', { class: 'bb-caption', style: 'margin-top:8px' },
      'Only checked sections are analyzed.'));
    return ui.card('Sections', rows);
  }

  BB.analyze = {
    render: render,
    buildAnalyzePayload: buildAnalyzePayload,
    setSectionEnabled: setSectionEnabled,
    isSectionEnabled: isSectionEnabled,
    canStart: canStart,
    chooseFile: chooseFile,
    start: start,
    reset: reset,
    loadSections: loadSections
  };
})(typeof window !== 'undefined' ? window : this);
