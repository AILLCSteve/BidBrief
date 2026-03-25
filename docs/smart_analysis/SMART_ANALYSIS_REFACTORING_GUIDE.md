# Smart Analysis Refactoring Guide

**Authority level:** Prescriptive. Follow this guide before touching any file in `services/smart_analysis/`.

---

## When to Refactor

Do not refactor preemptively. Refactor when one or more of these symptoms appear in real output:

| Symptom | Likely Cause | Affected Agent |
|---------|-------------|----------------|
| Assessment categories repeat across different document types | UNIQUE ASSESSMENT CATEGORIES rule not enforced or model non-compliant | SynthesisAgent |
| Lenses in SCOUT or MIRROR output are generic (e.g. "Financial Risk", "Legal") | LENS GENERATION RULE ineffective or absent | ScoutAgent, MirrorAgent |
| Benchmarks in expertise_profile are generic ("typical projects...") | EXPERTISE UNIQUENESS RULE ineffective | DocumentProfileAgent |
| Output counts fall below stated minimums | Token truncation or prompt non-compliance | SynthesisAgent |
| follow_up_direction fields are vague or single-step | Prompt instruction weak; may need example-driven prompt | Any agent |
| document_understanding is empty or missing major workstreams | DocumentProfileAgent failing silently or token-capped | DocumentProfileAgent |
| All risks are HIGH severity with no differentiation | Synthesis prompt not requiring severity calibration | SynthesisAgent |
| User question responses are thin or off-topic | UserInputAgent receiving insufficient context | UserInputAgent, ContextAggregator |
| Analysis ignores confirmed-absent items | doc_profile not consumed correctly downstream | Orchestrator, SynthesisAgent |
| 4-tier labels absent or inconsistent in output | Language discipline instruction degraded | SynthesisAgent |

---

## The 6-Phase Process

Never skip a phase. Every Smart Analysis refactor, regardless of scope, follows this sequence.

### Phase 1 — Analysis (read-only, no edits)

1. Read `digestsynopsisSUMMARY.md` (or the canonical digest) first.
2. Read `memory/debug_history.md` for confirmed architectural facts and past wrong assumptions.
3. Read the actual failing output — do not work from a description of the problem.
4. For each symptom, trace the execution path: which agent produced the output, what inputs it received, what prompt rule governs the behavior.
5. Grep for every function and field name you plan to change before forming a plan. Missing one site = broken build.

### Phase 2 — Plan

Write a complete plan before any edit:
- Every file to be changed
- Every function to be modified
- Every field to be added, removed, or renamed
- The order of changes (upstream before downstream)
- Interface preservation notes: if a field's name or type changes, list every consumer

### Phase 3 — Self-Critique

Before writing code, critique the plan:
- Does the plan cover every consumer of changed fields?
- Do fallback/empty return paths in each agent include all new required fields?
- Does the frontend rendering handle both the old and new field formats if you are changing a schema?
- Will token increases introduce unacceptable latency?
- Are prompt-only enforcement changes sufficient, or is post-processing validation required?
- What breaks if an agent times out or returns empty?

Revise the plan until critique finds nothing. Only then proceed to Phase 4.

### Phase 4 — Implement

File by file, per the plan. In dependency order (ContextAggregator → DocumentProfileAgent → parallel agents → SynthesisAgent → Orchestrator → Models → Frontend).

- **Read the exact lines before every Edit.** Never guess at indentation, variable names, or surrounding context.
- Use `replace_all: true` for identical repeated patterns (e.g. upgrading follow_up_direction field names across multiple prompt strings).
- Update empty/fallback return dicts in the same edit as the main prompt change.

### Phase 5 — Validate

Before committing:
1. Grep for every old symbol name, field name, and prompt instruction you changed. Any remaining hit = missed update.
2. Confirm all fallback dicts include every key accessed by downstream agents.
3. Confirm frontend rendering handles both old and new formats if schema changed.
4. State explicitly: what changed, what the behavioral difference is, what is not changed.

### Phase 6 — Commit and Push

One atomic commit covering all touched files. Commit message must include:
- Summary of the problem that prompted the refactor
- Per-file list of what changed
- Behavioral delta (what the system does differently)
- Commit hash reference if this supersedes a previous fix

---

## Per-Agent Refactoring Checklist

Use this checklist before and after touching each agent.

### ContextAggregator

Before:
- [ ] Does `_resolve_question_fields()` handle all field name variants in session data?
- [ ] Does `analysis_text` include all Q&A pairs and key_details_list entries?
- [ ] Does `rich_analysis_text` preserve full text and citations?

