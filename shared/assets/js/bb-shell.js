/* The app shell: four pages over the orb + a floating capsule tab bar that
   throbs a "Next" chip on the tab the guided flow wants next.
   Mirrors Sources/Features/Home/HomeView.swift. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};
  var ui = BB.ui;

  var ALL_TABS = {
    analyze:   { id: 'analyze',   label: 'Analyze',   icon: '🔍' },
    questions: { id: 'questions', label: 'Questions', icon: '📋' },
    admin:     { id: 'admin',     label: 'Admin',     icon: '🔑' },
    bonus:     { id: 'admin',     label: 'Bonus',     icon: '✨' },
    settings:  { id: 'settings',  label: 'Settings',  icon: '⚙' }
  };

  var pages = {};

  /** Admins get Admin; Bonus Features users get the same slot relabelled. */
  function tabsFor(session) {
    var tabs = [ALL_TABS.analyze, ALL_TABS.questions];
    if (session && session.isAdmin) tabs.push(ALL_TABS.admin);
    else if (session && session.hasPremium) tabs.push(ALL_TABS.bonus);
    tabs.push(ALL_TABS.settings);
    return tabs;
  }

  var HINT_TAB = { chooseQuestions: 'questions', goAnalyze: 'analyze' };

  function nudgedTab() {
    var target = HINT_TAB[BB.state.onboardingHint()] || null;
    if (!target) return null;
    return target === BB.state.navigation.selectedTab ? null : target;
  }

  function renderTabBar() {
    var host = ui.qs('#bb-tabbar');
    if (!host) return;
    var tabs = tabsFor(BB.state.session);
    var nudge = nudgedTab();
    ui.fill(host, tabs.map(function (tab) {
      var active = BB.state.navigation.selectedTab === tab.id;
      var nudged = nudge === tab.id;
      return ui.el('button', {
        class: 'bb-tab' + (active ? ' bb-active' : '') + (nudged ? ' bb-nudged bb-throb' : ''),
        type: 'button',
        'data-tab': tab.id,
        'aria-current': active ? 'page' : null,
        onclick: function () { go(tab.id); }
      }, [
        nudged ? ui.el('span', { class: 'bb-next-chip' }, 'Next') : null,
        ui.el('span', { class: 'bb-tab-icon' }, tab.icon),
        ui.el('span', {}, tab.label)
      ]);
    }));
  }

  function go(tabId) {
    BB.state.navigation.selectedTab = tabId;

    var tabs = tabsFor(BB.state.session);
    var index = 0;
    tabs.forEach(function (t, i) { if (t.id === tabId) index = i; });
    BB.orb.setDrift(BB.orb.driftFor(index, tabs.length));

    ui.qsa('.bb-page').forEach(function (page) {
      var mine = page.id === 'bb-page-' + tabId;
      page.hidden = !mine;
      if (mine) {
        page.classList.remove('bb-stage');
        void page.offsetWidth;              /* restart the fade-in */
        page.classList.add('bb-stage');
      }
    });

    if (pages[tabId]) {
      try { pages[tabId](); } catch (e) {
        if (window.console) window.console.error('page render failed: ' + tabId, e);
      }
    }
    renderTabBar();
    if (window.scrollTo) window.scrollTo(0, 0);
  }

  function registerPage(tabId, renderFn) { pages[tabId] = renderFn; }

  /** Re-render whichever page is showing (state changed underneath it). */
  function refresh() {
    var tabId = BB.state.navigation.selectedTab;
    if (pages[tabId]) {
      try { pages[tabId](); } catch (e) {
        if (window.console) window.console.error('page refresh failed: ' + tabId, e);
      }
    }
    renderTabBar();
  }

  /** Fill BB.state.session from an /api/user/info payload. */
  function applyUserInfo(data) {
    if (!data || !data.success) return BB.state.session;
    var s = BB.state.session;
    s.username = data.username || data.email || '';
    s.role = data.role || 'user';
    s.isAdmin = !!data.is_admin;
    s.hasPremium = !!(data.is_admin || data.premium ||
      (data.bonus_features && data.bonus_features.length));
    return s;
  }

  function loadUserInfo() {
    return window.fetch('/api/user/info')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        applyUserInfo(data);
        renderTabBar();
        refresh();
      })
      .catch(function () { /* stay a plain user */ });
  }

  function init() {
    BB.orb.mount(ui.qs('#bb-orb'));
    BB.state.subscribe(renderTabBar);
    renderTabBar();
    go('analyze');
    loadUserInfo();
  }

  BB.shell = {
    init: init, go: go, registerPage: registerPage, refresh: refresh,
    renderTabBar: renderTabBar, tabsFor: tabsFor, nudgedTab: nudgedTab,
    applyUserInfo: applyUserInfo, loadUserInfo: loadUserInfo
  };
})(typeof window !== 'undefined' ? window : this);
