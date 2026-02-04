"""
Extraction agents for CityScraper Phase 3.

These agents extract specific data points from web sources
discovered during the pre-flight phase.
"""

from .infrastructure_extractor import InfrastructureExtractorAgent

__all__ = ['InfrastructureExtractorAgent']
