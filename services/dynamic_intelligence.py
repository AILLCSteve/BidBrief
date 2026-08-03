"""
Dynamic Intelligence Engine — shared document-sensing table generator.

The same architectural move HOTDOG Layer 2 makes for expertise (let the AI
sense what THIS document is about and specialize), applied to OUTPUT SHAPE:
instead of every run producing the same fixed sections, the engine reads the
evidence and decides which 3-6 data tables are most relevant, interesting,
and prevalent for THIS document — then builds them, grounded in the evidence.

Consumers (one engine, three integration points):
  1. Smart Analysis      — runs in the parallel agent gather
  2. HOTDOG /api/analyze — post-compilation pass over the Q&A results
  3. CityScraper         — post-extraction pass over the guardrailed table

Output contract (stable across all consumers, JSON-safe, strings-only rows):
{
  "intelligence_focus": "why these tables were chosen for this document",
  "tables": [
    {
      "table_id": "snake_case_id",
      "title": "Human Title",
      "why_relevant": "one sentence tying the table to THIS document",
      "columns": [{"key": "col_key", "label": "Column Label"}, ...],
      "rows": [{"col_key": "string value", ...}, ...],
      "insights": ["short takeaway", ...]
    }
  ]
}
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from services.ai_models import completion_params

logger = logging.getLogger(__name__)

MAX_TABLES = 6
MAX_COLUMNS = 10
MAX_ROWS = 25

_SYSTEM = """\
You are a dynamic intelligence architect for BidBrief. Your job is to SENSE what is
actually in the evidence you are given and design the data tables a decision-maker
would most want for THIS specific document or dataset — then populate them.

TABLE SELECTION RULE (mandatory):
  Derive every table from what is genuinely relevant, interesting, and PREVALENT in
  the evidence. Two different documents must yield different table sets. Never emit a
  generic template table that would fit any document. Before building, reason about
  which dimensions of THIS evidence are dense enough to support a table.

GROUNDING RULES (mandatory):
  - Populate cells ONLY from the provided evidence. Never invent values.
  - When the evidence indicates a value exists but is unclear, use "Unclear — see source".
  - When a cell is genuinely not in the evidence, use "Not found".
  - Prefer fewer, denser tables over many sparse ones. A table needs at least 2 rows
    of real evidence to justify existing.

FORMAT RULES (mandatory):
  - At most {max_tables} tables, {max_columns} columns per table, {max_rows} rows per table.
  - Every row value must be a plain string (no nested objects, no numbers-as-numbers).
  - Column keys are snake_case; every row object uses exactly the declared column keys.
  - table_id is snake_case and unique within the response.
  - Each table includes 1-3 "insights": short, specific takeaways from that table's data.

Respond with valid JSON only:
{{
  "intelligence_focus": "2-3 sentences: what you sensed as most relevant/prevalent in this evidence and why these tables",
  "tables": [
    {{
      "table_id": "...",
      "title": "...",
      "why_relevant": "...",
      "columns": [{{"key": "...", "label": "..."}}],
      "rows": [{{"...": "..."}}],
      "insights": ["..."]
    }}
  ]
}}"""

_USER_TEMPLATE = """\
CONTEXT: {context_label}
{focus_note}
EVIDENCE:
{evidence}

