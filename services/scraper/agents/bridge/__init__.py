"""
Bridge Layer agents for CityScraper.

These agents form the bridge between HOTDOG AI document analysis
and the CityScraper municipal research pipeline.

BR-1: Municipality Detector - Detects municipality from document content
BR-2: Gap Analyzer - Identifies data gaps that scraper can fill
BR-3: Data Merger - Merges scraper results with HOTDOG output
BR-4: Scraper Dispatcher - Triggers appropriate scraper workflows (MECHANICAL)
"""

from .municipality_detector import MunicipalityDetectorAgent
from .gap_analyzer import GapAnalyzerAgent
from .data_merger import DataMergerAgent
from .scraper_dispatcher import ScraperDispatcherAgent

__all__ = [
    'MunicipalityDetectorAgent',
    'GapAnalyzerAgent',
    'DataMergerAgent',
    'ScraperDispatcherAgent',
]
