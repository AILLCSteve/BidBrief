"""
Document Structure Analyzer for HOTDOG7ATE Comprehensive Quick-Scan.

HOTDOG7ATE = Hierarchical Orchestrated Thorough Document Oversight & Guidance -
             Adaptive Thorough Extraction

Identifies and extracts structural elements:
- Table of Contents (TOC)
- Index/Appendix
- Section Headers
- Page Headers/Footers
- Title blocks
"""

import re
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StructuralElement:
    """A structural element found in the document."""
    element_type: str  # 'toc', 'index', 'header', 'footer', 'title', 'appendix'
    pages: List[int]
    text: str
    references: Dict[str, List[int]] = field(default_factory=dict)  # topic -> page numbers


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
    page_titles: Dict[int, str] = field(default_factory=dict)  # page -> title


class DocumentStructureAnalyzer:
    """
    Analyzes document structure for quick-scan optimization.

    Identifies structural elements that can fast-track answer discovery:
    - TOC tells us where to look for specific topics
    - Index provides term -> page mappings
    - Headers reveal section organization
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
    ]

    def __init__(self):
        self.structure = DocumentStructure()

    def analyze(self, pages: List[Dict]) -> DocumentStructure:
        """
        Analyze document structure from extracted pages.

        Args:
            pages: List of {'page_num': int, 'text': str}

        Returns:
            DocumentStructure with all identified elements
        """
        logger.info("Analyzing document structure...")

        self.structure = DocumentStructure()

        # Pass 1: Find TOC
        self._find_toc(pages)

        # Pass 2: Find Index
        self._find_index(pages)

        # Pass 3: Find Appendix sections
        self._find_appendix(pages)

        # Pass 4: Extract section headers
        self._extract_section_headers(pages)

        logger.info(f"  TOC: {self.structure.has_toc} ({len(self.structure.toc_entries)} entries)")
        logger.info(f"  Index: {self.structure.has_index} ({len(self.structure.index_entries)} terms)")
        logger.info(f"  Appendix: {self.structure.has_appendix} ({len(self.structure.appendix_sections)} sections)")
        logger.info(f"  Headers found: {len(self.structure.section_headers)} pages")

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
        # Index typically in last 20 pages
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
        """Extract section headers from each page."""
        for page in pages:
            # Look for header patterns in first 500 chars of page
            header_text = page['text'][:500]

            for pattern in self.SECTION_HEADER_PATTERNS:
                match = re.search(pattern, header_text, re.MULTILINE | re.IGNORECASE)
                if match:
                    self.structure.section_headers[page['page_num']] = match.group(0).strip()
                    break

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

        # Dedupe and sort
        return sorted(set(relevant_pages))
