/* BB.state - the web mirror of the iOS AppModels (analysis + questionHub +
   navigation). The onboarding cue rules live here and nowhere else. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var CONFIRMED_KEY = 'bb.questionSetConfirmed';

  function storage() {
    try { return window.localStorage; } catch (e) { return null; }
  }

  function readConfirmed() {
    var s = storage();
    return !!(s && s.getItem(CONFIRMED_KEY) === 'true');
  }

  function countSections(config) {
    if (!config || !config.sections || !config.sections.length) return null;
    return {
      sections: config.sections.length,
      questions: config.sections.reduce(function (sum, sec) {
        return sum + ((sec.questions && sec.questions.length) || 0);
      }, 0)
    };
  }

  var listeners = [];

  var state = {
    session: {
      username: '', role: 'user', isAdmin: false, hasPremium: false,
      isBeta: false, beta: null
    },

    navigation: { selectedTab: 'analyze' },

    analysis: {
      phase: 'idle',            /* idle | uploading | configuring | analyzing | done | failed */
      file: null,               /* the File object chosen in the browser */
      filename: '',
      uploadId: null,
      sessionId: null,
      hasPendingDocument: false,
      needsQuestionChoice: false,
      enabledSections: null,    /* null = "not yet chosen"; otherwise an explicit array */
      contextGuardrails: '',
      mode: 'bid_spec',
      highPower: false,
      enableSecondPass: false,
      recheckEmptyWindows: false,
      enableDeepRAG: false,
      pipelineMode: 'classic',
      results: null,
      events: [],
      errorMessage: null
    },

    questionHub: {
      config: null,
      isConfirmed: readConfirmed(),
      isDirty: false,
      currentSetSummary: function () {
        return state.questionHub.isConfirmed ? countSections(state.questionHub.config) : null;
      },
      loadedSetSummary: function () {
        return countSections(state.questionHub.config);
      }
    },

    subscribe: function (fn) { listeners.push(fn); return fn; },

    notify: function () {
      listeners.forEach(function (fn) {
        try { fn(state); } catch (e) {
          if (window.console && window.console.error) window.console.error(e);
        }
      });
    },

    /** A freshly attached PDF: the "which questions?" decision reopens. */
    noteFreshUpload: function (file) {
      state.analysis.file = file || null;
      state.analysis.filename = (file && file.name) || '';
      state.analysis.hasPendingDocument = true;
      state.analysis.needsQuestionChoice = true;
      state.notify();
    },

    /** Confirming a set resolves that decision - the iOS onConfirmSet hook.
        Never gate the Analyze cue on isConfirmed alone (regression 2.1.3). */
    setConfirmed: function (confirmed) {
      state.questionHub.isConfirmed = !!confirmed;
      var s = storage();
      if (s) s.setItem(CONFIRMED_KEY, confirmed ? 'true' : 'false');
      if (confirmed) state.analysis.needsQuestionChoice = false;
      state.notify();
    },

    beginChoosing: function () { state.setConfirmed(false); },

    reset: function () {
      var a = state.analysis;
      a.phase = 'idle'; a.file = null; a.filename = ''; a.uploadId = null;
      a.sessionId = null; a.hasPendingDocument = false; a.needsQuestionChoice = false;
      a.enabledSections = null; a.results = null; a.events = []; a.errorMessage = null;
      state.notify();
    },

    /** Only nudge once a document is waiting to be analyzed. */
    onboardingHint: function () {
      if (!state.analysis.hasPendingDocument) return 'none';
      if (state.analysis.needsQuestionChoice || !state.questionHub.isConfirmed) {
        return 'chooseQuestions';
      }
      return state.navigation.selectedTab === 'analyze' ? 'startAnalysis' : 'goAnalyze';
    },

    /** Prune a stored selection against the section ids that actually exist. */
    prunedSelection: function (selection, validIds) {
      if (!selection) return null;
      var valid = {};
      (validIds || []).forEach(function (id) { valid[id] = true; });
      var kept = selection.filter(function (id) { return valid[id]; });
      return kept.length ? kept : null;
    }
  };

  BB.state = state;
})(typeof window !== 'undefined' ? window : this);
