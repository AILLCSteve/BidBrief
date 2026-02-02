"""
Document Structure Analyzer for HOTDOG7ATE Optimized Scan Pass.

HOTDOG7ATE = Hierarchical Orchestrated Thorough Document Oversight & Guidance -
             Adaptive Thorough Extraction

Enhanced structural analysis that identifies:
- Table of Contents (TOC)
- Index/Appendix
- Section Headers (running headers on all pages)
- Page Footers (running footers)
- Topic Areas (keyword-rich regions in body text)
- Title blocks and specification divisions
"""

import re
import logging
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class StructuralElement:
    """A structural element found in the document."""
    element_type: str  # 'toc', 'index', 'header', 'footer', 'title', 'appendix', 'topic_area'
    pages: List[int]
    text: str
    references: Dict[str, List[int]] = field(default_factory=dict)  # topic -> page numbers


@dataclass
class TopicHotspot:
    """A detected topic hotspot - area where keywords concentrate."""
    page_num: int
    topic_keywords: List[str]
    context_snippet: str  # Short text around the keywords
    density_score: float  # How concentrated keywords are


@dataclass
class DocumentStructure:
    """Complete structural analysis of document."""
    has_toc: bool = False
    toc_pages: List[int] = field(default_factory=list)
    toc_entries: Dict[str, int] = field(default_factory=dict)  # section_name -> page_num

    has_index: bool = False
    index_pages: List[int] = field(default_factory=list)
    index_entries: Dict[str, List[int]] = field(default_factory=dict)  # term -> [page_nums]

    has_appendix: bool = False
    appendix_pages: List[int] = field(default_factory=list)
    appendix_sections: Dict[str, int] = field(default_factory=dict)  # appendix_name -> start_page

    section_headers: Dict[int, str] = field(default_factory=dict)  # page -> header_text
    page_footers: Dict[int, str] = field(default_factory=dict)  # page -> footer_text
    page_titles: Dict[int, str] = field(default_factory=dict)  # page -> title

    # Enhanced: Topic hotspots - pages with keyword concentrations
    topic_hotspots: Dict[int, TopicHotspot] = field(default_factory=dict)  # page -> hotspot

    # Enhanced: Running headers/footers across document
    running_headers: Dict[int, str] = field(default_factory=dict)  # page -> recurring header
    running_footers: Dict[int, str] = field(default_factory=dict)  # page -> recurring footer

    # Enhanced: Specification divisions (common in construction docs)
    spec_divisions: Dict[str, int] = field(default_factory=dict)  # division name -> start page


