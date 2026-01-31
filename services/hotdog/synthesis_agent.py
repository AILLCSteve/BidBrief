"""
Layer 7: Synthesis Agent for BestPrep mode.
Reviews all accumulated fragments and footnotes to produce one cohesive final answer.
"""
import logging
import asyncio
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI

from .append_accumulator import CumulativeAnswer, AppendOnlyAccumulator

logger = logging.getLogger(__name__)


class SynthesisAgent:
    """
    Final synthesis layer that reviews all answer fragments and footnotes
    to produce one comprehensive, coherent answer per question.

    Guarantees:
    1. Every fragment is considered
    2. Every footnote is included in the final answer
    3. All page citations are preserved
    4. Contradictions are noted and reconciled
    """

    SYNTHESIS_SYSTEM_PROMPT = """You are an expert synthesis agent specializing in combining multiple answer fragments into one cohesive, natural language response.

CRITICAL REQUIREMENTS:
1. Produce a NATURAL LANGUAGE answer - written as flowing prose, NOT as a list of citations
2. NEVER include page numbers, citations, or source references in the answer text itself
3. DO NOT use phrases like "According to page X", "As stated in...", "Per the document...", etc.
4. Combine ALL information from ALL fragments into a unified, coherent response
5. If fragments contain contradictory information, reconcile them or present both perspectives naturally
6. Structure the answer appropriately based on length:
   - Short answers (1-2 sentences): Direct, concise statement
   - Medium answers (paragraph): Well-structured paragraph with logical flow
   - Long answers (multiple points): Use natural paragraph breaks, not bullet points
7. The answer should read as if written by a knowledgeable expert who has internalized all the source material
8. Every piece of information from every fragment MUST be included - omit NOTHING
9. Citations, page numbers, and footnotes are tracked SEPARATELY - they should NOT appear in your synthesized answer

OUTPUT FORMAT: Pure, natural language prose. No citations. No page references. No source attributions.
The footnotes and citations are already captured elsewhere - your job is ONLY to produce the synthesized answer text."""

    SYNTHESIS_USER_TEMPLATE = """QUESTION: {question}

COLLECTED FRAGMENTS ({fragment_count} total):
{fragments_text}

COLLECTED FOOTNOTES ({footnote_count} total):
{footnotes_text}

ALL PAGES REFERENCED (for tracking only, NOT for inclusion in answer): {all_pages}

---

TASK: Synthesize ALL the information from the fragments above into ONE comprehensive, natural language answer.

RULES:
- Write in natural prose - NO inline citations or page references
- Include EVERY piece of information from EVERY fragment
- Structure the answer appropriately (short/medium/long based on content)
- The answer should read as expert knowledge, not as a document summary
- DO NOT include "Sources:", "References:", or any citation section

OUTPUT: Natural language answer ONLY."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self._stats = {
            'questions_synthesized': 0,
            'total_tokens_used': 0,
            'synthesis_errors': 0
        }

    async def synthesize_question(
        self,
        cumulative_answer: CumulativeAnswer
    ) -> Optional[str]:
        """
        Synthesize all fragments for a single question into one answer.

        Returns the synthesized answer text, or None on failure.
        """
        if cumulative_answer.fragment_count == 0:
            logger.warning(f"No fragments to synthesize for {cumulative_answer.question_id}")
            return None

        # Build fragments text
        fragments_lines = []
        for i, frag in enumerate(cumulative_answer.fragments, 1):
            fragments_lines.append(
                f"[Fragment {i} - Window {frag.window_index}, "
                f"Pages {frag.pages}, Confidence {frag.confidence:.0%}]\n"
                f"{frag.text}\n"
            )
        fragments_text = "\n".join(fragments_lines)

        # Build footnotes text
        footnotes_lines = []
        for fn in cumulative_answer.footnotes:
            footnotes_lines.append(
                f"[{fn.footnote_id} - Page {fn.page}]\n"
                f"Quote: \"{fn.quote}\"\n"
            )
        footnotes_text = "\n".join(footnotes_lines) if footnotes_lines else "(No explicit footnotes extracted)"

        # Build the prompt
        user_prompt = self.SYNTHESIS_USER_TEMPLATE.format(
            question=cumulative_answer.question_text,
            fragment_count=cumulative_answer.fragment_count,
            fragments_text=fragments_text,
            footnote_count=cumulative_answer.footnote_count,
            footnotes_text=footnotes_text,
            all_pages=cumulative_answer.all_pages
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Lower temperature for factual synthesis
                max_tokens=4000
            )

            synthesized = response.choices[0].message.content
            self._stats['questions_synthesized'] += 1
            self._stats['total_tokens_used'] += response.usage.total_tokens

            logger.info(
                f"Synthesized {cumulative_answer.question_id}: "
                f"{cumulative_answer.fragment_count} fragments -> "
                f"{len(synthesized)} chars"
            )

            return synthesized

        except Exception as e:
            logger.error(f"Synthesis failed for {cumulative_answer.question_id}: {e}")
            self._stats['synthesis_errors'] += 1
            return None

    async def synthesize_all(
        self,
        accumulator: AppendOnlyAccumulator,
        section_ids: Optional[List[str]] = None,
        max_concurrent: int = 3
    ) -> Dict[str, str]:
        """
        Synthesize answers for all questions (or filtered by section).

        Args:
            accumulator: The AppendOnlyAccumulator with all fragments
            section_ids: Optional filter for specific sections
            max_concurrent: Max concurrent synthesis calls

        Returns:
            Dict mapping question_id to synthesized answer
        """
        questions = accumulator.get_questions_for_synthesis()

        if section_ids:
            questions = [q for q in questions if any(
                q.question_id.startswith(sid) for sid in section_ids
            )]

        logger.info(f"Starting synthesis for {len(questions)} questions")

        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def synthesize_with_limit(ca: CumulativeAnswer):
            async with semaphore:
                result = await self.synthesize_question(ca)
                if result:
                    accumulator.set_synthesized_answer(ca.question_id, result)
                    results[ca.question_id] = result

        await asyncio.gather(*[synthesize_with_limit(q) for q in questions])

        logger.info(
            f"Synthesis complete: {len(results)}/{len(questions)} successful, "
            f"{self._stats['total_tokens_used']} tokens used"
        )

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get synthesis statistics."""
        return self._stats.copy()
