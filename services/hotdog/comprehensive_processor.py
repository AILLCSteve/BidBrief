"""
Comprehensive Quick-Scan Processor for HOTDOG7ATE Stage 1.

HOTDOG7ATE = Hierarchical Orchestrated Thorough Document Oversight & Guidance -
             Adaptive Thorough Extraction

Uses document structure to fast-track answer discovery before exhaustive processing.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from openai import AsyncOpenAI

from .models import Question, Answer, PageData
from .document_structure_analyzer import DocumentStructureAnalyzer, DocumentStructure

logger = logging.getLogger(__name__)


class ComprehensiveProcessor:
    """
    Stage 1: Comprehensive Quick-Scan Processor.

    Strategy:
    1. Analyze document structure (TOC, index, headers)
    2. For each question, identify likely pages using structure
    3. Query those specific pages first (targeted extraction)
    4. Mark questions with >=90% confidence as "answered"
    5. Return remaining questions for exhaustive processing
    """

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        model: str = "gpt-4o",
        confidence_threshold: float = 0.90
    ):
        self.client = openai_client
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.structure_analyzer = DocumentStructureAnalyzer()

        # Stats
        self.questions_processed = 0
        self.high_confidence_answers = 0
        self.api_calls = 0
        self.tokens_used = 0

    async def quick_scan(
        self,
        pages: List[PageData],
        questions: List[Question],
        experts: Dict  # section_id -> ExpertPersona
    ) -> Tuple[Dict[str, Answer], List[Question]]:
        """
        Perform comprehensive quick-scan on document.

        Args:
            pages: All extracted pages
            questions: All questions to answer
            experts: Expert personas by section

        Returns:
            Tuple of:
            - Dict of high-confidence answers (question_id -> Answer)
            - List of questions needing exhaustive processing
        """
        logger.info(f"\n{'='*64}")
        logger.info("STAGE 1: HOTDOG7ATE Comprehensive Quick-Scan")
        logger.info(f"{'='*64}")

        start_time = datetime.now()

        # Analyze document structure
        pages_data = [{'page_num': p.page_num, 'text': p.text} for p in pages]
        structure = self.structure_analyzer.analyze(pages_data)

        high_confidence_answers = {}
        questions_for_exhaustive = []

        # Process each question
        for question in questions:
            self.questions_processed += 1

            # Find relevant pages using structure
            relevant_pages = self.structure_analyzer.get_pages_for_topic(question.text)

            if relevant_pages:
                # Try targeted extraction on relevant pages
                answer = await self._targeted_extraction(
                    question=question,
                    pages=[p for p in pages if p.page_num in relevant_pages],
                    expert=experts.get(question.section_id)
                )

                if answer and answer.confidence >= self.confidence_threshold:
                    high_confidence_answers[question.id] = answer
                    self.high_confidence_answers += 1
                    logger.info(f"  {question.id}: Quick-scan success ({answer.confidence:.0%})")
                else:
                    questions_for_exhaustive.append(question)
                    logger.debug(f"  {question.id}: Needs exhaustive pass")
            else:
                # No structural hints - send to exhaustive
                questions_for_exhaustive.append(question)
                logger.debug(f"  {question.id}: No structural hints, queued for exhaustive")

        elapsed = (datetime.now() - start_time).total_seconds()

        logger.info(f"\nQuick-Scan Complete ({elapsed:.1f}s)")
        logger.info(f"   High-confidence answers: {len(high_confidence_answers)}/{len(questions)}")
        logger.info(f"   Questions for exhaustive: {len(questions_for_exhaustive)}")

        return high_confidence_answers, questions_for_exhaustive

    async def _targeted_extraction(
        self,
        question: Question,
        pages: List[PageData],
        expert: Optional[object]
    ) -> Optional[Answer]:
        """
        Extract answer from targeted pages.
        """
        if not pages:
            return None

        # Combine page texts
        context = "\n\n".join([
            f"[Page {p.page_num}]\n{p.text}"
            for p in pages[:5]  # Max 5 pages per targeted query
        ])

        page_nums = [p.page_num for p in pages[:5]]

        prompt = f"""Analyze these document pages to answer the following question.

QUESTION: {question.text}

DOCUMENT PAGES:
{context}

INSTRUCTIONS:
1. Find the BEST answer to the question from the provided pages
2. Include direct quotes with page citations in format <PDF pg X>
3. Rate your confidence (0.0-1.0) based on how clearly the answer is stated
4. If the answer is not clearly found, respond with confidence 0.0

OUTPUT FORMAT (JSON):
{{
    "answer": "Your answer with <PDF pg X> citation",
    "pages": [{', '.join(map(str, page_nums))}],
    "confidence": 0.95,
    "reasoning": "Brief explanation of how you found this"
}}
"""

        try:
            self.api_calls += 1
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": expert.system_prompt if expert else "You are a document analysis expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            self.tokens_used += response.usage.total_tokens

            import json
            data = json.loads(response.choices[0].message.content)

            answer_text = data.get('answer', '')
            confidence = data.get('confidence', 0.0)
            pages_cited = data.get('pages', page_nums)

            if not answer_text or confidence == 0.0:
                return None

            # Ensure citation marker
            if '<PDF pg' not in answer_text:
                pages_str = ', '.join(map(str, pages_cited))
                answer_text += f" <PDF pg {pages_str}>"

            return Answer(
                question_id=question.id,
                text=answer_text,
                pages=pages_cited,
                confidence=confidence,
                expert=expert.name if expert else "Quick-Scan",
                window=0  # Not window-based
            )

        except Exception as e:
            logger.warning(f"Targeted extraction failed for {question.id}: {e}")
            return None

    def get_statistics(self) -> Dict:
        """Get processing statistics."""
        return {
            'questions_processed': self.questions_processed,
            'high_confidence_answers': self.high_confidence_answers,
            'success_rate': self.high_confidence_answers / self.questions_processed if self.questions_processed else 0,
            'api_calls': self.api_calls,
            'tokens_used': self.tokens_used
        }
