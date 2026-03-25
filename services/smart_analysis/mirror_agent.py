"""
MIRROR Agent — dynamic MIRROR-framework stress-testing.

Missing elements · Interpretation stress testing · Risk identification
Perspective simulation · Outcome simulation · Refinement

Acts as adversarial reviewer: finds what's wrong, what's missing, what could
fail, and what looks different from other angles.
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
and how this looks from angles the original analysis may have missed. But be selective: \
only flag findings that are genuinely important, not noise.

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Stress-test this analysis of a {doc_type} document called "{doc_name}":

{analysis_text}

Apply MIRROR reasoning to surface the most important concerns:

- MISSING ELEMENTS: What important data, clauses, requirements, or context is absent from \
this analysis? What should have been found but wasn't?

- INTERPRETATION RISKS: Where could the analysis be reading something wrong? What terms, \
provisions, or findings are open to multiple interpretations — and which interpretation is \
more favorable vs. more risky?

- RISKS: What are the concrete threats to success, profitability, execution, or outcome? \
Be specific about likelihood and impact.

- STAKEHOLDER PERSPECTIVES: How does this document look from the contractor's perspective? \
The owner/agency? Subcontractors? Other relevant parties? What concerns would each raise?

- FAILURE SCENARIOS: How could this project, engagement, or execution go wrong? \
What are the most plausible failure paths?

Only include findings that would actually change a professional's decision or concern level.

Respond as JSON:
{{
  "missing_elements": [
    {{"element": "...", "importance": "high|medium|low", "why_it_matters": "..."}}
  ],
  "interpretation_risks": [
    {{
      "area": "...",
      "current_reading": "...",
      "risky_alternative": "...",
      "recommendation": "..."
    }}
  ],
  "risks": [
    {{
      "risk": "...",
      "likelihood": "high|medium|low",
      "impact": "high|medium|low",
      "specific_concern": "...",
      "mitigation": "..."
    }}
  ],
  "stakeholder_perspectives": [
    {{"stakeholder": "...", "concern": "...", "implication": "..."}}
  ],
  "failure_scenarios": [
    {{"scenario": "...", "trigger": "...", "likelihood": "high|medium|low", "consequence": "..."}}
  ]
}}"""


class MIRRORAgent:
    def __init__(self, api_key: str, model: str = 'gpt-4o'):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def analyze(self, ctx: dict, analysis_text: str) -> dict:
        doc_type = ctx.get('document_type_label') or ctx.get('document_type', 'document')
        doc_name = ctx.get('document_name', 'Unknown')

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': _SYSTEM},
                    {'role': 'user', 'content': _USER_TEMPLATE.format(
                        doc_type=doc_type,
                        doc_name=doc_name,
                        analysis_text=analysis_text,
                    )},
                ],
                temperature=0.3,
                max_tokens=3000,
                response_format={'type': 'json_object'},
                timeout=90.0,
            )
            result = json.loads(response.choices[0].message.content)
            total = sum(len(v) for v in result.values() if isinstance(v, list))
            logger.info(f'[MIRROR] Complete: {total} findings')
            return result

        except Exception as e:
            logger.error(f'[MIRROR] Failed: {e}')
            return {
                'missing_elements': [],
                'interpretation_risks': [],
                'risks': [],
                'stakeholder_perspectives': [],
                'failure_scenarios': [],
            }
