"""
Layer 0.5: Visual Intelligence Scanner (OPT-IN, ADDITIVE).

Deep-processes drawing/diagram/map/photo-heavy pages with AI vision and feeds
what it sees back into the standard pipeline as extra page text — engineering
drawings, plan/profile sheets, site maps, detail callouts, legends, photos,
schedules rendered as images.

Contract (do not weaken):
- OFF by default. When disabled the pipeline is byte-identical to before.
- When enabled it only ADDS: each analyzed page's text gains an appended
  [VISUAL CONTENT ...] block (so the L3 experts read it inside normal windows
  and cite <PDF pg X> as usual), and the run collects `visual_findings` for
  results/exports. Nothing is removed, reordered, or re-prompted.
- Failure-safe per page and per layer: a vision error never fails the analysis.

Page selection is a zero-AI-cost heuristic over PyMuPDF page stats (image area
coverage, image count, vector drawing density, text sparsity), capped at
BIDBRIEF_VISUAL_MAX_PAGES (default 25) so cost stays bounded on huge specs.
"""

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .models import PageData

logger = logging.getLogger(__name__)

# Pages scoring at or above this are considered visual-heavy.
VISUAL_SCORE_THRESHOLD = 0.35

# Longest rendered image edge sent to the vision model.
_MAX_RENDER_EDGE = 1568

# Text below this length marks a page as text-sparse (a drawing sheet usually
# carries only a title block and callouts).
_SPARSE_TEXT_CHARS = 600


def visual_model() -> str:
    """Model used for vision calls. Defaults to the analysis model the caller
    passes in; BIDBRIEF_MODEL_VISION overrides it ops-side without a deploy."""
    return os.environ.get('BIDBRIEF_MODEL_VISION', '')


def max_visual_pages() -> int:
    try:
        return max(1, int(os.environ.get('BIDBRIEF_VISUAL_MAX_PAGES', '25')))
    except ValueError:
        return 25


@dataclass
class VisualPageStats:
    """Raw, cheaply-computed facts about one page's visual weight."""
    page_num: int                 # 1-indexed
    text_chars: int = 0
    image_count: int = 0
    image_coverage: float = 0.0   # fraction of page area covered by raster images
    drawing_count: int = 0        # vector paths (lines/curves/fills)
    score: float = field(default=0.0)


def score_page(text_chars: int, image_coverage: float, image_count: int,
               drawing_count: int) -> float:
    """
    Pure scoring heuristic — unit-tested in isolation.

    Signals:
    - Raster coverage dominates: a page that is mostly image is visual.
    - Vector density: engineering drawings are often pure vector (no rasters),
      so hundreds of drawing paths on a text-sparse page count strongly.
    - Text sparsity amplifies both: dense text pages with an inline logo or a
      small figure should NOT win a slot over a real plan sheet.
    """
    coverage_signal = min(max(image_coverage, 0.0), 1.0)
    vector_signal = min(drawing_count / 300.0, 1.0)
    sparse = text_chars < _SPARSE_TEXT_CHARS

    score = coverage_signal * 0.9 + vector_signal * 0.5
    if image_count > 0 and sparse:
        score += 0.15
    if sparse and (coverage_signal > 0.05 or vector_signal >= 0.15):
        score += 0.2
    if sparse and drawing_count >= 40:
        # A near-textless page with even a modest number of vector paths is a
        # diagram/detail sheet — text-page underlines and table borders never
        # combine with this little text.
        score += 0.2
    if not sparse:
        # A text-dense page needs substantial visual mass to qualify — a
        # half-page embedded map should make it, a small inline logo should not.
        score *= 0.75
    return round(min(score, 2.0), 4)


def is_visual_page(score: float) -> bool:
    return score >= VISUAL_SCORE_THRESHOLD


def select_candidates(stats: List[VisualPageStats], cap: int) -> List[VisualPageStats]:
    """Visual-heavy pages, highest score first, capped; ties break on page order."""
    hits = [s for s in stats if is_visual_page(s.score)]
    hits.sort(key=lambda s: (-s.score, s.page_num))
    return hits[:max(0, cap)]


def build_visual_block(finding: Dict) -> str:
    """
    The text appended to the page for the standard pipeline to read.
    Keep the framing explicit so experts can attribute answers to imagery.
    """
    lines = ['', '[VISUAL CONTENT — AI vision analysis of the drawing/map/imagery on this page]']
    kind = finding.get('kind') or 'visual'
    title = (finding.get('title') or '').strip()
    header = f'Type: {kind}'
    if title:
        header += f' — {title}'
    lines.append(header)
    description = (finding.get('description') or '').strip()
    if description:
        lines.append(f'What it shows: {description}')
    extracted = (finding.get('extracted_text') or '').strip()
    if extracted:
        lines.append(f'Labels, dimensions & callouts transcribed: {extracted}')
    facts = [str(f).strip() for f in (finding.get('key_facts') or []) if str(f).strip()]
    if facts:
        lines.append('Key facts from the visual:')
        lines.extend(f'- {f}' for f in facts)
    lines.append('[END VISUAL CONTENT]')
    return '\n'.join(lines)


