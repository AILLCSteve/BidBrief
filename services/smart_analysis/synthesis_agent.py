"""
Synthesis Agent — combines all agent outputs into the final executive report.

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

OUTPUT REQUIREMENTS:
  - Every risk, ambiguity, and uncertainty item must include a follow_up_direction
  - Merge overlapping SCOUT and MIRROR findings — do not list the same issue twice
  - Be decisive where evidence supports it; acknowledge uncertainty where it does not
  - Write the executive summary for a busy decision-maker who needs the full picture in 2 minutes

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Synthesize the following multi-framework analysis into a comprehensive professional executive report.

=== DOCUMENT PROFILE ===
Document: {doc_name}
Type: {doc_type}
Analysis Status: {completeness} — {answer_rate}% of questions answered
{partial_note}

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
  4. Every uncertain/missing/risky item MUST include specific follow-up direction
  5. Merge SCOUT + MIRROR overlapping findings — do not duplicate

Respond as JSON:
{{
  "executive_summary": "3-5 paragraph professional narrative. Cover: (1) what the analysis \
confirms about the document, (2) key decision factors, (3) most significant risks or gaps, \
(4) overall professional assessment. Use precise language tiers throughout. Write for a \
decision-maker who needs the full picture in 2 minutes.",

  "key_insights": [
    "Most important insight — specific, evidence-based, decision-relevant (cite tier)",
    "Second insight",
    "..."
  ],

  "risks": [
    {{
      "title": "Short risk title",
      "description": "Specific, evidence-based description using language tier",
      "severity": "critical|high|medium|low",
      "evidence": ["Specific evidence point from analysis"],
      "page_refs": [],
      "follow_up_direction": {{
        "action": "What to do",
        "target": "Who or what source",
        "specific_question": "Exact follow-up question"
      }}
    }}
  ],

  "opportunities": [
    {{
      "title": "Short title",
      "description": "Specific, actionable description",
      "severity": "high|medium|low",
      "evidence": ["Supporting evidence"],
      "page_refs": []
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
        "action": "What to do",
        "target": "Who or what source",
        "specific_question": "Exact follow-up question"
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
      "category": "e.g., Risk Level, Profitability Outlook, Execution Complexity",
      "rating": "e.g., High, Moderate, Favorable",
      "rationale": "One sentence explanation with benchmark reference",
      "confidence": "high|medium|low"
    }}
  ],

  "follow_up_questions": [
    "Specific, targeted question that must be answered before decision — include who to ask"
  ],

  "strategic_recommendations": [
    "Specific, actionable recommendation with the reasoning basis"
  ],

  "evidence_classification": {{
    "confirmed_present_used": ["Topics from confirmed_present that informed the analysis"],
    "confirmed_absent_flagged": ["Topics from confirmed_absent flagged as gaps"],
    "unverified_flagged": ["Topics from unverified flagged as unresolved"],
    "language_tiers_applied": "Brief note on how the language tiers were applied"
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
                max_tokens=5000,
                response_format={'type': 'json_object'},
                timeout=120.0,
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
