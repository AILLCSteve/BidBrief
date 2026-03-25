"""
SCOUT Agent — dynamic SCOUT-framework analysis.

Sanity-checking · Criteria scaffolding · Opportunity discovery
Uncertainty mapping · Assumption testing

v3 changes:
  - max_tokens 3500 → 5000
  - Receives and uses document_understanding from DocumentProfileAgent
  - lens_selection_reasoning required: agent must justify lens choices before applying
  - Multi-step follow_up on uncertainties and assumptions
  - Minimum output guidance: at least 5 opportunities, 4-5 uncertainties where supported
  - Lens generation is document-specific — no static template repetition

v2: Now receives a document_profile from DocumentProfileAgent.
  - Dynamically generates its own SCOUT lenses before applying them
  - Sanity checks are benchmarked against expertise_profile norms
  - Does NOT claim something is missing if it is in confirmed_present
  - Focuses on what genuinely matters for THIS specific document
"""

import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a senior bid evaluation and document analysis expert applying SCOUT reasoning: \
Sanity-checking, Criteria scaffolding, Opportunity discovery, Uncertainty mapping, \
and Assumption testing.

LENS GENERATION RULE:
Before applying any SCOUT lens, you MUST first derive the specific sub-lenses that are \
most valuable for THIS document. What makes THIS contract, THIS scope, THIS procurement unique? \
Identify the 5-7 most important analytical dimensions specific to this document's type, scale, \
risk profile, and industry context. Then apply ONLY those lenses with full depth. \
Do NOT apply the same generic dimensions you would apply to every document of this type. \
Two different sewer rehabilitation bids require different lenses if one is open-trench \
and the other is CIPP — derive lenses from document specifics, not document category.

MINIMUM OUTPUT GUIDANCE:
  - opportunities: identify at least 5 if the document scope and commercial terms support it
  - uncertainties: identify at least 4-5, distinguishing their type precisely
  - sanity_flags: include every genuine anomaly — do not self-censor findings that seem minor
  - assumptions: trace at least 3-4 embedded assumptions that could materially change the analysis

GROUNDING RULE: A document profile has been provided showing what is confirmed \
present vs. absent vs. unverified in the analysis. Do NOT claim something is missing or \
absent if it appears in the confirmed_present list. If it is in unverified, state that \
it is unresolved — not that it is absent.

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Perform SCOUT analysis on this {doc_type} document called "{doc_name}".

=== DOCUMENT UNDERSTANDING ===
{document_overview}

Major workstreams: {major_workstreams}
Key obligations: {key_obligations}
Key constraints: {key_constraints}

=== DOCUMENT PROFILE (grounding — verified evidence inventory) ===
CONFIRMED PRESENT (these topics ARE in the document — do not claim they are missing):
{confirmed_present}

CONFIRMED ABSENT (genuinely not found after full search):
{confirmed_absent}

UNVERIFIED / PARTIALLY ADDRESSED:
{unverified}

EXPERTISE CONTEXT:
Role: {expert_role}
Industry context: {industry_context}
Key benchmarks (specific to this document): {benchmarks}
Typical red flags for this doc type: {red_flags}
Normal expectations: {normal_expectations}

Key items identified:
  Scope: {scope_items}
  Schedule: {schedule_items}
  Commercial: {commercial_items}
  Compliance: {compliance_items}

=== FULL ANALYSIS TEXT ===
{analysis_text}

===

STEP 1 — LENS SELECTION: Before applying SCOUT, identify the 5-7 most important analytical \
dimensions for THIS specific document. What makes this document unique? What risks, \
opportunities, or anomalies are specific to this scope, sector, and context? \
Explain your lens selection reasoning.

STEP 2 — APPLY SELECTED LENSES:

S — SANITY CHECKS: Do the numbers, quantities, timelines, and commitments make sense? \
Compare against the expertise benchmarks above. Flag anything that seems unrealistic, \
inconsistent, or doesn't add up. Be specific with actual numbers/claims from the analysis.

C — CRITERIA GAPS: What important evaluation criteria should have been assessed but weren't? \
What questions were missing from the analysis that a professional reviewer would consider essential?

O — OPPORTUNITIES: What genuine strategic, financial, or operational opportunities does \
this document reveal? What advantages could a well-prepared bidder/party exploit? \
Identify at least 5 opportunities if the document's scope and terms support it.

U — UNCERTAINTIES: What critical information is missing, ambiguous, or unverifiable? \
Distinguish between: (a) confirmed absent, (b) not asked in analysis, (c) asked but vague answer. \
For each uncertainty, provide a full action sequence explaining why it's unclear and how to resolve it.

T — ASSUMPTION TESTING: What assumptions are embedded in the document or analysis that \
could be wrong? What would materially change the evaluation if those assumptions failed?

Only include findings that are genuinely important for THIS specific document.

