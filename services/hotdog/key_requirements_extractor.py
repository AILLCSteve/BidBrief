"""
Key Project Requirements Extractor

Always runs regardless of user-selected sections to ensure the Summary page
has complete key requirement data for every analysis.

Extracts:
- Project Name / Title
- Project Location
- Owner / Agency
- Engineer / Designer
- Bid Deadline / Opening Date
- Completion Date / Timeline
- Contract Days
- Liquidated Damages
- Bond Requirements
- Insurance Requirements
- Warranty Period
- Retention / Payment Terms
"""

import logging
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class KeyRequirement:
    """A single key project requirement."""
    name: str
    value: str
    page: int
    confidence: float
    raw_quote: str = ""


class KeyRequirementsExtractor:
    """
    Extracts key project requirements from bid specs.

    This runs ALWAYS, regardless of which sections the user selects.
    Ensures the Summary/Executive view has complete requirement data.
    """

    # The key requirements to always extract (aligned with excel/modal display)
    REQUIREMENTS = [
        ('project_name', 'Project Name or Title'),
        ('owner_agency', 'Owner / Agency / Municipality'),
        ('engineer', 'Engineer / Designer / Architect / Design Firm'),
        ('location', 'Project Location (City, State, Address)'),
        ('timeline', 'Project Timeline / Duration / Start-Completion Dates / Contract Days'),
        ('scope', 'Project Scope Summary (LF, diameter, pipe sizes, work type)'),
        ('bid_deadline', 'Bid Deadline / Bid Opening Date and Time'),
        ('payment', 'Payment Terms / Progress Payments / Retention Percentage'),
        ('warranty', 'Warranty Period / Guarantee Requirements'),
        ('liquidated_damages', 'Liquidated Damages ($/day for delays)'),
        ('bonding', 'Bond Requirements (Bid Bond, Performance Bond, Payment Bond percentages)'),
        ('certifications', 'Required Certifications (NASSCO, PACP, Operator Certifications)'),
        ('insurance', 'Insurance Requirements (Liability limits, coverage types)'),
    ]

    EXTRACTION_PROMPT = """You are a bid specification analyst. Extract ONLY the following key project requirements from this document text.

For each requirement found, provide:
1. The exact value/answer
2. The page number where found (from <PDF pg X> markers or context)
3. A brief direct quote from the source

REQUIREMENTS TO FIND:
{requirements_list}

DOCUMENT TEXT:
{document_text}

---

Respond in this EXACT JSON format (include ALL fields even if not found):
{{
    "project_name": {{"value": "...", "page": X, "quote": "...", "found": true/false}},
    "project_location": {{"value": "...", "page": X, "quote": "...", "found": true/false}},
    ... (all other requirements)
}}

If a requirement is not found, set "found": false and leave other fields empty.
CRITICAL: Include page numbers from <PDF pg X> markers when available."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.extracted_requirements: Dict[str, KeyRequirement] = {}

    async def extract_from_document(
        self,
        pages_text: List[Dict[str, Any]],
        sample_pages: Optional[List[int]] = None
    ) -> Dict[str, KeyRequirement]:
        """
        Extract key requirements from document pages.

        Args:
            pages_text: List of page data with 'page_num' and 'text'
            sample_pages: Optional list of specific pages to check (default: first 20, last 5)

        Returns:
            Dict mapping requirement_id to KeyRequirement
        """
        logger.info("🔑 Extracting Key Project Requirements...")

        # Select pages to analyze (focus on front matter and appendices)
        if sample_pages is None:
            # First 20 pages often have project info, last 5 for addenda
            total_pages = len(pages_text)
            sample_pages = list(range(1, min(21, total_pages + 1)))
            if total_pages > 25:
                sample_pages.extend(range(total_pages - 4, total_pages + 1))

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

        # Build requirements list for prompt
        req_list = "\n".join([f"- {name}: {desc}" for name, desc in self.REQUIREMENTS])

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise bid specification analyst. Extract key project requirements exactly as they appear in documents."
                    },
                    {
                        "role": "user",
                        "content": self.EXTRACTION_PROMPT.format(
                            requirements_list=req_list,
                            document_text=document_text
                        )
                    }
                ],
                temperature=0.1,  # Low temperature for factual extraction
                max_tokens=2000,
                response_format={"type": "json_object"},
                timeout=90.0  # Prevent indefinite hang on slow/failed API calls
            )

            result_text = response.choices[0].message.content

            # Parse JSON response
            import json
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                logger.error("Failed to parse key requirements JSON response")
                return {}

            # Convert to KeyRequirement objects
            for req_id, req_desc in self.REQUIREMENTS:
                if req_id in result and result[req_id].get('found'):
                    req_data = result[req_id]
                    self.extracted_requirements[req_id] = KeyRequirement(
                        name=req_desc,
                        value=req_data.get('value', ''),
                        page=req_data.get('page', 0),
                        confidence=0.9 if req_data.get('quote') else 0.7,
                        raw_quote=req_data.get('quote', '')
                    )

            found_count = len(self.extracted_requirements)
            logger.info(f"✅ Extracted {found_count}/{len(self.REQUIREMENTS)} key requirements")

            return self.extracted_requirements

        except Exception as e:
            logger.error(f"Key requirements extraction failed: {e}")
            return {}

    def get_requirements_dict(self) -> Dict[str, Any]:
        """Get extracted requirements as a simple dict for export."""
        return {
            req_id: {
                'name': req.name,
                'value': req.value,
                'page': req.page,
                'confidence': req.confidence,
                'quote': req.raw_quote
            }
            for req_id, req in self.extracted_requirements.items()
        }

    def get_summary_data(self) -> Dict[str, str]:
        """Get simplified key->value mapping for Summary display."""
        # Map internal IDs to display names matching the Excel export
        display_mapping = {
            'project_name': 'Project Name',
            'owner_agency': 'Owner/Agency',
            'engineer': 'Engineer',
            'location': 'Location',
            'timeline': 'Timeline',
            'scope': 'Scope',
            'bid_deadline': 'Bid Deadline',
            'payment': 'Payment',
            'warranty': 'Warranty',
            'liquidated_damages': 'Liquidated Damages',
            'bonding': 'Bonding',
            'certifications': 'Certifications',
            'insurance': 'Insurance',
        }

        summary = {}
        for req_id, req in self.extracted_requirements.items():
            display_name = display_mapping.get(req_id)
            if display_name and display_name not in summary:
                summary[display_name] = req.value

        return summary
