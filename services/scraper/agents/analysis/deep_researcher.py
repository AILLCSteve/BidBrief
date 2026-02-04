"""
Deep Researcher Agent (AN-3)

Generates Level 1-10 trail maps for deep research exploration of municipal data.
Based on commsdev Task 4 functionality.

Part of the Analysis Layer for CityScraper.

Trail Map Levels:
- Levels 1-3: Surface Analysis (raw observations, basic patterns, initial implications)
- Levels 4-6: Intermediate Analysis (correlations, operational dynamics, resource implications)
- Levels 7-8: Strategic Analysis (systemic vulnerabilities, strategic implications)
- Levels 9-10: Deep Research (hidden relationships, predictive insights)

Each level includes:
- topic: Descriptive topic for this research tier
- findings: 2-5 specific findings grounded in data
- data_connections: Explicit links to extraction data
- tangential_leads: Related research directions
- questions_raised: Actionable research questions

Additional outputs:
- overlaps: Cross-domain connections
- outliers: Unusual data points warranting investigation
- relationship_implications: Key insights from relationship analysis
- recommended_next_research: Prioritized next research steps
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
from services.scraper.prompts.an3_deep_researcher import get_prompt

logger = logging.getLogger(__name__)


class DeepResearcherAgent(BaseAgent):
    """
    AN-3: Deep Researcher Agent

    Generates Level 1-10 trail maps for deep exploration of CityScraper
    extraction results, enabling systematic research from surface observations
    to deep strategic implications.

    This agent transforms raw municipal data into structured research trails
    with cross-domain connections, outliers, and actionable next steps.
    """

    AGENT_ID = "an-3"
    AGENT_NAME = "Deep Researcher"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-04"

    # Valid confidence levels
    VALID_CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")

    # Valid priority levels for recommended research
    VALID_PRIORITY_LEVELS = ("HIGH", "MEDIUM", "LOW")

    # Research depth bounds
    MIN_RESEARCH_DEPTH = 1
    MAX_RESEARCH_DEPTH = 10
    DEFAULT_RESEARCH_DEPTH = 5

    # Required fields in trail_map.levels
    LEVEL_REQUIRED_FIELDS = (
        "level",
        "topic",
        "findings",
        "data_connections",
        "tangential_leads",
        "questions_raised"
    )

    # Required fields in overlap objects
    OVERLAP_REQUIRED_FIELDS = (
        "domain_a",
        "domain_b",
        "connection",
        "implication"
    )

    # Required fields in recommended_next_research objects
    RESEARCH_REC_REQUIRED_FIELDS = (
        "topic",
        "priority",
        "rationale",
        "suggested_sources"
    )

    # Maximum length for extraction data sent to LLM
    MAX_EXTRACTION_DATA_LENGTH = 8000

    # Minimum items expected in list fields
    MIN_FINDINGS_PER_LEVEL = 2
    MIN_DATA_CONNECTIONS_PER_LEVEL = 1
    MIN_OVERLAPS = 1
    MIN_OUTLIERS = 1
    MIN_RELATIONSHIP_IMPLICATIONS = 1
    MIN_RECOMMENDED_RESEARCH = 1

    # Display limits for LLM context
    MAX_EXTRACTED_DATA_DISPLAY = 25
    MAX_SYSTEMS_INFO_DISPLAY = 5
    MAX_PUBLIC_BIDS_DISPLAY = 5
    MAX_DATA_GAPS_DISPLAY = 10
    MAX_CONFLICTS_DISPLAY = 5

    # Level tier labels for display
    LEVEL_TIER_LABELS = {
        1: "Surface Analysis",
        2: "Surface Analysis",
        3: "Surface Analysis",
        4: "Intermediate Analysis",
        5: "Intermediate Analysis",
        6: "Intermediate Analysis",
        7: "Strategic Analysis",
        8: "Strategic Analysis",
        9: "Deep Research",
        10: "Deep Research"
    }

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt(
            "{{municipality}}",
            self.DEFAULT_RESEARCH_DEPTH,
            "{{focus_topic}}"
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
            TypeError: If content is not a string
        """
        # Type validation
        if not isinstance(content, str):
            raise TypeError(f"content must be string, got {type(content).__name__}")

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
            for field_name, field_data in list(extracted_data.items())[:self.MAX_EXTRACTED_DATA_DISPLAY]:
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

            if len(extracted_data) > self.MAX_EXTRACTED_DATA_DISPLAY:
                parts.append(f"\n... and {len(extracted_data) - self.MAX_EXTRACTED_DATA_DISPLAY} more fields")

        # Include systems info rows if present
        systems_info = extraction_result.get('systems_info_rows', [])
        if systems_info:
            parts.append(f"\n## Systems Information ({len(systems_info)} records):\n")
            for i, row in enumerate(systems_info[:self.MAX_SYSTEMS_INFO_DISPLAY], 1):
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
            for i, bid in enumerate(public_bids[:self.MAX_PUBLIC_BIDS_DISPLAY], 1):
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
            for gap in data_gaps[:self.MAX_DATA_GAPS_DISPLAY]:
                parts.append(f"  - {gap}")
            if len(data_gaps) > self.MAX_DATA_GAPS_DISPLAY:
                parts.append(f"  ... and {len(data_gaps) - self.MAX_DATA_GAPS_DISPLAY} more")

        # Include conflicts if present
        conflicts = extraction_result.get('conflicts_detected', [])
        if conflicts:
            parts.append(f"\n## Data Conflicts ({len(conflicts)} items):")
            for conflict in conflicts[:self.MAX_CONFLICTS_DISPLAY]:
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

    def _validate_research_depth(self, depth: Any) -> int:
        """
        Validate and normalize research depth.

        Args:
            depth: Input research depth value

        Returns:
            Valid research depth integer 1-10
        """
        try:
            depth_int = int(depth)
            if depth_int < self.MIN_RESEARCH_DEPTH:
                return self.MIN_RESEARCH_DEPTH
            if depth_int > self.MAX_RESEARCH_DEPTH:
                return self.MAX_RESEARCH_DEPTH
            return depth_int
        except (TypeError, ValueError):
            return self.DEFAULT_RESEARCH_DEPTH

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process deep research request.

        Expected input_data:
        - extraction_result: dict - CityScraper extraction results (from EX-O or PR-3)
        - municipality: dict - Optional municipality info (city, state)
        - research_depth: int - 1-10 (default 5)
        - focus_topic: str - Optional starting topic for research focus

        Returns AgentResponse with:
        - trail_map: dict with starting_point and levels
        - overlaps: list of cross-domain connections
        - outliers: list of unusual data points
        - relationship_implications: list of key insights
        - recommended_next_research: list of prioritized next steps
        - confidence: str - HIGH/MEDIUM/LOW
        """
        start_time = time.time()
        content = ''  # Initialize before any operation
        json_str = ''  # Initialize before any operation

        # Extract input data
        extraction_result = request.input_data.get('extraction_result', {})
        municipality = request.input_data.get('municipality', {})
        research_depth = request.input_data.get('research_depth', self.DEFAULT_RESEARCH_DEPTH)
        focus_topic = request.input_data.get('focus_topic', '')

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

        # Validate and normalize research_depth
        research_depth = self._validate_research_depth(research_depth)

        # Type validation for focus_topic (optional, must be string or None)
        if focus_topic is None:
            focus_topic = ''
        elif not isinstance(focus_topic, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"focus_topic must be string or None, got {type(focus_topic).__name__}"]
            )

        # Handle empty extraction result
        if not extraction_result:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["No extraction data provided. Cannot generate research trail without data."],
                processing_time_seconds=time.time() - start_time
            )

        try:
            # Get municipality name for prompt
            municipality_name = self._get_municipality_name(extraction_result, municipality)

            # Emit event for UI activity feed
            self.emit_event(
                "processing",
                f"Generating Level 1-{research_depth} research trail for {municipality_name}..."
            )

            # Format extraction data for prompt
            extraction_text = self._format_extraction_data(extraction_result)

            # Get the prompt with inputs substituted
            prompt = get_prompt(
                municipality=municipality_name,
                research_depth=research_depth,
                focus_topic=focus_topic
            )

            # Build user message
            focus_instruction = ""
            if focus_topic:
                focus_instruction = f"\n\n**Focus Topic:** {focus_topic}\nOrient the trail map around this topic."

            user_message = f"""Analyze the following municipal data and generate a research trail map.

