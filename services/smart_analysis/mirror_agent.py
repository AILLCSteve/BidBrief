"""
MIRROR Agent — dynamic MIRROR-framework stress-testing.

Missing elements · Interpretation stress testing · Risk identification
Perspective simulation · Outcome simulation · Refinement

v2: Now receives a document_profile from DocumentProfileAgent.
  - Dynamically generates its own MIRROR lenses before applying them
  - Adversarial but grounded — cannot claim absence of confirmed_present items
  - Stakeholder perspectives calibrated to the expertise profile
  - Risk identification benchmarked against industry norms
"""

import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a risk analyst, adversarial reviewer, and stress-tester for document analyses. \
You apply MIRROR reasoning: Missing elements detection, Interpretation stress testing, \
Risk identification, Perspective simulation, Outcome simulation, and Refinement.

Your job is to be the critical voice — find what's wrong, what's missing, what could fail, \
and how this looks from angles the original analysis may have missed.

CRITICAL GROUNDING RULE: A document profile has been provided. Topics in confirmed_present \
ARE in the document — do not claim they are absent or missing. For topics in unverified, \
you may flag that they are inadequately resolved, but do not say they are absent. \
Only topics in confirmed_absent can be flagged as genuinely missing.

Apply only the MIRROR lenses that yield the most valuable insights for THIS specific document. \
Quality over mechanical checklist application.

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Stress-test this analysis of a {doc_type} document called "{doc_name}".

=== DOCUMENT PROFILE (grounding — what is and is not confirmed) ===
CONFIRMED PRESENT (do NOT claim these are missing or absent):
{confirmed_present}

CONFIRMED ABSENT (genuinely not found — can be flagged as gaps):
{confirmed_absent}

UNVERIFIED / PARTIALLY ADDRESSED (flag as inadequately resolved, not absent):
{unverified}

EXPERTISE CONTEXT:
Role: {expert_role}
Industry context: {industry_context}
Benchmarks: {benchmarks}
Typical red flags for this doc type: {red_flags}
Normal expectations: {normal_expectations}

Key items identified:
  Scope: {scope_items}
  Schedule: {schedule_items}
  Commercial: {commercial_items}
  Compliance: {compliance_items}
  Risk-bearing clauses: {risk_items}

=== FULL ANALYSIS TEXT ===
{analysis_text}

===

Apply MIRROR reasoning. First state which MIRROR lenses are most relevant, then apply them:

M — MISSING ELEMENTS: What important information, clauses, data, or analysis is genuinely \
absent (in confirmed_absent or seriously unverified)? What should have been found but wasn't? \
Distinguish clearly between: absent from document, not asked in analysis, partially addressed.

I — INTERPRETATION RISKS: Where could the analysis be reading something wrong? What terms, \
provisions, or findings are open to multiple interpretations — and which reading is more risky?

R — RISKS: What are the concrete threats to success, profitability, or execution? Be specific \
about likelihood, impact, and what makes this risk non-obvious. Benchmark against industry norms.

R — OTHER PERSPECTIVES: How does this document look from each relevant stakeholder's viewpoint? \
Use stakeholders appropriate to this document type. What concerns would each raise?

O — OUTCOME SCENARIOS: What are the most plausible failure paths? What specific triggers \
would lead to bad outcomes?

R — REFINEMENT: What would the next analysis pass need to address? What key gaps remain?

Only include findings that would actually change a professional's decision or concern level.

Respond as JSON:
{{
  "mirror_lenses_applied": ["List the specific MIRROR sub-lenses you determined are most relevant"],
  "missing_elements": [
    {{
      "element": "What is missing",
      "absence_type": "confirmed_absent|not_asked_in_analysis|partially_addressed|unresolved",
      "importance": "high|medium|low",
      "why_it_matters": "Specific decision risk",
      "how_to_verify": "What source or action would resolve this"
    }}
  ],
  "interpretation_risks": [
    {{
      "area": "Provision or finding",
      "current_reading": "How the analysis reads it",
      "risky_alternative": "The more adverse interpretation",
      "recommendation": "How to clarify or protect against this"
    }}
  ],
  "risks": [
    {{
      "risk": "Concise risk title",
      "likelihood": "high|medium|low",
      "impact": "high|medium|low",
      "specific_concern": "Evidence-based description",
      "benchmark_context": "How this compares to typical for this doc type",
      "mitigation": "Specific recommended mitigation"
    }}
  ],
  "stakeholder_perspectives": [
    {{
      "stakeholder": "e.g., Prime Contractor, Owner/Agency, Subcontractor, Engineer",
      "concern": "Their primary concern with this document",
      "implication": "How this perspective should change the evaluation"
    }}
  ],
  "failure_scenarios": [
    {{
      "scenario": "Plausible failure description",
      "trigger": "What would cause it",
      "likelihood": "high|medium|low",
      "consequence": "Material impact"
    }}
  ],
  "refinement_needs": [
    "What follow-up analysis or verification is most needed"
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


class MIRRORAgent:
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
                        risk_items=', '.join(key_items.get('risk_bearing', [])) or '(see analysis)',
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
                f'[MIRROR] Complete: {total} findings | '
                f'lenses={result.get("mirror_lenses_applied", [])}'
            )
            return result

        except Exception as e:
            logger.error(f'[MIRROR] Failed: {e}')
            return {
                'mirror_lenses_applied': [],
                'missing_elements': [],
                'interpretation_risks': [],
                'risks': [],
                'stakeholder_perspectives': [],
                'failure_scenarios': [],
                'refinement_needs': [],
            }