After:
- [ ] No downstream agent accesses raw session Q&A directly (all go through aggregator output)
- [ ] Both `analysis_text` and `rich_analysis_text` are produced for every session
- [ ] Legacy field name support is not removed

### DocumentProfileAgent

Before:
- [ ] Does `expertise_profile` prompt require specific figures, not generic descriptions?
- [ ] Does `document_understanding` block appear in prompt schema?
- [ ] Is `rich_analysis_text` (not `analysis_text`) used as input?
- [ ] Does the empty fallback include `document_understanding` with all sub-keys?

After:
- [ ] Empty fallback has all keys: `confirmed_present`, `confirmed_absent`, `unverified`, `expertise_profile` (5 sub-keys), `key_items` (6 sub-keys), `document_understanding` (5 sub-keys)
- [ ] max_tokens is appropriate for expected output size (currently 4500)
- [ ] Timeout is appropriate (currently 90s)

### ScoutAgent

Before:
- [ ] Does prompt include LENS GENERATION RULE (derive before apply)?
- [ ] Are follow_up_direction fields on `uncertainties` and `assumptions` the current 5-field format?
- [ ] Is max_tokens sufficient for minimum-compliant output?

After:
- [ ] LENS GENERATION RULE appears before the lens application instruction, not after
- [ ] No hardcoded lens category names appear in the prompt
- [ ] `scout_findings` passed to SynthesisAgent includes `lens_selection_reasoning`

### MirrorAgent

Before:
- [ ] Does prompt include LENS GENERATION RULE for adversarial dimensions?
- [ ] Does `stakeholder_perspectives` instruction require document-derived parties?
- [ ] Are follow_up_direction fields on `risks` and `missing_elements` the current 5-field format?

After:
- [ ] No hardcoded stakeholder type names (Owner, Contractor, Subcontractor) in prompt
- [ ] LENS GENERATION RULE appears before adversarial dimension application
- [ ] Fallback for failed agent includes all keys accessed by SynthesisAgent

### UserInputAgent

Before:
- [ ] Is the agent correctly skipped when no user questions are present?
- [ ] Does it receive `analysis_text` and `doc_context`?

After:
- [ ] Skip condition has not been accidentally removed
- [ ] Orchestrator handles `None` return from skipped agent correctly

### SynthesisAgent

Before:
- [ ] Do mandatory minimum counts appear in prompt?
- [ ] Does UNIQUE ASSESSMENT CATEGORIES rule appear in prompt?
- [ ] Does 4-tier language discipline block appear with definitions?
- [ ] Are follow_up_direction fields on `risks`, `opportunities`, `ambiguities` the current 5-field format?
- [ ] Is max_tokens sufficient for minimum-compliant output across all arrays?

After:
- [ ] Minimum count instruction specifies exact numbers (not "several" or "multiple")
- [ ] 4-tier definitions are precise and unambiguous
- [ ] evidence_classification includes minimum_count_notes
- [ ] max_tokens is 8000 or higher

### Orchestrator

Before:
- [ ] Does `_build_result()` extract `document_understanding` from `doc_profile`?
- [ ] Do all agent fallback/empty results include the full expected key set?
- [ ] Does `asyncio.new_event_loop()` pattern remain intact?

After:
- [ ] No new blocking I/O added outside the event loop
- [ ] All agent outputs are accessed via `.get()` with safe defaults, not direct key access
- [ ] `smart_analysis_results[session_id]` is set before the route returns

### Models

Before:
- [ ] Does `SmartAnalysisResult` include `document_understanding: Dict`?
- [ ] Does `SmartAnalysisItem.follow_up_direction` type match current field set?

After:
- [ ] All new fields have `field(default_factory=...)` defaults to avoid breaking cached result deserialization
- [ ] No required fields without defaults (cache may contain older result shapes)

---

## Token Budget Reasoning

### When to Increase max_tokens

Increase an agent's max_tokens when:
- Output is being truncated (arrays cut off mid-item, JSON not closed properly)
- The agent is required to produce more items than before (e.g. minimum count increase)
- A new output block was added to the prompt schema
- Input context grew significantly (e.g. after adding `document_understanding` to downstream prompts)

Do not increase max_tokens preemptively. Token spend increases latency and cost linearly.

### Sizing Guidelines

- Each SmartAnalysisItem (title + description + evidence + follow_up_direction) consumes approximately 150–250 tokens in output.
- A minimum-compliant SynthesisAgent response (5 risks + 5 opportunities + 5 ambiguities + 6 assessments + 5 insights + 6 follow-up questions + 5 recommendations + executive summary) requires approximately 5,000–6,500 tokens.
- Budget 20–30% headroom above the expected minimum-compliant output size.
- The parallel stage latency is bounded by the slowest of SCOUT/MIRROR. Give them equal budgets unless there is a specific reason for asymmetry.