**CRITICAL**: Build each level on the previous levels. Ground all findings in extraction data.

**Research Depth:** Generate levels 1 through {research_depth}.
{focus_instruction}

---

## EXTRACTION DATA

{extraction_text}

---

Generate a complete trail map with:
1. Levels 1-{research_depth} following the defined progression
2. Cross-domain overlaps found in the data
3. Outliers and anomalies warranting investigation
4. Relationship implications
5. Recommended next research with priorities

Each level must include:
- topic: Descriptive topic name
- findings: 2-5 specific findings grounded in data
- data_connections: Links to extraction data
- tangential_leads: Related research directions
- questions_raised: Actionable research questions

Return the complete JSON output as specified in your instructions."""

            self.emit_event(
                "processing",
                f"Building research trail through {research_depth} levels..."
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
            errors = self.validate_output(output_data, research_depth)

            if errors:
                logger.warning(f"AN-3 validation failed: {errors}")
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
            trail_map = output_data.get('trail_map', {})
            levels_generated = len(trail_map.get('levels', []))
            overlaps_found = len(output_data.get('overlaps', []))
            outliers_found = len(output_data.get('outliers', []))

            completion_msg = (
                f"Deep research complete: {levels_generated} levels generated, "
                f"{overlaps_found} cross-domain overlaps, {outliers_found} outliers, "
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
            logger.error(f"AN-3 JSON parse failed: {e}")
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
            logger.error(f"AN-3 JSON extraction failed: {e}")
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
            logger.error(f"AN-3 data structure error: {e}")
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
            logger.exception(f"AN-3 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def validate_output(
        self,
        output: Dict[str, Any],
        expected_depth: int = DEFAULT_RESEARCH_DEPTH
    ) -> List[str]:
        """
        Validate deep researcher output against spec.

        Args:
            output: The output data to validate
            expected_depth: Expected research depth (for level count validation)

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required top-level fields
        required_fields = [
            'trail_map',
            'overlaps',
            'outliers',
            'relationship_implications',
            'recommended_next_research',
            'confidence'
        ]

        for field_name in required_fields:
            if field_name not in output:
                errors.append(f"Missing required field: '{field_name}'")

        # Return early if missing required fields
        if errors:
            return errors

        # Validate trail_map structure
        trail_map = output.get('trail_map')
        if not isinstance(trail_map, dict):
            errors.append("'trail_map' must be a dict")
            return errors

        # Validate starting_point
        starting_point = trail_map.get('starting_point')
        if not isinstance(starting_point, str) or len(starting_point.strip()) < 10:
            errors.append("'trail_map.starting_point' must be a meaningful string (min 10 chars)")

        # Validate levels
        levels = trail_map.get('levels')
        if not isinstance(levels, list):
            errors.append("'trail_map.levels' must be a list")
            return errors

        # Check level count (allow some flexibility - at least half of expected depth)
        min_expected_levels = max(1, expected_depth // 2)
        if len(levels) < min_expected_levels:
            errors.append(
                f"Expected at least {min_expected_levels} levels for depth {expected_depth}, "
                f"got {len(levels)}"
            )

        # Validate each level
        for i, level in enumerate(levels):
            if not isinstance(level, dict):
                errors.append(f"trail_map.levels[{i}] must be a dict")
                continue

            # Check required fields in each level
            for field in self.LEVEL_REQUIRED_FIELDS:
                if field not in level:
                    errors.append(f"trail_map.levels[{i}] missing '{field}'")

            # Validate level number
            level_num = level.get('level')
            if not isinstance(level_num, int) or level_num < 1 or level_num > 10:
                errors.append(f"trail_map.levels[{i}].level must be integer 1-10")

            # Validate topic is a non-empty string
            topic = level.get('topic')
            if not isinstance(topic, str) or len(topic.strip()) < 3:
                errors.append(f"trail_map.levels[{i}].topic must be a non-empty string")

            # Validate findings is a list with items
            findings = level.get('findings')
            if not isinstance(findings, list):
                errors.append(f"trail_map.levels[{i}].findings must be a list")
            elif len(findings) < self.MIN_FINDINGS_PER_LEVEL:
                errors.append(
                    f"trail_map.levels[{i}].findings should have at least "
                    f"{self.MIN_FINDINGS_PER_LEVEL} items, got {len(findings)}"
                )
            else:
                for j, finding in enumerate(findings):
                    if not isinstance(finding, str) or len(finding.strip()) < 10:
                        errors.append(
                            f"trail_map.levels[{i}].findings[{j}] must be a meaningful string"
                        )

            # Validate data_connections is a list with items
            data_connections = level.get('data_connections')
            if not isinstance(data_connections, list):
                errors.append(f"trail_map.levels[{i}].data_connections must be a list")
            elif len(data_connections) < self.MIN_DATA_CONNECTIONS_PER_LEVEL:
                errors.append(
                    f"trail_map.levels[{i}].data_connections should have at least "
                    f"{self.MIN_DATA_CONNECTIONS_PER_LEVEL} items"
                )

            # Validate tangential_leads is a list
            tangential_leads = level.get('tangential_leads')
            if not isinstance(tangential_leads, list):
                errors.append(f"trail_map.levels[{i}].tangential_leads must be a list")

            # Validate questions_raised is a list
            questions_raised = level.get('questions_raised')
            if not isinstance(questions_raised, list):
                errors.append(f"trail_map.levels[{i}].questions_raised must be a list")

        # Validate overlaps is a list
        overlaps = output.get('overlaps')
        if not isinstance(overlaps, list):
            errors.append("'overlaps' must be a list")
        elif len(overlaps) < self.MIN_OVERLAPS:
            errors.append(f"'overlaps' should have at least {self.MIN_OVERLAPS} items")
        else:
            for i, overlap in enumerate(overlaps):
                if not isinstance(overlap, dict):
                    errors.append(f"overlaps[{i}] must be a dict")
                    continue
                for field in self.OVERLAP_REQUIRED_FIELDS:
                    if field not in overlap:
                        errors.append(f"overlaps[{i}] missing '{field}'")

        # Validate outliers is a list
        outliers = output.get('outliers')
        if not isinstance(outliers, list):
            errors.append("'outliers' must be a list")
        elif len(outliers) < self.MIN_OUTLIERS:
            errors.append(f"'outliers' should have at least {self.MIN_OUTLIERS} items")
        else:
            for i, outlier in enumerate(outliers):
                if not isinstance(outlier, str) or len(outlier.strip()) < 10:
                    errors.append(f"outliers[{i}] must be a meaningful string")

        # Validate relationship_implications is a list
        relationship_implications = output.get('relationship_implications')
        if not isinstance(relationship_implications, list):
            errors.append("'relationship_implications' must be a list")
        elif len(relationship_implications) < self.MIN_RELATIONSHIP_IMPLICATIONS:
            errors.append(
                f"'relationship_implications' should have at least "
                f"{self.MIN_RELATIONSHIP_IMPLICATIONS} items"
            )

        # Validate recommended_next_research is a list
        recommended_next_research = output.get('recommended_next_research')
        if not isinstance(recommended_next_research, list):
            errors.append("'recommended_next_research' must be a list")
        elif len(recommended_next_research) < self.MIN_RECOMMENDED_RESEARCH:
            errors.append(
                f"'recommended_next_research' should have at least "
                f"{self.MIN_RECOMMENDED_RESEARCH} items"
            )
        else:
            for i, rec in enumerate(recommended_next_research):
                if not isinstance(rec, dict):
                    errors.append(f"recommended_next_research[{i}] must be a dict")
                    continue
                for field in self.RESEARCH_REC_REQUIRED_FIELDS:
                    if field not in rec:
                        errors.append(f"recommended_next_research[{i}] missing '{field}'")

                # Validate priority
                priority = rec.get('priority')
                if priority not in self.VALID_PRIORITY_LEVELS:
                    errors.append(
                        f"recommended_next_research[{i}].priority must be one of "
                        f"{self.VALID_PRIORITY_LEVELS}, got '{priority}'"
                    )

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
        trail_map = output.get('trail_map', {})
        levels = trail_map.get('levels', [])

        # Format levels for display with tier labels
        formatted_levels = []
        for level in levels:
            level_num = level.get('level', 0)
            formatted_levels.append({
                'level': level_num,
                'tier': self.LEVEL_TIER_LABELS.get(level_num, "Unknown"),
                'topic': level.get('topic', ''),
                'findings': level.get('findings', []),
                'data_connections': level.get('data_connections', []),
                'tangential_leads': level.get('tangential_leads', []),
                'questions_raised': level.get('questions_raised', [])
            })

        # Group levels by tier for alternative display
        by_tier = {}
        for level in formatted_levels:
            tier = level['tier']
            if tier not in by_tier:
                by_tier[tier] = []
            by_tier[tier].append(level)

        # Format overlaps
        overlaps = output.get('overlaps', [])
        formatted_overlaps = []
        for overlap in overlaps:
            if isinstance(overlap, dict):
                formatted_overlaps.append({
                    'domain_a': overlap.get('domain_a', ''),
                    'domain_b': overlap.get('domain_b', ''),
                    'connection': overlap.get('connection', ''),
                    'implication': overlap.get('implication', '')
                })

        # Format recommended research with priority badges
        recommended = output.get('recommended_next_research', [])
        formatted_recommended = []
        for rec in recommended:
            if isinstance(rec, dict):
                formatted_recommended.append({
                    'topic': rec.get('topic', ''),
                    'priority': rec.get('priority', 'MEDIUM'),
                    'rationale': rec.get('rationale', ''),
                    'suggested_sources': rec.get('suggested_sources', [])
                })

        # Sort by priority (HIGH first)
        priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        formatted_recommended.sort(
            key=lambda x: priority_order.get(x['priority'], 3)
        )

        return {
            'trail_map': {
                'starting_point': trail_map.get('starting_point', ''),
                'levels': formatted_levels,
                'levels_by_tier': by_tier
            },
            'overlaps': formatted_overlaps,
            'outliers': output.get('outliers', []),
            'relationship_implications': output.get('relationship_implications', []),
            'recommended_next_research': formatted_recommended,
            'confidence': output.get('confidence', 'UNKNOWN'),
            'total_levels': len(formatted_levels),
            'max_depth_reached': max([l['level'] for l in levels], default=0),
            'agent_id': self.AGENT_ID,
            'agent_name': self.AGENT_NAME
        }
