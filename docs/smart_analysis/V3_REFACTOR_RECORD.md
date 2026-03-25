# Smart Analysis v3 Refactor — Analysis and Record

**Commit:** `887e82a`
**Preceded by:** v2 (`e4cf7ca`), v1 (`d65a75d`)

---

## Executive Summary: Why v3 Was Needed

v2 fixed the critical data invisibility bug introduced in v1 (wrong Q&A field names in ContextAggregator meant agents received empty context). Once that was resolved, v2 produced structurally correct output — but the analysis was consistently shallow and generic. Specific failure modes:

1. **Assessment categories repeated across runs** — the same 6 category names appeared regardless of document type, scope, or sector. Assessments were templates, not analysis.
2. **SCOUT and MIRROR lenses were generic** — lenses like "Financial Risk" and "Compliance" appeared on every document. The lens selection was not derived from document content; it was a fixed menu.
3. **DocumentProfileAgent benchmarks were boilerplate** — expertise profiles described industry archetypes rather than the specific document's figures, timelines, and standards.
4. **follow_up_direction was a 3-field surface** — `action`, `target`, `specific_question` gave a direction but did not provide a fully actionable investigation sequence.
5. **No document_understanding layer** — agents had Q&A-derived context but no synthesized understanding of what the document actually was, what it required, and how it was structured. This caused the synthesis to lack structural grounding.
6. **No mandatory minimum enforcement** — thin documents produced thin output. There was no floor on item counts, creating inconsistent result quality.
7. **Token caps were too low** — several agents were hitting token limits and truncating output, particularly on longer or more complex documents.

v3 addressed all seven failure modes.

---

## Phase 1: Findings Per Agent

### ContextAggregator (`context_aggregator.py`)
- No problems found in Phase 1. The v2 fix (`_resolve_question_fields()`) was correct and complete.
- Identified opportunity: add `rich_analysis_text` path with higher fidelity for DocumentProfileAgent specifically.
- **Problem:** All agents consumed the same `analysis_text`. DocumentProfileAgent needed more raw signal (full answer text, page citations) than downstream agents needed.

### DocumentProfileAgent (`document_profile_agent.py`)
- **Problem 1:** `expertise_profile` fields were populated with generic industry descriptions. `key_benchmarks` said things like "Typical construction projects have tight timelines" rather than citing the specific document's schedule.
- **Problem 2:** No `document_understanding` block. The agent identified items but did not synthesize a coherent picture of what the document required.
- **Problem 3:** Empty fallback on failure did not include `document_understanding`, causing KeyError in orchestrator downstream.
- **Problem 4:** max_tokens=3500 (v2 value) was insufficient for documents with complex key_items breakdowns.

### ScoutAgent (`scout_agent.py`)
- **Problem 1:** Lens selection was static — the prompt described possible lens categories and the model selected from that menu rather than deriving lenses from the document.
- **Problem 2:** `uncertainties` and `assumptions` had 3-field follow_up_direction (v2 format). Not actionable enough.
- **Problem 3:** max_tokens=4000 caused truncation on complex documents, cutting off `opportunities` and `uncertainties` arrays.
- **Problem 4:** No LENS GENERATION RULE — nothing forced document-specific lens derivation before application.

### MirrorAgent (`mirror_agent.py`)
- **Problem 1:** Same static lens problem as ScoutAgent. Adversarial dimensions defaulted to generic categories.
- **Problem 2:** `stakeholder_perspectives` was hardcoded to a fixed set of stakeholder types (Owner, Contractor, Subcontractor) regardless of whether those parties were relevant to the document.
- **Problem 3:** `risks` and `missing_elements` had 3-field follow_up_direction. Not actionable enough.
- **Problem 4:** max_tokens=4000 caused truncation.

### UserInputAgent (`user_input_agent.py`)
- No structural problems found. max_tokens=2500 was appropriate for the task scope.
- Minor: `follow_up_direction` on responses used the 3-field format. Upgraded to 5-field for consistency, though less critical here than for risks/opportunities.

### SynthesisAgent (`synthesis_agent.py`)
- **Problem 1:** No minimum output count enforcement. Thin documents produced 2–3 risks, 2–3 opportunities. Results were inconsistent and incomplete.
- **Problem 2:** Assessment `category` values were reused across runs. The prompt did not require unique derivation.
- **Problem 3:** `follow_up_direction` on risks, opportunities, and ambiguities was the 3-field v2 format. The 3-field format identified what to ask but not who, where, or why.
- **Problem 4:** No 4-tier language discipline enforcement in v2 — agents used hedged language inconsistently ("may", "could", "possibly") without tying claims to evidence tier.
- **Problem 5:** max_tokens=6000 caused truncation on synthesis of complex multi-agent outputs.

### Orchestrator (`orchestrator.py`)
- **Problem:** `_build_result()` did not extract `document_understanding` from `doc_profile`. The field existed in the profile output but was not surfaced in `SmartAnalysisResult`.
- **Problem:** Empty fallback for failed agents did not include all required keys, causing downstream KeyErrors on partial failure.