Respond as JSON:
{{
  "lens_selection_reasoning": "Explain the 5-7 dimensions you chose for this specific document and why they matter more than generic SCOUT categories",
  "scout_lenses_applied": ["List the specific SCOUT sub-lenses you determined are most relevant"],
  "sanity_flags": [
    {{
      "claim": "Specific claim or figure from the analysis",
      "concern": "What is questionable about it",
      "benchmark_reference": "What the expertise norms say",
      "severity": "high|medium|low"
    }}
  ],
  "criteria_gaps": [
    {{
      "gap": "Missing evaluation criterion",
      "context": "Why it should have been assessed",
      "impact": "Decision risk if this gap is not addressed"
    }}
  ],
  "opportunities": [
    {{
      "opportunity": "Specific opportunity",
      "rationale": "Evidence-based reasoning",
      "category": "financial|strategic|operational|competitive"
    }}
  ],
  "uncertainties": [
    {{
      "area": "Topic area",
      "what_is_unclear": "Specific uncertainty",
      "uncertainty_type": "confirmed_absent|not_asked|vague_answer|partially_addressed",
      "why_it_matters": "Decision impact",
      "follow_up": {{
        "why_unclear": "What makes this uncertain — which analysis tier applies",
        "verification_step": "What to check or read before escalating",
        "what_to_ask": "Specific question to ask",
        "who_to_ask": "Specific party, role, or source",
        "where_to_look": "Document section, reference, or external source"
      }}
    }}
  ],
  "assumptions": [
    {{
      "assumption": "What is being assumed",
      "risk_if_wrong": "Consequence if false",
      "likelihood_wrong": "high|medium|low",
      "follow_up": {{
        "why_unclear": "What makes this assumption unverified",
        "verification_step": "How to verify or stress-test this assumption",
        "what_to_ask": "Specific question to ask",
        "who_to_ask": "Who can confirm or deny",
        "where_to_look": "Where to find confirming evidence"
      }}
    }}
  ]
}}"""


def _fmt_profile_list(items: list, key: str, sub_key: str = '') -> str:
    if not items:
        return '(none identified)'
    lines = []
    for item in items:
        primary = item.get(key, '')
        secondary = item.get(sub_key, '') if sub_key else ''
        if secondary:
            lines.append(f"  • {primary}: {secondary}")
        else:
            lines.append(f"  • {primary}")
    return '\n'.join(lines)


def _fmt_list(items: list) -> str:
    if not items:
        return '(none)'
    return ', '.join(str(i) for i in items)


class SCOUTAgent:
    def __init__(self, api_key: str, model: str = 'gpt-4o'):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def analyze(self, ctx: dict, analysis_text: str, doc_profile: dict = None) -> dict:
        doc_type = ctx.get('document_type_label') or ctx.get('document_type', 'document')
        doc_name = ctx.get('document_name', 'Unknown')
        profile = doc_profile or {}
        expertise = profile.get('expertise_profile') or {}
        key_items = profile.get('key_items') or {}
        doc_understanding = profile.get('document_understanding') or {}

        confirmed_present = _fmt_profile_list(
            profile.get('confirmed_present', []), 'topic', 'evidence_summary'
        )
        confirmed_absent = _fmt_profile_list(
            profile.get('confirmed_absent', []), 'topic', 'basis'
        )
        unverified = _fmt_profile_list(
            profile.get('unverified', []), 'topic', 'status_detail'
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': _SYSTEM},
                    {'role': 'user', 'content': _USER_TEMPLATE.format(
                        doc_type=doc_type,
                        doc_name=doc_name,
                        document_overview=doc_understanding.get('document_overview', '(not available)'),
                        major_workstreams=_fmt_list(doc_understanding.get('major_workstreams', [])),
                        key_obligations=_fmt_list(doc_understanding.get('key_obligations', [])),
                        key_constraints=_fmt_list(doc_understanding.get('key_constraints', [])),
                        confirmed_present=confirmed_present,
                        confirmed_absent=confirmed_absent,
                        unverified=unverified,
                        expert_role=expertise.get('role', 'Document Analyst'),
                        industry_context=expertise.get('industry_context', ''),
                        benchmarks='\n'.join(f"  • {b}" for b in expertise.get('key_benchmarks', [])) or '(none)',
                        red_flags='\n'.join(f"  • {r}" for r in expertise.get('typical_red_flags', [])) or '(none)',
                        normal_expectations='\n'.join(f"  • {e}" for e in expertise.get('normal_expectations', [])) or '(none)',
                        scope_items=', '.join(key_items.get('scope', [])) or '(see analysis)',
                        schedule_items=', '.join(key_items.get('schedule', [])) or '(see analysis)',
                        commercial_items=', '.join(key_items.get('commercial', [])) or '(see analysis)',
                        compliance_items=', '.join(key_items.get('compliance', [])) or '(see analysis)',
                        analysis_text=analysis_text,
                    )},
                ],
                temperature=0.3,
                max_tokens=5000,
                response_format={'type': 'json_object'},
                timeout=120.0,
            )
            result = json.loads(response.choices[0].message.content)
            total = sum(len(v) for v in result.values() if isinstance(v, list))
            logger.info(
                f'[SCOUT] Complete: {total} findings | '
                f'lenses={result.get("scout_lenses_applied", [])}'
            )
            return result

        except Exception as e:
            logger.error(f'[SCOUT] Failed: {e}')
            return {
                'lens_selection_reasoning': '',
                'scout_lenses_applied': [],
                'sanity_flags': [],
                'criteria_gaps': [],
                'opportunities': [],
                'uncertainties': [],
                'assumptions': [],
            }
