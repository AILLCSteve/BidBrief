# Project Memory Index — BidBrief (Flask backend + web front-end)

- `debug_history.md` — resolved debugging sessions (read before any debug work)
  - 2026-07-26: "nobg" brand PNGs are white-backed RGB — use the `*-transparent.png` twins (colour type 6)
  - 2026-07-26: iOS ratios don't port to desktop viewports unchanged (the orb mark)
  - 2026-07-26: byte-preserving inline-script splits must assert the identity, and write with `newline=''` on Windows
  - 2026-07-26: `/health` is registered twice in `app.py`; only the first route answers

## Digest / architecture nav

- `digestsynopsisSUMMARY.md` — canonical backend digest. Latest delta: **Δ 2026-07-26 — web front-end
  rebuilt to iOS parity (2.2.0)**; before that Δ 2026-07-06 (L6.5 summarizer, section filter, persona Q-gen).
- `docs/WEB_FRONTEND.md` — the web client's module map, `BB` namespace contract, state model, and the
  nine invariants (WYSIWYG `enabled_sections`, Q-gen always sends the analyzer doc, no `high_power` on
  Q-gen, lossless question-config round-trip, `answer_summary` placement, `analysis_complete` is not
  terminal, the first events poll can 403, alpha-keyed logos only, bonus users never see the sessions
  dashboard).
- `HANDOFF.md` — current state and what only the user can verify.
- `docs/superpowers/plans/` — the executed implementation plans.

## Cross-repo

- The **iOS app is the design source of truth** for the web UI:
  `C:\Users\pr0ph\Documents\AI LLC\Apps\BidBrief iOS` — `Sources/DesignSystem/Theme.swift` (palette),
  `OrbBackground.swift`, `Components.swift`, `Sources/Features/**` (screen structure),
  `Sources/App/AppModels.swift` (state + onboarding cue rules).
- Deploy is `git push origin master` → Render auto-redeploy. Confirm by watching `/health`'s `version`
  flip; the status code never blips (zero-downtime cutover).
