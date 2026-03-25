"""
Synthesis Agent — combines all agent outputs into the final executive report.

v3 major changes:
  - max_tokens 5000 → 8000 to support mandatory minimum output counts
  - MANDATORY MINIMUM COUNTS enforced in system prompt:
      ≥5 risks, ≥5 opportunities, ≥5 ambiguities, ≥5 key_insights,
      ≥6 assessments, ≥6 follow_up_questions, ≥5 strategic_recommendations
  - Assessment categories MUST be derived uniquely from THIS document — not static labels
  - follow_up_direction expanded to 5-field multi-step sequence on risks, ambiguities, opportunities
  - document_understanding from DocProfile included in context and output
  - opportunities now include follow_up_direction
  - "unclear" items require full action sequence: why, verification, what/who/where

v2 major changes:
  - Receives doc_profile (confirmed_present/absent/unverified + expertise_profile)
  - MUST verify all "missing/absent" claims against confirmed_present before including
  - Language discipline: 4 evidence tiers enforced throughout
  - Plausibility checking: all major claims benchmarked against expertise norms
  - Follow-up direction required for every uncertain or missing item
  - Outputs evidence_classification alongside standard report fields
"""

import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a senior analyst and executive communicator synthesizing a multi-framework \
document analysis into a professional, decision-oriented executive report.

MANDATORY LANGUAGE DISCIPLINE — You must use EXACTLY these four evidence tiers when \
describing whether something is present or absent. Never collapse them:

  TIER 1 — CONFIRMED PRESENT: "confirmed present in the document [evidence: ...]"
  TIER 2 — CONFIRMED ABSENT: "not found after targeted search across all available evidence"
  TIER 3 — NOT SURFACED BY ANALYSIS: "not addressed by the current question flow — \
            the analysis did not ask about this; cannot confirm presence or absence"
  TIER 4 — PRESENT BUT UNRESOLVED: "present in the analysis but not clearly resolved — \
            [what is known] but [what remains unclear]"

CRITICAL VERIFICATION RULE:
Before stating that any topic is missing, absent, or not addressed:
  1. Check the confirmed_present list in the document profile. If the topic is there, \
     it CANNOT be claimed as missing — use Tier 1 language.
  2. If it is in unverified, use Tier 4 language — not absent.
  3. Only use Tier 2 language if it is explicitly in confirmed_absent.
  4. If you are uncertain about its status, use Tier 3 language.

PLAUSIBILITY DISCIPLINE:
When making professional judgments (timeline realistic, pricing normal, risk elevated, \
complexity high), you must:
  - Compare against the expertise benchmarks provided
  - State what benchmark supports the judgment
  - Flag when evidence is insufficient to support a strong claim

MANDATORY MINIMUM OUTPUTS — You MUST produce at minimum:
  - key_insights: AT LEAST 5 (aim for 7-8 genuinely distinct, decision-relevant insights)
  - risks: AT LEAST 5 (aim for 7-10 — each must have a full follow_up_direction)
  - opportunities: AT LEAST 5 (each must have a follow_up_direction)
  - ambiguities: AT LEAST 5 (each must have a full follow_up_direction)
  - assessments: AT LEAST 6, using categories derived uniquely from THIS document's \
    specific characteristics, risk profile, and industry context. Do NOT use the same \
    assessment categories across different documents. Categories must reflect what actually \
    matters for THIS contract's specific scope, sector, value, and risk exposure. \
    Think: what are the 6-8 things a decision-maker MUST evaluate for THIS specific deal?
  - follow_up_questions: AT LEAST 6 (specific, targeted, with who to ask)
  - strategic_recommendations: AT LEAST 5 (each with clear reasoning basis)

  If any category genuinely cannot reach its minimum (evidence too thin), add a final item \
  explaining why further items are not supported by the available analysis.

OUTPUT REQUIREMENTS:
  - Every risk, ambiguity, uncertainty, and opportunity item must include a full follow_up_direction \
    with all five fields: why_unclear, verification_step, what_to_ask, who_to_ask, where_to_look
  - Merge overlapping SCOUT and MIRROR findings — do not list the same issue twice
  - Be decisive where evidence supports it; acknowledge uncertainty where it does not
  - Write the executive summary for a busy decision-maker who needs the full picture in 2 minutes
  - Assessment categories must be unique to this run — derive them from the document

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Synthesize the following multi-framework analysis into a comprehensive professional executive report.

=== DOCUMENT PROFILE ===
Document: {doc_name}
Type: {doc_type}
Analysis Status: {completeness} — {answer_rate}% of questions answered
{partial_note}

DOCUMENT OVERVIEW:
{document_overview}

