"""
Layer 6.5: Answer Summarizer

Sits between Layer 4 accumulation and Layer 6 output compilation (BID_SPEC).
For every answered question, the section's expert persona receives the FULL
appended pile of verbatim quotes (the merged Answer.text) and distills it into
a direct 1-3 sentence summary answer — the single takeaway a bidder needs —
stored on Answer.summary.

Design notes:
- One JSON call PER SECTION (all of that section's answered questions batched)
  to bound cost/latency on 10x10 configs.
- Personified: the system prompt reuses the Layer 2 expert's name and
  specialization so synthesis stays in-domain (same pattern HOTDOG uses for
  extraction experts).
- Non-fatal by construction: any per-section failure logs and leaves
  summary="" — an analysis must never die in a cosmetics layer.
- BestPrep mode does NOT use this layer: its Layer 7 SynthesisAgent already
  produces the distilled per-question answer.
"""

import json
import logging
from typing import Callable, Dict, List, Optional, Set

from services.ai_models import completion_params
from .models import AnswerAccumulation, ExpertPersona, ParsedConfig

logger = logging.getLogger(__name__)

_SYSTEM_TEMPLATE = (
    "You are {expert_name}, {specialization} You are the Answer Synthesis "
    "specialist for the '{section_name}' section of a bid-document analysis. "
    "For each question you receive the full appended pile of verbatim quotes "
    "extracted from the document (page citations included). Distill EACH pile "
    "into a direct 1-3 sentence answer to the question itself — the single "
    "takeaway a bidder needs. Rules: never invent facts not present in the "
    "quotes; keep numbers, dates, dimensions, and named standards exact; write "
    "plainly; do NOT include citation markers like <PDF pg X> or <VIS pg X kind>. "
    "Some quotes come from [VISUAL CONTENT] blocks — an AI reading of the "
    "drawings, maps and imagery in the document. Where an answer rests on one, "
    "say so in plain words ('the plan sheet shows...', 'per the site map...', "
    "'the detail drawing calls for...') so the reader knows the fact came from a "
    "graphic rather than the written specification. Never present a graphic as "
    "written text or vice versa. "
    'Return JSON: {{"summaries": [{{"question_id": "...", "summary": "..."}}]}} '
    "with one entry per question given."
)


class AnswerSummarizer:
    """Layer 6.5: per-question distilled answer summaries."""

    def __init__(self, openai_client, model: str):
        self.client = openai_client
        self.model = model

    async def summarize_answers(
        self,
        accumulation: AnswerAccumulation,
        config: ParsedConfig,
        experts: Dict[str, ExpertPersona],
        progress_callback: Optional[Callable] = None,
        only_question_ids: Optional[Set[str]] = None,
    ) -> None:
        """
        Mutates each answered question's PRIMARY Answer.summary in place.

        only_question_ids: restrict to these ids (second-pass re-summarization).
        """
        for section in config.sections:
            # Collect this section's answered questions (primary answers only)
            batch = []
            for question in section.questions:
                if only_question_ids is not None and question.id not in only_question_ids:
                    continue
                answers = accumulation.get(question.id) or []
                if answers:
                    batch.append((question, answers[0]))
            if not batch:
                continue

            expert = experts.get(section.id)
            expert_name = expert.name if expert else "the section analyst"
            specialization = (expert.specialization if expert else "Document analysis.").rstrip()
            if specialization and not specialization.endswith('.'):
                specialization += '.'

            if progress_callback:
                progress_callback('summary_section_start', {
                    'section': section.name, 'questions': len(batch)})

            system = _SYSTEM_TEMPLATE.format(
                expert_name=expert_name,
                specialization=specialization,
                section_name=section.name,
            )
            user_lines = []
            for question, answer in batch:
                # Name the graphics behind this answer so the summary can
                # attribute them in prose rather than leaking raw markers.
                visual_note = ""
                sources = getattr(answer, 'visual_sources', None) or []
                if sources:
                    described = ", ".join(
                        f"{s.get('kind', 'visual')} on page {s.get('page')}"
                        for s in sources)
                    visual_note = (f"VISUAL EVIDENCE BEHIND THIS ANSWER: {described}\n")
                user_lines.append(
                    f"question_id: {question.id}\nQUESTION: {question.text}\n"
                    f"{visual_note}APPENDED QUOTES:\n{answer.text}\n---"
                )
            user = (
                "Synthesize a summary answer for each of the following:\n\n"
                + "\n".join(user_lines)
            )

            try:
                response = await self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    **completion_params(self.model, 2000, temperature=0.2),
                )
                data = json.loads(response.choices[0].message.content)
                by_id = {
                    str(item.get("question_id", "")): str(item.get("summary", "")).strip()
                    for item in data.get("summaries", [])
                }
                applied = 0
                for question, answer in batch:
                    summary = by_id.get(question.id, "")
                    if summary:
                        answer.summary = summary
                        applied += 1
                logger.info(
                    f"  ✅ L6.5 summaries for '{section.name}': {applied}/{len(batch)}")
                if progress_callback:
                    progress_callback('summary_section_complete', {
                        'section': section.name, 'summarized': applied})
            except Exception as e:
                # Non-fatal: leave summaries empty for this section.
                logger.warning(f"  ⚠️ L6.5 summarization failed for '{section.name}': {e}")
                if progress_callback:
                    progress_callback('summary_section_failed', {
                        'section': section.name, 'error': str(e)})
