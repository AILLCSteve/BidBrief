"""
Context Aggregator Agent — no AI calls.

Structures all available data sources into a unified context dict
and a human-readable analysis text for agent prompts.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Truncate individual answers to keep total prompt size manageable
_MAX_ANSWER_CHARS = 350
# Hard cap on total analysis text sent to each agent (~10K tokens)
_MAX_ANALYSIS_TEXT_CHARS = 40000
# Cap on unanswered questions listed per section
_MAX_UNANSWERED_PER_SECTION = 5


class ContextAggregatorAgent:

    def aggregate(
        self,
        analysis_data: Dict[str, Any],
        doc_context: str = '',
        user_input: str = ''
    ) -> dict:
        """
        Build structured context from analysis_data.

        analysis_data keys expected from app.py:
          is_partial, mode, pdf_filename, result (legacy_result dict),
          key_details, document_type, document_type_label
        """
        result = analysis_data.get('result') or {}
        sections_raw = result.get('sections', [])

        sections_summary = []
        total_q = 0
        answered_q = 0

        for section in sections_raw:
            sname = section.get('section_name', 'Unknown Section')
            questions = section.get('questions', [])

            answered = []
            unanswered = []

            for q in questions:
                total_q += 1
                status = q.get('status', '')
                if status == 'found':
                    answered_q += 1
                    answer_text = q.get('answer', '') or ''
                    if len(answer_text) > _MAX_ANSWER_CHARS:
                        answer_text = answer_text[:_MAX_ANSWER_CHARS] + '...'
                    answered.append({
                        'question': q.get('text', ''),
                        'answer': answer_text,
                        'pages': q.get('pages', []),
                        'confidence': q.get('confidence', 'unknown'),
                    })
                else:
                    unanswered.append(q.get('text', ''))

            sections_summary.append({
                'section': sname,
                'answered': answered,
                'unanswered': unanswered,
            })

        answer_rate = (answered_q / total_q * 100) if total_q > 0 else 0.0

        ctx = {
            'document_name': result.get('document_name') or analysis_data.get('pdf_filename', 'Unknown Document'),
            'document_type': analysis_data.get('document_type', 'unknown'),
            'document_type_label': analysis_data.get('document_type_label', ''),
            'is_partial': bool(analysis_data.get('is_partial', False)),
            'mode': analysis_data.get('mode', 'bid_spec'),
            'total_pages': result.get('total_pages', 0),
            'total_questions': total_q,
            'questions_answered': answered_q,
            'answer_rate_pct': round(answer_rate, 1),
            'key_details': analysis_data.get('key_details') or {},
            'sections': sections_summary,
            'doc_context': doc_context or '',
            'user_input': user_input or '',
        }

        logger.info(
            f"[ContextAggregator] {ctx['document_name']} | "
            f"type={ctx['document_type']} | "
            f"{ctx['questions_answered']}/{ctx['total_questions']} answered | "
            f"partial={ctx['is_partial']}"
        )
        return ctx

    def build_analysis_text(self, ctx: dict) -> str:
        """
        Render ctx as human-readable text for agent prompts.
        Stays within _MAX_ANALYSIS_TEXT_CHARS.
        """
        lines = []

        lines.append(f"DOCUMENT: {ctx['document_name']}")
        lines.append(f"TYPE: {ctx['document_type_label'] or ctx['document_type']}")
        completeness = 'PARTIAL (analysis was stopped early)' if ctx['is_partial'] else 'COMPLETE'
        lines.append(
            f"ANALYSIS STATUS: {completeness} — "
            f"{ctx['questions_answered']}/{ctx['total_questions']} questions answered "
            f"({ctx['answer_rate_pct']}%)"
        )
        lines.append(f"DOCUMENT PAGES: {ctx['total_pages']}")
        lines.append('')

        if ctx['key_details']:
            lines.append('KEY DOCUMENT DETAILS:')
            for k, v in ctx['key_details'].items():
                lines.append(f'  {k}: {v}')
            lines.append('')

        if ctx['doc_context']:
            lines.append('DOCUMENT CONTEXT (title page / TOC / glossary excerpt):')
            # Cap the context portion to leave room for Q&A
            lines.append(ctx['doc_context'][:3000])
            lines.append('')

        lines.append('ANALYSIS RESULTS BY SECTION:')
        for sec in ctx['sections']:
            lines.append(f"\n## {sec['section']}")

            if sec['answered']:
                for qa in sec['answered']:
                    pages_str = f"pp.{qa['pages']}" if qa['pages'] else 'page unknown'
                    lines.append(f"  Q: {qa['question']}")
                    lines.append(f"  A [{qa['confidence']} confidence, {pages_str}]: {qa['answer']}")

            if sec['unanswered']:
                capped = sec['unanswered'][:_MAX_UNANSWERED_PER_SECTION]
                remainder = len(sec['unanswered']) - len(capped)
                lines.append(f"  UNANSWERED ({len(sec['unanswered'])} questions):")
                for q in capped:
                    lines.append(f"    - {q}")
                if remainder > 0:
                    lines.append(f"    ... and {remainder} more unanswered")

        text = '\n'.join(lines)

        if len(text) > _MAX_ANALYSIS_TEXT_CHARS:
            text = text[:_MAX_ANALYSIS_TEXT_CHARS] + '\n\n[Context truncated for length]'

        return text
