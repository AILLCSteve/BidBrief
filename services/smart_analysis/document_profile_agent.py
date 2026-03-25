"""
Document Profile Agent — grounding pass before SCOUT/MIRROR run.

Establishes a verified evidence inventory and expertise posture before
any subjective analysis begins. This prevents downstream agents from
making false "X is missing" claims when X is actually present in the
analysis artifacts.

Outputs:
  confirmed_present  — topics explicitly evidenced in the analysis
  confirmed_absent   — topics confidently absent (conservative — high bar)
  unverified         — topics that exist but aren't clearly resolved
  expertise_profile  — expert role, industry norms, benchmarks, red flags
  key_items          — categorized summary: scope, schedule, commercial, compliance
"""

import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a senior document analyst and evidence auditor. Your role is to perform a \
grounding pass on a document analysis — establishing what is actually present, \
genuinely absent, or not yet clearly resolved before any subjective evaluation begins.

Your most important rule:
  Do NOT call something "absent" unless you have specifically looked for it across all \
  provided evidence (Q&A answers, key document details, document context, footnotes/citations) \
  and found no trace of it. A topic that was not asked about is NOT absent — it is unverified. \
  A topic where the analysis found partial or vague evidence is NOT absent — it is unresolved.

Use strict language tiers:
  confirmed_present  — explicit evidence exists in the provided analysis artifacts
  confirmed_absent   — actively searched, no evidence found anywhere in the artifacts
  unverified         — not clearly addressed, or addressed only partially/vaguely

Also establish the appropriate expert posture for this document type, industry, and geography.

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Perform a grounding analysis of this document analysis.

{rich_analysis_text}

---

Your task has two parts:

PART 1 — EVIDENCE INVENTORY
For each major topic area relevant to this document type, determine whether it is:
  - confirmed_present: the analysis contains clear evidence of this
  - confirmed_absent:  you searched the full analysis text above and found NO evidence of this
  - unverified:        partial, vague, or not addressed by the question flow

Focus on topics appropriate for a {doc_type} document. Common topics include:
  Scope of work / work items, Schedule / timeline / milestones, Owner / agency / engineer,
  Contract value / pricing / bid items, Payment terms / progress payments / retention,
  Liquidated damages / incentives, Bonding requirements / performance / payment bonds,
  Insurance requirements, Permits / regulatory / access constraints, Labor / prevailing wage,
  Environmental / safety requirements, Submission / bid requirements / addenda,
  Certifications / contractor qualifications, Warranty / guarantee provisions,
  Change order / dispute resolution provisions.

Only include topics that are genuinely relevant to this specific document. Do not manufacture topics.

PART 2 — EXPERTISE PROFILE
Determine the appropriate expert posture for evaluating this document. Consider:
  - Document type and mode ({doc_type}, mode={mode})
  - Industry / trade type (e.g., trenchless rehab, municipal water/sewer, public works)
  - Geographic context if known
  - Public vs. private sector context

Respond as JSON:
{{
  "confirmed_present": [
    {{
      "topic": "Brief topic name (e.g., Scope of Work)",
      "evidence_summary": "What the analysis found — cite specific answers, key details, or citations",
      "confidence": "high|medium"
    }}
  ],
  "confirmed_absent": [
    {{
      "topic": "Brief topic name",
      "basis": "Why you are confident this is absent — what you searched and didn't find"
    }}
  ],
  "unverified": [
    {{
      "topic": "Brief topic name",
      "status_detail": "What is partially known and what remains unclear"
    }}
  ],
  "expertise_profile": {{
    "role": "e.g., Public Works Bid/Spec Reviewer — Trenchless Sewer Rehabilitation",
    "industry_context": "2-3 sentences on typical norms for this type of work",
    "key_benchmarks": [
      "e.g., CIPP lining production rates typically 500-1000 LF/day depending on pipe size",
      "e.g., Public works projects typically require 10% bid bond and 100% performance/payment bonds"
    ],
    "typical_red_flags": [
      "e.g., Missing soil/groundwater investigation data in an open-trench spec",
      "e.g., Liquidated damages with no definition of substantial vs. final completion"
    ],
    "normal_expectations": [
      "e.g., Working-day contracts in CA municipal work typically run 60-120 days for trenchless rehab",
      "e.g., Prevailing wage requirement is standard for CA public works > $25K threshold"
    ]
  }},
  "key_items": {{
    "scope": ["Major scope item 1", "Major scope item 2"],
    "schedule": ["Key date or duration 1", "Key milestone 2"],
    "commercial": ["Contract value or pricing note 1", "Payment term note 2"],
    "compliance": ["Regulatory requirement 1", "Certification/license requirement 2"],
    "risk_bearing": ["Notable risk-bearing clause 1"],
    "submission": ["Key submission requirement 1"]
  }}
}}"""


class DocumentProfileAgent:
    """
    Pre-analysis grounding agent. Runs before SCOUT/MIRROR.
    Returns a doc_profile dict used by all downstream agents.
    """

    def __init__(self, api_key: str, model: str = 'gpt-4o'):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def profile(self, ctx: dict, rich_analysis_text: str) -> dict:
        """
        Returns doc_profile dict, or an empty safe fallback on failure.
        Caller should always check for empty dict and handle gracefully.
        """
        doc_type = ctx.get('document_type_label') or ctx.get('document_type', 'document')
        mode = ctx.get('mode', 'bid_spec')

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': _SYSTEM},
                    {'role': 'user', 'content': _USER_TEMPLATE.format(
                        rich_analysis_text=rich_analysis_text,
                        doc_type=doc_type,
                        mode=mode,
                    )},
                ],
                temperature=0.15,
                max_tokens=3000,
                response_format={'type': 'json_object'},
                timeout=60.0,
            )
            result = json.loads(response.choices[0].message.content)

            n_present = len(result.get('confirmed_present', []))
            n_absent = len(result.get('confirmed_absent', []))
            n_unverified = len(result.get('unverified', []))
            logger.info(
                f'[DocProfile] {n_present} confirmed present, '
                f'{n_absent} confirmed absent, '
                f'{n_unverified} unverified | '
                f'role={result.get("expertise_profile", {}).get("role", "unknown")}'
            )
            return result

        except Exception as e:
            logger.error(f'[DocProfile] Failed: {e}')
            # Return safe empty profile — downstream agents handle this gracefully
            return {
                'confirmed_present': [],
                'confirmed_absent': [],
                'unverified': [],
                'expertise_profile': {
                    'role': 'Document Analyst',
                    'industry_context': '',
                    'key_benchmarks': [],
                    'typical_red_flags': [],
                    'normal_expectations': [],
                },
                'key_items': {
                    'scope': [],
                    'schedule': [],
                    'commercial': [],
                    'compliance': [],
                    'risk_bearing': [],
                    'submission': [],
                },
            }
