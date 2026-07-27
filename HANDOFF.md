# HANDOFF — BidBrief (Flask backend + web front-end)

> Updated: 2026-07-27 — **2.3.0: Free Beta Testing — a one-click trial login on the web sign-in
> page, an admin panel to run it, and a 5-document quota per tester. iOS untouched this round.**

## 2.3.0 — Free Beta Testing (this round)

Front-end map + invariants: **`docs/WEB_FRONTEND.md`** (invariants 9–12 are new).

**The shape of it.** A "Free Beta Testing" button appears on `/login` only while the switch is on.
It opens a terms modal ("free while the beta is open · N documents · 24 hours · a subscription is
required afterwards"), and one click starts a session. **Each click mints its own ephemeral
identity** (`beta-<hex>`) — never a shared account, because analyses are owner-scoped by username
and a shared login would let any tester read any other tester's results. Beta testers are ordinary
users: no admin, no premium, no High Power, no BestPrep, no CityScraper.

1. **`services/beta_access.py` (new)** — the switch and the tester registry, both in memory, all
   mutations under a lock (analyses run on background threads). Boot state comes from
   `BETA_LOGIN_ENABLED`; quota from `BETA_DOC_LIMIT` (default 5). Hands out dict *copies*, never
   live records.
2. **Endpoints** — `GET /api/beta/status` (public, drives the button), `POST /auth/beta-login`,
   `GET|POST /api/admin/beta`, `POST /api/admin/beta/testers/<username>` (`reset` | `grant` |
   `doc_limit`), `DELETE /api/admin/beta/testers/<username>` (also revokes their live sessions;
   their analyses are deliberately kept).
3. **Quota enforcement** in `/api/analyze`: checked up front so an exhausted tester gets the
   paywall rather than an unrelated error, then claimed atomically at session pre-registration —
   so a malformed or unauthorized request never costs a tester a free document. The wall is
   **402** with `beta_quota_exhausted: true`.
4. **SECURITY FIX — `/api/analyze` now requires auth.** It had no `@require_auth` (unlike
   `/api/upload`). An anonymous caller started analyses with `owner=None`, which bypassed the
   quota entirely *and* produced unowned sessions that `_is_authorized_for_session` lets anyone
   read. Found by a test written for the quota. **Do not remove that decorator.**
5. **Admin panel** (`Admin → Free Beta Testing`): the on/off switch, a population summary, and a
   card per tester — quota meter, signed-in state, timestamps, **their sessions** (filename,
   status, answers/pages, View results, Excel) and **+5 documents / Reset usage / Delete**.
   Session rows are built by the same `format_session_info` that `/api/admin/sessions` uses, so
   the admin panel and the iOS dashboard can never drift.
6. **BUG FIX — the Bonus Features manager was broken.** `bb-admin.js` posted `{username: …}` while
   the API expects `{email: …}`, and read `user.premium`/`user.has_bonus` while the API returns
   `bonus_features` — so every toggle rendered off and every grant 400'd. Now matches the API.
7. **Refactors**: `_issue_session` / `_set_auth_cookie` are now the single source of truth for
   session shape and cookie policy (form login, API login and beta login all use them);
   `format_session_info` and `_snapshot_sessions_by_bucket` were lifted out of the
   `/api/admin/sessions` route body so the beta dashboard reuses them.

**Verified:** `pytest -q` → **130 passed**; `node --test tests/js/*.test.js` → **97 passed**;
and a real Chromium pass over the whole flow (button → modal → session → Settings quota → admin
panel → +5 → reset → delete → tester's next call 401s → switch off hides the button and 403s the
route), desktop and 390px mobile, **zero console errors**.

**Operational note:** the switch lives in memory. A Render deploy resets it to `BETA_LOGIN_ENABLED`.
To keep free beta open across deploys, set that env var on Render — toggling in the UI is not enough.
Turning the switch off stops *new* beta logins; testers already signed in keep their session until
it expires (delete them individually to cut them off now).

> Previous round (2.2.0) below.

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
