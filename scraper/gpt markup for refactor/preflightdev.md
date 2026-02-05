Pre flight

City Scraper Pre Flight



# PRE-FLIGHT VALIDATION (BEFORE RESEARCH) — SINGLE MUNICIPALITY + SINGLE TABLE MODE (SANITARY-SEWER-PRIMARY)



## PURPOSE

Run a deterministic “gate” that prepares research for exactly:

- ONE municipality (one city/agency context), and

- ONE output table (either “Municipal Systems Information” OR “Municipal Public Bids”)

…with **Sanitary Sewer as the primary focus** (while still checking Public Works/Utilities and Stormwater/MS4 where relevant).



## INPUTS (REQUIRED)

### A) Municipality in scope (single)

- Municipality (City): <CITY NAME>

- State: <STATE>

- County/Region (optional): <VALUE OR "Not provided">



### B) Table mode (choose exactly one)

- Table Mode: "Municipal Systems Information"  OR  "Municipal Public Bids"



## MISSING-INPUT HANDLING (ASK, DO NOT DECLARE FAILURE)

If any required input is missing or unclear, ask ONLY for what is needed, then STOP.



### If Municipality (City) or State is missing, ask:

1) What municipality (City) should I research for this run?

2) What state is that municipality in?



### If Table Mode is missing or unclear, ask:

3) Which table should I produce for this run: "Municipal Systems Information" or "Municipal Public Bids"?



Rules:

- Ask only the questions necessary to fill missing inputs.

- Do not browse, extract, or generate tables until the missing inputs are provided.



## STEP 1 — MUNICIPALITY ID NORMALIZATION (DO NOT INFER)

Once inputs are provided, output the normalized identifiers exactly as provided:

- Municipality (City): <as provided>

- State: <as provided>

- County/Region: <value OR "Not provided"> **(MAY OBTAIN COUNTY/REGION ID INFO FROM HIGH CONFIDENCE INFERENCE WITH REASONING TO SUPPORT FINDING)**

Rules:

- Do not “correct” spelling unless a primary source explicitly shows an official naming variant; if so, record the variant in Notes later.



## STEP 2 — JURISDICTION CONFIRMATION (WHO OWNS/OPERATES WHAT) — SANITARY SEWER FIRST

Determine, using primary sources where possible, the responsible entity for the relevant assets.



### 2.1 Required determinations (no guessing; use "Not found")

Populate:

- Primary sanitary sewer collection owner/operator: <agency name OR "Not found">

- Primary sanitary sewer maintenance/CCTV/cleaning operator (if distinct): <agency name OR "Not found">

- Primary storm drainage owner/operator (storm sewer/storm drain/MS4) (secondary): <agency name OR "Not found">

- Notes on split responsibility (city vs authority vs county vs district): <text OR "Not found">



### 2.2 Evidence standard to proceed (do not stop; do not guess)

You must attempt to locate at least one credible statement indicating responsibility for the system(s) relevant to the selected Table Mode:

- If Table Mode = "Municipal Systems Information":

  - Seek evidence of responsibility for **sanitary sewer** assets (minimum).

  - Stormwater/MS4 responsibility should be captured if available, but sanitary sewer is the priority.

- If Table Mode = "Municipal Public Bids":

  - Seek evidence of which procurement entity publishes bids for the municipality/agency, and preferably evidence that it covers utility/public works (sanitary sewer-related) procurement.



If you cannot find such evidence:

- Populate the fields as **Not found**

- Continue to STEP 3 (baseline source map)

- Assign readiness as PARTIAL (but continue; do not terminate research unless instructed elsewhere)



## STEP 3 — BASELINE SOURCE MAP (WHERE YOU WILL LOOK FIRST) — SANITARY-SEWER-PRIMARY

Build a municipality-specific source set before extracting any numbers or bid details.



### 3.1 Required source categories (use "Not found" if absent)

Always attempt to identify:

- Official municipal website (home)

- Public Works / Utilities department page

- **Sanitary Sewer / Wastewater / Sewer Utility page (PRIMARY)**

- Stormwater / MS4 page (secondary, if present)

- Procurement / bids page OR bid portal used

- GIS / open data portal OR utility map page (look specifically for wastewater/sewer layers)

- CIP / budget documents repository (council packets, finance docs, annual reports; prioritize wastewater/sewer CIPs)

- Incident / compliance sources (SSO/CMOM, enforcement, environmental reporting), if applicable



### 3.2 Source map entry fields (for every category)

For each category, output:

- Source name (what it is)

- URL

- Expected contents (why it matters for THIS Table Mode, with sanitary sewer priority)

- Evidence excerpt (verbatim text showing relevance) OR **Not found**



## STEP 4 — TABLE-MODE-SPECIFIC PRE-CHECKS (DEFINITIONS + SEARCH KEYS)

This step prevents incorrect extraction due to mismatched terminology.



### 4A) If Table Mode = "Municipal Systems Information" (SANITARY-SEWER-PRIMARY)

You must pre-lock local definitions/terminology (as found in sources) for:

- “Sanitary sewer pipe” (collection vs interceptor vs force main)

- “Wastewater” vs “sewer” terminology (what the municipality uses)

- “Lift stations” / “pump stations” terminology (if relevant to assets requiring maintenance)

- “Positive storm drain pipe” (secondary; storm sewer vs storm drain naming)

- “Catch basins” vs “inlets” vs “structures” (secondary; local terminology)

Output:

- Definitions/terms found (with verbatim excerpts) OR **Not found**

