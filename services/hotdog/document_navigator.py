"""
Document Navigator Agent for HOTDOG7ATE Optimized Scan Pass.

Analyzes document structure (TOC, index, appendix, headers, footers, topic hotspots)
and creates a navigation map that directs each expert to the most relevant pages/windows.

Key enhancements over simple scanning:
1. Consults expert personas for their recommended keywords
2. Analyzes running headers/footers for topic context
3. Identifies topic hotspots (keyword-dense regions)
4. Automatically includes window context (before + after target pages)

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
    primary_pages: List[int]  # Pages most likely to have answers (hotspots)
    context_pages: List[int]  # Window before + after for context (ALWAYS included)
    keywords_found: List[str]  # Keywords that led to this assignment
    expert_recommended_keywords: List[str]  # Keywords the expert suggested
    confidence: float  # How confident we are this is the right area


@dataclass
class NavigationMap:
    """Complete navigation map for all experts."""
    structure: DocumentStructure
    expert_assignments: Dict[str, ExpertAssignment]  # expert_name -> assignment
    unassigned_questions: List[str]  # Question IDs with no structural hints
    total_pages_to_scan: int
    estimated_reduction: float  # % reduction vs exhaustive scan
    all_keywords_by_expert: Dict[str, List[str]] = field(default_factory=dict)  # For audit
    topic_hotspots_found: int = 0  # Count of topic hotspots detected


class DocumentNavigator:
    """
    Optimized Scan Pass agent that creates a navigation map for targeted extraction.

    Enhanced analysis including:
    1. Table of Contents - section-to-page mapping
    2. Index - keyword-to-page mapping
    3. Appendices - supplementary material locations
    4. Headers/Footers - running headers reveal section context
    5. Topic Hotspots - keyword-dense regions in body text
    6. Expert Keyword Consultation - each expert suggests their best keywords
    7. Automatic Window Context - always include window before + after targets

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
        'same', 'than', 'too', 'very', 'just', 'can', 'will', 'should',
        'document', 'documents', 'section', 'page', 'pages', 'provide',
        'provided', 'include', 'includes', 'including', 'describe', 'described'
    }

    # Expert persona keyword templates - suggest relevant keywords based on expert type
    EXPERT_KEYWORD_TEMPLATES = {
        'bond': ['bond', 'bonding', 'surety', 'performance bond', 'payment bond', 'bid bond',
                 'maintenance bond', 'bonding requirements', 'bonded', 'bondsman'],
        'insurance': ['insurance', 'liability', 'coverage', 'indemnification', 'indemnity',
                     'certificate', 'policy', 'insured', 'claims', 'risk'],
        'warranty': ['warranty', 'guarantee', 'warrantee', 'warranty period', 'defect',
                    'defective', 'repair', 'replacement', 'one year', 'two year', 'workmanship'],
        'payment': ['payment', 'pay', 'invoice', 'billing', 'retainage', 'retention',
                   'progress payment', 'final payment', 'payment schedule', 'net 30'],
        'timeline': ['schedule', 'timeline', 'deadline', 'completion', 'duration', 'days',
                    'calendar days', 'working days', 'substantial completion', 'final completion'],
        'liquidated': ['liquidated damages', 'damages', 'penalty', 'penalties', 'per day',
                      'per diem', 'delay', 'delayed', 'extension', 'time extension'],
        'submittal': ['submittal', 'submittals', 'shop drawing', 'sample', 'mockup',
                     'product data', 'manufacturer', 'approval', 'rfi', 'request'],
        'testing': ['testing', 'test', 'inspection', 'quality', 'qc', 'qa', 'cctv',
                   'deflection', 'air test', 'mandrel', 'certification', 'certified'],
        'safety': ['safety', 'osha', 'ppe', 'hazard', 'hazardous', 'msds', 'sds',
                  'confined space', 'permit', 'training', 'competent person'],
        'material': ['material', 'materials', 'cipp', 'liner', 'resin', 'felt', 'fiberglass',
                    'thickness', 'diameter', 'length', 'astm', 'specification'],
        'installation': ['installation', 'install', 'installer', 'procedure', 'method',
                        'workmanship', 'cure', 'curing', 'inversion', 'pull-in'],
        'scope': ['scope', 'work', 'linear feet', 'lf', 'footage', 'quantity', 'quantities',
                 'unit price', 'bid item', 'pay item', 'measurement'],
        'qualification': ['qualification', 'qualifications', 'experience', 'similar project',
                         'reference', 'references', 'resume', 'certified', 'licensed'],
        'general': ['general', 'general requirements', 'conditions', 'supplementary',
                   'special provisions', 'specifications', 'technical specifications']
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

        Enhanced process:
        1. Consult each expert for their recommended keywords
        2. Analyze document structure with all keywords
        3. Identify topic hotspots for each expert's domain
        4. Create assignments with automatic window context

        Args:
            pages: All document pages
            questions: Questions to answer (filtered by user selection)
            experts: Expert personas by section_id
            progress_callback: Optional callback for progress updates

        Returns:
            NavigationMap with expert assignments including window context
        """
        logger.info("\n" + "="*64)
        logger.info("OPTIMIZED SCAN PASS: Document Navigation Analysis")
        logger.info("="*64)

        if progress_callback:
            progress_callback('prescan_start', {
                'total_pages': len(pages),
                'total_questions': len(questions),
                'total_experts': len(experts)
            })

        # Step 1: Get expert-recommended keywords for each section
        expert_keywords = self._get_expert_recommended_keywords(questions, experts)

        # Step 2: Collect ALL keywords for hotspot detection
        all_keywords = []
        for keywords in expert_keywords.values():
            all_keywords.extend(keywords)
        all_keywords = list(set(all_keywords))

        # Step 3: Analyze document structure with keywords for hotspot detection
        pages_data = [{'page_num': p.page_num, 'text': p.text} for p in pages]
        structure = self.structure_analyzer.analyze(pages_data, target_keywords=all_keywords)

        logger.info(f"  Structure Analysis:")
        logger.info(f"    TOC: {structure.has_toc} ({len(structure.toc_entries)} entries)")
        logger.info(f"    Index: {structure.has_index} ({len(structure.index_entries)} terms)")
        logger.info(f"    Appendix: {structure.has_appendix} ({len(structure.appendix_pages)} pages)")
        logger.info(f"    Section Headers: {len(structure.section_headers)}")
        logger.info(f"    Running Headers: {len(structure.running_headers)}")
        logger.info(f"    Spec Divisions: {len(structure.spec_divisions)}")
        logger.info(f"    Topic Hotspots: {len(structure.topic_hotspots)}")

        # Step 4: Create assignments for each expert with window context
        expert_assignments = {}
        unassigned_questions = []
        total_pages = len(pages)

        for section_id, expert in experts.items():
            # Get questions for this expert
            expert_questions = [q for q in questions if q.section_id == section_id]
            if not expert_questions:
                continue

            keywords = expert_keywords.get(section_id, [])
            expert_rec_keywords = self._get_expert_specific_keywords(expert)

            # Find pages for this expert using ALL structure elements
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
                    for offset in range(1, 3):
                        if page_num + offset <= total_pages:
                            primary_pages.add(page_num + offset)
                    keywords_found.append(f"Header: {header[:30]}")

            # Check running headers (NEW)
            for page_num, header in structure.running_headers.items():
                if self._matches_keywords(header, keywords):
                    primary_pages.add(page_num)
                    keywords_found.append(f"RunningHdr: {header[:25]}")

            # Check spec divisions (NEW)
            for div_name, start_page in structure.spec_divisions.items():
                if self._matches_keywords(div_name, keywords):
                    primary_pages.add(start_page)
                    for offset in range(1, 5):
                        if start_page + offset <= total_pages:
                            primary_pages.add(start_page + offset)
                    keywords_found.append(f"Division: {div_name[:25]}")

            # Check topic hotspots (NEW)
            for page_num, hotspot in structure.topic_hotspots.items():
                if any(kw in keywords for kw in hotspot.topic_keywords):
                    primary_pages.add(page_num)
                    keywords_found.append(f"Hotspot p{page_num}: {', '.join(hotspot.topic_keywords[:3])}")

            # Check appendix sections
            for appendix_name, start_page in structure.appendix_sections.items():
                if self._matches_keywords(appendix_name, keywords):
                    primary_pages.add(start_page)
                    for offset in range(1, 5):
                        if start_page + offset <= total_pages:
                            primary_pages.add(start_page + offset)
                    keywords_found.append(f"Appendix: {appendix_name[:30]}")

            # ENHANCED: Calculate context pages - ALWAYS include window before + after
            # This is critical: experts should ALWAYS examine surrounding context
            context_pages = set()
            for page in primary_pages:
                # Window BEFORE (always check up to 3 pages before)
                for offset in range(1, 4):
                    if page - offset >= 1:
                        context_pages.add(page - offset)
                # Window AFTER (always check up to 3 pages after)
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
                    keywords_found=keywords_found[:15],  # Keep more for audit
                    expert_recommended_keywords=expert_rec_keywords[:10],
                    confidence=min(0.95, 0.5 + (len(keywords_found) * 0.08))
                )
                expert_assignments[expert.name] = assignment
                logger.info(f"  {expert.name}:")
                logger.info(f"    Primary: {len(primary_pages)} pages | Context: {len(context_pages)} pages")
                logger.info(f"    Expert keywords: {', '.join(expert_rec_keywords[:5])}")
                logger.info(f"    Matches: {', '.join(keywords_found[:4])}")
            else:
                # No structural hints - these questions go to full exhaustive
                for q in expert_questions:
                    unassigned_questions.append(q.id)
                logger.info(f"  {expert.name}: No structural matches (will use exhaustive scan)")

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
            estimated_reduction=max(0, estimated_reduction),
            all_keywords_by_expert=expert_keywords,
            topic_hotspots_found=len(structure.topic_hotspots)
        )

        if progress_callback:
            progress_callback('prescan_complete', {
                'has_toc': structure.has_toc,
                'has_index': structure.has_index,
                'has_appendix': structure.has_appendix,
                'toc_entries': len(structure.toc_entries),
                'index_terms': len(structure.index_entries),
                'running_headers': len(structure.running_headers),
                'spec_divisions': len(structure.spec_divisions),
                'topic_hotspots': len(structure.topic_hotspots),
                'expert_assignments': [
                    {
                        'expert': a.expert_name,
                        'section_id': a.section_id,
                        'primary_pages': a.primary_pages,
                        'context_pages': a.context_pages,
                        'total_pages': len(a.primary_pages) + len(a.context_pages),
                        'keywords_matched': a.keywords_found,
                        'expert_keywords': a.expert_recommended_keywords,
                        'all_keywords_searched': expert_keywords.get(a.section_id, [])
                    }
                    for a in expert_assignments.values()
                ],
                'unassigned_questions': unassigned_questions,
                'all_keywords_by_section': {
                    section_id: keywords
                    for section_id, keywords in expert_keywords.items()
                },
                'estimated_reduction': f"{estimated_reduction*100:.0f}%"
            })

        logger.info(f"\nOptimized Scan Pass Complete:")
        logger.info(f"  Experts with assignments: {len(expert_assignments)}/{len(experts)}")
        logger.info(f"  Total pages to analyze: {total_to_scan} (primary + context)")
        logger.info(f"  Topic hotspots detected: {len(structure.topic_hotspots)}")
        logger.info(f"  Estimated reduction: {estimated_reduction*100:.0f}%")
        logger.info(f"  Unassigned questions (full exhaustive): {len(unassigned_questions)}")

        return nav_map

    def _get_expert_recommended_keywords(
        self,
        questions: List[Question],
        experts: Dict[str, ExpertPersona]
    ) -> Dict[str, List[str]]:
        """
        Get comprehensive keywords for each expert, including:
        1. Keywords from the expert's name and specialization
        2. Keywords recommended based on expert type (from templates)
        3. Keywords extracted from the expert's questions
        4. Domain-specific technical terms
        """
        expert_keywords = {}

        for section_id, expert in experts.items():
            keywords = set()

            # 1. Add keywords from expert name/specialization
            expert_words = re.findall(r'\b[a-zA-Z]+\b', expert.name.lower())
            keywords.update(w for w in expert_words if w not in self.STOP_WORDS and len(w) > 2)

            # 2. Get expert-recommended keywords based on expert type
            expert_rec = self._get_expert_specific_keywords(expert)
            keywords.update(expert_rec)

            # 3. Add keywords from expert's system prompt if available
            if hasattr(expert, 'system_prompt') and expert.system_prompt:
                prompt_words = re.findall(r'\b[a-zA-Z]+\b', expert.system_prompt.lower())
                keywords.update(w for w in prompt_words if w not in self.STOP_WORDS and len(w) > 4)

            # 4. Add keywords from questions assigned to this expert
            section_questions = [q for q in questions if q.section_id == section_id]
            for q in section_questions:
                q_words = re.findall(r'\b[a-zA-Z]+\b', q.text.lower())
                keywords.update(w for w in q_words if w not in self.STOP_WORDS and len(w) > 3)

            # 5. Prioritize domain-specific terms
            domain_terms = self._extract_domain_terms(section_questions)
            keywords.update(domain_terms)

            # Store up to 35 keywords (increased from 25)
            expert_keywords[section_id] = list(keywords)[:35]

        return expert_keywords

    def _get_expert_specific_keywords(self, expert: ExpertPersona) -> List[str]:
        """
        Get the 10 best keywords an expert would suggest for their domain.
        This simulates asking the expert: "What keywords should I search for?"
        """
        expert_name_lower = expert.name.lower()
        recommended = []

        # Match expert name to keyword templates
        for template_key, keywords in self.EXPERT_KEYWORD_TEMPLATES.items():
            if template_key in expert_name_lower:
                recommended.extend(keywords)

        # If expert has a system prompt, extract key nouns
        if hasattr(expert, 'system_prompt') and expert.system_prompt:
            # Look for capitalized terms or quoted terms in prompt
            prompt = expert.system_prompt
            capitalized = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', prompt)
            recommended.extend([term.lower() for term in capitalized if len(term) > 3])

            # Look for terms in quotes
            quoted = re.findall(r'"([^"]+)"', prompt)
            recommended.extend([term.lower() for term in quoted if len(term) > 3])

        # Return unique keywords, up to 10
        return list(dict.fromkeys(recommended))[:10]

    def _extract_domain_terms(self, questions: List[Question]) -> Set[str]:
        """Extract domain-specific technical terms from questions."""
        domain_terms = set()

        # Comprehensive bid/spec domain patterns for CIPP and municipal projects
        domain_patterns = [
            # Pipe materials and methods
            r'\b(cipp|hdpe|pvc|frp|grp|fiberglass|polyester|vinyl|ester)\b',
            r'\b(pipe|liner|lining|rehabilitation|trenchless|relining)\b',
            r'\b(manhole|lateral|mainline|sewer|storm|sanitary|culvert)\b',
            # Specifications and standards
            r'\b(astm|awwa|nassco|asce|ansi|iso)\b',
            r'\b(specification|standard|requirement|compliance|certification)\b',
            r'\b(pacp|lacp|macp|itpipes)\b',
            # Bonding and insurance
            r'\b(warranty|bond|insurance|surety|indemnity|liability)\b',
            r'\b(performance|payment|bid|maintenance)\b',
            # Construction terms
            r'\b(cure|curing|installation|testing|inspection|bypass)\b',
            r'\b(excavation|restoration|traffic|control|mobilization)\b',
            # Measurements and specifications
            r'\b(diameter|thickness|length|footage|lf|sf|cy)\b',
            r'\b(psi|mil|inch|foot|gallon|hour|day)\b',
            # Financial and timeline
            r'\b(payment|retention|retainage|schedule|timeline|deadline)\b',
            r'\b(liquidated|damages|penalty|penalties|extension)\b',
            r'\b(progress|final|partial|invoice|billing)\b',
            # Submittal and documentation
            r'\b(submittal|rfi|shop|drawing|sample|mockup)\b',
            r'\b(certification|license|qualification|experience)\b',
            # Quality and testing
            r'\b(quality|control|assurance|test|inspection|cctv)\b',
            r'\b(deflection|ovality|wrinkle|delamination|infiltration)\b',
            # Safety and environment
            r'\b(safety|osha|confined|space|permit|environmental)\b',
            r'\b(hazardous|waste|disposal|erosion|sediment)\b',
            # Equipment and materials
            r'\b(inversion|pull|ambient|steam|uv|ultraviolet)\b',
            r'\b(resin|felt|tube|bladder|calibration|hose)\b',
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

        IMPORTANT: Context is ALWAYS recommended. When include_context=True,
        the expert will analyze window before + after each target page.

        Args:
            nav_map: The navigation map
            expert_name: Name of the expert
            include_context: Whether to include context pages (default True, recommended)

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
