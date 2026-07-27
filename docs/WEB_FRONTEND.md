# BidBrief Web Front-End (2.3.0)

The web app was rebuilt in 2.2.0 to match the BidBrief iOS app's visual language
and information architecture. This is the map of what owns what, and the
invariants a future change must not break.

## Shape of the app

`index.html` is a shell, not an app: the orb layer, four page containers, the
tab bar, a banner host, and a modal host. Everything else is CSS + classic
browser scripts served from `shared/assets/` by the pre-existing
`/shared/<path:filename>` Flask route (`app.py`). There is no bundler, no
framework, and no external CDN.

```
index.html
├── #bb-orb            the suspended planet (fixed, z-index -1)
├── main.bb-app
│   ├── #bb-page-analyze      Analyze  (upload → configure → progress → results)
│   ├── #bb-page-questions    Question Hub
│   ├── #bb-page-admin        Admin / Bonus (+ CityScraper)
│   └── #bb-page-settings     Settings
├── #bb-tabbar         floating capsule tab bar with the "Next" cue
├── #bb-banner-host    bottom toasts
└── #bb-modal-host     one modal at a time
```

## Module map

| File | Owns |
|---|---|
| `css/bb-theme.css` | Design tokens (the exact iOS `BBTheme` hex values) and every primitive: `.bb-glass-card`, `.bb-btn-glow`, `.bb-btn-ghost`, `.bb-hub-btn`, `.bb-stage-header`, `.bb-eyebrow`, `.bb-back-chip`, `.bb-field`, `.bb-segmented`, `.bb-toggle`, `.bb-banner`, `.bb-tabbar`, `.bb-modal`, and the `bb-breathe` / `bb-throb` animations |
| `css/bb-orb.css` | The planet: space gradient, halo, body, rim light, gleam, orbital ring, moon, legibility scrims, `--bb-drift` parallax |
| `css/bb-screens.css` | Screen layout: app column, upload orb, progress ring + phase track, feed rows, results tables, scraper grid |
| `css/bb-login.css` | The login card |
| `js/bb-ui.js` | `BB.ui` DOM/format helpers (`el`, `fill`, `card`, `stageHeader`, `hubButton`, `toggleRow`, `banner`, `escapeHtml`, `html` tagged template) and `BB.modal` |
| `js/bb-orb.js` | `BB.orb.mount/setDrift`, the deterministic starfield, `driftFor(index, count)` |
| `js/bb-state.js` | `BB.state` — the mirror of the iOS `AppModels`. Analysis, questionHub, navigation, session, and `onboardingHint()` |
| `js/bb-status.js` | `BB.status` — the transcription of `AnalysisPhase` / `AnalysisStatus`: event → phase, detail, fraction |
| `js/bb-shell.js` | `BB.shell` — tab bar, page routing, the cue, `/api/user/info` |
| `js/bb-engine.js` | `BB.engine` — the pipeline client: upload, analyze, event polling, results fetch with backoff, stop, second pass / RAG, Smart Analysis. **No DOM rendering.** |
| `js/bb-analyze.js` | `BB.analyze` — idle / uploading / configure stages and `buildAnalyzePayload` |
| `js/bb-progress.js` | `BB.progress` — orb ring, phase track, Live Activity popup |
| `js/bb-results.js` | `BB.results` — overview / sections / key details / intelligence / improve / exports / table, plus CSV + HTML export and the Smart Analysis renderer |
| `js/bb-questionhub.js` | `BB.questionHub` — hub menu, sections, questions, question edit, libraries stage, load/save |
| `js/bb-qgen.js` | `BB.qgen` — the Create / Add Question Set screen and `buildGeneratePayload` |
| `js/bb-libraries.js` | `BB.libraries` — localStorage snapshots + the one-time Starter Set seed |
| `js/bb-admin.js` | `BB.admin` — admin/bonus hub, the Bonus Features manager, and the Free Beta manager (switch, testers, quotas, per-tester sessions) |
| `js/bb-login.js` | `BB.login` — the sign-in page: orb mount, `?error=` copy, and the Free Beta Testing button + terms modal |
| `js/bb-settings.js` | `BB.settings` |
| `js/bb-scraper.js` | `BB.scraper` — CityScraper on glass |
| `js/bb-boot.js` | Registers the pages and starts the shell. The only entry point. |

Every module is a classic script wrapped in an IIFE that attaches to
`window.BB`. Load order is the order in `index.html`; `bb-boot.js` is last.

## State and the onboarding cue

