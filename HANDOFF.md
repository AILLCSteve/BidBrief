# HANDOFF — BidBrief (Flask backend + web front-end)

> Updated: 2026-08-02 — **2.4.0: Visual Intelligence (opt-in vision pass over drawing/map/photo
> pages), the results screen rebuilt as the Excel workbook, and the admin Session Dashboard
> brought in-app with per-session Excel export. iOS untouched this round.**

## 2.5.0 — Durable session storage (Neon) — backend only

Setup + design: **`docs/PERSISTENCE.md`**. Nothing about this appears in the user UI
(deliberate: admin/backend concern only).

Server state used to live in one worker's memory, so every deploy wiped logins,
entitlements and every completed analysis. Now memory stays the hot path and Postgres
is the durable mirror.

- **`services/persistence.py` (NEW)** — schema bootstrap, pooled connections, repo
  functions. **Without `DATABASE_URL` every call is a no-op and the app is unchanged**;
  every operation is failure-safe so a Neon outage can never fail an analysis or a login.
- **Analyses persist as a JSON snapshot**, not the orchestrator (which cannot be
  serialized). The snapshot holds the legacy result payload, statistics, key details,
  document type and BestPrep data — enough for `/api/results`, the Excel/CSV exports AND
  Smart Analysis to work on a restored session, because those paths consume the dict, not
  the orchestrator. Second pass / Deep RAG need the live cached windows and refuse with a
  clear 409.
- **Also durable**: signed-in sessions, Bonus grants, beta testers and their spent quota,
  cached Smart Analysis results (never re-billed after a restart), and the free-beta switch
  (which no longer reverts to `BETA_LOGIN_ENABLED` on deploy).
- **In-flight analyses** are marked `interrupted` at boot — their worker thread died with
  the previous process, so a run that can never resume now says so.
- Recovered rows **fold into the existing admin buckets** with `restored: true` rather than
  adding a fifth bucket: those four names are the contract the iOS dashboard decodes.
- `requirements.txt` gains `psycopg[binary]` + `psycopg-pool`.

**Env vars (Render):** `DATABASE_URL` (pooled Neon string — the on/off switch),
optional `BIDBRIEF_DB_RETENTION_DAYS` (90), `BIDBRIEF_DB_POOL_MAX` (4).
**Verify:** `DATABASE_URL='...' python -m services.persistence` round-trips the schema;
after deploy, `/api/admin/sessions` → `diagnostics.persistence` (admin-only, never on the
public `/health`).

**Verified:** `pytest -q` → **194 passed** (+18); `node --test` → **115 passed**; boot with
no `DATABASE_URL` confirmed unchanged. **A live Neon round-trip has NOT been run — that
needs your connection string** (see the one-command self-check above).

> Previous round (2.4.1) below.

## 2.4.1 — Visual evidence woven INTO HOTDOG + GPT-5.6 model tiers

**Model tiers moved a generation forward** (configuration, not code — both IDs keep the
`gpt-5` prefix so `is_reasoning_model` and the 400K TokenOptimizer budget still apply):
standard `gpt-5.4` → **`gpt-5.6-terra`** (cheaper: $2/$12 vs $2.50/$15 per Mtok, and it
out-scores gpt-5.5 on vision), high power `gpt-5.5` → **`gpt-5.6-sol`** (same $5/$30, the
strongest vision model OpenAI has shipped — 46.2 vs 13.8 mAP@50). Rollback is a Render env
var. The vision prompt also now forbids counting/tallying items from a drawing (GPT-5.x
vision is weak at dense quantification, ~30%); quantities must be printed on the sheet.

**The visual layer is no longer a separate report.** 2.4.0 shipped it as a bolt-on: it
analyzed drawings, summarized them, and added a sheet. It is now evidence *inside* the
HOTDOG orchestration, answering the user's own question set:

1. **Windows carry visual tagging.** `PageData.visual_kind` is set by the scanner;
   `create_windows` collects `WindowContext.visual_pages` ({page: kind}). Preserved when
   the orchestrator rebuilds a truncated window — dropping it there would disarm the
   contract for exactly the biggest, most drawing-heavy windows.
2. **Every expert is told the evidence exists and must attribute it.** The L3 prompt gains
   a VISUAL EVIDENCE block naming each page and kind, framing it as real document evidence
   equal to the written text, and requiring `<PDF pg 7> <VIS pg 7 drawing>` when an answer
   uses it. The second pass gets the same block, pointed harder at the graphics (its
   questions already failed against the text). A text-only window gets NO block — the
   prompt is byte-identical to pre-2.4.0.
3. **Provenance flows end to end.** Markers parse into `Answer.visual_sources` (bounded by
   the pages actually analyzed, so a hallucinated marker cannot invent a graphic), union on
   `merge_with`, aggregate across BestPrep fragments (`CumulativeAnswer.all_visual_sources`,
   used for the L7-synthesized answer since synthesis rewrites the text and drops markers),
   feed L6.5 (which now attributes graphics in prose — "the plan sheet shows…" — instead of
   leaking raw markers), and reach `/api/results` as `visual_sources` per question.