### Models (`models.py`)
- `SmartAnalysisResult` was missing `document_understanding: Dict` field.
- `SmartAnalysisItem.follow_up_direction` was typed as `Dict[str, str]` — correct, but the expected keys changed between v2 (3-field) and v3 (5-field). No migration path for cached v2 results.

---

## Phase 2: Plan Summary

### Per-File Plan

| File | Planned Change |
|------|---------------|
| `context_aggregator.py` | Add `rich_analysis_text` output path with full answer text and page citations |
| `document_profile_agent.py` | Add `document_understanding` block to prompt and output schema; add EXPERTISE UNIQUENESS RULE to prompt; increase max_tokens to 4500; fix empty fallback to include `document_understanding` |
| `scout_agent.py` | Add LENS GENERATION RULE to prompt (derive lenses before applying); upgrade follow_up_direction to 5-field; increase max_tokens to 5000 |
| `mirror_agent.py` | Add LENS GENERATION RULE to prompt; make `stakeholder_perspectives` document-derived; upgrade follow_up_direction to 5-field; increase max_tokens to 5000 |
| `user_input_agent.py` | Minor: upgrade follow_up_direction to 5-field for consistency |
| `synthesis_agent.py` | Add mandatory minimums to prompt; add UNIQUE ASSESSMENT CATEGORIES rule; add 4-tier language discipline; upgrade follow_up_direction to 5-field; increase max_tokens to 8000 |
| `orchestrator.py` | Extract `document_understanding` from `doc_profile` in `_build_result()`; harden fallback dicts |
| `models.py` | Add `document_understanding: Dict` to `SmartAnalysisResult` |
| `excel_generator.py` | Add Document Overview section from `document_understanding` |
| `pdf_generator.py` | Add Document Overview section from `document_understanding` |

---

## Phase 3: Critique

Edge cases considered before implementation:

1. **Backward compatibility of cached v2 results.** Cached `SmartAnalysisResult` dicts from v2 would not have `document_understanding`. Frontend must handle missing field gracefully without throwing. Decision: frontend renders section only if field is present and non-empty.

2. **follow_up_direction field migration.** Cached v2 items have 3-field follow_up_direction. Frontend must render both formats. Decision: render v2 fields if present, then render v3 fields if present. No server-side migration needed.

3. **DocumentProfileAgent failure path.** If DocumentProfileAgent fails (timeout, API error), downstream agents receive an empty doc_profile. Empty fallback must include all keys that downstream agents reference, including `document_understanding`, `expertise_profile`, and all `key_items` sub-keys. Without this, SCOUT and MIRROR KeyError on partial failure.

4. **Token increase impact on latency.** Increasing all agents by 25–33% increases worst-case latency. With SCOUT + MIRROR running in parallel, the parallel stage latency is bounded by the slower of the two (same budget). Total worst-case increases from ~7 minutes to ~9 minutes. Acceptable given the quality improvement.

5. **LENS GENERATION RULE compliance.** The rule is enforced via prompt instruction only — there is no structural validation that lenses are document-specific. A sufficiently generic document could still produce generic-looking lenses. This is a known limitation; structural validation would require a separate evaluation pass.

6. **Minimum count enforcement.** Minimums are enforced via prompt instruction, not via post-processing. If the model truncates due to hitting max_tokens before completing all arrays, counts could still fall below minimum. The token increases in v3 were sized to give headroom for minimum-compliant output on typical documents.

---

## Phase 4: Implementation — Per-File Changes

### `context_aggregator.py`
**Added:** `rich_analysis_text` build path. Uses full `primary_answer` / `answer` text without truncation, includes `page_citations` inline, and formats key_details_list with full value text. `analysis_text` unchanged for downstream agents.

**Key change:** `_resolve_question_fields()` now returns a 3-tuple: `(question_text, answer_text, citations)`. Callers updated accordingly.

### `document_profile_agent.py`
**Added to prompt:** EXPERTISE UNIQUENESS RULE block requiring specific figures, not archetypes. `document_understanding` output block with `document_overview`, `major_workstreams`, `key_obligations`, `key_constraints`, `structural_organization`.

**max_tokens:** 3500 → 4500

**Empty fallback before:**
```python
return {"confirmed_present": [], "confirmed_absent": [], "unverified": [],
        "expertise_profile": {}, "key_items": {}}
```

**Empty fallback after:**
```python
return {
    "confirmed_present": [], "confirmed_absent": [], "unverified": [],
    "expertise_profile": {"role": "", "industry_context": "", "key_benchmarks": "",
                          "typical_red_flags": "", "normal_expectations": ""},
    "key_items": {"scope": [], "schedule": [], "commercial": [],
                  "compliance": [], "risk_bearing": [], "submission": []},
    "document_understanding": {"document_overview": "", "major_workstreams": [],
                               "key_obligations": [], "key_constraints": [],
                               "structural_organization": ""}
}
```

