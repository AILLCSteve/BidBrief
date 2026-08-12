# Debug History — BidBrief (Flask backend + web front-end)

Read this before debugging anything in this repo. Also read
`~/.claude/memory/debug_history.md` (global, shared across projects).

---

## 2026-08-12 (c) — The E2E button settled it: the database was fine, the store was racing itself (2.5.13 → 2.5.14)

**What one click of `/api/admin/storage/e2e` proved that a week of reasoning
could not:** write 36ms · read 31ms · delete 44ms against live Neon. The
database, credentials, and pooled endpoint were healthy the entire time. Every
"cannot connect" this week was self-inflicted.

**The hang-leak (2.5.13).** The status line's error had NO `[pool: …]` suffix —
the psycopg_pool logger capture heard nothing — so connections were not failing
to open; they were being taken and never returned. A query through PgBouncer can
hang forever on a healthy socket (the pooler ACKs while the backend never
answers): keepalives can't fire, psycopg has no read timeout, statement_timeout
is rejected at startup. Fix: every operation runs under a 30s watchdog firing
`conn.cancel_safe()` (out-of-band on its own socket — the only thing that can
interrupt a stuck recv). **Absence of a captured pool error + PoolTimeout =
leak, not connectivity.**

**The TOCTOU race (2.5.14).** The three-strike self-heal nulls `self._pool` from
whatever thread trips it. `_run` checked the attribute then dereferenced it
AGAIN → `'NoneType' object has no attribute 'connection'`, observed in
production BETWEEN two successful steps of one request (the dashboard's parallel
status fetch tripped the discard). Fix: snapshot the pool reference once per
attempt; a discarded-but-referenced pool raises PoolClosed, already retriable.
**Rule: any attribute a self-healing path can null must be read exactly once
into a local.**

**Evidence destroyed by success (2.5.14).** The E2E reported "Last error:
unknown" for a failed run because the LATER delete step succeeded and cleared
`last_error` before the report read it. Diagnostic steps must capture error
state at the instant of failure, not at the end.

**Contradictory status line (2.5.13).** `health()` reported `enabled` from
before its own probe — which was itself the failure that disabled the store —
while `self_test()` saw the new state, producing "connected but (disabled: …)".
Status endpoints must report one consistent moment, and "disabled" should
attempt the reinit before being reported.

---

## 2026-08-12 (b) — "couldn't get a connection" says NOTHING, and four ways to lose an analysis (2.5.9 → 2.5.12)

After 2.5.8 fixed the malformed INSERT, storage still reported
`write_failed: set_setting: couldn't get a connection after 10.00 sec`.
The instinct was "Neon is asleep / over quota". It was not. Every defect below
was ours, and the first one is why the week was unfalsifiable.

### 1. PoolTimeout is a symptom with no diagnosis in it

Reproduced against a host that can never connect:

```
error connecting in 'pool-1': connection timeout expired   <- the REAL cause
PoolTimeout: couldn't get a connection after 10.00 sec     <- all the caller sees
```

**psycopg_pool opens connections on a background worker. When that fails it logs
the real reason to its OWN logger and hands the caller a bare PoolTimeout.**
Auth failure, SSL, connection cap, a sleeping compute and *pool starvation* are
all one sentence. Fix: a `logging.Handler` on the `psycopg_pool` logger keeps the
last real message; `last_error` appends it.

**Worse — two unrelated causes wear that same string:**
* connections cannot be ESTABLISHED (`connections_errors` climbing), or
* the pool is STARVED (`pool_size` at max, `pool_available` 0,
  `requests_waiting` high, `connections_errors` **zero**).

Only `pool.get_stats()` separates them, so it is now on `/api/admin/storage`.
Never debug a pool timeout without those counters again.

### 2. The pool was sized for 4 while gunicorn runs 10 threads

`gunicorn_config.py` sets `threads = 10`; `BIDBRIEF_DB_POOL_MAX` defaulted to
**4**, with `num_workers=1` — a single thread opening every connection, so all
ten serialize behind one `connect_timeout`. Now 10 and 3.

