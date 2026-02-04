"""
Analysis Layer agents for CityScraper.

These agents provide deep analysis capabilities on scraped municipal data,
based on commsdev functionality for generating stakeholder-specific insights.

AN-1: Summary Generator - Generates 4-perspective summaries from scraped data
      (municipal owner, citizen, contractor, competitor views)

AN-2: Brainstormer - Generates 10 creative opportunities using 5 approaches
      (direct_need, gap_exploitation, timing_play, relationship_build, lateral_thinking)

Future agents:
AN-3: Deep Researcher - Performs exhaustive tangential research
AN-4: Bid Analyzer - Detailed bid/contract analysis
"""

from .summary_generator import SummaryGeneratorAgent
from .brainstormer import BrainstormerAgent

__all__ = [
    'SummaryGeneratorAgent',
    'BrainstormerAgent',
]
