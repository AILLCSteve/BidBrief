/* Question Hub - staged navigation over the orb. Opens on a bare header with
   the create/add entry point glowing above everything else; every deeper level
   fades in with a back chip.
   Ports Sources/Features/QuestionHub/QuestionHubView.swift + QuestionHubModel. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var path = [];                 /* stage stack; empty = menu */
  var showCurrent = false;       /* the "Current Question Set" disclosure */
  var loading = false;

  function config() { return BB.state.questionHub.config; }

  function sectionById(id) {
    return ((config() || {}).sections || []).filter(function (s) {
      return s.section_id === id;
    })[0];
  }

  function uid(prefix) {
    return prefix + '_' + Date.now().toString(36) + '_' +
      Math.floor(Math.random() * 1e6).toString(36);
  }

  function markDirty() {
    BB.state.questionHub.isDirty = true;
    BB.state.notify();
  }

  // ---- Mutators -----------------------------------------------------------

  /** The PUT body. Question config is a LOSSLESS round-tripper: unknown keys
      (required / expected_type / section_description / section_summary) drive
      backend expert generation, so the sections go back untouched. */
  function buildSaveBody(cfg) {
    return { sections: (cfg && cfg.sections) || [] };
  }

  function toggleQuestion(sectionId, questionId) {
    var sec = sectionById(sectionId); if (!sec) return;
    (sec.questions || []).forEach(function (q) {
      if (q.id === questionId) q.enabled = !q.enabled;
    });
    markDirty();
  }

  function setSectionEnabled(sectionId, enabled) {
    var sec = sectionById(sectionId); if (!sec) return;
    (sec.questions || []).forEach(function (q) { q.enabled = !!enabled; });
    markDirty();
  }

  function addSection(name) {
    var clean = (name || '').trim(); if (!clean) return;
    var cfg = config();
    if (!cfg) { cfg = { sections: [] }; BB.state.questionHub.config = cfg; }
    cfg.sections = cfg.sections || [];
    cfg.sections.push({ section_id: uid('sec'), section_name: clean, questions: [] });
    BB.state.setConfirmed(true);   /* a genuine confirm path */
    markDirty();
  }

  function addQuestion(sectionId, text) {
    var clean = (text || '').trim(); if (!clean) return;
    var sec = sectionById(sectionId); if (!sec) return;
    sec.questions = sec.questions || [];
    sec.questions.push({ id: uid('q'), text: clean, enabled: true });
    markDirty();
  }

  function updateQuestion(sectionId, questionId, text, enabled) {
    var sec = sectionById(sectionId); if (!sec) return;
    (sec.questions || []).forEach(function (q) {
      if (q.id !== questionId) return;
      q.text = text;
      q.enabled = !!enabled;
    });
    markDirty();
  }

  function renameSection(sectionId, name) {
    var clean = (name || '').trim(); if (!clean) return;
    var sec = sectionById(sectionId);
    if (sec) { sec.section_name = clean; markDirty(); }
  }

  function deleteSection(sectionId) {
    var cfg = config(); if (!cfg) return;
    cfg.sections = (cfg.sections || []).filter(function (s) {
      return s.section_id !== sectionId;
    });
    markDirty();
  }

  /** Replace the whole set - generate, library apply, upload. Confirms. */
  function apply(cfg) {
    (cfg.sections || []).forEach(function (s) {
      s.questions = s.questions || [];
      s.questions.forEach(function (q) { if (q.enabled === undefined) q.enabled = true; });
    });
    BB.state.questionHub.config = cfg;
    BB.state.setConfirmed(true);
  }

  /** The backend always physically holds a set; adopting it is the user's call. */
  function proceedWithDefaults() { BB.state.setConfirmed(true); }

  // ---- Network ------------------------------------------------------------

  /** Loading is NOT confirming: the backend always ships a set, but the user
      has to choose it before analysis is unblocked. */
  function load() {
    loading = true;
    return window.fetch('/api/config/questions')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        loading = false;
        if (!data || !data.success) throw new Error(data && data.error);
        (data.config.sections || []).forEach(function (s) {
          (s.questions || []).forEach(function (q) {
            if (q.enabled === undefined) q.enabled = true;
          });
        });
        BB.state.questionHub.config = data.config;
        BB.state.notify();
        if (BB.state.navigation.selectedTab === 'questions') render();
      })
      .catch(function () {
        loading = false;
        if (BB.state.navigation.selectedTab === 'questions') render();
      });
  }

  function save() {
    return window.fetch('/api/config/questions', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildSaveBody(config()))
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) throw new Error((data && data.error) || 'Save failed');
        BB.state.questionHub.isDirty = false;
        BB.state.notify();
        return data;
      })
      .catch(function (error) {
        ui.banner('error', 'Could not save: ' + error.message);
        throw error;
      });
  }

  // ---- Navigation ---------------------------------------------------------

  function push(stage, arg) { path.push({ stage: stage, arg: arg }); render(); }
  function back() { path.pop(); render(); }
  function top() { return path.length ? path[path.length - 1] : null; }

  function render() {
    var host = ui.qs('#bb-page-questions');
    if (!host) return;

    if (!config()) {
      if (loading) {
        return ui.fill(host, [ui.el('div', { class: 'bb-row bb-center' }, [
          ui.el('span', { class: 'bb-spinner' }),
          ui.el('span', { class: 'bb-body' }, 'Loading question set...')
        ])]);
      }
      return ui.fill(host, [
        ui.stageHeader("Couldn't Load Questions", 'Check your connection and try again.'),
        ui.el('button', { class: 'bb-btn-ghost', type: 'button', onclick: load }, 'Retry')
      ]);
    }

    var here = top();
    if (!here) return renderMenu(host);
    switch (here.stage) {
      case 'generate':      return BB.qgen.render(host, function () { back(); });
      case 'libraries':     return renderLibraries(host);
      case 'sections':      return renderSections(host);
      case 'sectionDetail': return renderSectionDetail(host, here.arg);
      case 'allQuestions':  return renderAllQuestions(host);
      case 'questionEdit':  return renderQuestionEdit(host, here.arg);
      default:              return renderMenu(host);
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

  /** The Save pill, shown whenever the set has unsaved edits. */
  function saveBar() {
    if (!BB.state.questionHub.isDirty) return null;
    return ui.el('div', { class: 'bb-bottom-action' }, [
      ui.el('button', {
        class: 'bb-btn-glow', type: 'button',
        onclick: function () {
          save().then(function () { ui.banner('info', 'Question set saved.'); render(); });
        }
      }, '☁  Save Question Set')
    ]);
  }

  // ---- Menu ---------------------------------------------------------------

  function renderMenu(host) {
    var current = BB.state.questionHub.currentSetSummary();
    var subtitle = current
      ? (current.sections + ' sections · ' + current.questions + ' questions')
      : 'No set currently loaded';

    var children = [
      ui.stageHeader('Question Hub',
        'Start here: build the set of questions to analyze your document against.')
    ];

    /* The natural first step - enlarged and glowing above all else. */
    children.push(ui.hubButton({
      title: 'Create / Add Question Set',
      subtitle: 'Paste questions, describe what to ask, or upload - BidBrief builds the set',
      icon: '✨', primary: true,
      onClick: function () { BB.qgen.reset(); push('generate'); }
    }));

    children.push(ui.hubButton({
      title: 'Libraries',
      subtitle: 'Choose or save a question set',
      icon: '📚',
      onClick: function () { push('libraries'); }
    }));

    var disclosure = [ui.hubButton({
      title: 'Current Question Set',
      subtitle: subtitle,
      icon: '📋',
      onClick: function () { showCurrent = !showCurrent; render(); }
    })];

    if (showCurrent) {
      if (BB.state.questionHub.isConfirmed) {
        disclosure.push(ui.hubButton({
          title: 'Sections',
          subtitle: 'Browse, add, and switch whole sections',
          icon: '🗂',
          onClick: function () { push('sections'); }
        }));
        disclosure.push(ui.hubButton({
          title: 'Questions',
          subtitle: 'Every question - view, edit, toggle',
          icon: '📝',
          onClick: function () { push('allQuestions'); }
        }));
      } else {
        disclosure.push(ui.el('p', { class: 'bb-caption', style: 'padding: 0 6px' },
          'Create or choose a set first.'));
      }
    }
    children.push(ui.el('div', { class: 'bb-stack' }, disclosure));
    children.push(saveBar());

    ui.fill(host, children);
  }

  // ---- Sections -----------------------------------------------------------

  function renderSections(host) {
    var sections = (config().sections || []);
    var children = chrome('Sections');

    if (sections.length) {
      var rows = [];
      sections.forEach(function (section) {
        var enabledCount = (section.questions || []).filter(function (q) {
          return q.enabled;
        }).length;
        rows.push(ui.el('div', { class: 'bb-qrow' }, [
          ui.el('button', {
            class: 'bb-qrow-text', type: 'button',
            onclick: function () { push('sectionDetail', section.section_id); }
          }, [
            ui.el('span', { class: 'bb-list-title', style: 'display:block' }, section.section_name),
            ui.el('span', { class: 'bb-list-sub', style: 'display:block' },
              enabledCount + '/' + (section.questions || []).length + ' questions on'),
            /* AI rationale - why this section exists. */
            section.section_summary
              ? ui.el('span', { class: 'bb-list-why', style: 'display:block' }, section.section_summary)
              : null
          ]),
          toggleOnly(enabledCount > 0, function (on) {
            setSectionEnabled(section.section_id, on);
            render();
          })
        ]));
      });
      children.push(ui.card(null, rows));
    }

    var nameInput = ui.el('input', { type: 'text', placeholder: 'e.g. Bonds & Insurance' });
    children.push(ui.card('Add a Section', [
      ui.el('div', { class: 'bb-field' }, [nameInput]),
      ui.el('button', {
        class: 'bb-btn-ghost', type: 'button', style: 'margin-top:10px',
        onclick: function () {
          if (!nameInput.value.trim()) return;
          addSection(nameInput.value);
          nameInput.value = '';
          render();
        }
      }, '＋  Add Section')
    ]));

    children.push(ui.el('p', { class: 'bb-caption bb-center' },
      'Tap a section to open its questions. The switch turns every question in the section on or off.'));
    children.push(saveBar());
    ui.fill(host, children);
  }

  function toggleOnly(checked, onChange) {
    var input = ui.el('input', { type: 'checkbox' });
    input.checked = !!checked;
    input.addEventListener('change', function () { onChange(input.checked); });
    return ui.el('label', { class: 'bb-toggle' }, [input]);
  }

  function renderSectionDetail(host, sectionId) {
    var section = sectionById(sectionId);
    if (!section) return renderSections(host);

    var children = chrome(section.section_name, section.section_description || section.description);

    var rows = (section.questions || []).map(function (q) {
      return questionRow(section.section_id, q);
    });
    children.push(ui.card('Questions', rows.length ? rows
      : [ui.el('p', { class: 'bb-caption' }, 'No questions in this section yet.')]));

    var qInput = ui.el('textarea', {
      rows: '2', placeholder: 'What is the bid bond percentage?'
    });
    children.push(ui.card('Add a Question', [
      ui.el('div', { class: 'bb-field' }, [qInput]),
      ui.el('button', {
        class: 'bb-btn-ghost', type: 'button', style: 'margin-top:10px',
        onclick: function () {
          if (!qInput.value.trim()) return;
          addQuestion(section.section_id, qInput.value);
          qInput.value = '';
          render();
        }
      }, '＋  Add Question')
    ]));

    var renameInput = ui.el('input', { type: 'text' });
    renameInput.value = section.section_name;
    children.push(ui.card('Section', [
      ui.el('div', { class: 'bb-field' }, [renameInput]),
      ui.el('div', { class: 'bb-row', style: 'margin-top:10px' }, [
        ui.el('button', {
          class: 'bb-btn-ghost bb-success bb-grow', type: 'button',
          onclick: function () { renameSection(section.section_id, renameInput.value); render(); }
        }, 'Rename'),
        ui.el('button', {
          class: 'bb-btn-ghost bb-danger bb-grow', type: 'button',
          onclick: function () {
            deleteSection(section.section_id);
            back();
          }
        }, 'Delete Section')
      ])
    ]));

    children.push(saveBar());
    ui.fill(host, children);
  }

  function questionRow(sectionId, question) {
    return ui.el('div', { class: 'bb-qrow' }, [
      ui.el('button', {
        class: 'bb-qrow-text' + (question.enabled ? '' : ' bb-off'), type: 'button',
        onclick: function () {
          push('questionEdit', { sectionId: sectionId, questionId: question.id });
        }
      }, question.text || ''),
      toggleOnly(question.enabled, function () {
        toggleQuestion(sectionId, question.id);
        render();
      })
    ]);
  }

  // ---- All questions ------------------------------------------------------

  function renderAllQuestions(host) {
    var children = chrome('Questions');
    (config().sections || []).forEach(function (section) {
      children.push(ui.card(section.section_name,
        (section.questions || []).map(function (q) {
          return questionRow(section.section_id, q);
        })));
    });
    children.push(saveBar());
    ui.fill(host, children);
  }

  // ---- Question edit ------------------------------------------------------

  function renderQuestionEdit(host, arg) {
    var section = sectionById(arg.sectionId);
    var question = section && (section.questions || []).filter(function (q) {
      return q.id === arg.questionId;
    })[0];
    if (!question) return back();

    var textarea = ui.el('textarea', { rows: '4' });
    textarea.value = question.text || '';
    var enabled = question.enabled;

    var children = chrome('Edit Question', section.section_name);
    children.push(ui.card('Question', [
      ui.el('div', { class: 'bb-field' }, [textarea]),
      ui.toggleRow({
        title: 'Included in analyses',
        checked: enabled,
        onChange: function (on) { enabled = on; }
      })
    ]));
    children.push(ui.el('button', {
      class: 'bb-btn-glow', type: 'button',
      onclick: function () {
        if (!textarea.value.trim()) return;
        updateQuestion(arg.sectionId, arg.questionId, textarea.value.trim(), enabled);
        back();
      }
    }, '✓  Apply Changes'));
    children.push(saveBar());
    ui.fill(host, children);
  }

  // ---- Libraries ----------------------------------------------------------

  function renderLibraries(host) {
    var children = chrome('Libraries',
      'Named snapshots of question sets, kept in this browser.');

    var nameInput = ui.el('input', { type: 'text', placeholder: 'e.g. CIPP lining bids' });
    children.push(ui.card('Save Current Set', [
      ui.el('div', { class: 'bb-field' }, [nameInput]),
      ui.el('button', {
        class: 'bb-btn-ghost', type: 'button', style: 'margin-top:10px',
        onclick: function () {
          if (!nameInput.value.trim()) return;
          BB.libraries.save(nameInput.value, config());
          nameInput.value = '';
          ui.banner('info', 'Library saved.');
          render();
        }
      }, '＋  Save as Library')
    ]));

    var libs = BB.libraries.list();
    if (!libs.length) {
      children.push(ui.el('p', { class: 'bb-caption bb-center' },
        'No libraries yet. Save the current set to start one.'));
    } else {
      children.push(ui.card('Saved Libraries', libs.map(function (lib) {
        return ui.el('div', { style: 'padding:10px 0;border-top:1px solid var(--bb-glass-stroke)' }, [
          ui.el('div', { class: 'bb-list-title' }, lib.name),
          ui.el('div', { class: 'bb-list-sub' },
            lib.sectionCount + ' sections · ' + lib.questionCount + ' questions · ' +
            new Date(lib.savedAt).toLocaleString()),
          ui.el('div', { class: 'bb-row', style: 'margin-top:8px' }, [
            ui.el('button', {
              class: 'bb-btn-ghost bb-success', type: 'button',
              onclick: function () {
                apply(JSON.parse(JSON.stringify(lib.config)));
                save().then(function () {
                  ui.banner('info', 'Question set applied.');
                  path = [];
                  render();
                });
              }
            }, 'Use'),
            ui.el('button', {
              class: 'bb-btn-ghost bb-danger', type: 'button',
              onclick: function () { BB.libraries.remove(lib.id); render(); }
            }, 'Delete')
          ])
        ]);
      })));
    }

    ui.fill(host, children);
  }

  BB.questionHub = {
    render: render, push: push, back: back, load: load, save: save,
    buildSaveBody: buildSaveBody,
    toggleQuestion: toggleQuestion, setSectionEnabled: setSectionEnabled,
    addSection: addSection, addQuestion: addQuestion,
    updateQuestion: updateQuestion, renameSection: renameSection,
    deleteSection: deleteSection,
    apply: apply, proceedWithDefaults: proceedWithDefaults
  };
})(typeof window !== 'undefined' ? window : this);
