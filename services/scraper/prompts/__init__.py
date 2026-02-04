"""
Scraper agent prompts.

Each prompt module contains:
- SYSTEM_PROMPT: The detailed expert prompt
- get_prompt(): Function to get prompt with substitutions
- PROMPT DEVELOPMENT HISTORY: Documentation of critique cycles
"""

# Pre-flight prompts
from .pf1_municipality_normalizer import get_prompt as get_pf1_prompt
from .pf2_jurisdiction_mapper import get_prompt as get_pf2_prompt
from .pf3_source_discovery import get_prompt as get_pf3_prompt
from .pf4_terminology_extractor import get_prompt as get_pf4_prompt
from .pf5_readiness_validator import get_prompt as get_pf5_prompt

__all__ = ['get_pf1_prompt', 'get_pf2_prompt', 'get_pf3_prompt', 'get_pf4_prompt', 'get_pf5_prompt']
