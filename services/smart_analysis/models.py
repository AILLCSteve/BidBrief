"""
Data models for Smart Analysis results.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class SmartAnalysisItem:
    """A single finding: risk, opportunity, ambiguity, or contradiction."""
    title: str
    description: str
    severity: str       # 'critical' | 'high' | 'medium' | 'low' | 'info'
    evidence: List[str] = field(default_factory=list)
    page_refs: List[int] = field(default_factory=list)


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

    user_question_responses: List[Dict[str, Any]]   # [{question, response, confidence, evidence_summary}]

    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'document_name': self.document_name,
            'document_type': self.document_type,
            'document_type_label': self.document_type_label,
            'analysis_completeness': self.analysis_completeness,
            'generated_at': self.generated_at,
            'executive_summary': self.executive_summary,
            'key_insights': self.key_insights,
            'risks': [vars(r) for r in self.risks],
            'opportunities': [vars(o) for o in self.opportunities],
            'ambiguities': [vars(a) for a in self.ambiguities],
            'contradictions': [vars(c) for c in self.contradictions],
            'assessments': [vars(a) for a in self.assessments],
            'follow_up_questions': self.follow_up_questions,
            'strategic_recommendations': self.strategic_recommendations,
            'user_question_responses': self.user_question_responses,
        }
