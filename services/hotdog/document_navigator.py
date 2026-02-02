"""
Document Navigator Agent for HOTDOG7ATE Pre-Scan.

Analyzes document structure (TOC, index, appendix, headers) and creates
a navigation map that directs each expert to the most relevant pages/windows.

This is used ONLY by the v2 pipeline for Bid/Spec mode.
Classic analysis and BestPrep mode do not use this component.
"""

import logging
import re
from typing import Dict, List, Set, Optional, Tuple, Callable
from dataclasses import dataclass, field

from .models import Question, ExpertPersona, PageData
from .document_structure_analyzer import DocumentStructureAnalyzer, DocumentStructure

logger = logging.getLogger(__name__)


@dataclass
class ExpertAssignment:
    """Assignment of pages/windows to an expert based on document structure."""
    expert_name: str
    section_id: str
    primary_pages: List[int]  # Pages most likely to have answers
    context_pages: List[int]  # Window before + after for context
    keywords_found: List[str]  # Keywords that led to this assignment
    confidence: float  # How confident we are this is the right area


@dataclass
class NavigationMap:
    """Complete navigation map for all experts."""
    structure: DocumentStructure
    expert_assignments: Dict[str, ExpertAssignment]  # expert_name -> assignment
    unassigned_questions: List[str]  # Question IDs with no structural hints
    total_pages_to_scan: int
    estimated_reduction: float  # % reduction vs exhaustive scan