### 3. A broken pool could never rebuild itself

`enabled` was set False in exactly two places, both inside `init()`. No runtime
failure ever cleared it, and `_try_reinit()` returns immediately when `enabled`
is True. **A pool that broke once stayed broken for the life of the process** —
"it worked, then it stopped, and it stayed stopped". Three consecutive failures
now discard the pool so the next call rebuilds it.

### 4. Failed writes were silently discarded (the one that actually loses data)

`save_analysis()` returns **False** rather than raising, so a storage fault can
never fail an analysis. `_persist_analysis` **ignored the return value** — the
only signal there was. A 20-minute run finishing during a blip was gone for good.
Failed snapshots are now queued and retried every 60s (`pending_writes` on the
admin endpoint); first write and retry share one `_write_snapshot()`.

### Ruled out by experiment, not by argument

The pool's connection-creating worker thread **survives** repeated failures
(checked `threading.enumerate()` after forced failures) — so "the worker died"
is not a cause, however well it fits the symptom.

### The probe that writes nothing

`self_test()`'s analysis check now runs `EXPLAIN` on the real INSERT: it resolves
every column against the live schema (which is what a Python call in the column
list failed) while executing nothing. Paired with the settings round-trip, which
proves the connection can genuinely write. `count_analyses`/`list_analysis_index`
also exclude `__…probe…` ids so a diagnostic can never be counted as a user's
analysis.

### Still open, honestly

Which of "cannot connect" or "starved" was the live failure is **not** proven —
until 2.5.9 the system could not tell them apart. The counters answer it in one
reading now. Do not claim it is solved from a green test suite.

---

## 2026-08-12 — Every analysis write failed for six releases: a Python call inside SQL (2.5.8)

**Symptom, as reported:** storage behaved erratically for over a week — "at times
working, then suddenly claiming it cannot write, then claiming in-session memory
again." In Neon: `bb_settings` and `bb_beta_testers` held rows, **`bb_analyses`
was empty**, and no analysis ever survived a deploy.

**Root cause — one line, `services/persistence.py:328`:**

```sql
INSERT INTO bb_analyses
    (session_id, owner, pdf_filename, mode, status, _aware_utc(completed_at),
                                                    ^^^^^^^^^^^^^^^^^^^^^^^^
```

The 2.5.3 timezone hotfix (`97582e9`) wrapped the completed_at **parameter** in
`_aware_utc(...)` — correct — and the same edit also rewrote the matching text
inside the **column list**, where it is not a column but a syntax error.
Postgres rejected every analysis write with `syntax error at or near "("`,
`_run()` swallowed it exactly as designed, and the analysis went on succeeding
for the user. Shipped in 2.5.3 and live through 2.5.7.

**Why the symptoms looked intermittent (two separate reporting defects):**
1. `self_test()` round-tripped a **bb_settings** row. Settings writes were
   always valid, so the dashboard certified "storage writable" the entire time
   analyses were being dropped. *A probe must exercise the statement it speaks
   for* — the INSERT now lives in one `_INSERT_ANALYSIS` constant that both
   `save_analysis()` and the probe use, and the probe runs it for real inside a
   transaction it then rolls back (`psycopg.Rollback` is swallowed by the block,
   confirmed against psycopg 3.3.4 `_rollback_gen`), so it can never leave a row.
2. `last_error` was **sticky** — set on every failure, never cleared on success.
   One transient blip was reported forever, so the status line contradicted a
   store that was healthy at that moment. It now clears on success and names the
   failing operation (`save_analysis: ...`, not a bare driver message).

**How it was found — no database required.** Every statement the Store can
execute was captured through a recording fake, `%s` replaced with `NULL`, and
parsed by **pglast** (libpg_query — the real Postgres parser): 21 valid, 1
invalid, and the one invalid statement was the one table with no rows. That is
now `tests/test_persistence_sql.py`, which fails on the shipped code and passes
on the fix.

**The lesson that matters most:** the suite had 223 passing tests over this
module and could not see this, because **every fake connection recorded SQL
without ever parsing it**. A fake will happily "execute" anything. The project's
own recorded standing gap — "validated against reproductions and instrumented
fakes, never against a real database" — was exactly the blind spot, and the fix
is not the corrected line but the parser in the test path.