4. **Every surface shows it.** Excel Detailed Results + By Section gain a **Visual Source**
   column ("Drawing p.7"), the OutputCompiler Answers sheet too; the web workbook badges
   drawing-sourced answers inline with a tooltip, adds the same column, and the Visual
   Intelligence sheet now lists **which questions each graphic answered** — the proof it fed
   the question set. CSV and the HTML report carry the column.

**Verified:** `pytest -q` → **176 passed** (+25 in `tests/test_visual_integration.py`);
`node --test` → **115 passed**; a stubbed end-to-end run proving a fact that exists ONLY in
a drawing reaches the expert prompt, is answered against a normal question, and returns
badged as drawing-sourced; a Chromium pass (10/10) on the badges, columns, cross-reference
and 390px, zero console errors.

> Previous round (2.4.0) below.

## 2.4.0 — Visual Intelligence + results workbook + in-app session dashboard

Plan: `docs/superpowers/plans/2026-08-02-visual-intelligence-results-workbook-admin.md`.
Front-end invariants 13–15 are new: **`docs/WEB_FRONTEND.md`**.

1. **Layer 0.5 — Visual Intelligence** (`services/hotdog/visual_intelligence.py`, NEW). Opt-in
   (`enable_visual_analysis` on `/api/analyze`, the "Analyze drawings, maps & images" switch on
   the web configure stage). A zero-AI-cost heuristic scores every page (raster coverage via
   `get_image_rects`, vector path density via `get_drawings`, text sparsity), the top pages
   (cap `BIDBRIEF_VISUAL_MAX_PAGES`, default 25) are rendered ≤1568px and sent to the vision
   model (`BIDBRIEF_MODEL_VISION` overrides; defaults to the analysis model) through
   `completion_params`. Each finding appends a `[VISUAL CONTENT]` block to the page text BEFORE
   windows are built — the L3 experts read it inside normal windows and cite `<PDF pg X>`
   naturally — and is collected as `visual_findings` for results + exports. **ADDITIVE ONLY:
   with the box off the pipeline is byte-identical; every failure is non-fatal**
   (`visual_scan_failed` event, analysis continues).
2. **Findings surfaces**: `visual_findings` rides `get_browser_output` /
   `_build_partial_browser_output` → `_transform_to_legacy_format` → `/api/results` (all four
   session types), `results_ready`, and the Excel export, which gains a **Visual Intelligence
   sheet** (Page / Type / Title / What It Shows / Labels & Callouts / Key Facts). The HTML
   report gains the same table. Progress events `visual_scan_start/page_complete/complete/
   failed` narrate under the 12% window band (`bb-status.js`).
3. **Results = the Excel workbook** (`bb-results.js` rebuilt): sheet tabs on glass —
   Executive Summary (stats + Key Document Details in the Excel order/labels), Detailed
   Results (#/Section/Question/Answer/Answer Summary/PDF Pages/FN/Status), By Section
   (header bands with rates), Document Intelligence, Visual Intelligence, Footnotes —
   `sheetList()` decides which tabs a payload earns. Improve Results and Exports & Smart
   Analysis remain their own layers. The public helper API (`summarize/flatten/...`, used by
   bb-admin) is unchanged.
4. **Admin Session Dashboard in-app** (`bb-admin.js`): the hub entry renders on the design
   system instead of opening the legacy page — summary line, Refresh, lifecycle buckets,
   and per-session **View results / mode-aware Excel export (restored) / Stop**. The legacy
   `/admin/sessions` route still answers; nothing links to it.
5. `/health` → **2.4.0** (the FIRST `/health` route — the second registration is dead code).

**Verified:** `pytest -q` → **149 passed** (was 130; +19 in `tests/test_visual_intelligence.py`);
`node --test tests/js/*.test.js` → **110 passed** (was 97; +13 in `bb-visual-workbook.test.js`);
page-selection heuristic exercised against a real PyMuPDF-built PDF (drawing page picked, text
page skipped); full Chromium walkthrough (login → configure toggle → payload flag → all six
workbook sheets → in-app session dashboard → 390px) — **zero console errors**.

**What only the user can verify (first real run):**
1. **A live vision call on production** — no OpenAI key exists on this dev machine, so
   gpt-5.4/5.5 accepting `image_url` content was not exercised end-to-end. The layer is
   failure-safe (worst case: `visual_scan_failed`, standard analysis unaffected). If the
   model family rejects images, set `BIDBRIEF_MODEL_VISION` on Render to a vision-capable
   model — no deploy needed.
2. Cost/latency of a real visual run on a drawing-heavy spec (25-page cap ≈ bounded; tune
   `BIDBRIEF_VISUAL_MAX_PAGES` on Render if needed).
3. The workbook view against a real completed analysis (synthetic payloads exercised every
   sheet, but not a live 100-question run).

> **iOS note:** the web results view now presents as a workbook while iOS 2.1.3 keeps the
> staged results UX, and iOS does not send `enable_visual_analysis` (Swift Codable ignores
> unknown keys, so the new `visual_findings` field is invisible to its decoder). The user
> deliberately deferred the iOS port of 2.4.0.

> Previous round (2.3.0) below.

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