def parse_vision_response(raw: str, page_num: int) -> Optional[Dict]:
    """Tolerant parse of the model's JSON. Returns a normalized finding or None."""
    try:
        data = json.loads(raw or '{}')
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    def _s(key):
        v = data.get(key)
        return v.strip() if isinstance(v, str) else ''

    facts = data.get('key_facts')
    if not isinstance(facts, list):
        facts = []
    facts = [str(f).strip() for f in facts if str(f).strip()][:12]

    kind = _s('page_kind') or _s('kind') or 'visual'
    finding = {
        'page': page_num,
        'kind': kind.lower()[:24],
        'title': _s('title')[:200],
        'description': _s('description')[:2000],
        'extracted_text': _s('extracted_text')[:3000],
        'key_facts': facts,
        'confidence': _s('confidence').lower() or 'medium',
    }
    if not (finding['description'] or finding['extracted_text'] or facts):
        return None
    return finding


_VISION_SYSTEM_PROMPT = (
    'You are a senior construction and civil-engineering document analyst who reads '
    'engineering drawings, plan and profile sheets, site and utility maps, standard '
    'details, schedules, charts and jobsite photographs for bid preparation teams. '
    'You will be shown ONE page from a bid specification or construction document. '
    'Extract every piece of decision-relevant information a bidder could not get '
    'from the page\'s machine-readable text alone.\n\n'
    'Respond ONLY with a JSON object with these keys:\n'
    '  "page_kind": one of "drawing" | "map" | "photo" | "table" | "chart" | "mixed"\n'
    '  "title": the sheet/figure title if visible (title block, caption), else ""\n'
    '  "description": 2-6 sentences describing exactly what the visual shows — '
    'systems, structures, alignments, areas, phases, anything a bidder needs\n'
    '  "extracted_text": labels, dimensions, callouts, station numbers, pipe sizes/'
    'materials, legend entries, scale, north arrow, notes — transcribed verbatim, '
    'separated by "; "\n'
    '  "key_facts": array of up to 12 short strings, each ONE concrete fact useful '
    'for bidding (quantities, dimensions, materials, locations, constraints)\n'
    '  "confidence": "high" | "medium" | "low" — how legible the page was\n\n'
    'Transcribe numbers and units EXACTLY as printed. If the page is a pure text '
    'page with no meaningful visual content, return {"page_kind":"mixed",'
    '"description":"","extracted_text":"","key_facts":[],"confidence":"low"}.'
)


