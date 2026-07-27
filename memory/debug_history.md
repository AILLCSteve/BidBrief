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

## 2026-07-26 — Flask registers two `/health` routes; only the first answers

`app.py` defines `/health` twice (`health` at ~line 774 with the version payload, `health_check` at
~line 5173 with session counts). Different function names, same rule → Flask accepts both, and the
**first registered wins**. Editing the second one changes nothing. Note this before "fixing" a
`/health` payload that appears not to update.
