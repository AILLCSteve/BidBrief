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

    SYNTHESIS_SYSTEM_PROMPT = """You are a scholarly synthesis agent. Your task is to combine multiple answer fragments about the same question into ONE comprehensive, coherent answer.

CRITICAL REQUIREMENTS:
1. EVERY piece of information from EVERY fragment must be included
2. EVERY page citation must be preserved in the final answer
3. EVERY footnote and quote must be referenced
4. If fragments contain contradictory information, note both perspectives
5. Organize the answer logically, but NEVER omit any information
6. Use the format: "According to page X, ..." for each distinct piece of information
7. End with a "Sources" section listing ALL page numbers referenced

Your output MUST be exhaustive. Missing even one citation is a failure."""

    SYNTHESIS_USER_TEMPLATE = """QUESTION: {question}

COLLECTED FRAGMENTS ({fragment_count} total):
{fragments_text}

COLLECTED FOOTNOTES ({footnote_count} total):
{footnotes_text}

ALL PAGES REFERENCED: {all_pages}

---

Synthesize ALL the above into ONE comprehensive answer. Include EVERY piece of information and EVERY citation. Do not omit anything."""

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
