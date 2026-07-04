"""
Document Profile Agent — grounding pass before SCOUT/MIRROR run.

v3 changes:
  - max_tokens 3000 → 4500 for richer output
  - Adds document_understanding block: overview, workstreams, constraints, obligations
  - Expertise profile forced to derive uniquely from THIS document's specifics
  - Example benchmarks removed from schema to prevent cross-run repetition
  - Empty fallback includes document_understanding

Establishes a verified evidence inventory and expertise posture before
any subjective analysis begins. This prevents downstream agents from
making false "X is missing" claims when X is actually present in the
analysis artifacts.

Outputs:
  confirmed_present    — topics explicitly evidenced in the analysis
  confirmed_absent     — topics confidently absent (conservative — high bar)
  unverified           — topics that exist but aren't clearly resolved
  expertise_profile    — expert role, industry norms, benchmarks, red flags
  key_items            — categorized summary: scope, schedule, commercial, compliance
  document_understanding — holistic document overview (v3 addition)
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

EXPERTISE UNIQUENESS RULE:
  Your expertise_profile must be derived entirely from the specific characteristics of THIS \
  document — its trade type, scope scale, contract value, geographic context, public/private \
  sector, complexity, and identified risk profile. Do NOT reuse generic textbook benchmarks. \
  Two contracts of the same general type will have different benchmarks if their specifics differ. \
  Your benchmarks, red flags, and normal expectations must be specific enough that they \
  could only apply to THIS document, not to every document of this type.

Also establish the appropriate expert posture for this document type, industry, and geography.

Respond with valid JSON only."""

_USER_TEMPLATE = """\
Perform a grounding analysis of this document analysis.

{rich_analysis_text}

---

Your task has three parts:

PART 1 — DOCUMENT UNDERSTANDING
Provide a holistic understanding of what this document IS and what it is trying to accomplish.
This is not a risk assessment — it is a clear-eyed description of the document's structure, \
intent, and major components before any evaluation begins.

PART 2 — EVIDENCE INVENTORY
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

PART 3 — EXPERTISE PROFILE
Determine the appropriate expert posture for evaluating this document. Derive ALL elements \
from the actual characteristics of THIS document — not from generic industry examples:
  - Document type and mode ({doc_type}, mode={mode})
  - Specific trade type, work methodology, and scale found in the document
  - Geographic context and regulatory environment if evident
  - Public vs. private sector, agency type, procurement method
  - Contract value range and corresponding risk/bonding expectations
  - Specific complexity factors visible in this document

Your benchmarks must be derived from what you observe in this specific document.

Respond as JSON:
{{
  "document_understanding": {{
    "document_title": "The official title of the document exactly as it appears on the cover page or header (e.g. 'Request for Proposals — Downtown Streetscape Improvements', 'Invitation to Bid No. 2024-017'). If no formal title is present, derive a concise descriptive title from the document's subject and issuing agency.",
    "document_overview": "2-3 sentences: what this document IS, its purpose, and what it's trying to procure or accomplish",
    "major_workstreams": [
      "Major scope workstream or deliverable 1",
      "Major scope workstream or deliverable 2"
    ],
    "key_obligations": [
      "Primary obligation on the contractor/party",
      "Secondary obligation"
    ],
    "key_constraints": [
      "Time, access, regulatory, or operational constraint 1",
      "Constraint 2"
    ],
    "structural_organization": "1-2 sentences describing how the document is organized (sections, divisions, spec format, etc.)"
  }},
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
    "role": "Specific expert role title derived from THIS document's trade/industry/context",
    "industry_context": "2-3 sentences on typical norms for THIS specific type of work, derived from document specifics",
    "key_benchmarks": [
      "Benchmark specific to THIS document's trade, scale, and method — not a generic example",
      "Second benchmark specific to this document"
    ],
    "typical_red_flags": [
      "Red flag specific to the risk profile evident in THIS document",
      "Second red flag relevant to this specific document type and scope"
    ],
    "normal_expectations": [
      "Expectation calibrated to THIS document's geography, sector, and scale",
      "Second expectation relevant to this specific work"
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
            from services.ai_models import completion_params
            response = await self.client.chat.completions.create(
                messages=[
                    {'role': 'system', 'content': _SYSTEM},
                    {'role': 'user', 'content': _USER_TEMPLATE.format(
                        rich_analysis_text=rich_analysis_text,
                        doc_type=doc_type,
                        mode=mode,
                    )},
                ],
                response_format={'type': 'json_object'},
                timeout=90.0,
                **completion_params(self.model, 4500, temperature=0.15),
            )
            result = json.loads(response.choices[0].message.content)

            n_present = len(result.get('confirmed_present', []))
            n_absent = len(result.get('confirmed_absent', []))
            n_unverified = len(result.get('unverified', []))
            logger.info(
                f'[DocProfile] {n_present} confirmed present, '
                f'{n_absent} confirmed absent, '
                f'{n_unverified} unverified | '
                f'role={result.get("expertise_profile", {}).get("role", "unknown")} | '
                f'doc_understanding={"yes" if result.get("document_understanding") else "no"}'
            )
            return result

        except Exception as e:
            logger.error(f'[DocProfile] Failed: {e}')
            # Return safe empty profile — downstream agents handle this gracefully
            return {
                'document_understanding': {
                    'document_title': '',
                    'document_overview': '',
                    'major_workstreams': [],
                    'key_obligations': [],
                    'key_constraints': [],
                    'structural_organization': '',
                },
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
