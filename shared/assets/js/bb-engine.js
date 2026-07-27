/* BB.engine - the analysis pipeline client. Network and event handling only;
   every pixel is drawn by BB.analyze / BB.progress / BB.results.

   Ported from the original inline implementation, preserving the behaviours
   that were hard-won there:
   - the first /api/events poll after /api/analyze can 403 (registration race),
     so polling tolerates failures and simply retries a second later;
   - `analysis_complete` fires BEFORE the server finishes packaging results,
     so only `results_ready` (or a successful /api/results fetch) is terminal;
   - /api/results is retried with backoff because /api/stop can return before
     the session lands in partial_analyses. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  var POLL_MS = 1000;
  var pollTimer = null;
  var lastEventIndex = 0;
  var earlyPollFailures = 0;

  /* In-memory activity log. The Live Activity popup reads this; nothing is
     written to the page as it arrives. */
  var log = [];

  function note(level, message) {
    log.push({ level: level, message: message, at: new Date().toISOString() });
    if (log.length > 500) log.shift();
    if (window.console && window.console.log) window.console.log('[BB] ' + message);
  }

  function state() { return BB.state.analysis; }

  /** Normalise a backend event (flat payload) into the {event, payload} shape
      BB.status understands. */
  function normalize(data) {
    return { event: data.event, timestamp: data.timestamp || '', payload: data };
  }

  // ---- Upload -------------------------------------------------------------

  function upload(file) {
    var form = new window.FormData();
    form.append('file', file);
    return window.fetch('/api/upload', { method: 'POST', body: form })
      .then(function (resp) {
        if (!resp.ok) throw new Error('File upload failed (HTTP ' + resp.status + ')');
        return resp.json();
      })
      .then(function (data) {
        if (data && data.success === false) throw new Error(data.error || 'File upload failed');
        note('success', 'Uploaded ' + (data.filename || file.name));
        return { uploadId: data.upload_id, filename: data.filename || file.name };
      });
  }

  // ---- Start --------------------------------------------------------------

  function analyze(body) {
    return window.fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (data) {
        if (!resp.ok || data.success === false) {
          throw new Error(data.error || ('Analysis failed to start (HTTP ' + resp.status + ')'));
        }
        return data;
      });
    });
  }

  // ---- Polling ------------------------------------------------------------

  function startPolling(sessionId) {
    stopPolling();
    lastEventIndex = 0;
    earlyPollFailures = 0;
    state().sessionId = sessionId;
    note('info', 'Polling events for session ' + sessionId);
    poll();
    pollTimer = window.setInterval(poll, POLL_MS);
  }

  function stopPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
      note('info', 'Stopped event polling');
    }
  }

  function poll() {
    var sessionId = state().sessionId;
    if (!sessionId) return;
    return window.fetch('/api/events/' + sessionId + '?last_index=' + lastEventIndex)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) {
          /* The very first poll can lose a race with session registration
             (historic 403). Tolerate a few, then surface the problem. */
          earlyPollFailures += 1;
          if (earlyPollFailures > 5) note('error', 'Event polling failed: ' + ((data && data.error) || 'unknown'));
          return;
        }
        earlyPollFailures = 0;
        (data.events || []).forEach(handleEvent);
        if (typeof data.last_index === 'number') lastEventIndex = data.last_index;
      })
      .catch(function () { /* transient - the next tick retries */ });
  }

  // ---- Events -------------------------------------------------------------

  function handleEvent(data) {
    try {
      var a = state();
      a.events.push(normalize(data));

      switch (data.event) {
        case 'results_ready':
          if (data.result) {
            a.results = data.result;
            if (data.result.key_requirements) a.keyRequirements = data.result.key_requirements;
            if (data.result.optimized_scan_data) a.optimizedScan = data.result.optimized_scan_data;
          }
          note('success', 'Results received');
          break;

        case 'key_requirements_complete':
          if (data.requirements) a.keyRequirements = data.requirements;
          break;

        case 'window_complete':
          /* Live answers stream in while the analysis runs. */
          if (data.new_answers && data.new_answers.length && BB.results.ingestLiveAnswers) {
            BB.results.ingestLiveAnswers(data.new_answers, data.stage || 'classic');
          }
          break;

        case 'analysis_complete': case 'done':
          stopPolling();
          if (a.results && a.results.sections) finish(a.results, false);
          else fetchResults();
          break;

        case 'analysis_failed': case 'error': {
          var message = data.error || data.error_type || 'Unknown error';
          stopPolling();
          if (message === 'Analysis stopped by user') {
            note('warning', 'Analysis stopped by user - collecting partial results');
            fetchResults();
          } else {
            fail(message);
          }
          break;
        }

        default:
          break;
      }

      if (BB.progress && BB.progress.update) BB.progress.update();
    } catch (err) {
      note('error', 'Failed to process event: ' + err.message);
    }
  }

  // ---- Results ------------------------------------------------------------

  /** Retry with backoff: /api/stop can return before the session lands in
      partial_analyses, and results_ready can beat the packaging step. */
  function fetchResults(maxRetries) {
    maxRetries = maxRetries || 5;
    var sessionId = state().sessionId;
    if (!sessionId) return window.Promise.resolve(null);

    function attempt(n) {
      return window.fetch('/api/results/' + sessionId)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.success) {
            if (n < maxRetries) {
              return delay(500 * n).then(function () { return attempt(n + 1); });
            }
            throw new Error(data.error || 'Results not available');
          }
          finish(data.result, !!data.partial, data.statistics);
          return data.result;
        })
        .catch(function (error) {
          if (n < maxRetries) {
            return delay(500 * n).then(function () { return attempt(n + 1); });
          }
          fail('Could not fetch results: ' + error.message);
          return null;
        });
    }
    return attempt(1);
  }

  function delay(ms) {
    return new window.Promise(function (resolve) { window.setTimeout(resolve, ms); });
  }

  function finish(result, isPartial, statistics) {
    var a = state();
    a.results = result;
    a.isPartial = !!isPartial;
    if (statistics) a.statistics = statistics;
    a.phase = 'done';
    stopPolling();
    note('success', 'Analysis complete');
    BB.state.notify();
    BB.shell.refresh();
  }

  function fail(message) {
    var a = state();
    a.phase = 'failed';
    a.errorMessage = message;
    stopPolling();
    note('error', message);
    BB.state.notify();
    BB.shell.refresh();
  }

  // ---- Stop ---------------------------------------------------------------

  function stop() {
    var sessionId = state().sessionId;
    if (!sessionId) return window.Promise.resolve();
    return window.fetch('/api/stop/' + sessionId, { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.success) {
          note('warning', 'Analysis stopped by user');
          stopPolling();
          return fetchResults();
        }
      })
      .catch(function (e) { note('error', 'Failed to stop analysis: ' + e.message); });
  }

  // ---- Improvement passes -------------------------------------------------

  function runPass(kind, questionIds) {
    var sessionId = state().sessionId;
    if (!sessionId) return window.Promise.reject(new Error('No analysis session'));
    var url = (kind === 'rag' ? '/api/analyze/rag/' : '/api/analyze/second-pass/') + sessionId;
    return window.fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_ids: questionIds })
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'Pass failed');
        return fetchResults();
      });
  }

  // ---- Smart Analysis -----------------------------------------------------

  function smartAnalysis(userInput) {
    var sessionId = state().sessionId;
    if (!sessionId) return window.Promise.reject(new Error('No analysis session'));
    return window.fetch('/api/smart-analysis/' + sessionId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_input: userInput || '' })
    }).then(function (resp) {
      return resp.json().then(function (data) {
        if (!resp.ok || !data.success) throw new Error(data.error || ('HTTP ' + resp.status));
        return data.result;
      });
    });
  }

  BB.engine = {
    upload: upload,
    analyze: analyze,
    startPolling: startPolling,
    stopPolling: stopPolling,
    handleEvent: handleEvent,
    fetchResults: fetchResults,
    finish: finish,
    fail: fail,
    stop: stop,
    runPass: runPass,
    smartAnalysis: smartAnalysis,
    note: note,
    log: function () { return log.slice(); }
  };
})(typeof window !== 'undefined' ? window : this);
