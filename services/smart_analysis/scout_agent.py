"""
SCOUT Agent — dynamic SCOUT-framework analysis.

Sanity-checking · Criteria scaffolding · Opportunity discovery
Uncertainty mapping · Assumption testing

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

Before applying each SCOUT principle, you FIRST determine which specific lenses are \
most valuable for THIS document — then apply only those. Quality over quantity.

IMPORTANT GROUNDING RULE: A document profile has been provided showing what is confirmed \
present vs. absent vs. unverified in the analysis. Do NOT claim something is missing or \
absent if it appears in the confirmed_present list. If it is in unverified, state that \
it is unresolved — not that it is absent.

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Perform SCOUT analysis on this {doc_type} document called "{doc_name}".

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
Key benchmarks: {benchmarks}
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

Apply SCOUT reasoning. First state which SCOUT lenses are most relevant for THIS specific \
document, then apply them:

S — SANITY CHECKS: Do the numbers, quantities, timelines, and commitments make sense? \
Compare against the expertise benchmarks above. Flag anything that seems unrealistic, \
inconsistent, or doesn't add up. Be specific with actual numbers/claims from the analysis.

C — CRITERIA GAPS: What important evaluation criteria should have been assessed but weren't? \
What questions were missing from the analysis that a professional reviewer would consider essential?

O — OPPORTUNITIES: What genuine strategic, financial, or operational opportunities does \
this document reveal? What advantages could a well-prepared bidder/party exploit?

U — UNCERTAINTIES: What critical information is missing, ambiguous, or unverifiable? \
Distinguish between: (a) confirmed absent, (b) not asked in analysis, (c) asked but vague answer. \
Use precise language — don't conflate these categories.

T — ASSUMPTION TESTING: What assumptions are embedded in the document or analysis that \
could be wrong? What would materially change the evaluation if those assumptions failed?

Only include findings that are genuinely important for THIS specific document.

Respond as JSON:
{{
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
      "why_it_matters": "Decision impact"
    }}
  ],
  "assumptions": [
    {{
      "assumption": "What is being assumed",
      "risk_if_wrong": "Consequence if false",
      "likelihood_wrong": "high|medium|low"
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
                max_tokens=3500,
                response_format={'type': 'json_object'},
                timeout=90.0,
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
                'scout_lenses_applied': [],
                'sanity_flags': [],
                'criteria_gaps': [],
                'opportunities': [],
                'uncertainties': [],
                'assumptions': [],
            }
