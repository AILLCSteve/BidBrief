"""
Analysis mode configuration for BidBrief dual-mode system.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class AnalysisMode(Enum):
    """Available analysis modes."""
    BID_SPEC = "bid_spec"      # Original mode: deduplication, merge similar
    BESTPREP = "bestprep"      # New mode: append-only, never discard


@dataclass
class ModeConfig:
    """Configuration parameters for each analysis mode."""
    mode: AnalysisMode

    # Accumulation behavior
    deduplicate: bool                  # Whether to merge similar answers
    similarity_threshold: float        # Jaccard threshold (only if deduplicate=True)
    preserve_all_fragments: bool       # Keep every answer fragment found

    # Footnote handling
    individual_footnote_tracking: bool # Track each footnote separately
    max_footnotes_per_answer: int      # 0 = unlimited

    # Synthesis layer
    enable_synthesis: bool             # Run Layer 7 synthesis agent
    synthesis_per_section: bool        # One synthesis per section vs global

    # Export format
    export_format: str                 # 'bid_spec' or 'bestprep'

    @classmethod
    def bid_spec_default(cls) -> 'ModeConfig':
        """Default config for Bid/Spec mode (existing behavior)."""
        return cls(
            mode=AnalysisMode.BID_SPEC,
            deduplicate=True,
            similarity_threshold=0.75,
            preserve_all_fragments=False,
            individual_footnote_tracking=False,
            max_footnotes_per_answer=0,
            enable_synthesis=False,
            synthesis_per_section=False,
            export_format='bid_spec'
        )

    @classmethod
    def bestprep_default(cls) -> 'ModeConfig':
        """Default config for BestPrep mode (new exhaustive behavior)."""
        return cls(
            mode=AnalysisMode.BESTPREP,
            deduplicate=False,
            similarity_threshold=0.0,  # Not used
            preserve_all_fragments=True,
            individual_footnote_tracking=True,
            max_footnotes_per_answer=0,  # Unlimited
            enable_synthesis=True,
            synthesis_per_section=True,
            export_format='bestprep'
        )


def get_mode_config(mode_name: str) -> ModeConfig:
    """Get mode configuration by name."""
    if mode_name == 'bestprep':
        return ModeConfig.bestprep_default()
    return ModeConfig.bid_spec_default()