### `scout_agent.py`
**Added to prompt:** LENS GENERATION RULE — "Before selecting lenses, identify what analytical dimensions are actually present in this document. Derive your lenses from the document's content. Do not select from a predefined menu."

**follow_up_direction upgrade:** 3-field → 5-field on `uncertainties[]` and `assumptions[]`.

**max_tokens:** 4000 → 5000

### `mirror_agent.py`
**Added to prompt:** LENS GENERATION RULE for adversarial dimensions. `stakeholder_perspectives` instruction changed from "identify perspectives of Owner, Contractor, Subcontractor" to "identify the actual parties named or implied in this document and analyze their perspectives."

**follow_up_direction upgrade:** 3-field → 5-field on `risks[]` and `missing_elements[]`.

**max_tokens:** 4000 → 5000

### `synthesis_agent.py`
**Added to prompt:** Mandatory minimum output counts block. UNIQUE ASSESSMENT CATEGORIES instruction. 4-tier language discipline block with definitions and usage rules.

**follow_up_direction upgrade:** 3-field → 5-field on `risks[]`, `opportunities[]`, `ambiguities[]`.

**max_tokens:** 6000 → 8000

### `orchestrator.py`
**Added in `_build_result()`:**
```python
result.document_understanding = doc_profile.get("document_understanding", {})
```

### `models.py`
**Added to `SmartAnalysisResult`:**
```python
document_understanding: Dict[str, Any] = field(default_factory=dict)
```

### Frontend (`index.html`)
**Added:** Document Overview section rendered from `document_understanding`. Renders `document_overview` as paragraph, `major_workstreams` / `key_obligations` / `key_constraints` as lists, `structural_organization` as paragraph.

**Added:** follow_up_direction v3 rendering block alongside existing v2 rendering for backward compatibility.

---

## Phase 5: Validation

### What Was Verified

1. **Field name grep** — searched for all v2 follow_up_direction field names (`action`, `target`, `specific_question`) in agent prompt strings. Confirmed all upgraded to 5-field format. Frontend rendering preserved v2 fallback.

2. **Empty fallback completeness** — confirmed all keys accessed by downstream agents were present in DocumentProfileAgent empty fallback. Traced `doc_profile.get(...)` calls in scout_agent.py, mirror_agent.py, and orchestrator.py.

3. **SmartAnalysisResult field presence** — confirmed `document_understanding` added to dataclass and populated in `_build_result()`.

4. **Token budget headroom** — estimated worst-case output size for minimum-compliant responses at new token budgets. All agents have headroom for minimum-compliant output on typical bid documents.

5. **Frontend backward compatibility** — confirmed UI renders both v2 and v3 follow_up_direction fields without errors when only one format is present.

---

## Behavioral Delta: v2 vs v3

| Dimension | v2 Behavior | v3 Behavior |
|-----------|-------------|-------------|
| Assessment categories | Same 6 categories on every run | Uniquely derived per document per run |
| SCOUT/MIRROR lenses | Selected from static category list | Derived from document content before application |
| DocumentProfile benchmarks | Generic industry description | Document-specific figures, timelines, standards |
| follow_up_direction | 3 fields (action, target, question) | 5 fields (why_unclear, verification_step, what_to_ask, who_to_ask, where_to_look) |
| Document understanding | Not present | Synthesized overview, workstreams, obligations, constraints |
| Output minimums | Not enforced | Hard minimums in prompt (5–6 per category) |
| Language discipline | Inconsistent hedging | 4-tier tier labels on all claims |
| Token budgets | 3500–6000 across agents | 4500–8000 across agents |
| Stakeholder perspectives | Hardcoded party types | Derived from document parties |

---

## Known Remaining Constraints

1. **Prompt-only enforcement.** LENS GENERATION RULE, EXPERTISE UNIQUENESS RULE, mandatory minimums, and 4-tier language discipline are all enforced via prompt instruction. There is no post-processing validation layer. Model non-compliance produces no error — it just produces lower-quality output silently.

2. **In-memory result cache.** v3 results are not persisted. Server restart loses all cached analyses.

3. **No streaming.** The pipeline is fully blocking. Users wait for all agents to complete before seeing any output.

4. **Token truncation risk remains.** On extremely complex documents (>50 Q&A pairs, dense key details), even 8000 tokens may be insufficient for Synthesis. This has not been observed in testing but remains a theoretical risk.

---

## Suggested v4 Directions

1. **Post-processing validation layer** — after each agent completes, validate output against schema and minimum counts. Re-prompt with targeted correction if validation fails.
2. **Streaming result delivery** — surface Document Overview and Professional Assessments as soon as DocumentProfileAgent completes, rather than waiting for full pipeline.
3. **Result persistence** — write completed SmartAnalysisResult to SQLite or Redis. Survive server restarts. Enable result history per document.
4. **Adaptive token budgets** — estimate input token count before calling each agent; scale max_tokens proportionally rather than using fixed values.
5. **LENS GENERATION structural validation** — add a brief evaluation pass after SCOUT/MIRROR to confirm lenses are document-specific before synthesis consumes them.

---