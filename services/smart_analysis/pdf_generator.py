"""
Smart Analysis PDF Generator — executive-level reportlab PDF.

Layout:
  Page 1:  Cover (document name, type, BidBrief branding, generation date)
  Page 2:  Executive Summary (prose)
  Page 3+: Professional Assessments → Key Insights → Risks →
           Opportunities → Ambiguities → Contradictions →
           Recommendations → User Questions (if any)
  Footer:  Page numbers + "Prepared by BidBrief"
"""

import io
import logging
import os
import re as _re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import SmartAnalysisResult

logger = logging.getLogger(__name__)

# ── Brand Colours ─────────────────────────────────────────────────────────────
C_NAVY = colors.HexColor('#1E3A8A')
C_BLUE = colors.HexColor('#3B82F6')
C_LIGHT_BLUE = colors.HexColor('#EFF6FF')
C_GREEN = colors.HexColor('#22C55E')
C_AMBER = colors.HexColor('#F59E0B')
C_RED = colors.HexColor('#EF4444')
C_DARK_RED = colors.HexColor('#DC2626')
C_GREY_TEXT = colors.HexColor('#6B7280')
C_DARK_TEXT = colors.HexColor('#1F2937')
C_ALT_ROW = colors.HexColor('#F8FAFC')
C_WHITE = colors.white

# ── Severity colour map ───────────────────────────────────────────────────────
_SEVERITY_COLORS = {
    'critical': C_DARK_RED,
    'high':     C_RED,
    'medium':   C_AMBER,
    'low':      C_GREEN,
    'info':     C_BLUE,
}

# ── Page size ─────────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = letter
MARGIN = 0.85 * inch
CONTENT_W = PAGE_W - 2 * MARGIN