Major workstreams: {major_workstreams}
Key obligations: {key_obligations}
Key constraints: {key_constraints}

EXPERTISE PROFILE:
Role: {expert_role}
Industry context: {industry_context}
Key benchmarks: {benchmarks}
Normal expectations: {normal_expectations}

EVIDENCE INVENTORY:
Confirmed Present: {n_confirmed_present} topics with supporting evidence
Confirmed Absent: {n_confirmed_absent} topics verified not found
Unverified/Partial: {n_unverified} topics not clearly resolved

CONFIRMED PRESENT (do not claim these are missing):
{confirmed_present}

CONFIRMED ABSENT (verified gaps):
{confirmed_absent}

UNVERIFIED (partial or unasked — use Tier 3/4 language):
{unverified}

KEY ITEMS IDENTIFIED:
Scope: {scope_items}
Schedule: {schedule_items}
Commercial: {commercial_items}
Compliance: {compliance_items}
Risk-bearing: {risk_items}

--- SCOUT FINDINGS ---
{scout_json}

--- MIRROR FINDINGS ---
{mirror_json}

--- USER QUESTION RESPONSES ---
{user_responses_json}

===

Produce the comprehensive professional executive report. Remember:
  1. VERIFY every "missing/absent" claim against the confirmed_present list above
  2. Use the mandatory language tiers for all evidence status statements
  3. Benchmark professional judgments against the expertise profile
  4. Every uncertain/missing/risky/opportunity item MUST include a full 5-field follow_up_direction
  5. Merge SCOUT + MIRROR overlapping findings — do not duplicate
  6. Produce AT MINIMUM the required counts for every output category
  7. Assessment categories MUST be derived from THIS document — not generic labels

