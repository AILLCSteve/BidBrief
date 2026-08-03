# 2.4.0 — Visual Intelligence, Results-as-Workbook, Admin Sessions In-App

> Web app only (iOS untouched). Four deliverables, one release.

## User requirements (verbatim intent)

1. **Visual deep-scan (opt-in, ADDITIVE).** An option (checkbox on configure) that adds AI vision
   processing of drawing/diagram/map/photo-heavy pages ON TOP of standard text analysis. It must
   never dilute or replace standard processing — with the box off, byte-identical behavior; with it
   on, extra signal only. Results + exports must surface answers gleaned from imagery.
2. **Results view = the Excel workbook.** The web results screen presents the same multi-sheet
   depth as the Excel export (Executive Summary / Detailed Results / By Section / Footnotes /
   Document Intelligence [+ Visual Intelligence]) in the existing bb-theme styling.
3. **Admin session Excel export restored** (per-session, mode-aware).
4. **Admin sessions panel streamlined** — rebuilt in-app on the bb design system, replacing the
   legacy-styled `/admin/sessions` new-tab page.

## A. Backend — `services/hotdog/visual_intelligence.py` (NEW)

`VisualIntelligenceScanner(openai_client, model, max_pages, max_parallel=3)`.

- **Detection (no AI cost, pure + unit-testable):** `score_page(text_chars, image_coverage,
  image_count, drawing_count)` → float; `is_visual_page(score)` threshold. The fitz walk
  (`collect_page_stats`) computes image rect coverage (`page.get_image_rects`), drawing count
  (`page.get_drawings`, guarded), text chars. Candidates ranked by score, capped at
  `BIDBRIEF_VISUAL_MAX_PAGES` (default 25).
- **Render:** `page.get_pixmap` scaled to max dim ~1568px → PNG → base64 data URL.
- **Vision call:** AsyncOpenAI chat.completions with image content part, THROUGH
  `services.ai_models.completion_params` (mandatory adapter), `response_format=json_object`,
  semaphore(3). Prompt: construction/civil engineering visual analyst — transcribe labels,
  dimensions, callouts, legends, scales, station numbers; classify page kind
  (drawing|map|photo|table|chart|mixed); JSON out.
- **Augmentation:** append a `[VISUAL CONTENT — AI analysis of ...]` block to the matching
  `PageData.text` BEFORE windows are created → experts see it inside normal windows and cite
  `<PDF pg X>` naturally. Zero change to prompts/pipeline otherwise.
- **Findings:** `[{page, kind, title, description, extracted_text, key_facts[], confidence}]`
  kept on `orchestrator.visual_findings` for results + exports.
- Failure-safe per page AND per layer (`visual_scan_failed` event, analysis continues).

**Orchestrator:** ctor gains `enable_visual_analysis=False`. In `analyze_document`, after
`extract_pdf`, run the scan (events `visual_scan_start` / `visual_page_complete` /
`visual_scan_complete`), THEN `create_windows(pages)` (moved after the scan so windows carry the
enrichment). `get_browser_output` + `_build_partial_browser_output` attach `visual_findings`.

**app.py:** `/api/analyze` reads `enable_visual_analysis` (bool, no entitlement gate — standard
tier, cost bounded by page cap); passes to orchestrator. `_transform_to_legacy_format` passes
`visual_findings` through. Completion stores it on `completed_analyses` (like `dynamic_tables`);
`/api/results` (all 4 session types) and the Excel export route attach it.

**excel_dashboard.py:** new `Visual Intelligence` sheet (after Document Intelligence) when
`visual_findings` present: Page, Type, Title, Description, Extracted Labels & Data, Key Facts.

## B. Web results → workbook (bb-results.js, bb-screens.css)

Overview: stats header + **sheet tab strip** (`.bb-sheet-tabs`, workbook-tab affordance in
bb-theme glass) + sheet panel:

| Sheet tab | Mirrors Excel sheet | Content |
|---|---|---|
| Executive Summary | Sheet 1 | stats rows (total/answered/rate/avg confidence/date) + Key Document Details in the same preferred order + partial banner |
| Detailed Results | Sheet 3 | full table: #, Section, Question, Answer (click-expand), Answer Summary, PDF Pages, FN, Found/Not-Found status pill |
| By Section | Sheet 4 | per-section header band (name + n/m + rate) + section table with the Excel columns |
| Document Intelligence | dyn sheet | existing dynamic-tables renderer (only when tables exist) |
| Visual Intelligence | NEW sheet | per-page finding cards: kind chip, title, description, extracted data, key facts (only when findings exist) |
| Footnotes | Sheet 6 | numbered footnote table |

Improve Results + Exports & Smart Analysis remain (hub buttons under the workbook). The old
separate "Table View" stage is superseded by Detailed Results. `BB.results` public API
(summarize/flatten/answerSummaryOf/isAnswered/confidenceOf/toCsv/ingestLiveAnswers) is preserved —
bb-admin.js consumes it.

## C. Configure toggle (bb-analyze.js, bb-state.js)

`analysis.visualAnalysis` (default false, cleared on reset). New "Visual Intelligence" card with an
iOS switch: "Analyze drawings, maps & images — adds vision processing of visual-heavy pages on top
of the standard analysis; standard processing is unchanged." `buildAnalyzePayload` adds
`enable_visual_analysis`.

**bb-status.js:** friendly lines + pre-window fractions (~0.06–0.11) for the visual_scan events.

## D. Admin sessions in-app (bb-admin.js)

`ENTRIES.sessions` renders in-app (`path.push('sessions')`) instead of `window.open('/admin/sessions')`.
New screen: summary chips (active/completed/partial/legacy counts), Refresh, bucket groups with
session cards — filename, status chip, owner, `sessionMeta` line, actions: **View results** (modal,
same pattern as the beta manager), **Excel** (mode-aware: bestprep → `/api/export/bestprep-excel/`,
else `/api/export/excel-dashboard/`), **Stop** for active sessions (`POST /api/stop/<sid>`).
Legacy `/admin/sessions` route stays but nothing links to it.

## E. Version + docs

`/health` (the FIRST registered route, ~line 863 — the second is dead per debug history) → 2.4.0.
Update `docs/WEB_FRONTEND.md`, `digestsynopsisSUMMARY.md` Δ, `HANDOFF.md`, `memory/debug_history.md`
if anything fights back.

## F. Tests

- `tests/test_visual_intelligence.py`: score/select pure fns; enrichment block format; finding
  parse tolerance; orchestrator default-off; Excel sheet present/absent; legacy passthrough.
- `tests/test_web_ui.py`: served assets carry the new markers (enable_visual_analysis in
  bb-analyze.js, sessions dashboard fetch in bb-admin.js, sheet tabs in bb-results.js).
- `tests/js`: bb-analyze payload flag; bb-results sheet-list/status helpers (pure); bb-admin
  export-URL + bucket helpers.
- Full suites: `python -m pytest -q` (130 baseline) + `node --test tests/js/*.test.js` (97 baseline).
- Playwright pass: login → configure (toggle) → admin dashboard → results view with synthetic
  payload; zero console errors, desktop + 390px.

## G. Ship

Commit granularity: backend visual layer → exports/results → web workbook UI → admin dashboard →
docs/version. Push `master` → Render auto-deploy → watch `/health` flip to 2.4.0.
