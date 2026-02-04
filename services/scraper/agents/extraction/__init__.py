"""
Extraction agents for CityScraper Phase 3.

These agents extract specific data points from web sources
discovered during the pre-flight phase.

EX-1 through EX-5: Use LLM (OpenAI) for parsing and extraction
EX-6: Document Downloader - Mechanical downloader, no LLM required
"""

from .infrastructure_extractor import InfrastructureExtractorAgent
from .equipment_extractor import EquipmentExtractorAgent
from .maintenance_extractor import MaintenanceExtractorAgent
from .incident_extractor import IncidentExtractorAgent
from .bid_extractor import BidExtractorAgent
from .document_downloader import DocumentDownloaderAgent

__all__ = [
    'InfrastructureExtractorAgent',
    'EquipmentExtractorAgent',
    'MaintenanceExtractorAgent',
    'IncidentExtractorAgent',
    'BidExtractorAgent',
    'DocumentDownloaderAgent'
]