def _styles():
    base = getSampleStyleSheet()

    s = {
        'cover_title': ParagraphStyle(
            'cover_title',
            fontSize=28,
            textColor=C_WHITE,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        'cover_sub': ParagraphStyle(
            'cover_sub',
            fontSize=14,
            textColor=colors.HexColor('#BFDBFE'),
            fontName='Helvetica',
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        'cover_meta': ParagraphStyle(
            'cover_meta',
            fontSize=11,
            textColor=colors.HexColor('#93C5FD'),
            fontName='Helvetica',
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        'h1': ParagraphStyle(
            'h1',
            fontSize=18,
            textColor=C_NAVY,
            fontName='Helvetica-Bold',
            spaceBefore=24,
            spaceAfter=10,
            borderPadding=(0, 0, 4, 0),
        ),
        'h2': ParagraphStyle(
            'h2',
            fontSize=13,
            textColor=C_WHITE,
            fontName='Helvetica-Bold',
            spaceBefore=18,
            spaceAfter=8,
            backColor=C_NAVY,
            leftIndent=-8,
            rightIndent=-8,
            borderPadding=(6, 8, 6, 8),
        ),
        'h3': ParagraphStyle(
            'h3',
            fontSize=11,
            textColor=C_NAVY,
            fontName='Helvetica-Bold',
            spaceBefore=10,
            spaceAfter=4,
        ),
        'body': ParagraphStyle(
            'body',
            fontSize=10,
            textColor=C_DARK_TEXT,
            fontName='Helvetica',
            leading=15,
            alignment=TA_JUSTIFY,
            spaceBefore=4,
            spaceAfter=4,
        ),
        'bullet': ParagraphStyle(
            'bullet',
            fontSize=10,
            textColor=C_DARK_TEXT,
            fontName='Helvetica',
            leading=14,
            leftIndent=16,
            spaceBefore=2,
            spaceAfter=2,
            bulletFontName='Helvetica',
            bulletFontSize=10,
        ),
        'caption': ParagraphStyle(
            'caption',
            fontSize=8,
            textColor=C_GREY_TEXT,
            fontName='Helvetica-Oblique',
            alignment=TA_CENTER,
        ),
        'label': ParagraphStyle(
            'label',
            fontSize=9,
            textColor=C_GREY_TEXT,
            fontName='Helvetica-Bold',
            spaceBefore=2,
        ),
    }
    return s


def _clean_display_title(result: 'SmartAnalysisResult') -> str:
    """
    Returns the best human-readable document title for the cover page.

    Priority:
      1. document_understanding.document_title  (AI-extracted from the document)
      2. Cleaned document_name (strip .tmp paths, decode percent-encoding,
         remove UUID-style prefixes, strip extension)
    """
    # 1 — AI-extracted title
    doc_title = (result.document_understanding or {}).get('document_title', '').strip()
    if doc_title:
        return doc_title

    # 2 — Clean up the raw filename fallback
    name = result.document_name or 'Document'
    # Strip directory path components (handles both / and \)
    name = os.path.basename(name.replace('\\', '/'))
    # Remove UUID-style prefixes like "abc123_" or "tmpXXXXXX_"
    name = _re.sub(r'^[a-f0-9\-]{6,}_', '', name, flags=_re.IGNORECASE)
    name = _re.sub(r'^tmp[a-z0-9]+_?', '', name, flags=_re.IGNORECASE)
    # Decode percent-encoding artifacts
    try:
        from urllib.parse import unquote
        name = unquote(name)
    except Exception:
        pass
    # Drop file extension
    name = _re.sub(r'\.(pdf|tmp|docx?|xlsx?)$', '', name, flags=_re.IGNORECASE)
    # Replace underscores/hyphens with spaces, collapse whitespace
    name = _re.sub(r'[_\-]+', ' ', name).strip()
    return name or 'Document'


class SmartAnalysisPDFGenerator:
    def __init__(self, result: SmartAnalysisResult):
        self.result = result
        self.styles = _styles()
        self._page_num = 0

    def generate(self) -> io.BytesIO:
        buf = io.BytesIO()

        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN + 0.3 * inch,   # Extra for footer
            title=f'Smart Analysis — {_clean_display_title(self.result)}',
            author='BidBrief',
            subject='Executive Analysis Report',
        )

        story = []
        story += self._cover_page()
        story.append(PageBreak())
        story += self._exec_summary_section()
        story += self._assessments_section()
        story += self._key_insights_section()
        story += self._findings_section('Risks', self.result.risks)
        story += self._findings_section('Opportunities', self.result.opportunities)
        story += self._findings_section('Ambiguities', self.result.ambiguities)
        story += self._findings_section('Contradictions', self.result.contradictions)
        story += self._recommendations_section()
        if self.result.user_question_responses:
            story += self._user_questions_section()

        doc.build(
            story,
            onFirstPage=self._draw_cover_bg,
            onLaterPages=self._draw_footer,
        )

        buf.seek(0)
        return buf

    # ── Cover page ────────────────────────────────────────────────────────────
    def _cover_page(self):
        s = self.styles
        story = []

        # Large top spacer (push content toward vertical centre)
        story.append(Spacer(1, 2.2 * inch))

        story.append(Paragraph('BidBrief', s['cover_meta']))
        story.append(Paragraph('Smart Analysis', s['cover_title']))
        story.append(Spacer(1, 0.1 * inch))
        story.append(HRFlowable(
            width=3 * inch,
            thickness=2,
            color=colors.HexColor('#93C5FD'),
            hAlign='CENTER',
        ))
        story.append(Spacer(1, 0.3 * inch))

        story.append(Paragraph(
            _clean_display_title(self.result),
            ParagraphStyle(
                'doc_name',
                fontSize=18,
                textColor=C_WHITE,
                fontName='Helvetica-Bold',
                alignment=TA_CENTER,
                spaceAfter=8,
            ),
        ))

        doc_type = self.result.document_type_label or self.result.document_type
        story.append(Paragraph(doc_type, s['cover_sub']))

        completeness_badge = (
            '⚠ Partial Analysis' if self.result.analysis_completeness == 'partial'
            else '✓ Complete Analysis'
        )
        story.append(Paragraph(completeness_badge, s['cover_meta']))
        story.append(Spacer(1, 0.4 * inch))

        gen_date = _fmt_date(self.result.generated_at)
        story.append(Paragraph(f'Generated: {gen_date}', s['cover_meta']))
        story.append(Paragraph('Prepared by BidBrief AI', s['cover_meta']))

        story.append(Spacer(1, 0.5 * inch))
        story.append(HRFlowable(
            width=CONTENT_W,
            thickness=1,
            color=colors.HexColor('#3B82F6'),
            hAlign='CENTER',
        ))

        # Risk count summary bar
        risk_count = len(self.result.risks)
        opp_count = len(self.result.opportunities)
        story.append(Spacer(1, 0.25 * inch))
        summary_text = (
            f'{risk_count} Risk{"s" if risk_count != 1 else ""}  ·  '
            f'{opp_count} Opportunit{"ies" if opp_count != 1 else "y"}  ·  '
            f'{len(self.result.ambiguities)} Ambigu{"ities" if len(self.result.ambiguities) != 1 else "ity"}  ·  '
            f'{len(self.result.contradictions)} Contradiction{"s" if len(self.result.contradictions) != 1 else ""}'
        )
        story.append(Paragraph(summary_text, s['cover_meta']))

        return story

    # ── Page background callbacks ─────────────────────────────────────────────
    def _draw_cover_bg(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_NAVY)
        canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        # Accent stripe at top
        canvas.setFillColor(C_BLUE)
        canvas.rect(0, PAGE_H - 0.4 * inch, PAGE_W, 0.4 * inch, fill=1, stroke=0)
        canvas.restoreState()

    def _draw_footer(self, canvas, doc):
        canvas.saveState()
        footer_y = 0.5 * inch
        canvas.setStrokeColor(C_NAVY)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, footer_y + 14, PAGE_W - MARGIN, footer_y + 14)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(C_GREY_TEXT)
        canvas.drawString(MARGIN, footer_y, 'Prepared by BidBrief AI')
        canvas.drawRightString(
            PAGE_W - MARGIN, footer_y,
            f'Page {doc.page}'
        )
        canvas.restoreState()

    # ── Executive Summary ─────────────────────────────────────────────────────
    def _exec_summary_section(self):
        s = self.styles
        story = [Paragraph('Executive Summary', s['h1'])]
        story.append(HRFlowable(
            width=CONTENT_W, thickness=2, color=C_NAVY, spaceAfter=10
        ))
        for para in self.result.executive_summary.split('\n\n'):
            if para.strip():
                story.append(Paragraph(_safe(para), s['body']))
        return story

    # ── Professional Assessments ──────────────────────────────────────────────
    def _assessments_section(self):
        if not self.result.assessments:
            return []

        s = self.styles
        story = [Paragraph('Professional Assessments', s['h1'])]

        table_data = [
            [
                Paragraph('Category', _th_style()),
                Paragraph('Rating', _th_style()),
                Paragraph('Rationale', _th_style()),
                Paragraph('Confidence', _th_style()),
            ]
        ]

        for a in self.result.assessments:
            table_data.append([
                Paragraph(_safe(a.category), s['body']),
                Paragraph(f'<b>{_safe(a.rating)}</b>', s['body']),
                Paragraph(_safe(a.rationale), s['body']),
                Paragraph(a.confidence.title(), s['body']),
            ])

        col_widths = [
            CONTENT_W * 0.22,
            CONTENT_W * 0.15,
            CONTENT_W * 0.47,
            CONTENT_W * 0.16,
        ]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND',  (0, 0), (-1, 0), C_NAVY),
            ('TEXTCOLOR',   (0, 0), (-1, 0), C_WHITE),
            ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',    (0, 0), (-1, 0), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_WHITE, C_ALT_ROW]),
            ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
            ('VALIGN',      (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING',  (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        return story

    # ── Key Insights ──────────────────────────────────────────────────────────
    def _key_insights_section(self):
        if not self.result.key_insights:
            return []

        s = self.styles
        story = [Spacer(1, 0.2 * inch), Paragraph('Key Insights', s['h1'])]
        for insight in self.result.key_insights:
            story.append(Paragraph(f'• {_safe(insight)}', s['bullet']))
        return story

    # ── Generic findings section (Risks / Opportunities / etc.) ──────────────
    def _findings_section(self, title: str, items):
        if not items:
            return []

        s = self.styles
        story = [Spacer(1, 0.2 * inch), Paragraph(title, s['h1'])]

        for item in items:
            sev = item.severity.lower()
            sev_color = _SEVERITY_COLORS.get(sev, C_AMBER)

            # Severity + title row
            badge_data = [[
                Paragraph(
                    f'<font color="white"><b>{sev.upper()}</b></font>',
                    ParagraphStyle('badge', fontSize=8, fontName='Helvetica-Bold',
                                   alignment=TA_CENTER),
                ),
                Paragraph(f'<b>{_safe(item.title)}</b>', s['h3']),
            ]]
            badge_t = Table(
                badge_data,
                colWidths=[0.65 * inch, CONTENT_W - 0.65 * inch],
            )
            badge_t.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (0, 0), sev_color),
                ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING',   (0, 0), (-1, -1), 5),
                ('TOPPADDING',    (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(badge_t)

            # Description
            story.append(Paragraph(_safe(item.description), s['body']))

            # Evidence bullets
            if item.evidence:
                for ev in item.evidence:
                    story.append(Paragraph(
                        f'<font color="#6B7280">↳ {_safe(ev)}</font>',
                        s['bullet'],
                    ))

            if item.page_refs:
                story.append(Paragraph(
                    f'<font color="#6B7280"><i>Referenced pages: {item.page_refs}</i></font>',
                    s['caption'],
                ))

            story.append(Spacer(1, 0.08 * inch))

        return story

    # ── Recommendations ───────────────────────────────────────────────────────
    def _recommendations_section(self):
        s = self.styles
        story = []

        if self.result.strategic_recommendations:
            story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph('Strategic Recommendations', s['h1']))
            for i, rec in enumerate(self.result.strategic_recommendations, 1):
                story.append(Paragraph(
                    f'<b>{i}.</b> {_safe(rec)}',
                    ParagraphStyle(
                        'rec',
                        parent=s['body'],
                        leftIndent=16,
                        spaceAfter=6,
                    ),
                ))

        if self.result.follow_up_questions:
            story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph('Follow-Up Questions', s['h1']))
            for i, q in enumerate(self.result.follow_up_questions, 1):
                story.append(Paragraph(f'<b>{i}.</b> {_safe(q)}', s['bullet']))

        return story

    # ── User Questions ────────────────────────────────────────────────────────
    def _user_questions_section(self):
        s = self.styles
        story = [PageBreak(), Paragraph('Your Questions', s['h1'])]

        for resp in self.result.user_question_responses:
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph(
                f'<b>Q: {_safe(resp.get("question", ""))}</b>',
                ParagraphStyle(
                    'q_label',
                    fontSize=10,
                    fontName='Helvetica-Bold',
                    textColor=C_NAVY,
                    spaceBefore=8,
                    spaceAfter=4,
                ),
            ))
            story.append(Paragraph(
                _safe(resp.get('response', '')),
                s['body'],
            ))
            confidence = resp.get('confidence', '')
            if confidence:
                story.append(Paragraph(
                    f'<i>Confidence: {confidence.title()}</i>',
                    ParagraphStyle(
                        'conf',
                        fontSize=9,
                        textColor=C_GREY_TEXT,
                        fontName='Helvetica-Oblique',
                    ),
                ))
            story.append(HRFlowable(
                width=CONTENT_W, thickness=0.5,
                color=colors.HexColor('#E5E7EB'),
            ))

        return story


# ── Helpers ───────────────────────────────────────────────────────────────────

def _th_style():
    return ParagraphStyle(
        'th',
        fontSize=9,
        fontName='Helvetica-Bold',
        textColor=C_WHITE,
    )


def _safe(text: str) -> str:
    """Escape XML special characters for reportlab Paragraphs."""
    if not text:
        return ''
    return (
        str(text)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def _fmt_date(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime('%B %d, %Y')
    except Exception:
        return iso_str