- Notes on any ambiguity that could affect totals



### 4B) If Table Mode = "Municipal Public Bids" (SANITARY-SEWER-PRIMARY FILTER)

You must pre-lock procurement discovery and keyword filters:

- Identify the primary bid portal(s) used (city page or third-party host)

- Confirm that portal supports searching for:

  "sewer", "sanitary sewer", "wastewater", "lift station", "storm sewer", "storm drain"

Output:

- Portal name + URL

- Verbatim excerpt indicating where bids are posted OR **Not found**

- Confirmed search keywords to use (exact list above)



## STEP 5 — READINESS STATUS (PASS / PARTIAL / FAIL)

Assign exactly one:

- PASS:

  - Municipality + State present, AND

  - At least one credible sanitary-sewer responsibility source found (or procurement authority for bids mode), AND

  - Baseline source map includes at least the official site + Public Works/Utilities + **Sanitary Sewer/Wastewater** page (or bid portal for bids mode)

- PARTIAL:

  - Municipality + State present, BUT sanitary-sewer responsibility is unclear OR baseline sources incomplete

- FAIL:

  - Use FAIL only if, after asking, the user still does not provide required inputs (municipality/state and/or table mode). In that case, re-ask only the missing inputs and STOP.



## PRE-FLIGHT OUTPUT (WHAT YOU MUST RETURN BEFORE EXTRACTION)

Return a short pre-flight report (no proposals), consisting of:

1) Municipality normalization (City / State / County)

2) Jurisdiction confirmation (sanitary sewer owner/operator first; stormwater secondary; procurement if bids mode)

3) Baseline source map (required categories; sanitary sewer/wastewater highlighted)

4) Table-mode-specific pre-checks (4A or 4B)

5) Readiness status (PASS / PARTIAL / FAIL)



----------------------------------------------------------------

# REQUESTED EXPORTS (BY REQUEST ONLY) — EXCEL + WORD (VERY POLISHED)



## EXPORT REQUIREMENT

After you produce the selected table output for this run, you ASK THE USER IF YOU SHOULD also produce:

1) A professionally formatted Excel workbook export of the same content, AND

2) A professionally formatted Word document export of the same content.



These exports must contain the same information as the on-screen output (no missing fields).

All “no truncation / no placeholders / Not found handling” rules still apply.



## IF BINARY FILE EXPORT IS SUPPORTED IN THIS ENVIRONMENT

Create and provide both files directly:

- Excel: .xlsx

- Word: .docx

Provide the files with clear names (see naming convention) and make them available for download.



## IF BINARY FILE EXPORT IS NOT SUPPORTED IN THIS ENVIRONMENT

You MUST still provide export-ready outputs in addition to the on-screen table:

- Excel-ready: a clean CSV (RFC 4180 style) for each sheet, AND a brief “Import Instructions” note.

- Word-ready: a copy/paste-ready Word layout in Markdown that preserves headings and tables cleanly.



In either case, the exports must be “very very nice” in presentation and immediately usable.



## EXCEL WORKBOOK SPEC (LOOKS VERY NICE)

### Workbook structure (sheets)

- Sheet 1: "Pre-Flight" (the pre-flight report)

- Sheet 2: "Table Output" (the selected table for this run)

- Optional Sheet 3: "Sources" (normalized list of all sources used, one per row) if it improves clarity



### Excel formatting requirements

- Freeze top row on every sheet.

- Apply a clean table style with banded rows.

- Set consistent fonts and readable sizing.

- Wrap text for long cells; vertical top alignment for wrapped cells.

- Auto-fit or set thoughtful column widths (wide for quotes/notes/URLs).

- Use hyperlinks for Source URLs (clickable).

- Add filters to the header row.

- Keep date fields consistently formatted (e.g., YYYY-MM-DD) where applicable.

- Ensure no cell contains ellipses indicating truncation.



### Excel “Sources” sheet (if used)

Columns:

- Source name

- URL

- Document title (if applicable)

- Publisher/agency

- Access date (today’s date)

- What it supported (brief)

- Verbatim excerpt used (exact quote)



## WORD DOCUMENT SPEC (LOOKS VERY NICE)

### Document structure

- Title page (stylish, formatted and professional):

  - Municipality (City, State)

  - Table Mode

  - Date generated

- Section 1: "Pre-Flight Validation Summary"

- Section 2: Selected table output (same schema/order as the on-screen table)

- Section 3 (optional but preferred): "Source Appendix" listing sources and excerpts



### Word formatting requirements

- Use true heading styles (Heading 1/2/3).

- Tables must be readable:

  - Header row repeated across pages

  - Consistent column widths

  - Shading on header row

  - Borders visible but not heavy

  - Wrapped text for citations/notes

- Insert page numbers in footer.

- No truncation in tables; if a cell is long, it must wrap.



## FILE NAMING CONVENTION (USE EXACTLY)

Use safe filenames (no special characters except hyphen/underscore):

- Excel: <STATE>_<CITY>_<TABLEMODE>_YYYY-MM-DD.xlsx

- Word:  <STATE>_<CITY>_<TABLEMODE>_YYYY-MM-DD.docx

Where <TABLEMODE> is either:

- Municipal_Systems_Information

- Municipal_Public_Bids



## EXPORT CONTENT INTEGRITY RULE

- The on-screen output, Excel export, and Word export must match in content.

- If a field is **Not found** on-screen, it must be **Not found** in both exports.

- Every non-“Not found” value must be supportable by the listed Source URL(s) and Verbatim textual citations.