"""
Brainstormer Agent (AN-2)

Generates 10 creative opportunities from scraped municipal data using 5 different
creative approaches. Based on commsdev Task 3 functionality.

Part of the Analysis Layer for CityScraper.

Creative Approaches:
1. direct_need - Address explicit needs shown in data
2. gap_exploitation - Exploit capability gaps
3. timing_play - Leverage time-sensitive factors
4. relationship_build - Build long-term positioning
5. lateral_thinking - Creative/unusual angles

Each opportunity includes:
- title: Compelling opportunity name
- approach: One of 5 approaches
- description: 2-3 sentence explanation
- data_backing: Specific data points supporting the opportunity
- plausibility: HIGH/MEDIUM/LOW based on data strength
- estimated_value: Rough value estimate
- next_steps: 2-3 actionable next steps
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse
)
from services.scraper.prompts.an2_brainstormer import get_prompt

logger = logging.getLogger(__name__)


class BrainstormerAgent(BaseAgent):
    """
    AN-2: Brainstormer Agent

    Generates creative opportunities from CityScraper extraction results,
    using 5 distinct approaches to ensure diverse and actionable ideas.

    This agent transforms raw municipal data into 10 business opportunities
    grounded in specific data points with realistic plausibility ratings.
    """

    AGENT_ID = "an-2"
    AGENT_NAME = "Brainstormer"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-04"

    # Valid confidence and plausibility levels
    VALID_CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")
    VALID_PLAUSIBILITY_LEVELS = ("HIGH", "MEDIUM", "LOW")

    # Required creative approaches
    REQUIRED_APPROACHES = (
        "direct_need",
        "gap_exploitation",
        "timing_play",
        "relationship_build",
        "lateral_thinking"
    )

    # Required fields in each opportunity
    OPPORTUNITY_REQUIRED_FIELDS = (
        "title",
        "approach",
        "description",
        "data_backing",
        "plausibility",
        "estimated_value",
        "next_steps"
    )

    # Expected number of opportunities
    EXPECTED_OPPORTUNITY_COUNT = 10
    MIN_OPPORTUNITY_COUNT = 8  # Allow some flexibility

    # Maximum length for extraction data sent to LLM
    MAX_EXTRACTION_DATA_LENGTH = 8000

    # Minimum items expected in list fields
    MIN_DATA_BACKING_ITEMS = 2
    MIN_NEXT_STEPS_ITEMS = 2

    # Display labels for approaches (UI-friendly names)
    APPROACH_LABELS = {
        "direct_need": "Direct Need",
        "gap_exploitation": "Gap Exploitation",
        "timing_play": "Timing Play",
        "relationship_build": "Relationship Building",
        "lateral_thinking": "Lateral Thinking"
    }

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt(
            "{{municipality}}",
            "{{opportunity_focus}}"
        )

    def _extract_json_from_response(self, content: str) -> str:
        """
        Safely extract JSON from LLM response with validation.

        Tries multiple extraction strategies:
        1. Markdown JSON block (```json ... ```)
        2. Generic markdown block (``` ... ```)
        3. Raw JSON (first { to last })

        Args:
            content: Raw LLM response content

        Returns:
            Extracted JSON string

        Raises:
            ValueError: If no valid JSON found in response
        """
        candidates = []

        # Try markdown JSON block
        if '```json' in content:
            parts = content.split('```json', 1)
            if len(parts) > 1:
                end_parts = parts[1].split('```', 1)
                if len(end_parts) > 0:
                    candidates.append(end_parts[0].strip())

        # Try generic markdown block
        if '```' in content:
            parts = content.split('```', 2)
            if len(parts) >= 3:
                candidates.append(parts[1].strip())

        # Try raw JSON (find first { and last })
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end > start:
            candidates.append(content[start:end+1])

        # Validate each candidate
        for candidate in candidates:
            try:
                json.loads(candidate)  # Validate it parses
                return candidate
            except json.JSONDecodeError:
                continue

        raise ValueError(f"No valid JSON found in response: {content[:200]}...")

    def _format_extraction_data(self, extraction_result: Dict[str, Any]) -> str:
        """
        Format extraction results for the user message.

        Args:
            extraction_result: CityScraper extraction results

        Returns:
            Formatted string for prompt
        """
        # Type validation - ensure extraction_result is dict
        if not isinstance(extraction_result, dict):
            return "Invalid extraction data type."

        if not extraction_result:
            return "No extraction data provided."

        parts = []

        # Include municipality info
        municipality = extraction_result.get('municipality', {})
        if municipality:
            if isinstance(municipality, dict):
                city = municipality.get('city', 'Unknown')
                state = municipality.get('state', 'Unknown')
                parts.append(f"Municipality: {city}, {state}")
            elif isinstance(municipality, str):
                parts.append(f"Municipality: {municipality}")

        # Include extracted data fields
        extracted_data = extraction_result.get('extracted_data', {})
        if extracted_data:
            parts.append(f"\n## Extracted Data ({len(extracted_data)} fields):\n")
            for field_name, field_data in list(extracted_data.items())[:25]:
                if isinstance(field_data, dict):
                    value = field_data.get('value', 'NOT FOUND')
                    source = field_data.get('source_url', '')
                    confidence = field_data.get('confidence', 'UNKNOWN')
                    parts.append(f"### {field_name}:")
                    parts.append(f"  Value: {str(value)[:500]}")
                    if source:
                        parts.append(f"  Source: {source}")
                    parts.append(f"  Confidence: {confidence}")
                    parts.append("")
                else:
                    parts.append(f"### {field_name}: {str(field_data)[:500]}")
                    parts.append("")

            if len(extracted_data) > 25:
                parts.append(f"\n... and {len(extracted_data) - 25} more fields")

        # Include systems info rows if present
        systems_info = extraction_result.get('systems_info_rows', [])
        if systems_info:
            parts.append(f"\n## Systems Information ({len(systems_info)} records):\n")
            for i, row in enumerate(systems_info[:5], 1):
                if isinstance(row, dict):
                    parts.append(f"### Record {i}:")
                    for key, val in row.items():
                        if key not in ('source_urls', 'verbatim_citations'):
                            if isinstance(val, dict):
                                parts.append(f"  {key}: {val.get('value', str(val)[:200])}")
                            else:
                                parts.append(f"  {key}: {str(val)[:200]}")
                    parts.append("")

        # Include public bids if present
        public_bids = extraction_result.get('public_bid_rows', [])
        if public_bids:
            parts.append(f"\n## Public Bids ({len(public_bids)} bids):\n")
            for i, bid in enumerate(public_bids[:5], 1):
                if isinstance(bid, dict):
                    parts.append(f"### Bid {i}:")
                    title = bid.get('bid_contract_title', 'Unknown')
                    parts.append(f"  Title: {title}")
                    status = bid.get('status', 'Unknown')
                    parts.append(f"  Status: {status}")
                    scope = bid.get('scope', {})
                    if isinstance(scope, dict):
                        parts.append(f"  Scope: {scope.get('value', str(scope)[:300])}")
                    timeline = bid.get('timeline_requirements', {})
                    if isinstance(timeline, dict):
                        parts.append(f"  Timeline: {timeline.get('value', str(timeline)[:200])}")
                    parts.append("")

        # Include data gaps
        data_gaps = extraction_result.get('data_gaps', [])
        if data_gaps:
            parts.append(f"\n## Data Gaps ({len(data_gaps)} items):")
            for gap in data_gaps[:10]:
                parts.append(f"  - {gap}")
            if len(data_gaps) > 10:
                parts.append(f"  ... and {len(data_gaps) - 10} more")

        # Include conflicts if present
        conflicts = extraction_result.get('conflicts_detected', [])
        if conflicts:
            parts.append(f"\n## Data Conflicts ({len(conflicts)} items):")
            for conflict in conflicts[:5]:
                if isinstance(conflict, dict):
                    parts.append(f"  - {conflict.get('description', str(conflict)[:200])}")
                else:
                    parts.append(f"  - {str(conflict)[:200]}")

        result = "\n".join(parts)

        # Truncate if too long
        if len(result) > self.MAX_EXTRACTION_DATA_LENGTH:
            result = result[:self.MAX_EXTRACTION_DATA_LENGTH] + "\n\n[... data truncated ...]"

        return result if result else "Minimal extraction data available."

    def _get_municipality_name(
        self,
        extraction_result: Dict[str, Any],
        municipality: Optional[Dict[str, Any]]
    ) -> str:
        """
        Extract municipality name from inputs.

        Args:
            extraction_result: Extraction result dict
            municipality: Optional municipality dict

        Returns:
            Municipality name string
        """
        # Try municipality parameter first
        if municipality:
            if isinstance(municipality, dict):
                city = municipality.get('city', '')
                state = municipality.get('state', '')
                if city and state:
                    return f"{city}, {state}"
                if city:
                    return city
            elif isinstance(municipality, str):
                return municipality

        # Try extraction result
        if extraction_result:
            muni = extraction_result.get('municipality', {})
            if isinstance(muni, dict):
                city = muni.get('city', '')
                state = muni.get('state', '')
                if city and state:
                    return f"{city}, {state}"
                if city:
                    return city
            elif isinstance(muni, str):
                return muni

        return "Unknown Municipality"

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process brainstorming request.

        Expected input_data:
        - extraction_result: dict - CityScraper extraction results (from EX-O or PR-3)
        - municipality: dict - Optional municipality info (city, state)
        - opportunity_focus: str - Optional focus (e.g., "maintenance_contracts", "consulting")

        Returns AgentResponse with:
        - opportunities: list of 10 opportunity dicts
        - approaches_used: dict with count per approach
        - data_quality_note: str - Assessment of data impact
        - confidence: str - HIGH/MEDIUM/LOW
        """
        start_time = time.time()
        content = ''  # Initialize before any operation
        json_str = ''  # Initialize before any operation

        # Extract input data
        extraction_result = request.input_data.get('extraction_result', {})
        municipality = request.input_data.get('municipality', {})
        opportunity_focus = request.input_data.get('opportunity_focus', '')

        # Type validation for extraction_result
        if not isinstance(extraction_result, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"extraction_result must be dict, got {type(extraction_result).__name__}"]
            )

        # Type validation for municipality (can be dict or None)
        if municipality is not None and not isinstance(municipality, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"municipality must be dict or None, got {type(municipality).__name__}"]
            )

        # Type validation for opportunity_focus (optional, must be string or None)
        if opportunity_focus is None:
            opportunity_focus = ''
        elif not isinstance(opportunity_focus, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"opportunity_focus must be string or None, got {type(opportunity_focus).__name__}"]
            )

        # Handle empty extraction result
        if not extraction_result:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["No extraction data provided. Cannot brainstorm opportunities without data."],
                processing_time_seconds=time.time() - start_time
            )

        try:
            # Get municipality name for prompt
            municipality_name = self._get_municipality_name(extraction_result, municipality)

            # Emit event for UI activity feed
            self.emit_event(
                "processing",
                f"Brainstorming opportunities for {municipality_name}..."
            )

            # Format extraction data for prompt
            extraction_text = self._format_extraction_data(extraction_result)

            # Get the prompt with inputs substituted
            prompt = get_prompt(
                municipality=municipality_name,
                opportunity_focus=opportunity_focus
            )

            # Build user message
            user_message = f"""Analyze the following municipal data and generate 10 creative opportunities.

**CRITICAL**: Ground every opportunity in specific data from the extraction. Use all 5 approaches.

---

## EXTRACTION DATA

{extraction_text}

---

Generate 10 distinct opportunities using all 5 creative approaches:
1. direct_need - Address explicit needs in the data
2. gap_exploitation - Exploit capability gaps
3. timing_play - Leverage time-sensitive factors
4. relationship_build - Build long-term positioning
5. lateral_thinking - Creative/unusual angles

Each opportunity must include specific data_backing with actual numbers from the data.
Aim for approximately 2 opportunities per approach.

Return the complete JSON output as specified in your instructions."""

            self.emit_event(
                "processing",
                "Generating opportunities using 5 creative approaches..."
            )

            # Call OpenAI
            result = await self.call_openai(
                user_message=user_message,
                system_prompt=prompt
            )

            # Validate result structure from OpenAI
            if not isinstance(result, dict):
                raise ValueError(f"OpenAI returned invalid response type: {type(result).__name__}")
            if 'content' not in result:
                raise ValueError(f"OpenAI response missing 'content' key. Keys: {list(result.keys())}")

            # Parse JSON from response
            content = result.get('content', '')
            json_str = self._extract_json_from_response(content)
            output_data = json.loads(json_str)

            # Validate output
            errors = self.validate_output(output_data)

            if errors:
                logger.warning(f"AN-2 validation failed: {errors}")
                self.emit_event("warning", f"Validation errors: {'; '.join(errors)}")
                return AgentResponse(
                    agent_id=self.AGENT_ID,
                    task=request.task,
                    success=False,
                    output_data={'validation_errors': errors, 'raw_output': output_data},
                    errors=errors,
                    tokens_used=result.get('tokens_used', 0),
                    processing_time_seconds=time.time() - start_time
                )

            elapsed = time.time() - start_time

            # Build completion message
            confidence = output_data.get('confidence', 'UNKNOWN')
            opportunity_count = len(output_data.get('opportunities', []))
            approaches = output_data.get('approaches_used', {})
            approach_summary = ", ".join([f"{k}: {v}" for k, v in approaches.items()])

            completion_msg = (
                f"Brainstorming complete: {opportunity_count} opportunities generated, "
                f"approaches used: {approach_summary}, confidence level {confidence}."
            )

            # Emit completion event
            self.emit_event("completed", completion_msg, is_completed=True)

            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=True,
                output_data=output_data,
                errors=[],
                tokens_used=result.get('tokens_used', 0),
                processing_time_seconds=elapsed
            )

        except json.JSONDecodeError as e:
            # JSONDecodeError is a subclass of ValueError, so catch it first
            logger.error(f"AN-2 JSON parse failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={
                    'parse_error': str(e),
                    'attempted_json': json_str[:500] if json_str else ''
                },
                errors=[f"JSON parse error at position {e.pos}: {e.msg}"],
                processing_time_seconds=time.time() - start_time
            )
        except ValueError as e:
            # JSON extraction failed (from _extract_json_from_response)
            logger.error(f"AN-2 JSON extraction failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={
                    'extraction_error': str(e),
                    'raw_response': content[:1000] if content else ''
                },
                errors=[f"JSON extraction error: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )
        except (TypeError, AttributeError, KeyError) as e:
            # Handle data structure issues
            logger.error(f"AN-2 data structure error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Data structure error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )
        except Exception as e:
            # Log but don't swallow critical exceptions like SystemExit, KeyboardInterrupt
            if isinstance(e, (SystemExit, KeyboardInterrupt)):
                raise
            logger.exception(f"AN-2 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """
        Validate brainstormer output against spec.

        Args:
            output: The output data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required top-level fields
        required_fields = ['opportunities', 'approaches_used', 'data_quality_note', 'confidence']

        for field_name in required_fields:
            if field_name not in output:
                errors.append(f"Missing required field: '{field_name}'")

        # Return early if missing required fields
        if errors:
            return errors

        # Validate opportunities is a list
        opportunities = output.get('opportunities')
        if not isinstance(opportunities, list):
            errors.append("'opportunities' must be a list")
            return errors

        # Validate opportunity count
        if len(opportunities) < self.MIN_OPPORTUNITY_COUNT:
            errors.append(
                f"Expected at least {self.MIN_OPPORTUNITY_COUNT} opportunities, got {len(opportunities)}"
            )

        # Validate each opportunity
        for i, opp in enumerate(opportunities):
            if not isinstance(opp, dict):
                errors.append(f"opportunities[{i}] must be a dict")
                continue

            # Check required fields in each opportunity
            for field in self.OPPORTUNITY_REQUIRED_FIELDS:
                if field not in opp:
                    errors.append(f"opportunities[{i}] missing '{field}'")

            # Validate title is a non-empty string
            title = opp.get('title')
            if not isinstance(title, str) or len(title.strip()) < 5:
                errors.append(f"opportunities[{i}].title must be a non-empty string (min 5 chars)")

            # Validate approach is valid
            approach = opp.get('approach')
            if approach not in self.REQUIRED_APPROACHES:
                errors.append(
                    f"opportunities[{i}].approach must be one of {self.REQUIRED_APPROACHES}, "
                    f"got '{approach}'"
                )

            # Validate description is a meaningful string
            description = opp.get('description')
            if not isinstance(description, str) or len(description.strip()) < 20:
                errors.append(
                    f"opportunities[{i}].description must be a string (min 20 chars)"
                )

            # Validate data_backing is a list with items
            data_backing = opp.get('data_backing')
            if not isinstance(data_backing, list):
                errors.append(f"opportunities[{i}].data_backing must be a list")
            elif len(data_backing) < self.MIN_DATA_BACKING_ITEMS:
                errors.append(
                    f"opportunities[{i}].data_backing should have at least "
                    f"{self.MIN_DATA_BACKING_ITEMS} items, got {len(data_backing)}"
                )
            else:
                for j, item in enumerate(data_backing):
                    if not isinstance(item, str) or len(item.strip()) < 5:
                        errors.append(
                            f"opportunities[{i}].data_backing[{j}] must be a non-empty string"
                        )

            # Validate plausibility
            plausibility = opp.get('plausibility')
            if plausibility not in self.VALID_PLAUSIBILITY_LEVELS:
                errors.append(
                    f"opportunities[{i}].plausibility must be one of "
                    f"{self.VALID_PLAUSIBILITY_LEVELS}, got '{plausibility}'"
                )

            # Validate estimated_value is a string
            estimated_value = opp.get('estimated_value')
            if not isinstance(estimated_value, str) or len(estimated_value.strip()) < 3:
                errors.append(
                    f"opportunities[{i}].estimated_value must be a non-empty string"
                )

            # Validate next_steps is a list with items
            next_steps = opp.get('next_steps')
            if not isinstance(next_steps, list):
                errors.append(f"opportunities[{i}].next_steps must be a list")
            elif len(next_steps) < self.MIN_NEXT_STEPS_ITEMS:
                errors.append(
                    f"opportunities[{i}].next_steps should have at least "
                    f"{self.MIN_NEXT_STEPS_ITEMS} items, got {len(next_steps)}"
                )
            else:
                for j, step in enumerate(next_steps):
                    if not isinstance(step, str) or len(step.strip()) < 10:
                        errors.append(
                            f"opportunities[{i}].next_steps[{j}] must be a meaningful string"
                        )

        # Validate approaches_used is a dict
        approaches_used = output.get('approaches_used')
        if not isinstance(approaches_used, dict):
            errors.append("'approaches_used' must be a dict")
        else:
            # Check all approaches are represented
            for approach in self.REQUIRED_APPROACHES:
                if approach not in approaches_used:
                    errors.append(f"approaches_used missing '{approach}'")
                elif not isinstance(approaches_used[approach], int):
                    errors.append(f"approaches_used['{approach}'] must be an integer")

        # Validate data_quality_note is a string
        data_quality_note = output.get('data_quality_note')
        if not isinstance(data_quality_note, str):
            errors.append("'data_quality_note' must be a string")

        # Validate confidence
        confidence = output.get('confidence')
        if confidence not in self.VALID_CONFIDENCE_LEVELS:
            errors.append(
                f"'confidence' must be one of {self.VALID_CONFIDENCE_LEVELS}, got '{confidence}'"
            )

        return errors

    def to_display_format(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert validated output to UI-friendly display format.

        Args:
            output: Validated output from process()

        Returns:
            Dict formatted for UI rendering
        """
        opportunities = output.get('opportunities', [])

        # Format opportunities for display with approach labels (using class constant)
        formatted_opportunities = []
        for opp in opportunities:
            approach = opp.get('approach', 'unknown')
            formatted_opportunities.append({
                'title': opp.get('title', ''),
                'approach': approach,
                'approach_label': self.APPROACH_LABELS.get(approach, approach.replace('_', ' ').title()),
                'description': opp.get('description', ''),
                'data_backing': opp.get('data_backing', []),
                'plausibility': opp.get('plausibility', 'UNKNOWN'),
                'estimated_value': opp.get('estimated_value', 'Unknown'),
                'next_steps': opp.get('next_steps', [])
            })

        # Group by approach for alternative display
        by_approach = {}
        for opp in formatted_opportunities:
            approach = opp['approach']
            if approach not in by_approach:
                by_approach[approach] = []
            by_approach[approach].append(opp)

        return {
            'opportunities': formatted_opportunities,
            'opportunities_by_approach': by_approach,
            'approaches_used': output.get('approaches_used', {}),
            'data_quality': output.get('data_quality_note', ''),
            'confidence': output.get('confidence', 'UNKNOWN'),
            'total_count': len(formatted_opportunities),
            'agent_id': self.AGENT_ID,
            'agent_name': self.AGENT_NAME
        }