Design and populate the dynamic intelligence tables for this evidence.
Remember: tables must lean into what is specific, prevalent, and decision-relevant HERE —
not what a generic template would include."""


def _normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp and sanitize model output to the stable contract (strings-only rows)."""
    tables_out: List[Dict[str, Any]] = []
    seen_ids = set()
    for t in (raw.get('tables') or [])[:MAX_TABLES]:
        if not isinstance(t, dict):
            continue
        columns_in = [c for c in (t.get('columns') or []) if isinstance(c, dict) and c.get('key')]
        columns = [{'key': str(c['key']), 'label': str(c.get('label') or c['key'])}
                   for c in columns_in[:MAX_COLUMNS]]
        if not columns:
            continue
        col_keys = [c['key'] for c in columns]
        rows = []
        for r in (t.get('rows') or [])[:MAX_ROWS]:
            if not isinstance(r, dict):
                continue
            rows.append({k: _cell(r.get(k)) for k in col_keys})
        if not rows:
            continue
        table_id = str(t.get('table_id') or f'table_{len(tables_out) + 1}')
        if table_id in seen_ids:
            table_id = f'{table_id}_{len(tables_out) + 1}'
        seen_ids.add(table_id)
        tables_out.append({
            'table_id': table_id,
            'title': str(t.get('title') or table_id.replace('_', ' ').title()),
            'why_relevant': str(t.get('why_relevant') or ''),
            'columns': columns,
            'rows': rows,
            'insights': [str(i) for i in (t.get('insights') or []) if str(i).strip()][:3],
        })
    return {
        'intelligence_focus': str(raw.get('intelligence_focus') or ''),
        'tables': tables_out,
    }


def _cell(value: Any) -> str:
    if value is None:
        return 'Not found'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


# A reasoning model over a full document's answers is a slow call; 150s was
# tight enough that a large run could time out and silently lose the tab.
DI_TIMEOUT_SECONDS = 300.0

# Retry once with a smaller evidence window before giving up.
DI_RETRY_EVIDENCE_CHARS = 25000


class DynamicIntelligenceEngine:
    """One AI call: evidence in, document-specific tables out. Failure-safe."""

    def __init__(self, api_key: str, model: str = ''):
        if not model:
            from services.ai_models import standard_model
            model = standard_model()
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def generate(
        self,
        context_label: str,
        evidence: str,
        focus_note: str = '',
        max_evidence_chars: int = 60000,
    ) -> Dict[str, Any]:
        """Returns the normalized table contract; empty tables list on any failure."""
        if not evidence or not evidence.strip():
            return {'intelligence_focus': '', 'tables': []}
        if len(evidence) > max_evidence_chars:
            evidence = evidence[:max_evidence_chars] + '\n[evidence truncated]'
        focus_block = f'FOCUS DIRECTIVE: {focus_note}\n' if focus_note else ''
        try:
            response = await self.client.chat.completions.create(
                messages=[
                    {'role': 'system', 'content': _SYSTEM.format(
                        max_tables=MAX_TABLES, max_columns=MAX_COLUMNS, max_rows=MAX_ROWS)},
                    {'role': 'user', 'content': _USER_TEMPLATE.format(
                        context_label=context_label, focus_note=focus_block, evidence=evidence)},
                ],
                response_format={'type': 'json_object'},
                timeout=DI_TIMEOUT_SECONDS,
                **completion_params(self.model, 6000, temperature=0.2),
            )
            raw = json.loads(response.choices[0].message.content)
            result = _normalize(raw)
            logger.info(
                f'[DynamicIntel] {len(result["tables"])} tables generated '
                f'({context_label}, model={self.model})'
            )
            return result
        except Exception as e:
            # Report the reason. Returning a bare empty result made a missing
            # Document Intelligence tab undiagnosable without server logs.
            logger.error(f'[DynamicIntel] Failed ({context_label}): '
                         f'{type(e).__name__}: {e}', exc_info=True)
            return {'intelligence_focus': '', 'tables': [],
                    'error': f'{type(e).__name__}: {e}'}

    def generate_sync(self, *args, **kwargs) -> Dict[str, Any]:
        """For sync callers (analysis/scraper worker threads). New event loop per call.

        Retries ONCE with a smaller evidence window: a timeout or a truncated
        response on a big document should not cost the whole tab.
        """
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(self.generate(*args, **kwargs))
            if not (result.get('tables') or []):
                logger.warning('[DynamicIntel] First pass produced nothing — '
                               'retrying with a smaller evidence window')
                kwargs['max_evidence_chars'] = DI_RETRY_EVIDENCE_CHARS
                retry = loop.run_until_complete(self.generate(*args, **kwargs))
                if retry.get('tables'):
                    return retry
                # Keep whichever error is more informative.
                result.setdefault('error', retry.get('error', ''))
            return result
        finally:
            loop.close()