class VisualIntelligenceScanner:
    """
    Runs between L0 extraction and window creation.

    analyze() returns (enriched_pages, findings): `enriched_pages` is the same
    list with visual-heavy pages REPLACED by new PageData carrying the appended
    visual block (PageData is frozen), `findings` is the structured list for
    results and exports.
    """

    def __init__(self, openai_client, model: str,
                 max_pages: Optional[int] = None, max_parallel: int = 3):
        self.client = openai_client
        self.model = visual_model() or model
        self.max_pages = max_pages if max_pages is not None else max_visual_pages()
        self.max_parallel = max_parallel
        self.total_api_calls = 0

    # ---- cheap page stats (no AI) ------------------------------------------

    def collect_page_stats(self, pdf_path: str, pages: List[PageData]) -> List[VisualPageStats]:
        import fitz

        stats: List[VisualPageStats] = []
        text_chars = {p.page_num: p.char_count for p in pages}
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.warning(f'Visual scan: could not reopen PDF for stats: {e}')
            return stats

        try:
            for index in range(len(doc)):
                page_num = index + 1
                page = doc[index]
                page_area = max(float(page.rect.width * page.rect.height), 1.0)

                image_count = 0
                covered = 0.0
                try:
                    seen = set()
                    for img in page.get_images(full=True):
                        xref = img[0]
                        if xref in seen:
                            continue
                        seen.add(xref)
                        for rect in page.get_image_rects(xref):
                            covered += float(rect.width * rect.height)
                        image_count += 1
                except Exception:
                    pass

                drawing_count = 0
                try:
                    # Vector paths are the signature of CAD-derived sheets.
                    drawing_count = len(page.get_drawings())
                except Exception:
                    pass

                s = VisualPageStats(
                    page_num=page_num,
                    text_chars=text_chars.get(page_num, 0),
                    image_count=image_count,
                    image_coverage=min(covered / page_area, 1.0),
                    drawing_count=drawing_count,
                )
                s.score = score_page(s.text_chars, s.image_coverage,
                                     s.image_count, s.drawing_count)
                stats.append(s)
        finally:
            doc.close()
        return stats

    # ---- rendering -----------------------------------------------------------

    def _render_page_b64(self, pdf_path: str, page_num: int) -> Optional[str]:
        import fitz
        try:
            doc = fitz.open(pdf_path)
            try:
                page = doc[page_num - 1]
                edge = max(float(page.rect.width), float(page.rect.height), 1.0)
                zoom = min(_MAX_RENDER_EDGE / edge, 3.0)
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                return base64.b64encode(pix.tobytes('png')).decode('ascii')
            finally:
                doc.close()
        except Exception as e:
            logger.warning(f'Visual scan: render failed for page {page_num}: {e}')
            return None

    # ---- the vision pass -------------------------------------------------------

    async def _analyze_page(self, pdf_path: str, stat: VisualPageStats,
                            page_text: str) -> Optional[Dict]:
        b64 = await asyncio.to_thread(self._render_page_b64, pdf_path, stat.page_num)
        if not b64:
            return None

        context_snippet = (page_text or '').strip()[:1200]
        user_content = [
            {'type': 'text', 'text':
                f'Page {stat.page_num} of the document. '
                + (f'Machine-readable text already extracted from this page '
                   f'(for context — do NOT repeat it, add what it misses):\n'
                   f'{context_snippet}' if context_snippet
                   else 'No machine-readable text was extracted from this page — '
                        'everything on it is visual.')},
            {'type': 'image_url',
             'image_url': {'url': f'data:image/png;base64,{b64}', 'detail': 'high'}},
        ]

        from services.ai_models import completion_params
        response = await self.client.chat.completions.create(
            messages=[
                {'role': 'system', 'content': _VISION_SYSTEM_PROMPT},
                {'role': 'user', 'content': user_content},
            ],
            response_format={'type': 'json_object'},
            **completion_params(self.model, 1600, temperature=0.2,
                                reasoning_effort='low')
        )
        self.total_api_calls += 1
        raw = (response.choices[0].message.content or '') if response.choices else ''
        return parse_vision_response(raw, stat.page_num)

    async def analyze(
        self,
        pdf_path: str,
        pages: List[PageData],
        emit: Optional[Callable[[str, dict], None]] = None,
    ) -> Tuple[List[PageData], List[Dict]]:
        """Run the full opt-in pass. Never raises for per-page failures."""
        def _emit(event, data):
            if emit:
                try:
                    emit(event, data)
                except Exception:
                    pass

        stats = await asyncio.to_thread(self.collect_page_stats, pdf_path, pages)
        candidates = select_candidates(stats, self.max_pages)
        _emit('visual_scan_start', {
            'candidate_pages': [c.page_num for c in candidates],
            'pages_considered': len(stats),
            'max_pages': self.max_pages,
        })
        if not candidates:
            _emit('visual_scan_complete', {'pages_scanned': 0, 'findings_count': 0})
            return pages, []

        page_by_num = {p.page_num: p for p in pages}
        semaphore = asyncio.Semaphore(self.max_parallel)
        done_counter = {'n': 0}

        async def run_one(stat: VisualPageStats) -> Optional[Dict]:
            async with semaphore:
                try:
                    finding = await self._analyze_page(
                        pdf_path, stat,
                        page_by_num.get(stat.page_num).text
                        if stat.page_num in page_by_num else '')
                except Exception as e:
                    logger.warning(
                        f'Visual scan: page {stat.page_num} failed (non-fatal): {e}')
                    finding = None
                done_counter['n'] += 1
                _emit('visual_page_complete', {
                    'page': stat.page_num,
                    'kind': (finding or {}).get('kind', ''),
                    'found': bool(finding),
                    'scanned': done_counter['n'],
                    'total_candidates': len(candidates),
                })
                return finding

        results = await asyncio.gather(*(run_one(c) for c in candidates))
        findings = sorted((f for f in results if f), key=lambda f: f['page'])

        # Rebuild the pages list, replacing enriched pages (PageData is frozen).
        blocks = {f['page']: build_visual_block(f) for f in findings}
        enriched: List[PageData] = []
        for p in pages:
            block = blocks.get(p.page_num)
            if block:
                text = p.text + '\n' + block
                enriched.append(PageData(
                    page_num=p.page_num, text=text,
                    char_count=len(text), has_content=True))
            else:
                enriched.append(p)

        _emit('visual_scan_complete', {
            'pages_scanned': len(candidates),
            'findings_count': len(findings),
            'pages_with_findings': [f['page'] for f in findings],
        })
        logger.info(f'  🖼️ Visual scan: {len(findings)} findings from '
                    f'{len(candidates)} candidate pages')
        return enriched, findings