### Diminishing Returns

Beyond 8,000 tokens for Synthesis and 5,000 for SCOUT/MIRROR, additional tokens are consumed by elaboration and repetition rather than new analytical content. If output quality is poor at 8,000 tokens, the problem is prompt quality, not token budget.

---

## Prompt Discipline Principles

### What Makes a Good SCOUT/MIRROR Prompt

1. **Derive before apply.** The LENS GENERATION RULE must appear before any instruction to apply lenses. The model must identify relevant dimensions from the document before it is told to analyze along those dimensions.

2. **Prohibit the generic explicitly.** Simply saying "derive document-specific lenses" is insufficient. The prompt must say "do not use lenses that could apply to any document" and name examples of prohibited generic lens names.

3. **Require reasoning traces.** `lens_selection_reasoning` and similar fields force the model to show its derivation work. This makes non-compliance visible in output.

4. **Constrain output shape precisely.** Vague schema descriptions produce inconsistent output shapes. Specify array element structure, field names, and value types explicitly in the prompt.

### What Makes a Good Synthesis Prompt

1. **State minimums as hard requirements.** "Produce at least 5 risks" is a minimum. "Produce a comprehensive list of risks" is not. Use exact numbers.

2. **4-tier labels must be defined in the prompt, not assumed.** Include the four labels with their definitions and a usage example. Models apply tier labels inconsistently without explicit definitions.

3. **Unique assessment categories must be derived, not selected.** The prompt must instruct the model to derive category names from the document's specific domain, not select from a list.

4. **follow_up_direction must be structured as a multi-step investigation sequence.** Frame the 5 fields as: (1) diagnosis, (2) immediate action, (3) question to pose, (4) target party, (5) reference source. This framing produces actionable output.

---

## Data Contract Rules

Every agent has a contract: what it must receive and what it must produce. Violating either side breaks the pipeline.

### ContextAggregator Contract

Must receive:
- Session state dict with Q&A results (either field name format)
- `key_details_list` from KeyDocumentDetailsExtractor output
- `doc_context` string (up to 10,000 chars)

Must produce:
- `analysis_text`: str (non-empty if session has any Q&A results)
- `rich_analysis_text`: str (non-empty if session has any Q&A results)
- `doc_context`: str (may be empty string; never None)

### DocumentProfileAgent Contract

Must receive:
- `rich_analysis_text`: str
- `doc_context`: str

Must produce (including in fallback):
- `confirmed_present`: List[str]
- `confirmed_absent`: List[str]
- `unverified`: List[str]
- `expertise_profile`: Dict with keys: role, industry_context, key_benchmarks, typical_red_flags, normal_expectations
- `key_items`: Dict with keys: scope, schedule, commercial, compliance, risk_bearing, submission (each a List)
- `document_understanding`: Dict with keys: document_overview, major_workstreams, key_obligations, key_constraints, structural_organization

### ScoutAgent Contract

Must receive:
- `analysis_text`: str
- `doc_context`: str
- `doc_profile`: Dict (full DocumentProfileAgent output, including `document_understanding`)

Must produce:
- `lens_selection_reasoning`: str
- `scout_lenses_applied`: List[Dict]
- `sanity_flags`: List
- `criteria_gaps`: List
- `opportunities`: List[SmartAnalysisItem-shaped Dict]
- `uncertainties`: List (with 5-field follow_up_direction)
- `assumptions`: List (with 5-field follow_up_direction)

### MirrorAgent Contract

Must receive:
- `analysis_text`: str
- `doc_context`: str
- `doc_profile`: Dict (full DocumentProfileAgent output, including `document_understanding`)

Must produce:
- `lens_selection_reasoning`: str
- `mirror_lenses_applied`: List[Dict]
- `missing_elements`: List (with 5-field follow_up_direction)
- `interpretation_risks`: List
- `risks`: List[SmartAnalysisItem-shaped Dict] (with 5-field follow_up_direction)
- `stakeholder_perspectives`: List (document-derived parties)
- `failure_scenarios`: List
- `refinement_needs`: List

### SynthesisAgent Contract

Must receive:
- `analysis_text`: str
- `doc_context`: str
- `doc_profile`: Dict
- `scout_findings`: Dict
- `mirror_findings`: Dict
- `user_responses`: Dict | None

