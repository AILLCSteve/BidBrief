"""
Context Aggregator Agent — no AI calls.

Structures all available data sources into a unified context dict
and human-readable analysis texts for agent prompts.

CRITICAL FIX (v2): The legacy result format from _transform_to_legacy_format() uses:
  - 'question'       (not 'text' or 'question_text')
  - 'answer'         (not 'status' — presence of non-empty answer = answered)
  - 'page_citations' (not 'pages')
  - 'footnote'       (direct PDF text excerpt — valuable grounding evidence)
The previous version used the wrong field names, causing ALL Q&A to appear as unanswered.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Truncation for standard analysis text (SCOUT/MIRROR agents)
_MAX_ANSWER_CHARS = 600           # was 350 — increased for better answer fidelity
_MAX_ANALYSIS_TEXT_CHARS = 40000  # ~10K tokens, unchanged
_MAX_FOOTNOTE_CHARS = 400         # per-answer footnote excerpt

# Rich analysis text (for DocumentProfileAgent — highest-fidelity pass)
_MAX_RICH_ANSWER_CHARS = 900
_MAX_RICH_ANALYSIS_TEXT_CHARS = 60000

# No longer cap unanswered questions per section — list them all
# (previously capped at 5, hiding important gaps from agents)
_MAX_UNANSWERED_PER_SECTION = 9999  # effectively uncapped


def _resolve_question_fields(q: dict) -> tuple:
    """
    Resolve question/answer fields for both legacy and modern result formats.

    Legacy (from _transform_to_legacy_format):
      question, answer, page_citations, confidence, footnote

    Modern (from get_browser_output before transform):
      question_text, primary_answer.text, primary_answer.pages, has_answer

    Returns: (question_text, answer_text, page_refs, confidence, footnote)
    """
    # Question text — try all known field names
    question_text = (
        q.get('question')
        or q.get('text')
        or q.get('question_text')
        or ''
    )

    # Answer text — legacy has 'answer'; modern wraps in 'primary_answer'
    answer_text = q.get('answer') or ''
    if not answer_text:
        primary = q.get('primary_answer') or {}
        answer_text = primary.get('text') or ''

    # Page refs — legacy: 'page_citations'; modern: 'pages' or primary_answer.pages
    page_refs = (
        q.get('page_citations')
        or q.get('pages')
        or (q.get('primary_answer') or {}).get('pages')
        or []
    )

    # Confidence
    confidence = q.get('confidence', 0.0)
    if not confidence and q.get('primary_answer'):
        confidence = (q.get('primary_answer') or {}).get('confidence', 0.0)

    # Footnote — actual PDF text excerpt
    footnote = q.get('footnote') or (q.get('primary_answer') or {}).get('footnote') or ''

    return question_text, answer_text, page_refs, confidence, footnote


class ContextAggregatorAgent:

    def aggregate(
        self,
        analysis_data: Dict[str, Any],
        doc_context: str = '',
        user_input: str = '',
    ) -> dict:
        """
        Build structured context from analysis_data.

        analysis_data keys expected from app.py:
          is_partial, mode, pdf_filename,
          result (legacy_result dict from _transform_to_legacy_format),
          key_details (Dict[str,str] from get_summary_data),
          key_details_list (List[Dict] from get_details_list — includes quotes/pages),
          document_type, document_type_label
        """
        result = analysis_data.get('result') or {}
        sections_raw = result.get('sections', [])

        sections_summary: List[dict] = []
        total_q = 0
        answered_q = 0

        for section in sections_raw:
            sname = section.get('section_name', 'Unknown Section')
            questions = section.get('questions', [])

            answered = []
            unanswered = []

            for q in questions:
                total_q += 1
                q_text, a_text, pages, conf, footnote = _resolve_question_fields(q)

                if a_text:  # answered = non-empty answer text
                    answered_q += 1
                    truncated = a_text
                    if len(truncated) > _MAX_ANSWER_CHARS:
                        truncated = truncated[:_MAX_ANSWER_CHARS] + '...'
                    entry = {
                        'question': q_text,
                        'answer': truncated,
                        'pages': pages,
                        'confidence': conf,
                    }
                    # Include footnote if high-confidence (>=0.7) — actual PDF text
                    if footnote and isinstance(conf, (int, float)) and conf >= 0.7:
                        entry['footnote'] = footnote[:_MAX_FOOTNOTE_CHARS]
                    answered.append(entry)
                else:
                    if q_text:
                        unanswered.append(q_text)

            sections_summary.append({
                'section': sname,
                'answered': answered,
                'unanswered': unanswered,
            })

        answer_rate = (answered_q / total_q * 100) if total_q > 0 else 0.0

        # key_details_list: richer format with quotes and page refs
        key_details_list = analysis_data.get('key_details_list') or []

        # Top-level footnotes from the result (document-level citations)
        result_footnotes = result.get('footnotes') or []

        ctx = {
            'document_name': (
                result.get('document_name')
                or analysis_data.get('pdf_filename', 'Unknown Document')
            ),
            'document_type': analysis_data.get('document_type', 'unknown'),
            'document_type_label': analysis_data.get('document_type_label', ''),
            'is_partial': bool(analysis_data.get('is_partial', False)),
            'mode': analysis_data.get('mode', 'bid_spec'),
            'total_pages': result.get('total_pages', 0),
            'total_questions': total_q,
            'questions_answered': answered_q,
            'answer_rate_pct': round(answer_rate, 1),
            'key_details': analysis_data.get('key_details') or {},
            'key_details_list': key_details_list,
            'result_footnotes': result_footnotes[:20],  # top-level citations, capped
            'sections': sections_summary,
            'doc_context': doc_context or '',
            'user_input': user_input or '',
        }

        logger.info(
            f"[ContextAggregator] {ctx['document_name']} | "
            f"type={ctx['document_type']} | "
            f"{ctx['questions_answered']}/{ctx['total_questions']} answered "
            f"({ctx['answer_rate_pct']}%) | "
            f"partial={ctx['is_partial']} | "
            f"key_details={len(key_details_list)} items"
        )
        return ctx

    # ------------------------------------------------------------------
    # Standard analysis text — for SCOUT / MIRROR / UserInput agents
    # ------------------------------------------------------------------

    def build_analysis_text(self, ctx: dict) -> str:
        """
        Render ctx as human-readable text for SCOUT/MIRROR agent prompts.
        Capped at _MAX_ANALYSIS_TEXT_CHARS.
        """
        lines = self._build_header_lines(ctx)

        lines.append('ANALYSIS RESULTS BY SECTION:')
        for sec in ctx['sections']:
            lines.append(f"\n## {sec['section']}")

            if sec['answered']:
                for qa in sec['answered']:
                    pages_str = f"pp.{qa['pages']}" if qa['pages'] else 'page unknown'
                    conf_str = (
                        f"{int(qa['confidence']*100)}%"
                        if isinstance(qa['confidence'], float)
                        else str(qa['confidence'])
                    )
                    lines.append(f"  Q: {qa['question']}")
                    lines.append(f"  A [{conf_str} confidence, {pages_str}]: {qa['answer']}")
                    if qa.get('footnote'):
                        lines.append(f"  CITATION: {qa['footnote']}")
            else:
                lines.append('  (no questions answered in this section)')

            if sec['unanswered']:
                lines.append(f"  GAPS — {len(sec['unanswered'])} unanswered questions:")
                for q in sec['unanswered']:
                    lines.append(f"    - {q}")

        text = '\n'.join(lines)
        if len(text) > _MAX_ANALYSIS_TEXT_CHARS:
            text = text[:_MAX_ANALYSIS_TEXT_CHARS] + '\n\n[Context truncated for length]'
        return text

    # ------------------------------------------------------------------
    # Rich analysis text — for DocumentProfileAgent (maximum fidelity)
    # ------------------------------------------------------------------

    def build_rich_analysis_text(self, ctx: dict) -> str:
        """
        High-fidelity analysis text for DocumentProfileAgent.
        Larger answer budget, no unanswered-question cap, includes all footnotes.
        Capped at _MAX_RICH_ANALYSIS_TEXT_CHARS.
        """
        lines = self._build_header_lines(ctx)

        # Include richer key_details with quotes if available
        key_details_list = ctx.get('key_details_list', [])
        if key_details_list:
            lines.append('KEY DOCUMENT DETAILS (with source evidence):')
            for item in key_details_list:
                name = item.get('name', '')
                value = item.get('value', '')
                page = item.get('page', 0)
                conf = item.get('confidence', 0.0)
                quote = item.get('quote', '')
                page_str = f" [p.{page}]" if page else ''
                conf_str = f" ({int(conf*100)}% confidence)" if conf else ''
                lines.append(f"  {name}: {value}{page_str}{conf_str}")
                if quote:
                    lines.append(f"    Source quote: \"{quote[:200]}\"")
            lines.append('')

        # Top-level result footnotes (document citations)
        result_footnotes = ctx.get('result_footnotes', [])
        if result_footnotes:
            lines.append('DOCUMENT CITATIONS (extracted during analysis):')
            for fn in result_footnotes[:10]:
                lines.append(f"  • {str(fn)[:300]}")
            lines.append('')

        lines.append('FULL ANALYSIS RESULTS BY SECTION:')
        for sec in ctx['sections']:
            lines.append(f"\n## {sec['section']}")

            if sec['answered']:
                for qa in sec['answered']:
                    pages_str = f"pp.{qa['pages']}" if qa['pages'] else 'page unknown'
                    conf_str = (
                        f"{int(qa['confidence']*100)}%"
                        if isinstance(qa['confidence'], float)
                        else str(qa['confidence'])
                    )
                    # Rich text uses larger answer budget
                    answer = qa['answer']
                    if len(answer) > _MAX_RICH_ANSWER_CHARS:
                        answer = answer[:_MAX_RICH_ANSWER_CHARS] + '...'
                    lines.append(f"  Q: {qa['question']}")
                    lines.append(f"  A [{conf_str}, {pages_str}]: {answer}")
                    if qa.get('footnote'):
                        lines.append(f"  PDF EVIDENCE: {qa['footnote']}")
            else:
                lines.append('  (no answers extracted for this section)')

            if sec['unanswered']:
                lines.append(
                    f"  UNANSWERED / NOT YET EXTRACTED "
                    f"({len(sec['unanswered'])} questions):"
                )
                for q in sec['unanswered']:
                    lines.append(f"    ? {q}")

        text = '\n'.join(lines)
        if len(text) > _MAX_RICH_ANALYSIS_TEXT_CHARS:
            text = text[:_MAX_RICH_ANALYSIS_TEXT_CHARS] + '\n\n[Context truncated for length]'
        return text

    # ------------------------------------------------------------------
    # Shared header builder
    # ------------------------------------------------------------------

    def _build_header_lines(self, ctx: dict) -> list:
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

        # Standard key_details (name→value) — always included
        if ctx['key_details'] and not ctx.get('key_details_list'):
            lines.append('KEY DOCUMENT DETAILS:')
            for k, v in ctx['key_details'].items():
                lines.append(f'  {k}: {v}')
            lines.append('')

        if ctx['doc_context']:
            lines.append('DOCUMENT CONTEXT (title page / TOC / scope excerpt):')
            lines.append(ctx['doc_context'][:5000])
            lines.append('')

        return lines
