"""
Summary Generator Agent (AN-1)

Generates 4-perspective summaries from scraped municipal data to provide
stakeholder-specific insights. Based on commsdev Task 2 functionality.

Part of the Analysis Layer for CityScraper.

Perspectives generated:
1. municipal_owner - City/utility perspective: budget, compliance, risk
2. citizen - Taxpayer perspective: service quality, costs, safety
3. contractor - Business perspective: opportunity size, competition, requirements
4. competitor - Strategic perspective: market position, entry points, timing

Each perspective includes:
- key_facts: Most important data points (with specific numbers)
- implications: What the facts mean for this stakeholder
- priorities: Recommended focus areas and actions
- leverage_points: Actionable opportunities
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
from services.scraper.prompts.an1_summary_generator import get_prompt

logger = logging.getLogger(__name__)


class SummaryGeneratorAgent(BaseAgent):
    """
    AN-1: Summary Generator Agent

    Generates multi-perspective summaries from CityScraper extraction results,
    providing stakeholder-specific insights grounded in actual data.

    This agent transforms raw municipal data into actionable intelligence
    for different audiences: municipal owners, citizens, contractors, and
    competitors.
    """

    AGENT_ID = "an-1"
    AGENT_NAME = "Summary Generator"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-04"

    # Valid confidence levels
    VALID_CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")
    # Required perspective names
    REQUIRED_PERSPECTIVES = ("municipal_owner", "citizen", "contractor", "competitor")
    # Required fields in each perspective
    PERSPECTIVE_REQUIRED_FIELDS = ("key_facts", "implications", "priorities", "leverage_points")

    # Maximum length for extraction data sent to LLM
    MAX_EXTRACTION_DATA_LENGTH = 8000
    # Minimum items expected in each perspective field
    MIN_ITEMS_PER_FIELD = 2
    # Maximum items expected in each perspective field
    MAX_ITEMS_PER_FIELD = 7

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt(
            "{{municipality}}",
            "{{focus_area}}"
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
            for i, row in enumerate(systems_info[:20], 1):  # Increased from 5
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
            for i, bid in enumerate(public_bids[:20], 1):
                if isinstance(bid, dict):
                    parts.append(f"### Bid {i}:")
                    title = bid.get('bid_contract_title', 'Unknown')
                    parts.append(f"  Title: {title}")
                    status = bid.get('status', 'Unknown')
                    parts.append(f"  Status: {status}")
                    scope = bid.get('scope', {})
                    if isinstance(scope, dict):
                        parts.append(f"  Scope: {scope.get('value', str(scope)[:300])}")
                    parts.append("")

        # Include data gaps
        data_gaps = extraction_result.get('data_gaps', [])
        if data_gaps:
            parts.append(f"\n## Data Gaps ({len(data_gaps)} items):")
            for gap in data_gaps[:30]:
                parts.append(f"  - {gap}")
            if len(data_gaps) > 30:
                parts.append(f"  ... and {len(data_gaps) - 30} more")

        # Include conflicts if present
        conflicts = extraction_result.get('conflicts_detected', [])
        if conflicts:
            parts.append(f"\n## Data Conflicts ({len(conflicts)} items):")
            for conflict in conflicts[:15]:
                if isinstance(conflict, dict):
                    parts.append(f"  - {conflict.get('description', str(conflict)[:200])}")
                else:
                    parts.append(f"  - {str(conflict)[:200]}")

        result = "\n".join(parts)

        # Truncate if too long
        if len(result) > self.MAX_EXTRACTION_DATA_LENGTH:
            result = result[:self.MAX_EXTRACTION_DATA_LENGTH] + "\n\n[... data truncated ...]"

        return result if result else "Minimal extraction data available."

    def _get_municipality_name(self, extraction_result: Dict[str, Any], municipality: Optional[Dict[str, Any]]) -> str:
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
        Process summary generation request.

        Expected input_data:
        - extraction_result: dict - CityScraper extraction results (from EX-O or PR-3)
        - municipality: dict - Optional municipality info (city, state)
        - focus_area: str - Optional focus (e.g., "infrastructure", "bids", "incidents")

        Returns AgentResponse with:
        - summaries: dict with 4 perspectives
        - executive_summary: str - 2-3 sentence overview
        - data_quality_note: str - Assessment of data completeness
        - confidence: str - HIGH/MEDIUM/LOW
        """
        start_time = time.time()
        content = ''  # Initialize before any operation
        json_str = ''  # Initialize before any operation

        # Extract input data
        extraction_result = request.input_data.get('extraction_result', {})
        municipality = request.input_data.get('municipality', {})
        focus_area = request.input_data.get('focus_area', '')

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

        # Type validation for focus_area (optional, must be string or None)
        if focus_area is None:
            focus_area = ''
        elif not isinstance(focus_area, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"focus_area must be string or None, got {type(focus_area).__name__}"]
            )

        # Handle empty extraction result
        if not extraction_result:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["No extraction data provided. Cannot generate summaries without data."],
                processing_time_seconds=time.time() - start_time
            )

        try:
            # Get municipality name for prompt
            municipality_name = self._get_municipality_name(extraction_result, municipality)

            # Emit event for UI activity feed
            self.emit_event(
                "processing",
                f"Generating 4-perspective summary for {municipality_name}..."
            )

            # Format extraction data for prompt
            extraction_text = self._format_extraction_data(extraction_result)

            # Get the prompt with inputs substituted
            prompt = get_prompt(
                municipality=municipality_name,
                focus_area=focus_area
            )

            # Build user message
            user_message = f"""Analyze the following municipal data and generate 4-perspective summaries.

**CRITICAL**: Ground every insight in specific data from the extraction. Cite actual numbers.

---

## EXTRACTION DATA

{extraction_text}

---

Generate comprehensive summaries from all four stakeholder perspectives:
1. Municipal Owner (city/utility manager)
2. Citizen (taxpayer/ratepayer)
3. Contractor (seeking work)
4. Competitor (strategic positioning)

Each perspective must include key_facts, implications, priorities, and leverage_points.
All key_facts MUST cite specific numbers from the data.

Return the complete JSON output as specified in your instructions."""

            self.emit_event("processing", "Analyzing data from multiple stakeholder viewpoints...")

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
                logger.warning(f"AN-1 validation failed: {errors}")
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
            perspectives_count = len(output_data.get('summaries', {}))

            completion_msg = (
                f"Summary generation complete: {perspectives_count} perspectives generated, "
                f"confidence level {confidence}."
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
            logger.error(f"AN-1 JSON parse failed: {e}")
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
            logger.error(f"AN-1 JSON extraction failed: {e}")
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
            logger.error(f"AN-1 data structure error: {e}")
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
            logger.exception(f"AN-1 unexpected error: {e}")
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
        Validate summary generator output against spec.

        Args:
            output: The output data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required top-level fields
        required_fields = ['executive_summary', 'summaries', 'data_quality_note', 'confidence']

        for field_name in required_fields:
            if field_name not in output:
                errors.append(f"Missing required field: '{field_name}'")

        # Return early if missing required fields
        if errors:
            return errors

        # Validate executive_summary is a non-empty string
        executive_summary = output.get('executive_summary')
        if not isinstance(executive_summary, str):
            errors.append("'executive_summary' must be a string")
        elif len(executive_summary.strip()) < 20:
            errors.append("'executive_summary' appears too short (minimum 20 characters)")

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

        # Validate summaries structure
        summaries = output.get('summaries')
        if not isinstance(summaries, dict):
            errors.append("'summaries' must be a dict")
            return errors

        # Check all required perspectives are present
        for perspective in self.REQUIRED_PERSPECTIVES:
            if perspective not in summaries:
                errors.append(f"Missing required perspective: '{perspective}'")
            else:
                # Validate each perspective's structure
                persp_data = summaries[perspective]
                if not isinstance(persp_data, dict):
                    errors.append(f"summaries.{perspective} must be a dict")
                    continue

                # Check required fields in each perspective
                for field in self.PERSPECTIVE_REQUIRED_FIELDS:
                    if field not in persp_data:
                        errors.append(f"summaries.{perspective} missing '{field}'")
                    else:
                        field_value = persp_data[field]
                        # Validate field is a list
                        if not isinstance(field_value, list):
                            errors.append(
                                f"summaries.{perspective}.{field} must be a list"
                            )
                        elif len(field_value) < self.MIN_ITEMS_PER_FIELD:
                            errors.append(
                                f"summaries.{perspective}.{field} should have at least "
                                f"{self.MIN_ITEMS_PER_FIELD} items, got {len(field_value)}"
                            )
                        else:
                            # Validate each item is a non-empty string
                            for i, item in enumerate(field_value):
                                if not isinstance(item, str):
                                    errors.append(
                                        f"summaries.{perspective}.{field}[{i}] must be string"
                                    )
                                elif len(item.strip()) < 10:
                                    errors.append(
                                        f"summaries.{perspective}.{field}[{i}] too short"
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
        summaries = output.get('summaries', {})

        # Format for display with perspective labels
        perspective_labels = {
            'municipal_owner': 'Municipal Owner Perspective',
            'citizen': 'Citizen/Taxpayer Perspective',
            'contractor': 'Contractor Perspective',
            'competitor': 'Competitor Perspective'
        }

        formatted_perspectives = []
        for persp_key, persp_label in perspective_labels.items():
            persp_data = summaries.get(persp_key, {})
            formatted_perspectives.append({
                'id': persp_key,
                'label': persp_label,
                'key_facts': persp_data.get('key_facts', []),
                'implications': persp_data.get('implications', []),
                'priorities': persp_data.get('priorities', []),
                'leverage_points': persp_data.get('leverage_points', [])
            })

        return {
            'executive_summary': output.get('executive_summary', ''),
            'perspectives': formatted_perspectives,
            'data_quality': output.get('data_quality_note', ''),
            'confidence': output.get('confidence', 'UNKNOWN'),
            'agent_id': self.AGENT_ID,
            'agent_name': self.AGENT_NAME
        }
