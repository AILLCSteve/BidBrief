"""
Synthesis Agent — combines SCOUT, MIRROR, and user input findings into a
single coherent executive-level SmartAnalysisResult.

This is the master call: receives all agent outputs plus the full context,
and produces the structured, professional final analysis.
"""

import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a senior analyst and executive communicator. You synthesize multi-framework \
document analyses into clear, professional, decision-oriented executive reports.

Your output must be:
- Highly professional and precise — written for executives making real decisions
- Free of hedging language where evidence is clear
- Honest about uncertainty where evidence is genuinely thin
- Non-redundant: merge overlapping findings from SCOUT and MIRROR into unified insights
- Context-appropriate: tailor assessments to the document type

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Synthesize the following analysis findings into a comprehensive professional executive report.

DOCUMENT: {doc_name}
TYPE: {doc_type}
ANALYSIS STATUS: {completeness} — {answer_rate}% of questions answered
{partial_note}
KEY DOCUMENT DETAILS:
{key_details}

--- SCOUT FINDINGS (systematic evaluation) ---
{scout_json}

--- MIRROR FINDINGS (risk & stress-test) ---
{mirror_json}

--- USER QUESTION RESPONSES ---
{user_responses_json}

---

Produce a comprehensive, professional executive analysis. Be decisive where evidence supports \
it. Acknowledge gaps honestly. Merge overlapping SCOUT and MIRROR findings — don't list the \
same issue twice under different headings.

CONTEXT-APPROPRIATE ASSESSMENTS to include (select only those relevant to this document type):
- Bid/spec/RFP/RFQ documents: Risk Level, Profitability Outlook, Execution Complexity, \
  Strategic Fit, Competitive Position
- Contract/agreement documents: Legal Risk, Commercial Viability, Compliance Risk, \
  Execution Feasibility
- Report/study documents: Finding Reliability, Recommendation Strength, \
  Implementation Feasibility
- Other types: determine the most relevant 2-4 assessments for professional decision-making

Respond as JSON:
{{
  "executive_summary": "3-5 paragraph professional narrative covering the most critical \
findings, overall assessment, and key decision factors. Write this for a busy executive \
who needs the full picture in 2 minutes.",
  "key_insights": [
    "Most important insight — concise, specific, decision-relevant",
    "Second insight",
    "..."
  ],
  "risks": [
    {{
      "title": "Short title",
      "description": "Specific, evidence-based description",
      "severity": "critical|high|medium|low",
      "evidence": ["specific evidence point 1", "..."],
      "page_refs": []
    }}
  ],
  "opportunities": [
    {{
      "title": "Short title",
      "description": "Specific, actionable description",
      "severity": "high|medium|low",
      "evidence": ["..."],
      "page_refs": []
    }}
  ],
  "ambiguities": [
    {{
      "title": "Short title",
      "description": "What is unclear and why it matters",
      "severity": "high|medium|low",
      "evidence": ["..."],
      "page_refs": []
    }}
  ],
  "contradictions": [
    {{
      "title": "Short title",
      "description": "What contradicts what, and the implication",
      "severity": "high|medium|low",
      "evidence": ["..."],
      "page_refs": []
    }}
  ],
  "assessments": [
    {{
      "category": "Risk Level",
      "rating": "High|Moderate|Low|Favorable|Unfavorable|...",
      "rationale": "One sentence explanation",
      "confidence": "high|medium|low"
    }}
  ],
  "follow_up_questions": [
    "Specific question that should be investigated before decision",
    "..."
  ],
  "strategic_recommendations": [
    "Specific, actionable recommendation",
    "..."
  ]
}}"""


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
    ) -> dict:
        doc_type = ctx.get('document_type_label') or ctx.get('document_type', 'document')
        doc_name = ctx.get('document_name', 'Unknown')
        is_partial = ctx.get('is_partial', False)
        partial_note = (
            'NOTE: This analysis is PARTIAL — it was stopped before completion. '
            'Factor incomplete coverage into your confidence levels and recommendations.\n'
            if is_partial else ''
        )

        key_details = ctx.get('key_details') or {}
        key_details_text = (
            '\n'.join(f'  {k}: {v}' for k, v in key_details.items())
            if key_details else '  Not extracted'
        )

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
                        key_details=key_details_text,
                        scout_json=json.dumps(scout_findings, indent=2),
                        mirror_json=json.dumps(mirror_findings, indent=2),
                        user_responses_json=(
                            json.dumps(user_resp_list, indent=2)
                            if user_resp_list else '(none provided)'
                        ),
                    )},
                ],
                temperature=0.2,
                max_tokens=4500,
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
            }
