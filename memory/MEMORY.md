# Project Memory Index — BidBrief (Flask backend + web front-end)

- `debug_history.md` — resolved debugging sessions (read before any debug work)
  - 2026-07-26: "nobg" brand PNGs are white-backed RGB — use the `*-transparent.png` twins (colour type 6)
  - 2026-07-26: iOS ratios don't port to desktop viewports unchanged (the orb mark)
  - 2026-07-26: byte-preserving inline-script splits must assert the identity, and write with `newline=''` on Windows
  - 2026-07-26: `/health` is registered twice in `app.py`; only the first route answers
  - 2026-08-02: calibrate visual-page heuristics against a REAL PDF, not imagined fixture numbers
  - 2026-08-02: a "module never loaded" false alarm — the wait condition was wrong, twice
  - 2026-08-03: **durable storage, four defects in one night** — TIMESTAMPTZ→aware datetimes 500'd
    every authenticated page; PgBouncer rejects `options='-c ...'`; a failed init LEAKED the whole
    connection pool; a diagnostic gated the data and hung the dashboard. **Read before touching
    `services/persistence.py`.**
  - 2026-08-03: Document Intelligence vanished from the web but not Excel — a fixed-key transform
    dropped it and `finish()` overwrote the richer payload
  - 2026-08-03: Excel fixed row heights + wrap = invisible text (compute heights AFTER the clamp)

## Digest / architecture nav

- `digestsynopsisSUMMARY.md` — canonical backend digest. Latest delta: **Δ 2026-08-03 — durable
  storage shakedown + results/export fixes (2.5.1→2.5.6)**; before that Δ 2026-08-02 (Visual
  Intelligence woven into HOTDOG, results-as-workbook, GPT-5.6 tiers) and Δ 2026-07-27 (Free Beta).
- `docs/WEB_FRONTEND.md` — the web client's module map, `BB` namespace contract, state model, and the
  nine invariants (WYSIWYG `enabled_sections`, Q-gen always sends the analyzer doc, no `high_power` on
  Q-gen, lossless question-config round-trip, `answer_summary` placement, `analysis_complete` is not
  terminal, the first events poll can 403, alpha-keyed logos only, bonus users never see the sessions
  dashboard).
- `HANDOFF.md` — current state and what only the user can verify. **Live: 2.5.6.**
- `docs/PERSISTENCE.md` — Neon setup, what survives a restart, and the storage design rules.
  `DATABASE_URL` IS set on Render. Pre-flight for ANY connection-parameter change:
  `DATABASE_URL='...' python -m services.persistence`.
- `docs/superpowers/plans/` — the executed implementation plans.

## Cross-repo

- The **iOS app is the design source of truth** for the web UI:
  `C:\Users\pr0ph\Documents\AI LLC\Apps\BidBrief iOS` — `Sources/DesignSystem/Theme.swift` (palette),
  `OrbBackground.swift`, `Components.swift`, `Sources/Features/**` (screen structure),
  `Sources/App/AppModels.swift` (state + onboarding cue rules).
- Deploy is `git push origin master` → Render auto-redeploy. Confirm by watching `/health`'s `version`
  flip; the status code never blips (zero-downtime cutover).
