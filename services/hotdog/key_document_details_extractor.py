"""
Key Document Details Extractor

Context-aware extraction of key details from any document type.
Always runs regardless of user-selected sections to ensure the Summary page
has complete detail data for every analysis.

Automatically detects document type and extracts only the fields relevant
to that document — bid specs, RFPs, contracts, reports, manuals, etc.

Replaces key_requirements_extractor.py (hardcoded 13 bid-spec fields).
"""

import logging
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class KeyDocumentDetail:
    """A single extracted key detail from a document."""
    name: str
    value: str
    page: int
    confidence: float
    raw_quote: str = ""


class KeyDocumentDetailsExtractor:
    """
    Extracts key details from any document type.

    This runs ALWAYS, regardless of which sections the user selects.
    Automatically determines document type, then extracts only the fields
    relevant to that type. Covers bid specs as well as any other document.
    """

    EXTRACTION_PROMPT = """You are an expert document analyst. Your task is two steps:

STEP 1 — Identify the document type.
Based on the content, identify what type of document this is. Choose the single best match:
- bid_spec (Invitation to Bid, Plans & Specs, Bidding Documents)
- rfp (Request for Proposals)
- rfq (Request for Qualifications)
- contract (Agreement, Contract, Subcontract)
- report (Engineering Report, Feasibility Study, Assessment)
- manual (Operations Manual, Maintenance Manual, Design Manual)
- permit (Permit Application, Environmental Permit, Agency Approval)
- addendum (Addendum, Amendment, Change Order)
- other (any other document type — specify)

STEP 2 — Extract the most important key details.
Based on the document type, extract UP TO 13 of the most decision-critical details.
Fewer is better — only include fields that are clearly present and genuinely important.

FIELD GUIDANCE BY DOCUMENT TYPE:

bid_spec / rfp / rfq:
  project_name, owner_agency, engineer, location, timeline, scope,
  bid_deadline, payment, warranty, liquidated_damages, bonding,
  certifications, insurance

contract / subcontract:
  parties, project_name, contract_value, start_date, completion_date,
  payment_terms, retention, liquidated_damages, bonding, insurance,
  dispute_resolution, governing_law, warranty

report:
  title, author, client, date, project_location, subject_scope,
  key_findings, recommendations, next_steps

manual:
  title, document_number, revision, applicable_equipment,
  scope_of_manual, key_procedures, safety_requirements

permit:
  permit_type, permitting_agency, applicant, project_description,
  permit_number, issue_date, expiration_date, key_conditions

addendum:
  project_name, original_document, addendum_number, issue_date,
  bid_deadline_revised, key_changes

other:
  Extract whatever fields are most important for this specific document.

DOCUMENT TEXT:
{document_text}

---

Respond in this EXACT JSON format:
{{
    "document_type": "bid_spec",
    "document_type_label": "Invitation to Bid — Water Main Replacement",
    "details": [
        {{
            "name": "Project Name",
            "value": "...",
            "page": 1,
            "confidence": 0.95,
            "quote": "..."
        }},
        ...
    ]
}}

Rules:
- Include page numbers from <PDF pg X> markers when available (use 0 if unknown)
- Set confidence: 0.95 if you have a direct quote, 0.75 if inferred from context
- Cap at 13 details — omit low-value or not-found fields entirely
- document_type_label: short human-readable description (document type + distinguishing info)
- For bid_spec documents, do not omit bonding, insurance, liquidated_damages if present"""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.extracted_details: List[KeyDocumentDetail] = []
        self._document_type: str = "unknown"
        self._document_type_label: str = ""

    async def extract_from_document(
        self,
        pages_text: List[Dict[str, Any]],
        sample_pages: Optional[List[int]] = None
    ) -> List[KeyDocumentDetail]:
        """
        Extract key details from document pages.

        Args:
            pages_text: List of page data with 'page_num' and 'text'
            sample_pages: Optional list of specific pages to check.
                          Default: first 8 pages + last 3 pages.

        Returns:
            List of KeyDocumentDetail objects
        """
        logger.info("🔑 Extracting Key Document Details...")

        total_pages = len(pages_text)

        if sample_pages is None:
            # First 8 pages: cover page, parties, dates, TOC, scope summary
            # Last 3 pages: appendices, addenda, signature blocks
            front = list(range(1, min(9, total_pages + 1)))
            back = list(range(max(total_pages - 2, 9), total_pages + 1)) if total_pages > 8 else []
            sample_pages = front + [p for p in back if p not in front]

        # Build document text from sample pages
        doc_text_parts = []
        for page_data in pages_text:
            if page_data.get('page_num') in sample_pages:
                text = page_data.get('text', '')
                if text.strip():
                    doc_text_parts.append(f"<PDF pg {page_data['page_num']}>\n{text}")

        document_text = "\n\n".join(doc_text_parts)

        # Truncate if too long (leave room for response)
        max_chars = 50000
        if len(document_text) > max_chars:
            document_text = document_text[:max_chars] + "\n\n[Document truncated...]"

        if not document_text.strip():
            logger.warning("No text extracted from sample pages for key document details")
            return []

        try:
            from services.ai_models import completion_params
            response = await self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise document analyst. Identify document type and extract only the most important key details. Respond with valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": self.EXTRACTION_PROMPT.format(
                            document_text=document_text
                        )
                    }
                ],
                response_format={"type": "json_object"},
                timeout=90.0,
                **completion_params(self.model, 2000, temperature=0.1)
            )

            result_text = response.choices[0].message.content

            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                logger.error("Failed to parse key document details JSON response")
                return []

            self._document_type = result.get("document_type", "unknown")
            self._document_type_label = result.get("document_type_label", "")

            raw_details = result.get("details", [])
            self.extracted_details = []

            for item in raw_details:
                name = item.get("name", "").strip()
                value = item.get("value", "").strip()
                if not name or not value:
                    continue
                self.extracted_details.append(KeyDocumentDetail(
                    name=name,
                    value=value,
                    page=item.get("page", 0),
                    confidence=item.get("confidence", 0.75),
                    raw_quote=item.get("quote", "")
                ))

            found_count = len(self.extracted_details)
            logger.info(
                f"✅ Extracted {found_count} key details "
                f"(document type: {self._document_type})"
            )

            return self.extracted_details

        except Exception as e:
            logger.error(f"Key document details extraction failed: {e}")
            return []

    def get_document_type(self) -> str:
        """Return the detected document type identifier (e.g. 'bid_spec', 'rfp')."""
        return self._document_type

    def get_document_type_label(self) -> str:
        """Return the human-readable document type label."""
        return self._document_type_label

    def get_details_list(self) -> List[Dict[str, Any]]:
        """Get extracted details as a list of dicts for serialization."""
        return [
            {
                "name": d.name,
                "value": d.value,
                "page": d.page,
                "confidence": d.confidence,
                "quote": d.raw_quote
            }
            for d in self.extracted_details
        ]

    def get_summary_data(self) -> Dict[str, str]:
        """
        Get simplified name→value mapping for Summary display.

        Returns same Dict[str, str] interface as the legacy
        KeyRequirementsExtractor.get_summary_data() for backward compatibility
        with all downstream consumers.
        """
        return {d.name: d.value for d in self.extracted_details}