`BB.state` is the single source of truth. The cue rules live in
`onboardingHint()` and nowhere else:

- No pending document → `none`.
- A pending document with `needsQuestionChoice` **or** an unconfirmed set →
  `chooseQuestions` (the tab bar throbs **Questions**).
- Otherwise → `goAnalyze`, or `startAnalysis` when you are already on Analyze.

`setConfirmed(true)` clears `needsQuestionChoice`. That is the 2.1.3 fix: the
cue points at the Questions tab, and following it bypasses the Analyze
prompt-card, so confirming a set from anywhere must resolve the pending choice
or the cue sticks on Questions forever.

## Invariants — do not break these

1. **`enabled_sections` is WYSIWYG.** `buildAnalyzePayload` always sends the
   explicit list of checked section ids. Never collapse a full selection to
   `null`/absent based on a count that could be stale.
2. **Q-gen always sends the analyzer document.** `buildGeneratePayload` sends it
   as the primary `file` (`source_kind=context`) when there is no PDF
   questions-source, and as `context_file` alongside the questions-source PDF
   otherwise. The Create screen auto-adopts `BB.state.analysis.file` on entry so
   this happens without the user asking. Dropping either half reproduces the
   2.1.1 / 2.1.2 "questions unrelated to the document" bug.
3. **Never send `high_power` for question generation.** The backend forces the
   high-power model for every user on that endpoint; sending the flag hits the
   entitlement gate and 403s non-premium users.
4. **Question config round-trips losslessly.** `buildSaveBody` PUTs the sections
   untouched. `required`, `expected_type`, `section_description` and
   `section_summary` drive backend expert generation.
5. **`answer_summary` renders between the answer and the page citations** on
   every surface (section detail, table view, CSV, HTML export).
6. **`analysis_complete` is not the end.** Only `results_ready` — or a
   successful `/api/results` fetch — completes the run. `/api/results` is
   retried with backoff because `/api/stop` can return first.
7. **The first `/api/events` poll can fail** (session-registration race). The
   engine tolerates several failures before surfacing an error.
8. **Only alpha-keyed logos.** The `*-nobg.png` masters are white-backed RGB and
   paint a white box over the planet; use the `*-transparent.png` twins. A test
   asserts the PNG colour type.
9. **Bonus users never see the sessions dashboard.** `BB.admin.entriesFor`
   gives non-admin premium users CityScraper only. The same rule covers the Free
   Beta manager — it can lift quotas and delete testers, so it is admin-only.
10. **Every beta login mints its own identity.** `/auth/beta-login` creates a new
    `beta-<hex>` user per click. Analyses are owner-scoped by username, so a
    shared beta account would let any tester read any other tester's results.
11. **`/api/analyze` requires authentication.** Without it a caller starts an
    analysis with `owner=None`, which bypasses the beta document quota AND
    produces an unowned session that `_is_authorized_for_session` lets anyone
    read. Never remove that decorator.
12. **The beta switch has an env-var floor.** `BETA_LOGIN_ENABLED` sets the boot
    state; the admin toggle overrides it in memory. Everything in this process is
    wiped on a Render deploy, so the env var is what survives — if free beta must
    stay open across deploys, it has to be set there, not just toggled in the UI.

## Tests

```bash
python -m pytest tests/test_web_ui.py -q     # served structure + invariants
node --test tests/js/*.test.js               # pure-logic unit tests, zero deps
```

`tests/js/_harness.js` evaluates a browser module against a minimal fake
`window`. Use its `plain()` helper when asserting on objects built inside that
sandbox — `deepStrictEqual` compares prototypes and the realm differs.

For a browser pass, run the app with test credentials and drive it with
Playwright:

```bash
AUTH_USER1_EMAIL=admin@test.local AUTH_USER1_PASSWORD=testpass123 \
  python -c "from app import app; app.run(port=5111)"
```

Note that `.bb-btn-glow.bb-pulses` and `.bb-throb` animate forever, so Playwright
clicks on the primary button and the cued tab need `{ force: true }` — its
actionability check waits for the element to stop moving.

## Adding a screen

1. Add a page container to `index.html` if it is a new tab, or a stage to an
   existing module's stage stack.
2. Build the UI from `BB.ui` primitives — never hand-write glass/button CSS.
3. Read and write state through `BB.state`; call `BB.shell.refresh()` when a
   change should repaint the current page.
4. Add a `node --test` case for any pure logic and a `tests/test_web_ui.py`
   assertion for anything the served page must contain.
