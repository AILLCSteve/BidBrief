"""
Scraper agent prompts.

Each prompt module contains:
- SYSTEM_PROMPT: The detailed expert prompt
- get_prompt(): Function to get prompt with substitutions
- PROMPT DEVELOPMENT HISTORY: Documentation of critique cycles
"""

# Pre-flight prompts
from .pf1_municipality_normalizer import get_prompt as get_pf1_prompt

__all__ = ['get_pf1_prompt']
