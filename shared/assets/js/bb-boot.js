/* Entry point: wire the pages into the shell, then start it. */
(function (window) {
  'use strict';
  var BB = window.BB;

  window.document.addEventListener('DOMContentLoaded', function () {
    BB.shell.registerPage('analyze', BB.analyze.render);
    BB.shell.registerPage('questions', BB.questionHub.render);
    BB.shell.registerPage('admin', BB.admin.render);
    BB.shell.registerPage('settings', BB.settings.render);

    BB.shell.init();

    /* One-time cleanup of libraries saved before duplicate auto-backups were
       fixed: collapses identical sets and renames the old timestamped entries.
       Runs before the seed so the Sample Set can't be re-added as a duplicate. */
    BB.libraries.tidyOnce();

    /* The Sample Set is seeded ONCE into Libraries - never auto-applied. */
    window.fetch('/shared/assets/data/starter-question-set.json')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (config) { if (config) BB.libraries.seedStarterOnce(config); })
      .catch(function () { /* the starter set is a convenience, not a requirement */ });

    /* Pre-load the backend's question config so the hub and the Analyze
       prompt can show real counts immediately. Loading is NOT confirming. */
    BB.questionHub.load();
  });
})(window);
