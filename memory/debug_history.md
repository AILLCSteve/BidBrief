# Debug History — BidBrief (Flask backend + web front-end)

Read this before debugging anything in this repo. Also read
`~/.claude/memory/debug_history.md` (global, shared across projects).

---

## 2026-07-26 — "Transparent" brand PNGs were white-backed RGB (web 2.2.0)

**Symptom:** the btools mark on the login page and behind every screen rendered as a pale grey
rectangle sitting on the planet. Nothing in the CSS was wrong.

**Root cause:** `branding/btools-iconlogo-nobg.png` and `btools-titlelogo-nobg.png` are **colour
type 2 (RGB, no alpha)** despite the "nobg" name — they are white-backed masters. The iOS repo
already knew this (`HANDOFF.md`: the nobg files were white-keyed to true transparency with PIL and
the results saved as the `*-transparent.png` twins), but the web build picked the wrong twin.

**Fix:** reference `btools-iconlogo-transparent.png` / `btools-titlelogo-transparent.png`
(colour type 6, RGBA) everywhere, and added a regression test that reads IHDR byte 25 of every
`/pics/brand/*.png` the pages reference and asserts colour type 6.

**Rule:** never trust a filename for transparency. `data[25] == 6` (RGBA) or `== 4` (grey+alpha);
`2` or `0` means it will paint a solid box. One line of Python confirms it:
`struct.unpack('>II', d[16:24])` for size, `d[25]` for colour type.

---

## 2026-07-26 — The orb mark was phone-proportioned on a desktop viewport

**Symptom:** the planet's brand mark (34% of the orb, ported straight from
`OrbBackground.swift`) collided with the upload orb and titles on a 1280px screen.

**Cause:** on iOS the orb is phone-width, so a 34% mark is small in absolute terms. On the web the
planet is capped at `min(100vw, 760px)` while the layout is much wider — the same ratio produces a
260px mark right where the content sits.

**Fix:** 15% width, 45% opacity, moved higher on the planet. **Rule:** ratios ported from a phone
layout need re-derivation against the web's max-width caps; port the *intent* (an engraved,
recessive mark), not the number.

---

## 2026-07-26 — Splitting a 4,438-line inline `<script>` safely

**Approach that worked** (zero behaviour risk): cut on the existing `// ====` section banners into
contiguous ranges, write the pieces with Python (`open(..., newline='')` — otherwise Windows
translates `\n` and doubles the CR on a CRLF file), then **assert the concatenation equals the
original slice** before touching `index.html`. Follow with `node --check` on each file to prove no
cut landed inside a function.

**Rule:** a mechanical refactor is only safe if it is *verifiably* mechanical. Assert the identity
in the same script that does the split.

---

## 2026-08-02 — Calibrate visual-page heuristics against a REAL PDF, not just unit fixtures (2.4.0)

**What happened:** the Visual Intelligence page-selection heuristic (`score_page` in
`services/hotdog/visual_intelligence.py`) passed all its hand-written unit tests, then missed an
actual drawing page in a PyMuPDF-generated test PDF: a near-textless page with a 60-line vector
diagram scored 0.075 against a 0.35 threshold, because the "vector CAD sheet" fixture had been
imagined at 600 paths. Real simple diagrams are an order of magnitude lighter.

**Fix:** added a sparse-page rule (`text < 600 chars AND drawing_count >= 40` ⇒ bonus) and kept a
real-fitz round-trip in the session before shipping. **Rule:** any content-detection heuristic
gets at least one assertion built from a REAL artifact of the library that will feed it —
hand-picked fixture numbers encode your guess, not the distribution.

**Also this round (facts, not bugs):** the vision pass appends `[VISUAL CONTENT]` blocks to
`PageData.text` BEFORE `create_windows` — PageData is `frozen=True`, so pages are REPLACED, not
mutated. `visual_findings` ride `get_browser_output`/`_build_partial_browser_output`, so every
results path and the Excel export inherit them with zero per-route wiring.

---

## 2026-08-02 — Python Playwright ignores browsers cached by the MCP driver

`%LOCALAPPDATA%\ms-playwright` had `chromium-1234` (installed by the Claude MCP playwright
plugin) but Python's `playwright` package wanted `chromium_headless_shell-1208` — each driver
pins its own build directory, so a populated cache does NOT mean YOUR driver can launch.
`python -m playwright install chromium` (no admin needed) fixes it in ~1 min. Recognize the
symptom: `Executable doesn't exist at ...chromium_headless_shell-<N>...` while `ls` shows other
chromium directories right next to it.

---

## 2026-07-26 — Flask registers two `/health` routes; only the first answers

`app.py` defines `/health` twice (`health` at ~line 774 with the version payload, `health_check` at
~line 5173 with session counts). Different function names, same rule → Flask accepts both, and the
**first registered wins**. Editing the second one changes nothing. Note this before "fixing" a
`/health` payload that appears not to update.