class DocumentNavigator:
    """
    Pre-scan agent that creates a navigation map for targeted extraction.

    Analyzes:
    1. Table of Contents - section-to-page mapping
    2. Index - keyword-to-page mapping
    3. Appendices - supplementary material locations
    4. Headers/Footers - section boundaries
    5. Question keywords - match to structural elements

    ISOLATION: This class is ONLY used when:
    - mode == 'bid_spec' AND
    - use_pipeline_v2 == True

    It has NO EFFECT on classic analysis or BestPrep mode.
    """

    # Stop words to exclude from keyword extraction
    STOP_WORDS = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'which',
        'who', 'how', 'when', 'where', 'why', 'does', 'do', 'did',
        'have', 'has', 'will', 'would', 'could', 'should', 'may',
        'required', 'requirements', 'specify', 'specified', 'project',
        'contractor', 'shall', 'must', 'for', 'with', 'this', 'that',
        'any', 'all', 'each', 'every', 'been', 'being', 'their',
        'from', 'about', 'into', 'through', 'during', 'before', 'after',
        'above', 'below', 'between', 'under', 'again', 'further', 'then',
        'once', 'here', 'there', 'when', 'where', 'why', 'how', 'both',
        'few', 'more', 'most', 'other', 'some', 'such', 'only', 'own',
        'same', 'than', 'too', 'very', 'just', 'can', 'will', 'should'
    }

    def __init__(self):
        """Initialize the Document Navigator."""
        self.structure_analyzer = DocumentStructureAnalyzer()

    async def create_navigation_map(
        self,
        pages: List[PageData],
        questions: List[Question],
        experts: Dict[str, ExpertPersona],
        progress_callback: Optional[Callable] = None
    ) -> NavigationMap:
        """
        Create a navigation map directing experts to relevant pages.

        Args:
            pages: All document pages
            questions: Questions to answer (filtered by user selection)
            experts: Expert personas by section_id
            progress_callback: Optional callback for progress updates

        Returns:
            NavigationMap with expert assignments
        """
        logger.info("\n" + "="*64)
        logger.info("DOCUMENT NAVIGATOR: Pre-Scan Analysis")
        logger.info("="*64)

        if progress_callback:
            progress_callback('prescan_start', {
                'total_pages': len(pages),
                'total_questions': len(questions),
                'total_experts': len(experts)
            })

        # Step 1: Analyze document structure
        pages_data = [{'page_num': p.page_num, 'text': p.text} for p in pages]
        structure = self.structure_analyzer.analyze(pages_data)

        logger.info(f"  TOC Found: {structure.has_toc} ({len(structure.toc_entries)} entries)")
        logger.info(f"  Index Found: {structure.has_index} ({len(structure.index_entries)} terms)")
        logger.info(f"  Appendix Found: {structure.has_appendix} ({len(structure.appendix_pages)} pages)")
        logger.info(f"  Section Headers: {len(structure.section_headers)}")

        # Step 2: Extract keywords from each expert's questions
        expert_keywords = self._extract_expert_keywords(questions, experts)

        # Step 3: Create assignments for each expert
        expert_assignments = {}
        unassigned_questions = []
        total_pages = len(pages)

        for section_id, expert in experts.items():
            # Get questions for this expert
            expert_questions = [q for q in questions if q.section_id == section_id]
            if not expert_questions:
                continue

            keywords = expert_keywords.get(section_id, [])

            # Find pages for this expert using structure
            primary_pages = set()
            keywords_found = []

            # Check TOC entries
            for entry_name, page_num in structure.toc_entries.items():
                if self._matches_keywords(entry_name, keywords):
                    primary_pages.add(page_num)
                    # Add a few pages after TOC entry (content usually follows)
                    for offset in range(1, 4):
                        if page_num + offset <= total_pages:
                            primary_pages.add(page_num + offset)
                    keywords_found.append(f"TOC: {entry_name[:30]}")

            # Check index entries
            for term, term_pages in structure.index_entries.items():
                if self._matches_keywords(term, keywords):
                    primary_pages.update(term_pages)
                    keywords_found.append(f"Index: {term[:30]}")

            # Check section headers
            for page_num, header in structure.section_headers.items():
                if self._matches_keywords(header, keywords):
                    primary_pages.add(page_num)
                    # Add following pages (section content)
                    for offset in range(1, 3):
                        if page_num + offset <= total_pages:
                            primary_pages.add(page_num + offset)
                    keywords_found.append(f"Header: {header[:30]}")

            # Check appendix sections
            for appendix_name, start_page in structure.appendix_sections.items():
                if self._matches_keywords(appendix_name, keywords):
                    # Appendices often have relevant specs
                    primary_pages.add(start_page)
                    for offset in range(1, 5):
                        if start_page + offset <= total_pages:
                            primary_pages.add(start_page + offset)
                    keywords_found.append(f"Appendix: {appendix_name[:30]}")

            # Calculate context pages (window before + after each primary)
            context_pages = set()
            for page in primary_pages:
                # Window before (up to 3 pages)
                for offset in range(1, 4):
                    if page - offset >= 1:
                        context_pages.add(page - offset)
                # Window after (up to 3 pages)
                for offset in range(1, 4):
                    if page + offset <= total_pages:
                        context_pages.add(page + offset)

            # Remove primary pages from context (avoid duplication)
            context_pages -= primary_pages

            if primary_pages:
                assignment = ExpertAssignment(
                    expert_name=expert.name,
                    section_id=section_id,
                    primary_pages=sorted(primary_pages),
                    context_pages=sorted(context_pages),
                    keywords_found=keywords_found[:10],  # Limit for display
                    confidence=min(0.9, 0.5 + (len(keywords_found) * 0.1))
                )
                expert_assignments[expert.name] = assignment
                logger.info(f"  {expert.name}:")
                logger.info(f"    Primary pages: {len(primary_pages)} | Context: {len(context_pages)}")
                logger.info(f"    Keywords matched: {', '.join(keywords_found[:3])}")
            else:
                # No structural hints - these questions go to full exhaustive
                for q in expert_questions:
                    unassigned_questions.append(q.id)
                logger.info(f"  {expert.name}: No structural hints found")

        # Calculate reduction
        total_primary = sum(len(a.primary_pages) for a in expert_assignments.values())
        total_context = sum(len(a.context_pages) for a in expert_assignments.values())
        total_to_scan = total_primary + total_context

        # Avoid division by zero
        if total_pages > 0 and len(experts) > 0:
            full_exhaustive = total_pages * len(experts)
            estimated_reduction = 1 - (total_to_scan / full_exhaustive)
        else:
            estimated_reduction = 0

        nav_map = NavigationMap(
            structure=structure,
            expert_assignments=expert_assignments,
            unassigned_questions=unassigned_questions,
            total_pages_to_scan=total_to_scan,
            estimated_reduction=max(0, estimated_reduction)
        )

        if progress_callback:
            progress_callback('prescan_complete', {
                'has_toc': structure.has_toc,
                'has_index': structure.has_index,
                'has_appendix': structure.has_appendix,
                'toc_entries': len(structure.toc_entries),
                'index_terms': len(structure.index_entries),
                'expert_assignments': [
                    {
                        'expert': a.expert_name,
                        'pages': a.primary_pages[:5],  # First 5 for display
                        'total_pages': len(a.primary_pages) + len(a.context_pages),
                        'keywords': a.keywords_found[:3]
                    }
                    for a in expert_assignments.values()
                ],
                'unassigned_questions': len(unassigned_questions),
                'estimated_reduction': f"{estimated_reduction*100:.0f}%"
            })

        logger.info(f"\nNavigation Map Complete:")
        logger.info(f"  Experts with assignments: {len(expert_assignments)}/{len(experts)}")
        logger.info(f"  Total pages to quick-scan: {total_to_scan}")
        logger.info(f"  Estimated reduction: {estimated_reduction*100:.0f}%")
        logger.info(f"  Unassigned questions (full exhaustive): {len(unassigned_questions)}")

        return nav_map

    def _extract_expert_keywords(
        self,
        questions: List[Question],
        experts: Dict[str, ExpertPersona]
    ) -> Dict[str, List[str]]:
        """Extract relevant keywords for each expert based on their questions and name."""
        expert_keywords = {}

        for section_id, expert in experts.items():
            keywords = set()

            # Add keywords from expert name/specialization
            expert_words = re.findall(r'\b[a-zA-Z]+\b', expert.name.lower())
            keywords.update(w for w in expert_words if w not in self.STOP_WORDS and len(w) > 2)

            # Add keywords from expert's system prompt if available
            if hasattr(expert, 'system_prompt') and expert.system_prompt:
                prompt_words = re.findall(r'\b[a-zA-Z]+\b', expert.system_prompt.lower())
                # Take significant words only
                keywords.update(w for w in prompt_words if w not in self.STOP_WORDS and len(w) > 4)

            # Add keywords from questions assigned to this expert
            section_questions = [q for q in questions if q.section_id == section_id]
            for q in section_questions:
                q_words = re.findall(r'\b[a-zA-Z]+\b', q.text.lower())
                keywords.update(w for w in q_words if w not in self.STOP_WORDS and len(w) > 3)

            # Prioritize domain-specific terms
            domain_terms = self._extract_domain_terms(section_questions)
            keywords.update(domain_terms)

            expert_keywords[section_id] = list(keywords)[:25]  # Limit keywords

        return expert_keywords

    def _extract_domain_terms(self, questions: List[Question]) -> Set[str]:
        """Extract domain-specific technical terms from questions."""
        domain_terms = set()

        # Common bid/spec domain patterns
        domain_patterns = [
            r'\b(cipp|hdpe|pvc|pipe|liner|lining)\b',
            r'\b(warranty|bond|insurance|surety)\b',
            r'\b(specifications?|requirements?|standards?)\b',
            r'\b(diameter|thickness|length|footage)\b',
            r'\b(cure|curing|installation|testing)\b',
            r'\b(payment|retention|schedule|timeline)\b',
            r'\b(submittal|certification|compliance)\b',
            r'\b(liquidated|damages|penalty|penalties)\b',
            r'\b(inspection|quality|control|assurance)\b',
        ]

        combined_text = ' '.join(q.text.lower() for q in questions)

        for pattern in domain_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            domain_terms.update(m.lower() if isinstance(m, str) else m[0].lower() for m in matches)

        return domain_terms

    def _matches_keywords(self, text: str, keywords: List[str]) -> bool:
        """Check if text contains any of the keywords."""
        if not text or not keywords:
            return False

        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)

    def get_pages_for_expert(
        self,
        nav_map: NavigationMap,
        expert_name: str,
        include_context: bool = True
    ) -> List[int]:
        """
        Get all pages an expert should examine.

        Args:
            nav_map: The navigation map
            expert_name: Name of the expert
            include_context: Whether to include context pages

        Returns:
            Sorted list of page numbers
        """
        assignment = nav_map.expert_assignments.get(expert_name)
        if not assignment:
            return []

        if include_context:
            all_pages = set(assignment.primary_pages) | set(assignment.context_pages)
        else:
            all_pages = set(assignment.primary_pages)

        return sorted(all_pages)