Must produce (at or above minimums):
- `executive_summary`: str
- `key_insights`: List[SmartAnalysisItem-shaped Dict] (≥5)
- `risks`: List[SmartAnalysisItem-shaped Dict] (≥5, with 5-field follow_up_direction)
- `opportunities`: List[SmartAnalysisItem-shaped Dict] (≥5, with 5-field follow_up_direction)
- `ambiguities`: List[SmartAnalysisItem-shaped Dict] (≥5, with 5-field follow_up_direction)
- `contradictions`: List
- `assessments`: List[ProfessionalAssessment-shaped Dict] (≥6, unique categories)
- `follow_up_questions`: List[str] (≥6)
- `strategic_recommendations`: List[str] (≥5)
- `evidence_classification`: Dict (including `minimum_count_notes`)

### Orchestrator Contract

Must produce `SmartAnalysisResult` with all fields populated (defaults acceptable for optional fields). Must not raise exceptions on agent partial failure — degrade gracefully using fallback outputs.

---

## Frontend Rendering Contract

The frontend (`index.html`) renders Smart Analysis results directly from the JSON-serialized `SmartAnalysisResult`. Any field added to the result schema must have a corresponding rendering path in the frontend, or be explicitly documented as backend-only.

### Fields the Frontend Currently Renders

| Field | Rendering |
|-------|-----------|
| `document_understanding.document_overview` | Paragraph in Document Overview section |
| `document_understanding.major_workstreams` | Bulleted list in Document Overview |
| `document_understanding.key_obligations` | Bulleted list in Document Overview |
| `document_understanding.key_constraints` | Bulleted list in Document Overview |
| `document_understanding.structural_organization` | Paragraph in Document Overview |
| `assessments[]` | Professional Assessments cards (category, rating, rationale, confidence) |
| `executive_summary` | Executive Summary section |
| `key_insights[]` | Key Insights cards (itemsHTML with badge) |
| `risks[]` | Risks cards (badge + follow_up_direction) |
| `opportunities[]` | Opportunities cards (badge + follow_up_direction) |
| `ambiguities[]` | Ambiguities cards (badge + follow_up_direction) |
| `contradictions[]` | Contradictions cards |
| `strategic_recommendations[]` | Strategic Recommendations list |
| `follow_up_questions[]` | Follow-Up Questions list |
| `user_question_responses[]` | Your Questions section |
| `evidence_classification` | Evidence Classification section |

### follow_up_direction Rendering Rules

The frontend renders both v2 and v3 follow_up_direction formats:

- If `why_unclear` / `verification_step` / `what_to_ask` / `who_to_ask` / `where_to_look` are present: render as 5-step investigation sequence (v3 format)
- If `action` / `target` / `specific_question` are present: render as 3-step action block (v2 format)
- If neither: render nothing (do not error)

Do not remove the v2 rendering path. Cached analyses from before the v3 migration use the v2 format.

### Handling Missing Fields

The frontend must handle missing or empty fields gracefully:
- Missing `document_understanding`: do not render the Document Overview section
- Empty array fields (`risks: []`): render section header with "No items identified" placeholder
- `null` or missing `executive_summary`: render placeholder text, not a blank section
- Missing `evidence_classification`: omit the Evidence Classification section entirely

---

## Anti-Patterns

These are confirmed failure modes from the v1–v3 history. Do not repeat them.

### 1. Wrong Field Names in ContextAggregator (v1 bug)
Accessing `result["question"]` instead of `result["question_text"]` (or vice versa) produces empty `analysis_text`. All agents receive blank context. Output looks structurally valid but contains no document-specific content. Use `_resolve_question_fields()` and never access Q&A fields directly.

### 2. Static Lens Selection in SCOUT/MIRROR (v2 bug)
Providing a list of possible lens categories in the prompt trains the model to select from that list rather than derive from document content. The output looks correct but is generic. Remove all category lists from lens selection instructions. Derive only.

### 3. Hardcoded Stakeholder Types in MIRROR (v2 bug)
Specifying "Owner, Contractor, Subcontractor" in the `stakeholder_perspectives` instruction produces those three perspectives on every document, regardless of relevance. Replace with instruction to identify parties from the document.

### 4. Incomplete Fallback Dicts (v2/v3 bug)
Empty fallback returns from failed agents that are missing keys cause KeyErrors in downstream agents. Every fallback dict must include every key that downstream code accesses. After any prompt schema change, update the fallback dict in the same commit.

### 5. Missing `document_understanding` in Orchestrator (v2 bug)
DocumentProfileAgent producing `document_understanding` is useless if orchestrator does not extract it into `SmartAnalysisResult`. Always check that `_build_result()` maps all doc_profile fields to the result.

