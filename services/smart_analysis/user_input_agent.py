"""
User Input Agent — interprets and responds to user-provided subjective questions.

Skipped entirely when no user input is provided.
Merges user questions into the analysis flow intelligently, using the full
analysis context to produce direct, evidence-based responses.
"""

import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are an expert document analyst responding to specific questions about a document analysis. \
Be direct, evidence-based, and professionally honest. Cite specific findings, page references, \
or analysis results where available. If the answer genuinely isn't in the analysis, say so \
clearly and explain what additional investigation would be needed.

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Based on this analysis of a {doc_type} document called "{doc_name}", answer the following \
questions as directly and specifically as possible.

USER QUESTIONS:
{user_questions}

ANALYSIS CONTEXT:
{analysis_text}

For each question:
- Provide a direct, professional answer
- Reference specific findings, answers, or data from the analysis where possible
- Be honest about what the analysis did and didn't cover
- Rate your confidence based on the quality of evidence available

Respond as JSON:
{{
  "responses": [
    {{
      "question": "...",
      "response": "...",
      "confidence": "high|medium|low",
      "evidence_summary": "brief summary of the supporting evidence"
    }}
  ]
}}"""


class UserInputAgent:
    def __init__(self, api_key: str, model: str = 'gpt-4o'):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def process(self, ctx: dict, analysis_text: str, user_input: str) -> dict:
        """Returns {'responses': []} if user_input is empty."""
        if not user_input or not user_input.strip():
            return {'responses': []}

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
                        user_questions=user_input,
                        analysis_text=analysis_text,
                    )},
                ],
                temperature=0.2,
                max_tokens=2000,
                response_format={'type': 'json_object'},
                timeout=90.0,
            )
            result = json.loads(response.choices[0].message.content)
            n = len(result.get('responses', []))
            logger.info(f'[UserInput] {n} responses produced')
            return result

        except Exception as e:
            logger.error(f'[UserInput] Failed: {e}')
            return {'responses': []}
