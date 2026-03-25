"""
Data models for Smart Analysis results.

v2 changes:
  - SmartAnalysisItem gains optional follow_up_direction field
  - SmartAnalysisResult gains optional evidence_classification field
  Both are backward-compatible (default_factory=dict/list).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SmartAnalysisItem:
    """A single finding: risk, opportunity, ambiguity, or contradiction."""
    title: str
    description: str
    severity: str       # 'critical' | 'high' | 'medium' | 'low' | 'info'
    evidence: List[str] = field(default_factory=list)
    page_refs: List[int] = field(default_factory=list)
    # v2: optional follow-up direction per finding
    follow_up_direction: Dict[str, str] = field(default_factory=dict)


@dataclass
class ProfessionalAssessment:
    """A professional evaluation in a specific category."""
    category: str       # e.g. 'Risk Level', 'Profitability Outlook'
    rating: str         # e.g. 'High', 'Moderate', 'Favorable'
    rationale: str
    confidence: str     # 'high' | 'medium' | 'low'


@dataclass
class SmartAnalysisResult:
    """Complete output of a Smart Analysis run."""
    session_id: str
    document_name: str
    document_type: str
    document_type_label: str
    analysis_completeness: str          # 'full' | 'partial'
    generated_at: str                   # ISO timestamp

    executive_summary: str
    key_insights: List[str]

    risks: List[SmartAnalysisItem]
    opportunities: List[SmartAnalysisItem]
    ambiguities: List[SmartAnalysisItem]
    contradictions: List[SmartAnalysisItem]

    assessments: List[ProfessionalAssessment]

    follow_up_questions: List[str]
    strategic_recommendations: List[str]

    user_question_responses: List[Dict[str, Any]]
    # Each element: {question, response, confidence, evidence_summary, follow_up_direction}

    # v2: evidence classification from synthesis (how language tiers were applied)
    evidence_classification: Dict[str, Any] = field(default_factory=dict)

    # v3: holistic document understanding (overview, workstreams, constraints, obligations)
    document_understanding: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        def _item_dict(item: SmartAnalysisItem) -> dict:
            d = vars(item).copy()
            return d

        return {
            'session_id': self.session_id,
            'document_name': self.document_name,
            'document_type': self.document_type,
            'document_type_label': self.document_type_label,
            'analysis_completeness': self.analysis_completeness,
            'generated_at': self.generated_at,
            'executive_summary': self.executive_summary,
            'key_insights': self.key_insights,
            'risks': [_item_dict(r) for r in self.risks],
            'opportunities': [_item_dict(o) for o in self.opportunities],
            'ambiguities': [_item_dict(a) for a in self.ambiguities],
            'contradictions': [_item_dict(c) for c in self.contradictions],
            'assessments': [vars(a) for a in self.assessments],
            'follow_up_questions': self.follow_up_questions,
            'strategic_recommendations': self.strategic_recommendations,
            'user_question_responses': self.user_question_responses,
            'evidence_classification': self.evidence_classification,
            'document_understanding': self.document_understanding,
        }
