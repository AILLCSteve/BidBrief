# BestPrep/TestPrep Mode

## Overview

BestPrep mode is designed for exhaustive textbook analysis where **every piece of information matters**. Unlike Bid/Spec mode which intelligently deduplicates similar answers, BestPrep mode:

1. **Never discards** any answer fragment
2. **Preserves every footnote** with full provenance
3. **Runs synthesis** at the end to combine all fragments into coherent answers

## When to Use

- Analyzing textbooks for exam preparation
- Questions that may have answers spread across 10+ pages
- When citation completeness is critical
- When you need to see all perspectives/fragments, not just the "best" one

## Mode Comparison

| Feature | Bid/Spec Mode | BestPrep Mode |
|---------|---------------|---------------|
| Deduplication | Smart merge similar answers | Never discard |
| Fragments | Best answer wins | All fragments preserved |
| Footnotes | Aggregated | Individual tracking |
| Synthesis | No | Yes (Layer 7) |
| Best for | Construction specs, RFPs | Textbooks, study materials |

## Architecture

```
Standard Layers 0-6
        |
        v
MODE SELECTION
        |
   +---------+---------+
   |                   |
   v                   v
SmartAccumulator   AppendOnlyAccumulator
(Bid/Spec)         (BestPrep)
   |                   |
   v                   v
EXPORT              Layer 7: Synthesis Agent
                       |
                       v
                  FINAL ANSWERS
                       |
                       v
                  BestPrep Excel
```

### Layer 7: Synthesis Agent

The Synthesis Agent runs after all windows are processed. It:

1. Reviews ALL fragments for each question
2. Combines information from all sources
3. Preserves all page citations
4. Notes contradictions where found
5. Produces one comprehensive final answer

## Export Format

BestPrep exports include 5 sheets:

1. **Summary** - Statistics and overview
   - Total questions, fragments, footnotes
   - Windows processed
   - Average fragments per question

2. **Synthesized Answers** - Final comprehensive answers
   - Question text
   - Synthesized answer (or concatenated fragments)
   - Source pages
   - Fragment count

3. **All Fragments** - Every fragment found, with provenance
   - Fragment ID
   - Question ID
   - Window index
   - Pages cited
   - Confidence level
   - Expert name
   - Full fragment text

4. **All Footnotes** - Every citation with quotes
   - Footnote ID
   - Question ID
   - Page number
   - Quoted text
   - Source fragment ID

5. **Page Index** - Which questions reference each page
   - Page number
   - Questions referencing this page
   - Reference count

## API Usage

### Starting a BestPrep Analysis

```javascript
fetch('/api/analyze', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        session_id: 'xxx',
        pdf_path: '/path/to/textbook.pdf',
        mode: 'bestprep'  // <-- Set mode here
    })
});
```

### Exporting BestPrep Results

```javascript
// For BestPrep mode, use the dedicated export endpoint
window.open(`/api/export/bestprep-excel/${sessionId}`, '_blank');

// For Bid/Spec mode, use standard export
window.open(`/api/export/excel-dashboard/${sessionId}`, '_blank');
```

## Data Structures

### AnswerFragment

Each piece of information found about a question:

```python
@dataclass
class AnswerFragment:
    fragment_id: str        # Unique identifier (FRAG-00001)
    text: str               # The answer text with citations
    pages: List[int]        # PDF pages referenced
    confidence: float       # 0.0-1.0
    window_index: int       # Which window this came from
    expert_name: str        # Which AI expert found this
    timestamp: str          # When found (ISO format)
    raw_footnote: str       # Any explicit footnote
```

### CumulativeAnswer

Accumulates all fragments for a question:

```python
@dataclass
class CumulativeAnswer:
    question_id: str
    question_text: str
    fragments: List[AnswerFragment]
    footnotes: List[Footnote]
    synthesized_answer: Optional[str]
    synthesis_timestamp: Optional[str]

    @property
    def all_pages(self) -> List[int]:
        """All unique pages across all fragments, sorted."""

    @property
    def highest_confidence(self) -> float:
        """Maximum confidence across all fragments."""
```

## Configuration

Mode configuration is defined in `services/hotdog/mode_config.py`:

```python
@classmethod
def bestprep_default(cls) -> 'ModeConfig':
    return cls(
        mode=AnalysisMode.BESTPREP,
        deduplicate=False,              # Never merge
        similarity_threshold=0.0,       # Not used
        preserve_all_fragments=True,    # Keep everything
        individual_footnote_tracking=True,
        max_footnotes_per_answer=0,     # Unlimited
        enable_synthesis=True,          # Run Layer 7
        synthesis_per_section=True,
        export_format='bestprep'
    )
```

## Files

Key files for BestPrep mode:

- `services/hotdog/mode_config.py` - Mode configuration and defaults
- `services/hotdog/append_accumulator.py` - Never-discard accumulator
- `services/hotdog/synthesis_agent.py` - Layer 7 synthesis
- `services/bestprep_excel.py` - 5-sheet Excel export
- `tests/test_bestprep_mode.py` - Integration tests