class DocumentStructureAnalyzer:
    """
    Analyzes document structure for Optimized Scan Pass.

    Enhanced analysis that identifies structural elements for targeted extraction:
    - TOC tells us where to look for specific topics
    - Index provides term -> page mappings
    - Headers/footers reveal section organization and page topics
    - Topic hotspots identify keyword-dense regions
    - Spec divisions help navigate construction documents
    """

    # Patterns for detecting structural elements
    TOC_PATTERNS = [
        r'table\s+of\s+contents',
        r'contents\s*$',
        r'^contents\s*\n',
        r'index\s+of\s+contents',
    ]

    INDEX_PATTERNS = [
        r'^index\s*$',
        r'subject\s+index',
        r'alphabetical\s+index',
    ]

    APPENDIX_PATTERNS = [
        r'appendix\s+[a-z]',
        r'appendices',
        r'attachment\s+[a-z0-9]',
        r'exhibit\s+[a-z0-9]',
    ]

    SECTION_HEADER_PATTERNS = [
        r'^(?:section|article|part|division)\s+\d+',
        r'^\d+\.\d+\s+[A-Z]',
        r'^[A-Z]{2,}\s*[-:]\s*[A-Z]',
        r'^\d{5,6}\s+[A-Z]',  # CSI MasterFormat division numbers
    ]

    # Specification division patterns (CSI MasterFormat)
    SPEC_DIVISION_PATTERNS = [
        r'division\s+(\d{1,2})',
        r'section\s+(\d{5,6})',
        r'(\d{2})\s*\d{2}\s*\d{2}',  # 6-digit spec format
    ]

    # Common running header/footer patterns
    RUNNING_HEADER_PATTERNS = [
        r'^[A-Z][A-Za-z\s&\-]+(?:SPECIFICATIONS?|PROJECT|CONTRACT)',
        r'^SECTION\s+\d+',
        r'^DIVISION\s+\d+',
    ]

    def __init__(self):
        self.structure = DocumentStructure()

    def analyze(self, pages: List[Dict], target_keywords: List[str] = None) -> DocumentStructure:
        """
        Analyze document structure from extracted pages.

        Args:
            pages: List of {'page_num': int, 'text': str}
            target_keywords: Optional list of keywords to look for in topic hotspots

        Returns:
            DocumentStructure with all identified elements
        """
        logger.info("Analyzing document structure (Optimized Scan Pass)...")

        self.structure = DocumentStructure()

        # Pass 1: Find TOC
        self._find_toc(pages)

        # Pass 2: Find Index
        self._find_index(pages)

        # Pass 3: Find Appendix sections
        self._find_appendix(pages)

        # Pass 4: Extract section headers (enhanced - all pages)
        self._extract_section_headers(pages)

        # Pass 5: NEW - Extract running headers/footers
        self._extract_running_headers_footers(pages)

        # Pass 6: NEW - Find specification divisions
        self._find_spec_divisions(pages)

        # Pass 7: NEW - Find topic hotspots (if keywords provided)
        if target_keywords:
            self._find_topic_hotspots(pages, target_keywords)

        logger.info(f"  TOC: {self.structure.has_toc} ({len(self.structure.toc_entries)} entries)")
        logger.info(f"  Index: {self.structure.has_index} ({len(self.structure.index_entries)} terms)")
        logger.info(f"  Appendix: {self.structure.has_appendix} ({len(self.structure.appendix_sections)} sections)")
        logger.info(f"  Section Headers: {len(self.structure.section_headers)} pages")
        logger.info(f"  Running Headers: {len(self.structure.running_headers)} pages")
        logger.info(f"  Spec Divisions: {len(self.structure.spec_divisions)}")
        logger.info(f"  Topic Hotspots: {len(self.structure.topic_hotspots)}")

        return self.structure

    def _find_toc(self, pages: List[Dict]) -> None:
        """Find and parse Table of Contents."""
        for page in pages[:20]:  # TOC typically in first 20 pages
            text_lower = page['text'].lower()

            for pattern in self.TOC_PATTERNS:
                if re.search(pattern, text_lower, re.MULTILINE | re.IGNORECASE):
                    self.structure.has_toc = True
                    self.structure.toc_pages.append(page['page_num'])

                    # Parse TOC entries: "Section Name ... 15" or "Section Name\t15"
                    toc_entry_pattern = r'([A-Za-z][A-Za-z\s&\-/]+?)\s*[\.…\t]+\s*(\d{1,3})'
                    matches = re.findall(toc_entry_pattern, page['text'])

                    for section_name, page_num in matches:
                        clean_name = section_name.strip()
                        if len(clean_name) > 3:  # Filter out noise
                            self.structure.toc_entries[clean_name] = int(page_num)

                    break

    def _find_index(self, pages: List[Dict]) -> None:
        """Find and parse Index/Subject Index."""
        # Index typically in last 30 pages
        for page in reversed(pages[-30:]):
            text_lower = page['text'].lower()

            for pattern in self.INDEX_PATTERNS:
                if re.search(pattern, text_lower, re.MULTILINE | re.IGNORECASE):
                    self.structure.has_index = True
                    self.structure.index_pages.append(page['page_num'])

                    # Parse index entries: "term, 5, 12, 45" or "term ... 5"
                    index_entry_pattern = r'^([A-Za-z][A-Za-z\s\-/]+?)[,\s]+(\d[\d,\s]+)'
                    matches = re.findall(index_entry_pattern, page['text'], re.MULTILINE)

                    for term, page_nums in matches:
                        clean_term = term.strip().lower()
                        if len(clean_term) > 2:
                            pages_list = [int(p.strip()) for p in re.findall(r'\d+', page_nums)]
                            if pages_list:
                                self.structure.index_entries[clean_term] = pages_list

                    break

    def _find_appendix(self, pages: List[Dict]) -> None:
        """Find Appendix/Attachment sections."""
        for page in pages:
            text_lower = page['text'].lower()

            for pattern in self.APPENDIX_PATTERNS:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    self.structure.has_appendix = True
                    self.structure.appendix_pages.append(page['page_num'])

                    # Extract appendix identifier
                    appendix_id = match.group(0).strip()
                    self.structure.appendix_sections[appendix_id] = page['page_num']

    def _extract_section_headers(self, pages: List[Dict]) -> None:
        """Extract section headers from each page - enhanced to look at full page."""
        for page in pages:
            text = page['text']

            # Look at first 800 chars (expanded from 500)
            header_region = text[:800]

            for pattern in self.SECTION_HEADER_PATTERNS:
                match = re.search(pattern, header_region, re.MULTILINE | re.IGNORECASE)
                if match:
                    self.structure.section_headers[page['page_num']] = match.group(0).strip()
                    break

            # Also check for prominent text at very top (first 200 chars, likely headers)
            top_region = text[:200]
            lines = top_region.split('\n')
            if lines:
                first_line = lines[0].strip()
                # If first line is short and all caps or title case, likely a header
                if first_line and len(first_line) < 100:
                    if first_line.isupper() or first_line.istitle():
                        if page['page_num'] not in self.structure.section_headers:
                            self.structure.section_headers[page['page_num']] = first_line

    def _extract_running_headers_footers(self, pages: List[Dict]) -> None:
        """
        Extract running headers and footers that repeat across pages.
        These often indicate section or document context.
        """
        header_candidates = Counter()
        footer_candidates = Counter()

        for page in pages:
            text = page['text']
            lines = text.split('\n')

            # Get first 3 non-empty lines as potential headers
            header_lines = []
            for line in lines[:10]:
                stripped = line.strip()
                if stripped and len(stripped) > 3 and len(stripped) < 100:
                    header_lines.append(stripped)
                if len(header_lines) >= 3:
                    break

            # Get last 3 non-empty lines as potential footers
            footer_lines = []
            for line in reversed(lines[-10:]):
                stripped = line.strip()
                if stripped and len(stripped) > 3 and len(stripped) < 100:
                    footer_lines.append(stripped)
                if len(footer_lines) >= 3:
                    break

            for h in header_lines:
                header_candidates[h] += 1
            for f in footer_lines:
                footer_candidates[f] += 1

        # Running headers/footers appear on multiple pages
        min_occurrences = max(3, len(pages) // 10)  # At least 10% of pages or 3

        common_headers = {text for text, count in header_candidates.items() if count >= min_occurrences}
        common_footers = {text for text, count in footer_candidates.items() if count >= min_occurrences}

        # Assign running headers/footers to pages
        for page in pages:
            text = page['text']
            lines = text.split('\n')

            # Check headers
            for line in lines[:5]:
                stripped = line.strip()
                if stripped in common_headers:
                    self.structure.running_headers[page['page_num']] = stripped
                    break

            # Check footers
            for line in reversed(lines[-5:]):
                stripped = line.strip()
                if stripped in common_footers:
                    self.structure.running_footers[page['page_num']] = stripped
                    break

    def _find_spec_divisions(self, pages: List[Dict]) -> None:
        """Find specification divisions (common in construction documents)."""
        for page in pages:
            text = page['text']

            # Look for division headers
            for pattern in self.SPEC_DIVISION_PATTERNS:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    div_name = f"Division {match}" if not match.startswith('Division') else match
                    if div_name not in self.structure.spec_divisions:
                        self.structure.spec_divisions[div_name] = page['page_num']

            # Also look for section titles that indicate divisions
            division_keywords = [
                'general requirements', 'earthwork', 'concrete', 'masonry',
                'metals', 'wood', 'thermal', 'moisture protection', 'openings',
                'finishes', 'specialties', 'equipment', 'furnishings',
                'special construction', 'conveying', 'plumbing', 'hvac',
                'electrical', 'communications', 'electronic safety',
                'site preparation', 'utilities', 'pipeline', 'rehabilitation'
            ]

            text_lower = text.lower()
            for keyword in division_keywords:
                if keyword in text_lower:
                    # Check if it's a section header, not just mentioned
                    pattern = rf'^.*{re.escape(keyword)}.*$'
                    match = re.search(pattern, text_lower, re.MULTILINE | re.IGNORECASE)
                    if match and len(match.group(0)) < 100:  # Not a full sentence
                        div_name = keyword.title()
                        if div_name not in self.structure.spec_divisions:
                            self.structure.spec_divisions[div_name] = page['page_num']

    def _find_topic_hotspots(self, pages: List[Dict], target_keywords: List[str]) -> None:
        """
        Find pages where target keywords are concentrated.
        These are 'hotspots' likely to contain relevant information.
        """
        if not target_keywords:
            return

        # Normalize keywords
        keywords = [kw.lower() for kw in target_keywords if len(kw) > 2]

        for page in pages:
            text_lower = page['text'].lower()

            # Count keyword occurrences
            found_keywords = []
            for kw in keywords:
                count = text_lower.count(kw)
                if count > 0:
                    found_keywords.extend([kw] * count)

            if len(found_keywords) >= 2:  # At least 2 keyword matches
                # Calculate density score
                text_length = max(len(text_lower), 1)
                density = len(found_keywords) / (text_length / 1000)  # keywords per 1000 chars

                # Get context snippet around first keyword
                first_kw = found_keywords[0]
                kw_pos = text_lower.find(first_kw)
                start = max(0, kw_pos - 100)
                end = min(len(text_lower), kw_pos + len(first_kw) + 100)
                snippet = page['text'][start:end].replace('\n', ' ').strip()

                self.structure.topic_hotspots[page['page_num']] = TopicHotspot(
                    page_num=page['page_num'],
                    topic_keywords=list(set(found_keywords)),
                    context_snippet=snippet[:200] + '...' if len(snippet) > 200 else snippet,
                    density_score=density
                )

    def get_pages_for_topic(self, topic: str) -> List[int]:
        """
        Get relevant pages for a topic using structure analysis.

        Args:
            topic: Topic/question text to find pages for

        Returns:
            List of page numbers likely to contain relevant info
        """
        relevant_pages = []
        topic_lower = topic.lower()
        topic_words = set(topic_lower.split())

        # Check TOC entries
        for section_name, page_num in self.structure.toc_entries.items():
            section_words = set(section_name.lower().split())
            if topic_words & section_words:  # Any word overlap
                relevant_pages.append(page_num)

        # Check Index entries
        for term, page_nums in self.structure.index_entries.items():
            if term in topic_lower or any(word in term for word in topic_words):
                relevant_pages.extend(page_nums)

        # Check section headers
        for page_num, header in self.structure.section_headers.items():
            header_words = set(header.lower().split())
            if topic_words & header_words:
                relevant_pages.append(page_num)

        # Check running headers
        for page_num, header in self.structure.running_headers.items():
            if any(word in header.lower() for word in topic_words if len(word) > 3):
                relevant_pages.append(page_num)

        # Check topic hotspots
        for page_num, hotspot in self.structure.topic_hotspots.items():
            if any(kw in topic_lower for kw in hotspot.topic_keywords):
                relevant_pages.append(page_num)

        # Check spec divisions
        for div_name, page_num in self.structure.spec_divisions.items():
            if any(word in div_name.lower() for word in topic_words if len(word) > 3):
                relevant_pages.append(page_num)

        # Dedupe and sort
        return sorted(set(relevant_pages))

    def get_all_structural_pages(self) -> Set[int]:
        """Get all pages that have some structural significance."""
        pages = set()

        pages.update(self.structure.toc_pages)
        pages.update(self.structure.index_pages)
        pages.update(self.structure.appendix_pages)
        pages.update(self.structure.section_headers.keys())
        pages.update(self.structure.running_headers.keys())
        pages.update(self.structure.spec_divisions.values())
        pages.update(self.structure.topic_hotspots.keys())

        for page_list in self.structure.index_entries.values():
            pages.update(page_list)

        return pages