**Also note:** a failure-safe wrapper is correct (a Neon hiccup must never fail a
15-minute analysis) but it converts *every* bug beneath it into silence. Anything
swallowed that way needs a probe that runs the real statement, plus a status
readout that cannot go stale.

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

## 2026-08-03 — Durable storage: four failures in one night (2.5.0 → 2.5.6)

Enabling `DATABASE_URL` on Render surfaced four defects in a row. Every one was
mine, and every one was found by reproduction rather than reasoning. Read this
before touching `services/persistence.py`.

### 1. TIMESTAMPTZ took the whole site down (2.5.3)

**Symptom:** every page returned
`{"error":"An unexpected error occurred. Please try again.","success":false}`
immediately after `DATABASE_URL` was set.

**Reproduction first, on the exact live code** — put an aware datetime in
`active_sessions`, `GET /` → 500 with the byte-identical body. Traceback:

```
app.py check_auth_cookie
  if session['expires_at'] < datetime.now():
TypeError: can't compare offset-naive and offset-aware datetimes
```

psycopg's `TimestamptzLoader` returns *"a datetime with the timezone of the
connection"* — **aware**. Restored sessions carried it; `datetime.now()` is
naive; Python refuses the comparison. Because `/` is `@require_auth`, one bad
datetime 500'd every authenticated page.

**Fix:** nothing timezone-aware escapes `persistence.py` (`_naive_local` on every
read, `_aware_utc` on every write), AND `check_auth_cookie` normalizes both
sides and **fails closed** on anything unparseable. An auth check must never be
able to take the site down, whatever ends up in that field.

### 2. `options='-c statement_timeout=...'` is rejected by PgBouncer (2.5.6)

Added in 2.5.5 to stop query hangs. **Neon's pooled endpoint IS PgBouncer**,
which rejects unknown startup parameters — so every connection failed and the
pool timed out: `couldn't get a connection after 30.00 sec`. It had been working
minutes earlier.

**Rule:** through a pooled endpoint, only pass libpq CONNECTION parameters.
TCP keepalives (`keepalives`, `keepalives_idle`, `keepalives_interval`,
`keepalives_count`) plus `connect_timeout` give the same dead-socket protection
and are pooler-safe. Server-side `SET`/startup options are not.

### 3. A failed init LEAKED THE WHOLE POOL (2.5.6) — the actual escalation

The failure path did `self._pool = None` **without closing it**. A
`ConnectionPool` runs a background worker that keeps opening connections, so the
thread and its server-side connections survived. Combined with the 60s retry
added in the same release, that leaked a fresh pool **every minute** until the
database refused everything — turning a transient blip into a permanent
"couldn't get a connection".

**Fix:** teardown centralized in `_discard_pool()` (always `close()` before
dropping), `init()` serialized behind its own lock so concurrent retries cannot
build two pools, stale pool discarded before any re-init. Regression test tracks
pool construction vs close: 3 failed inits → 3 created, 3 closed, 0 lingering
threads.

**Rule:** never drop a pool/client reference. `close()` it. Anything with a
background thread leaks silently and only shows up as resource exhaustion later.

### 4. A diagnostic that gated the data (2.5.5)

The admin dashboard hung on "Loading sessions..." forever, and Refresh did
nothing. Cause: 2.5.4 chained `/api/admin/storage` **in front of**
`/api/admin/sessions`, so one slow database call blocked the entire list.

**Rule:** a diagnostic must never gate the data it describes. Run it alongside
and let it paint in when it answers. Verified with the storage endpoint stubbed
to never resolve — the list still renders.

### What measurement ruled out

A realistic completed-analysis snapshot is **0.41 MB** (10×10 questions, quote
piles, visual findings, dynamic tables, key details, 10K doc_context). Payload
size was never the problem — measuring it is what redirected the hunt to the
leak. Measure before optimizing.

### Standing gap