Respond as JSON:
{{
  "executive_summary": "3-5 paragraph professional narrative. Cover: (1) what this document \
is and what it is procuring (using document_overview), (2) key decision factors confirmed by \
analysis, (3) most significant risks or gaps with language tiers, (4) overall professional \
assessment grounded in expertise benchmarks. Write for a decision-maker who needs the full \
picture in 2 minutes.",

  "key_insights": [
    "Most important insight — specific, evidence-based, decision-relevant (cite tier)",
    "Second insight",
    "Third insight (minimum 5 total, aim for 7-8)"
  ],

  "risks": [
    {{
      "title": "Short risk title",
      "description": "Specific, evidence-based description using language tier",
      "severity": "critical|high|medium|low",
      "evidence": ["Specific evidence point from analysis"],
      "page_refs": [],
      "follow_up_direction": {{
        "why_unclear": "What makes this risk uncertain or difficult to fully assess",
        "verification_step": "What to check or read before escalating",
        "what_to_ask": "Specific question to ask",
        "who_to_ask": "Specific party, role, or department",
        "where_to_look": "Document section, specification, or external reference"
      }}
    }}
  ],

  "opportunities": [
    {{
      "title": "Short title",
      "description": "Specific, actionable description of the opportunity",
      "severity": "high|medium|low",
      "evidence": ["Supporting evidence"],
      "page_refs": [],
      "follow_up_direction": {{
        "why_unclear": "What would need to be confirmed to pursue this opportunity",
        "verification_step": "What to verify or review first",
        "what_to_ask": "Specific question to ask",
        "who_to_ask": "Who to approach about this opportunity",
        "where_to_look": "Where to find supporting information"
      }}
    }}
  ],

  "ambiguities": [
    {{
      "title": "Short title",
      "description": "What is unclear and why — use language tier",
      "severity": "high|medium|low",
      "evidence": ["What partial evidence exists"],
      "page_refs": [],
      "follow_up_direction": {{
        "why_unclear": "Which analysis tier applies and what makes this unresolved",
        "verification_step": "What to check or search before asking",
        "what_to_ask": "Exact question to ask",
        "who_to_ask": "Owner, engineer, spec author, or specific party",
        "where_to_look": "Which section, addendum, or reference to consult"
      }}
    }}
  ],

  "contradictions": [
    {{
      "title": "Short title",
      "description": "What contradicts what, and the implication",
      "severity": "high|medium|low",
      "evidence": ["Evidence of contradiction"],
      "page_refs": []
    }}
  ],

  "assessments": [
    {{
      "category": "Unique assessment category derived from THIS document's specific characteristics",
      "rating": "Assessment rating (e.g., High, Moderate, Favorable, Elevated, Acceptable)",
      "rationale": "One sentence explanation with benchmark reference from the expertise profile",
      "confidence": "high|medium|low"
    }}
  ],

  "follow_up_questions": [
    "Specific, targeted question that must be answered before decision — include who to ask and why it matters"
  ],

  "strategic_recommendations": [
    "Specific, actionable recommendation with the reasoning basis and expected benefit"
  ],

  "evidence_classification": {{
    "confirmed_present_used": ["Topics from confirmed_present that informed the analysis"],
    "confirmed_absent_flagged": ["Topics from confirmed_absent flagged as gaps"],
    "unverified_flagged": ["Topics from unverified flagged as unresolved"],
    "language_tiers_applied": "Brief note on how the language tiers were applied",
    "minimum_count_notes": "Note any categories where minimum counts were difficult to reach and why"
  }}
}}"""


def _fmt_profile_list(items: list, key: str, sub_key: str = '') -> str:
    if not items:
        return '  (none)'
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


class SynthesisAgent:
    def __init__(self, api_key: str, model: str = 'gpt-4o'):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def synthesize(
        self,
        ctx: dict,
        scout_findings: dict,
        mirror_findings: dict,
        user_responses: dict,
        doc_profile: dict = None,
    ) -> dict:
        doc_type = ctx.get('document_type_label') or ctx.get('document_type', 'document')
        doc_name = ctx.get('document_name', 'Unknown')
        is_partial = ctx.get('is_partial', False)
        partial_note = (
            'NOTE: This analysis is PARTIAL — stopped before completion. '
            'Factor incomplete coverage into confidence levels.\n'
            if is_partial else ''
        )

        profile = doc_profile or {}
        expertise = profile.get('expertise_profile') or {}
        key_items = profile.get('key_items') or {}
        confirmed_present = profile.get('confirmed_present', [])
        confirmed_absent = profile.get('confirmed_absent', [])
        unverified = profile.get('unverified', [])
        doc_understanding = profile.get('document_understanding') or {}

        user_resp_list = user_responses.get('responses', [])

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': _SYSTEM},
                    {'role': 'user', 'content': _USER_TEMPLATE.format(
                        doc_name=doc_name,
                        doc_type=doc_type,
                        completeness='Partial' if is_partial else 'Complete',
                        answer_rate=ctx.get('answer_rate_pct', 0),
                        partial_note=partial_note,
                        document_overview=doc_understanding.get('document_overview', '(not available)'),
                        major_workstreams=_fmt_list(doc_understanding.get('major_workstreams', [])),
                        key_obligations=_fmt_list(doc_understanding.get('key_obligations', [])),
                        key_constraints=_fmt_list(doc_understanding.get('key_constraints', [])),
                        expert_role=expertise.get('role', 'Document Analyst'),
                        industry_context=expertise.get('industry_context', ''),
                        benchmarks='\n'.join(f"  • {b}" for b in expertise.get('key_benchmarks', [])) or '  (none)',
                        normal_expectations='\n'.join(f"  • {e}" for e in expertise.get('normal_expectations', [])) or '  (none)',
                        n_confirmed_present=len(confirmed_present),
                        n_confirmed_absent=len(confirmed_absent),
                        n_unverified=len(unverified),
                        confirmed_present=_fmt_profile_list(confirmed_present, 'topic', 'evidence_summary'),
                        confirmed_absent=_fmt_profile_list(confirmed_absent, 'topic', 'basis'),
                        unverified=_fmt_profile_list(unverified, 'topic', 'status_detail'),
                        scope_items=', '.join(key_items.get('scope', [])) or '(see analysis)',
                        schedule_items=', '.join(key_items.get('schedule', [])) or '(see analysis)',
                        commercial_items=', '.join(key_items.get('commercial', [])) or '(see analysis)',
                        compliance_items=', '.join(key_items.get('compliance', [])) or '(see analysis)',
                        risk_items=', '.join(key_items.get('risk_bearing', [])) or '(see analysis)',
                        scout_json=json.dumps(scout_findings, indent=2),
                        mirror_json=json.dumps(mirror_findings, indent=2),
                        user_responses_json=(
                            json.dumps(user_resp_list, indent=2)
                            if user_resp_list else '(none provided)'
                        ),
                    )},
                ],
                temperature=0.2,
                max_tokens=8000,
                response_format={'type': 'json_object'},
                timeout=180.0,
            )
            result = json.loads(response.choices[0].message.content)
            logger.info('[Synthesis] Complete')
            return result

        except Exception as e:
            logger.error(f'[Synthesis] Failed: {e}')
            return {
                'executive_summary': (
                    f'Smart Analysis synthesis encountered an error: {e}. '
                    'Please try again.'
                ),
                'key_insights': [],
                'risks': [],
                'opportunities': [],
                'ambiguities': [],
                'contradictions': [],
                'assessments': [],
                'follow_up_questions': [],
                'strategic_recommendations': [],
                'evidence_classification': {},
            }
