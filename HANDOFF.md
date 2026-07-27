# HANDOFF — BidBrief (Flask backend + web front-end)

> Updated: 2026-07-26 — **2.2.0: the web front-end was rebuilt to BidBrief iOS UX parity.
> Shipped to production (`master` → Render), `/health` reports 2.2.0.**

## Current state

- **Branch:** `master`, pushed (`d34da69`). Feature branch `feat/web-ios-parity-2.2.0` is merged and
  can be deleted whenever you like.
- **Production:** https://bidbrief.onrender.com — `/health` → `2.2.0`, login page and every new asset
  verified live in a real browser (no console errors).
- **Tests:** `python -m pytest -q` → **106 passed** (was 76). `node --test tests/js/*.test.js` → **85 passed**.

## 2.2.0 — Web front-end rebuilt to iOS parity (this round)

Plan: `docs/superpowers/plans/2026-07-26-web-frontend-ios-parity-overhaul.md`.
Architecture + invariants: **`docs/WEB_FRONTEND.md` (read this before touching the web app).**
Synopsis delta: `digestsynopsisSUMMARY.md` § Δ 2026-07-26.

**No backend behaviour changed.** The only `app.py` edit in this round is the `/health` version string.
Question generation, analysis, exports, and the scraper endpoints are untouched.

1. **Structure.** `index.html` went from 5,514 lines (inline CSS + markup + 4,438 lines of inline JS) to a
   ~55-line shell. All CSS/JS lives under `shared/assets/`, served by the pre-existing
   `/shared/<path:filename>` route — **no new Flask routes**. The dead `cdn.sheetjs.com` script is gone
   (every Excel export is server-side). No bundler, no framework: classic scripts on a `window.BB` namespace.
2. **Design system**: the iOS `BBTheme` palette verbatim, glass cards, glow/ghost/hub buttons, stage
   headers, back chips, segmented controls, iOS-style switches, and the suspended planet with per-tab
   parallax drift. Everything animated is disabled under `prefers-reduced-motion`.
3. **IA**: a floating bottom tab bar — Analyze / Questions / Admin·Bonus / Settings. `BB.state`
   (`shared/assets/js/bb-state.js`) mirrors the iOS `AppModels`, including the confirmed-question-set gate
   and the 2.1.3 onboarding cue rules.
4. **Screens**: Analyze (upload orb → configure with Start Analysis below the guardrails → progress orb
   ring + phase track + Live Activity popup → staged results), Question Hub (Create/Add, Libraries with a
   one-time Starter Set seed, Current Set disclosure, sections/questions/edit), Admin·Bonus (sessions
   dashboard, Bonus Features manager, glass CityScraper), Settings, and a rebuilt login page.
5. **Q-gen parity**: the web client now honours the 2.1.1/2.1.2 contract it never implemented — the
   analyzer document is ALWAYS sent for grounding (as `file` with `source_kind=context`, or as
   `context_file` beside a PDF questions-source), the Create screen auto-adopts it, `source_intent` is an
   inline field instead of `window.prompt`, and there is a Questions Source slot + Replace/Merge modes.

## What only the user can verify

1. **A real end-to-end analysis on production.** The pipeline UI was exercised with synthetic events and
   a real upload, but not a full 5–20 minute run against a live document.
2. **The Bonus Features manager against real users.** It matches the existing
   `GET/POST /api/admin/bonus-features` shape but was never exercised with live grants.
3. **CityScraper on production** (needs `TAVILY_API_KEY`). The flow and endpoints are unchanged from the
   previous client; only the presentation was rebuilt.

## Deploy

`git push origin master` → Render auto-redeploys in 2–3 minutes (`DEPLOYMENT.md`). Zero-downtime, so
`/health` never blips — confirm the cutover by watching the `version` field flip, not the status code.
Run `pytest` locally before pushing.

## Reference

- **Web front-end:** `docs/WEB_FRONTEND.md` — module map, the `BB` namespace contract, the state model,
  and the nine invariants a change must not break.
- **Debug lessons:** `memory/debug_history.md` (project) and `~/.claude/memory/debug_history.md` (global).
- **The iOS app is the design source of truth** for this UI:
  `C:\Users\pr0ph\Documents\AI LLC\Apps\BidBrief iOS` (`Sources/DesignSystem/`, `Sources/Features/`).