Every fix above was validated against reproductions, psycopg source and
instrumented fakes — **never against the real Neon database**, because no
Postgres exists on the dev machine. `DATABASE_URL='...' python -m
services.persistence` exercises connect → schema → write → read → cleanup and
would have caught the PgBouncer rejection before it shipped. Run it before any
future connection-parameter change.

---

## 2026-08-03 — Document Intelligence vanished from the web but not from Excel (2.5.1)

**Symptom:** the DI tab was missing from the web results while the Excel export
had the sheet — so the tables demonstrably existed.

**Cause, two halves:**
1. `_transform_to_legacy_format` rebuilds the payload from a FIXED key set, so it
   **drops** `dynamic_tables`/`intelligence_focus` (generated in `app.py` after
   the orchestrator finishes, not by the orchestrator). Only the `completed` and
   `legacy` branches of `/api/results` re-attached them; `partial` and `active`
   did not.
2. `bb-engine.finish()` **overwrote** `state.analysis.results` with whatever the
   follow-up fetch returned. `results_ready` carries the tables; a fetch landing
   on a thinner branch erased them.

Excel reads the session dict directly, which is why the two surfaces disagreed.

**Fix:** `_attach_dynamic_intel()` called by EVERY branch (never downgrades a
payload that already has tables), and `finish()` merges instead of overwriting
for `dynamic_tables`, `intelligence_focus`, `visual_findings`,
`key_requirements`, `footnotes`.

**Rule for this codebase:** any helper that rebuilds `legacy_result` from a fixed
key set silently drops app-level enrichments. Re-attach in one shared place, and
never let a later fetch downgrade a richer client payload.

---

## 2026-08-03 — Excel: fixed row heights hid wrapped answers (2.5.2)

`mobile_optimize` clamps the Answer column 60 → 42 chars and enables wrapping,
but the generator hard-coded `row_dimensions[row].height = 55` (~3.7 lines). An
800-character answer wraps to ~20 lines, so everything past line four was
invisible — present in the cell, impossible to see.

**Fix:** `autosize_rows()` computes height from real content against the FINAL
column widths and only ever GROWS a row (deliberate header heights survive).
It must run AFTER the clamp — measuring pre-clamp width under-sizes the row,
which is how this happened. Merged cells are measured across their whole span or
the summary sheets balloon. `_relieve_overflowing_columns()` widens a column
(bounded at 72) when 42 chars would push content past Excel's **409.5pt** row
ceiling.

**Known ceiling:** beyond ~2,000 characters no single Excel row can display a
whole cell. Not fixable in a row — needs a one-block-per-answer sheet.

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

## 2026-08-02 — "Module never loaded" was my wait condition, twice (web 2.4.1)

**Symptom:** after rewriting `bb-results.js`, a Playwright check reported `BB.results` was
`undefined`. `window.BB` held only the first 8 modules — everything from `bb-analyze.js`
onward was missing — with **zero console errors**. That reads exactly like a module throwing
at load time.

**It wasn't.** Two separate false alarms stacked:
1. The first probe waited for `#bb-tabbar`, which is **static markup in `index.html`**, so it
   resolves long before the ~16 classic scripts finish executing. I read `window.BB` mid-load
   and saw a partial namespace.
2. The retry waited on `window.BB.results && window.BB.boot` — but **`bb-boot.js` never
   attaches a `BB.boot` key**. The condition could never be true, so it timed out and
   "confirmed" the false diagnosis.

**What actually proved innocence:** listing network responses (all 19 JS files → 200) and
then `eval`ing each module's source in the page (all OK, `BB.results` became an object).

**Rules:** (a) when waiting for a classic-script app to be ready, wait on **the module you
are about to call**, never on static chrome; (b) before believing "the script threw", check
the response status AND eval the source — no console error plus a partial namespace almost
always means you looked too early; (c) verify a wait predicate's keys actually exist, or a
timeout will masquerade as a product bug.

**Related, same session:** `inner_text()` returns *rendered* text, so a heading styled
`text-transform: uppercase` fails a case-sensitive `in` check. Compare case-insensitively or
assert on `textContent`.

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