### 6. Non-Specific Minimum Instructions ("comprehensive", "thorough")
Vague quality instructions do not produce minimum-compliant output. Use exact numbers: "produce at least 5 risks". The word "comprehensive" produces 2–3 items on thin documents.

### 7. Schema Changes Without Frontend Updates
Adding a new field to `SmartAnalysisResult` and not adding a rendering path in the frontend means the field is silently ignored. Always trace the rendering path for new fields.

### 8. Schema Changes Without Fallback Updates
Same pattern as anti-pattern 4, but for the models layer. Adding `document_understanding: Dict` to `SmartAnalysisResult` without `field(default_factory=dict)` breaks deserialization of cached results that predate the field.

### 9. Increasing Token Budget Without Checking Parallel Latency
SCOUT and MIRROR run in parallel. Increasing one but not the other has no latency benefit (bounded by the slower agent). Increase both symmetrically unless there is a specific justification.

### 10. Prompt-Only Enforcement Without Output Validation
Rules stated only in prompts (minimums, uniqueness, 4-tier labels) are non-compliant silently. There is no error when the model ignores them. Until a post-processing validation layer exists, verify compliance by inspecting actual output on representative documents — do not assume the rule works because it is written.

---

## Test Approach for Smart Analysis

Smart Analysis has no automated test suite. Verification is manual. Use this checklist.

### Pre-Flight Checks (before testing output)

- [ ] Server restarted cleanly (no stale session cache)
- [ ] A complete session exists: document uploaded, Q&A extraction complete, key details extracted
- [ ] `doc_context` is present in session state (non-empty string)
- [ ] At least one user question entered (to test UserInputAgent path)

### Output Quality Checklist

For each test run, verify:

- [ ] Document Overview section renders and is document-specific (not generic)
- [ ] `document_overview` paragraph mentions the specific document type and scope
- [ ] `major_workstreams` are derived from this document (not generic phases)
- [ ] `expertise_profile.key_benchmarks` contains specific figures or standards
- [ ] Assessment categories are unique and relevant to this document type
- [ ] SCOUT lenses reference document-specific dimensions (not "Financial Risk", "Legal")
- [ ] MIRROR lenses reference document-specific adversarial dimensions
- [ ] `stakeholder_perspectives` names parties relevant to this document
- [ ] `risks`, `opportunities`, `ambiguities` each have at least 5 items
- [ ] `assessments` has at least 6 items with unique category names
- [ ] `follow_up_questions` has at least 6 items
- [ ] `strategic_recommendations` has at least 5 items
- [ ] At least one item in risks/opportunities/ambiguities uses a 4-tier label in its description
- [ ] follow_up_direction on risks includes all 5 fields (why_unclear, verification_step, what_to_ask, who_to_ask, where_to_look)
- [ ] User question responses are present if user questions were entered
- [ ] Evidence classification section renders

### Regression Checks After Refactor

- [ ] v2 cached result (if accessible) still renders without JS errors
- [ ] Empty user questions case produces no UserInputAgent errors
- [ ] Pipeline completes without KeyError on agent partial failure (simulate by temporarily breaking one agent and confirming graceful degradation)

---

## Version History and Migration Notes

| Version | Commit | Key Change | Migration Required |
|---------|--------|-----------|-------------------|
| v1 | `d65a75d` | Initial build — 10 service files, 4 API routes | None (first version) |
| v2 | `e4cf7ca` | ContextAggregator field name fix; DocumentProfileAgent added; 4-tier language discipline; evidence grounding; 3-field follow_up_direction; rich_analysis_text | Cached v1 results lack `document_understanding` — handled by frontend null-check |
| v3 | `887e82a` | document_understanding layer; EXPERTISE UNIQUENESS RULE; LENS GENERATION RULE per agent; mandatory minimums; 5-field follow_up_direction; unique assessments; token increases; UI updates | Cached v2 results have 3-field follow_up_direction — frontend renders both formats |

### Migration Rules

1. When adding a new field to `SmartAnalysisResult`, always add `field(default_factory=...)` default. Cached results from prior versions will be missing the field on deserialization.
2. When changing follow_up_direction field names, preserve rendering of the old field names in the frontend. Do not remove old rendering paths until cached results from the old format are known to be expired or cleared.
3. When changing agent output schemas, update fallback dicts in the same commit. Never ship a prompt schema change without a corresponding fallback update.
4. After any significant structural change, add an entry to this version history table and to `memory/debug_history.md`.