"""
SCOUT Agent — dynamic SCOUT-framework analysis.

Sanity-checking · Criteria scaffolding · Opportunity discovery
Uncertainty mapping · Assumption testing

Applies SCOUT principles as reasoning guides, not a mechanical checklist.
The AI determines which principles are most relevant to THIS specific document.
"""

import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a senior bid evaluation and document analysis expert. You apply SCOUT reasoning \
to evaluate analyses: Sanity-checking, Criteria scaffolding, Opportunity discovery, \
Uncertainty mapping, and Assumption testing.

Your role is NOT to mechanically apply every principle. Reason dynamically — determine \
which SCOUT principles yield the most valuable insights for THIS specific document type \
and analysis results. Skip principles that don't apply. Focus on what genuinely matters \
for professional decision-making.

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Analyze this {doc_type} document called "{doc_name}":

{analysis_text}

Apply SCOUT reasoning to produce insights tailored to this specific document and analysis:

- SANITY CHECKS: Do the numbers, claims, and commitments in this document hold together? \
Flag anything that doesn't add up, seems unrealistic, or contradicts itself.

- CRITERIA GAPS: What important evaluation criteria should have been assessed but weren't? \
What questions should have been asked but weren't in the analysis?

- OPPORTUNITIES: What genuine opportunities does this document reveal — strategic, \
financial, operational, or competitive?

- UNCERTAINTIES: Where is critical information missing, ambiguous, or unverifiable? \
What is unclear that a decision-maker needs to know?

- ASSUMPTIONS: What is being assumed to be true that could be wrong? What assumptions, \
if false, would materially change the evaluation?

Only include findings that are genuinely important for THIS document. Quality over quantity.

Respond as JSON:
{{
  "sanity_flags": [
    {{"claim": "...", "concern": "...", "severity": "high|medium|low"}}
  ],
  "criteria_gaps": [
    {{"gap": "...", "context": "...", "impact": "..."}}
  ],
  "opportunities": [
    {{"opportunity": "...", "rationale": "...", "category": "..."}}
  ],
  "uncertainties": [
    {{"area": "...", "what_is_unclear": "...", "why_it_matters": "..."}}
  ],
  "assumptions": [
    {{"assumption": "...", "risk_if_wrong": "...", "likelihood_wrong": "high|medium|low"}}
  ]
}}"""


class SCOUTAgent:
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
            logger.info(f'[SCOUT] Complete: {total} findings')
            return result

        except Exception as e:
            logger.error(f'[SCOUT] Failed: {e}')
            return {
                'sanity_flags': [],
                'criteria_gaps': [],
                'opportunities': [],
                'uncertainties': [],
                'assumptions': [],
            }
