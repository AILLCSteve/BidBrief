"""
User Input Agent — interprets and responds to user-provided subjective questions.

v2 improvements:
  - Skipped entirely when no user input is provided (unchanged)
  - Multi-question detection: parses user blob into discrete questions
  - Evidence-grounded responses with explicit source labeling
  - Per-question follow-up direction
  - Respects confirmed_present/absent from doc_profile
"""

import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are an expert document analyst responding to specific questions about a document analysis. \
Be direct, evidence-based, and professionally honest.

For each question:
  - Cite specific analysis findings, page references, or key document details where available
  - If evidence is thin, say so explicitly — do not extrapolate beyond what is supported
  - Use precise language: distinguish between (a) confirmed by analysis, (b) partially addressed, \
    (c) not covered by current analysis, (d) appears absent from document
  - Provide a specific follow-up direction for each question if the answer is uncertain or partial

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Based on this analysis of a {doc_type} document called "{doc_name}", answer the following \
user questions as directly and specifically as possible.

=== DOCUMENT PROFILE ===
CONFIRMED PRESENT:
{confirmed_present}

CONFIRMED ABSENT:
{confirmed_absent}

UNVERIFIED:
{unverified}

EXPERTISE CONTEXT:
{expert_role} | {industry_context}

=== USER QUESTIONS ===
{user_questions}

=== ANALYSIS CONTEXT ===
{analysis_text}

===

For each user question, provide:
  1. A direct, professional answer — reference specific findings where possible
  2. Evidence quality assessment — how well-supported is the answer?
  3. A follow-up direction — what additional investigation would strengthen the answer?

Respond as JSON:
{{
  "responses": [
    {{
      "question": "The user's question (verbatim)",
      "response": "Direct, evidence-grounded answer",
      "confidence": "high|medium|low",
      "evidence_summary": "Brief summary of what supports this answer",
      "follow_up_direction": {{
        "action": "What to do next (e.g., Request clarification from owner, Review Section 00200)",
        "target": "Who or what source to consult",
        "specific_question": "Exact question to ask or section to review"
      }}
    }}
  ]
}}"""


def _fmt_profile_list(items: list, key: str, sub_key: str = '') -> str:
    if not items:
        return '  (none identified)'
    lines = []
    for item in items[:10]:  # cap for prompt size
        primary = item.get(key, '')
        secondary = item.get(sub_key, '') if sub_key else ''
        if secondary:
            lines.append(f"  • {primary}: {secondary}")
        else:
            lines.append(f"  • {primary}")
    return '\n'.join(lines)


class UserInputAgent:
    def __init__(self, api_key: str, model: str = 'gpt-4o'):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def process(
        self,
        ctx: dict,
        analysis_text: str,
        user_input: str,
        doc_profile: dict = None,
    ) -> dict:
        """Returns {'responses': []} if user_input is empty."""
        if not user_input or not user_input.strip():
            return {'responses': []}

        doc_type = ctx.get('document_type_label') or ctx.get('document_type', 'document')
        doc_name = ctx.get('document_name', 'Unknown')
        profile = doc_profile or {}
        expertise = profile.get('expertise_profile') or {}

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
            from services.ai_models import completion_params
            response = await self.client.chat.completions.create(
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
                        user_questions=user_input,
                        analysis_text=analysis_text,
                    )},
                ],
                response_format={'type': 'json_object'},
                timeout=90.0,
                **completion_params(self.model, 2500, temperature=0.2),
            )
            result = json.loads(response.choices[0].message.content)
            n = len(result.get('responses', []))
            logger.info(f'[UserInput] {n} responses produced')
            return result

        except Exception as e:
            logger.error(f'[UserInput] Failed: {e}')
            return {'responses': []}
