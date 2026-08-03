/* Rolls the raw event stream up into phase + friendly detail + progress.
   Pure and order-tolerant: fraction and phase only move forward.
   Transcribed from Sources/Features/Analyze/AnalysisPhase.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var WINDOW_BAND_START = 0.12;
  var WINDOW_BAND_SPAN = 0.78;   /* 12% -> 90% */

  var PHASES = [
    { key: 'preparing',  title: 'Reading Document',   stepLabel: 'Read',    icon: '📄' },
    { key: 'experts',    title: 'Creating Experts',   stepLabel: 'Experts', icon: '👥' },
    { key: 'analyzing',  title: 'Analyzing',          stepLabel: 'Analyze', icon: '🔎' },
    { key: 'verifying',  title: 'Double-Checking',    stepLabel: 'Verify',  icon: '🛡' },
    { key: 'finalizing', title: 'Assembling Results', stepLabel: 'Finish',  icon: '📦' },
    { key: 'complete',   title: 'Complete',           stepLabel: 'Done',    icon: '✅' }
  ];
  var RANK = {};
  PHASES.forEach(function (p, i) { RANK[p.key] = i; });

  function payloadOf(event) { return (event && event.payload) || {}; }

  function num(v) {
    if (typeof v === 'number') return v;
    if (v == null || v === '') return null;
    var n = parseInt(v, 10);
    return isNaN(n) ? null : n;
  }

  function ingest(status, event) {
    var p = payloadOf(event);

    function advance(phase, fraction, detail) {
      if (RANK[phase] > RANK[status.phase]) status.phase = phase;
      if (fraction > status.fraction) status.fraction = Math.min(fraction, 1);
      if (detail != null) status.detail = detail;
    }

    switch (event.event) {
      case 'analysis_started': case 'processing_start': case 'pipeline_start':
        advance('preparing', 0.03, 'Starting the analysis pipeline'); break;
      case 'config_loaded':
        advance('preparing', 0.04, 'Question set loaded'); break;
      case 'prescan_start':
        advance('preparing', 0.05, 'Scanning the document'); break;
      case 'prescan_complete': case 'document_ingested': case 'layer_0_start':
        advance('preparing', 0.07, 'Reading the PDF'); break;
      /* Layer 0.5 - the opt-in vision pass runs before windows exist, so it
         must stay comfortably under the 12% window band. */
      case 'visual_scan_start': {
        var vc = (p.candidate_pages || []).length;
        advance('preparing', 0.06, vc
          ? ('Reading drawings, maps & imagery on ' + vc + ' page' + (vc === 1 ? '' : 's'))
          : 'Checking for drawings, maps & imagery');
        break;
      }
      case 'visual_page_complete': {
        var vDone = num(p.scanned), vTotal = num(p.total_candidates);
        if (vDone != null && vTotal) {
          advance('preparing', 0.06 + 0.05 * vDone / vTotal,
            'Visual analysis - page ' + (p.page != null ? p.page : '?') +
            ' (' + vDone + ' of ' + vTotal + ')');
        }
        break;
      }
      case 'visual_scan_complete': {
        var vf = num(p.findings_count);
        advance('preparing', 0.11, vf
          ? ('Visual intelligence captured from ' + vf + ' page' + (vf === 1 ? '' : 's'))
          : 'Visual scan finished');
        break;
      }
      case 'visual_scan_failed':
        advance('preparing', 0.11, 'Visual scan skipped - continuing with text analysis'); break;

      case 'layer_1_start':
        advance('preparing', 0.08, 'Mapping the document structure'); break;
      case 'layer_2_start':
        advance('preparing', 0.09, 'Splitting into analysis windows'); break;

      case 'expert_generated': {
        var name = p.expert_name || 'expert';
        advance('experts', 0.09, p.section ? ('Created ' + name + ' for ' + p.section)
                                           : ('Created ' + name));
        break;
      }
      case 'experts_dispatched': {
        var count = num(p.expert_count);
        advance('experts', 0.10, count != null ? ('Dispatched ' + count + ' expert agents')
                                               : 'Expert agents dispatched');
        break;
      }
      case 'experts_complete':
        advance('analyzing', 0.12, 'Experts ready - analysis underway'); break;

      /* Key details run EARLY. Mapping them high was the old
         "jumps to 94% and stalls" bug - they must never outrank the window band. */
      case 'key_requirements_start':
        advance('experts', 0.10, 'Extracting key document details'); break;
      case 'key_requirements_complete': case 'key_requirements_failed':
        advance('experts', 0.12, 'Key details captured'); break;

      case 'window_processing': {
        var n = num(p.window_num), total = num(p.total_windows);
        if (n != null && total) {
          status.windowNum = n; status.totalWindows = total;
          var pages = p.pages ? String(p.pages) : '';
          advance('analyzing',
            WINDOW_BAND_START + WINDOW_BAND_SPAN * (n - 1) / total,
            pages ? ('Analyzing window ' + n + ' of ' + total + ' - pages ' + pages)
                  : ('Analyzing window ' + n + ' of ' + total));
        } else {
          advance('analyzing', status.fraction, 'Analyzing the document');
        }
        break;
      }
      case 'window_complete': case 'progress_milestone': {
        var done = num(p.window_num);
        if (done == null) done = num(p.windows_processed);
        var tot = num(p.total_windows);
        if (tot == null) tot = status.totalWindows;
        if (done != null && tot) {
          status.windowNum = done; status.totalWindows = tot;
          advance('analyzing', WINDOW_BAND_START + WINDOW_BAND_SPAN * done / tot,
                  done + ' of ' + tot + ' windows finished');
        }
        break;
      }

      case 'recheck_start':
        advance('verifying', 0.905, 'Re-checking windows that came back empty'); break;
      case 'recheck_window_processing': {
        var rn = num(p.recheck_num), rt = num(p.total_rechecks);
        if (rn != null && rt) {
          advance('verifying', 0.905 + 0.02 * rn / rt, 'Re-checking window ' + rn + ' of ' + rt);
        }
        break;
      }
      case 'recheck_complete':
        advance('verifying', 0.925, 'Re-check finished'); break;
      case 'second_pass_started': case 'second_pass_processing': case 'second_pass_start': {
        var un = num(p.unanswered_count);
        advance('verifying', 0.93, un != null
          ? ('Second pass on ' + un + ' unanswered questions')
          : 'Second pass on unanswered questions');
        break;
      }
      case 'second_pass_complete':
        advance('verifying', 0.955, 'Second pass complete'); break;
      case 'second_pass_failed':
        advance('verifying', 0.955, 'Second pass skipped'); break;

      case 'layer_6_start':
        advance('finalizing', 0.96, 'Cross-checking answers'); break;
      case 'layer_7_start': case 'stage_4_start':
        advance('finalizing', 0.965, 'Assembling the final report'); break;

      /* The orchestrator's completion fires BEFORE results are packaged. */
      case 'analysis_complete': case 'pipeline_complete':
      case 'stage_4_complete': case 'layer_7_complete':
        advance('finalizing', 0.97, 'Wrapping up - assembling final results'); break;
      case 'status':
        if (p.message) {
          advance('finalizing',
            String(p.message).toLowerCase().indexOf('intelligence') >= 0 ? 0.98 : status.fraction,
            p.message);
        }
        break;
      case 'results_ready': case 'done':
        advance('complete', 1.0, 'Analysis complete'); break;

      default: break;   /* stage_* / layer_* internals never move the story */
    }
  }

  function fromEvents(events) {
    var status = {
      phase: 'preparing', detail: 'Warming up the pipeline...',
      fraction: 0.02, windowNum: null, totalWindows: null
    };
    (events || []).forEach(function (e) { ingest(status, e); });
    return status;
  }

  /** One friendly feed line per event, or null for technical noise. */
  function friendlyLine(event) {
    var probe = { phase: 'preparing', detail: '', fraction: 0, windowNum: null, totalWindows: null };
    ingest(probe, event);
    return probe.detail === '' ? null : probe.detail;
  }

  /** The phase an individual event belongs to - used for the feed row icon. */
  function phaseOf(event) {
    var probe = { phase: 'preparing', detail: '', fraction: 0, windowNum: null, totalWindows: null };
    ingest(probe, event);
    return probe.phase;
  }

  BB.status = {
    PHASES: PHASES,
    TRACK_STEPS: PHASES.slice(0, 5),
    fromEvents: fromEvents,
    friendlyLine: friendlyLine,
    phaseOf: phaseOf,
    rank: function (key) { return RANK[key]; },
    phaseInfo: function (key) { return PHASES[RANK[key]]; }
  };
})(typeof window !== 'undefined' ? window : this);
