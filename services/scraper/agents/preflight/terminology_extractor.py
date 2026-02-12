"""
Terminology Extractor Agent (PF-4)

Locks local naming conventions for a municipality before extraction phase.
Ensures consistent terminology throughout the extraction process.

Responsibilities:
- Identify sanitary sewer terminology used locally
- Identify stormwater/drainage terminology used locally
- Extract equipment naming conventions
- Extract bid portal keywords and search terms
- Handle acronyms and their local meanings
- Flag combined sewer systems and legacy terminology
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    TerminologyMap
)
from services.scraper.prompts.pf4_terminology_extractor import get_prompt

logger = logging.getLogger(__name__)


class TerminologyExtractorAgent(BaseAgent):
    """
    PF-4: Terminology Extractor Agent

    Locks local naming conventions to ensure consistent terminology
    during the extraction phase. Identifies regional variations in
    sewer, stormwater, equipment, and bid terminology.
    """

    AGENT_ID = "pf-4"
    AGENT_NAME = "Terminology Extractor"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-03"

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt("{{municipality_name}}", "{{state}}")

    def _extract_json_from_response(self, content: str) -> str:
        """Safely extract JSON from LLM response with validation.

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

    async def _gather_terminology_context(
        self,
        municipality_name: str,
        state: str
    ) -> List[Dict[str, Any]]:
        """
        Execute Tavily searches for terminology evidence.

        Search strategy focuses on finding documents that reveal local
        naming conventions for sewer, stormwater, and equipment.

        Args:
            municipality_name: Normalized municipality name
            state: Full state name

        Returns:
            List of search result dictionaries
        """
        all_results = []

        # Check if Tavily is available
        if not self.config.tavily or not self.config.tavily.api_key:
            logger.warning("PF-4: Tavily not configured — will use AI knowledge only")
            return all_results

        # Try one search first to check availability
        test_query = f"{municipality_name} {state} sanitary sewer terminology wastewater collection"
        self.emit_event("searching", f"Searching: {test_query[:50]}...")
        test_results = await self.search_tavily(test_query, max_results=10)

        if not test_results:
            logger.warning("PF-4: Tavily unavailable — using AI knowledge for terminology")
            self.emit_event("processing", "Web search unavailable — using AI knowledge base")
            return all_results

        for r in test_results:
            r['query'] = test_query
        all_results.extend(test_results)

        # Remaining searches
        search_configs = [
            (f"{municipality_name} {state} stormwater drainage MS4 system", 10),
            (f"{municipality_name} {state} CCTV sewer inspection equipment", 10),
            (f"{municipality_name} {state} bid RFP sewer wastewater", 10),
            (f"{municipality_name} {state} lift station pump station sewer", 10),
        ]

        for query, max_results in search_configs:
            self.emit_event("searching", f"Searching: {query[:50]}...")
            results = await self.search_tavily(query, max_results=max_results)
            if not results:
                continue
            for r in results:
                r['query'] = query
            all_results.extend(results)

        logger.debug(f"PF-4 gathered {len(all_results)} total search results")
        return all_results

    def _build_context(self, search_results: List[Dict[str, Any]]) -> str:
        """Build context string from search results with validation and deduplication."""
        if not search_results:
            return ("No search results available. Web search is currently unavailable.\n"
                    "IMPORTANT: You MUST still generate terminology using your training knowledge.\n"
                    "Use standard industry terminology for sewer/stormwater systems.\n"
                    "Set confidence to LOW since results are not verified by live search.")

        context_parts = ["## SEARCH RESULTS\n"]
        seen_urls = set()
        unique_results = []

        for result in search_results:
            # Validate result structure
            if not isinstance(result, dict):
                logger.warning(f"Skipping non-dict search result: {type(result)}")
                continue

            url = result.get('url', '').strip()
            content = result.get('content', '').strip()

            # Skip empty or too-short content
            if not content or len(content) < 20:
                continue

            # Deduplicate by URL
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)

        if not unique_results:
            return "Search returned no useful results."

        # Limit to top 20 unique results to avoid context overflow
        for i, result in enumerate(unique_results[:20], 1):
            title = result.get('title', 'Untitled').strip()
            url = result.get('url', '')
            content = result.get('content', '')
            query = result.get('query', '')

            context_parts.append(f"### Result {i}: {title}")
            context_parts.append(f"**URL:** {url}")
            if query:
                context_parts.append(f"**Query:** {query}")
            # Truncate content to avoid excessive context
            context_parts.append(f"**Content:**\n{content[:600]}\n")

        return "\n".join(context_parts)

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process terminology extraction request.

        Expected input_data:
        - municipality_name: str - Normalized municipality name (e.g., "Springfield")
        - state: str - Full state name (e.g., "Illinois")

        Returns AgentResponse with:
        - terminology: Local terminology by category
        - bid_portal_keywords: Keywords for bid searches
        - acronyms: Local acronym meanings
        - special_notes: Notable terminology considerations
        - confidence: Overall confidence rating
        - terminology_gaps: Terms not found
        """
        start_time = time.time()
        content = ''  # Initialize before any operation
        json_str = ''  # Initialize before any operation

        municipality_name = request.input_data.get('municipality_name', '')
        state = request.input_data.get('state', '')

        # Type validation
        if not isinstance(municipality_name, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"municipality_name must be string, got {type(municipality_name).__name__}"]
            )

        if not isinstance(state, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"state must be string, got {type(state).__name__}"]
            )

        municipality_name = municipality_name.strip()
        state = state.strip()

        if not municipality_name:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["municipality_name is required"]
            )

        if not state:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["state is required"]
            )

        # Length validation
        if len(municipality_name) > 200:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"municipality_name too long ({len(municipality_name)} chars, max 200)"]
            )

        if len(state) > 50:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"state too long ({len(state)} chars, max 50)"]
            )

        try:
            # Emit event for UI activity feed
            self.emit_event("processing", f"Extracting terminology for {municipality_name}, {state}")

            # Gather terminology evidence via Tavily searches
            search_results = await self._gather_terminology_context(municipality_name, state)

            # Build context from search results
            context = self._build_context(search_results)

            # Get the prompt with input substituted
            prompt = get_prompt(municipality_name, state)

            # Build user message with search context
            user_message = f"""Extract terminology for: {municipality_name}, {state}

SEARCH RESULTS TO ANALYZE:
{context}

Based on these search results, identify local terminology for:
- Sanitary sewer systems
- Stormwater/drainage systems
- Equipment and maintenance
- Bid portal keywords
- Acronyms used locally

Return the JSON terminology map as specified in your instructions."""

            self.emit_event("processing", "Analyzing terminology patterns...")

            # Call OpenAI
            result = await self.call_openai(
                user_message=user_message,
                system_prompt=prompt
            )

            # Parse JSON from response
            content = result.get('content', '')
            json_str = self._extract_json_from_response(content)
            output_data = json.loads(json_str)

            # Validate output
            errors = self.validate_output(output_data)

            if errors:
                logger.warning(f"PF-4 validation failed: {errors}")
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

            # Emit completion event with summary
            terminology = output_data.get('terminology', {})
            term_count = len(terminology)
            confidence = output_data.get('confidence', 'UNKNOWN')

            self.emit_event(
                "completed",
                f"Extracted {term_count} terminology categories ({confidence} confidence)",
                is_completed=True
            )

            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=True,
                output_data=output_data,
                errors=[],
                tokens_used=result.get('tokens_used', 0),
                processing_time_seconds=elapsed
            )

        except ValueError as e:
            # JSON extraction failed
            logger.error(f"PF-4 JSON extraction failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'extraction_error': str(e), 'raw_response': content[:1000] if content else ''},
                errors=[f"JSON extraction error: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )
        except json.JSONDecodeError as e:
            logger.error(f"PF-4 JSON parse failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'parse_error': str(e), 'attempted_json': json_str[:500] if json_str else ''},
                errors=[f"JSON parse error at position {e.pos}: {e.msg}"],
                processing_time_seconds=time.time() - start_time
            )
        except Exception as e:
            logger.exception(f"PF-4 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate terminology extraction output against spec."""
        errors = []

        # Check terminology section exists
        if 'terminology' not in output:
            errors.append("Missing 'terminology' section")
            return errors

        terminology = output['terminology']

        # Check sanitary_sewer (PRIMARY focus)
        if 'sanitary_sewer' not in terminology:
            errors.append("Missing required 'sanitary_sewer' terminology")
        else:
            sanitary = terminology['sanitary_sewer']
            if not sanitary.get('primary_term'):
                errors.append("sanitary_sewer missing 'primary_term'")
            if 'evidence' not in sanitary:
                errors.append("sanitary_sewer missing 'evidence'")

        # Check stormwater
        if 'stormwater' not in terminology:
            errors.append("Missing required 'stormwater' terminology")
        else:
            storm = terminology['stormwater']
            if not storm.get('primary_term'):
                errors.append("stormwater missing 'primary_term'")
            if 'evidence' not in storm:
                errors.append("stormwater missing 'evidence'")

        # Check bid_portal_keywords
        if 'bid_portal_keywords' not in output:
            errors.append("Missing 'bid_portal_keywords' section")
        else:
            keywords = output['bid_portal_keywords']
            if not isinstance(keywords, dict):
                errors.append("'bid_portal_keywords' must be a dictionary")
            elif not keywords.get('infrastructure') and not keywords.get('services'):
                errors.append("bid_portal_keywords needs at least 'infrastructure' or 'services'")

        # Validate confidence
        confidence = output.get('confidence')
        if not confidence:
            errors.append("Missing required 'confidence' field")
        elif confidence not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append(f"Invalid confidence: {confidence}")

        # Validate acronyms is a dict if present
        acronyms = output.get('acronyms')
        if acronyms is not None and not isinstance(acronyms, dict):
            errors.append("'acronyms' must be a dictionary")

        # Validate special_notes is a list if present
        special_notes = output.get('special_notes')
        if special_notes is not None and not isinstance(special_notes, list):
            errors.append("'special_notes' must be a list")

        # Validate terminology_gaps is a list if present
        gaps = output.get('terminology_gaps')
        if gaps is not None and not isinstance(gaps, list):
            errors.append("'terminology_gaps' must be a list")

        return errors

    def to_terminology_map(self, output: Dict[str, Any]) -> Optional[TerminologyMap]:
        """
        Convert validated output to TerminologyMap model object.

        Args:
            output: Validated output from process()

        Returns:
            TerminologyMap object or None if conversion fails
        """
        try:
            terminology = output.get('terminology', {})
            bid_keywords = output.get('bid_portal_keywords', {})

            # Extract sanitary terms
            sanitary_terms = []
            sanitary = terminology.get('sanitary_sewer', {})
            if sanitary.get('primary_term'):
                sanitary_terms.append(sanitary['primary_term'])
            sanitary_terms.extend(sanitary.get('alternate_terms', []))

            # Extract storm terms
            storm_terms = []
            storm = terminology.get('stormwater', {})
            if storm.get('primary_term'):
                storm_terms.append(storm['primary_term'])
            storm_terms.extend(storm.get('alternate_terms', []))

            # Extract lift station terms
            lift_station_terms = []
            lift = terminology.get('lift_stations', {})
            if lift.get('primary_term'):
                lift_station_terms.append(lift['primary_term'])
            lift_station_terms.extend(lift.get('alternate_terms', []))

            # Extract bid portal keywords
            bid_portal_keywords = []
            bid_portal_keywords.extend(bid_keywords.get('infrastructure', []))
            bid_portal_keywords.extend(bid_keywords.get('services', []))
            bid_portal_keywords.extend(bid_keywords.get('methods', []))

            return TerminologyMap(
                sanitary_terms=sanitary_terms,
                storm_terms=storm_terms,
                lift_station_terms=lift_station_terms,
                bid_portal_keywords=bid_portal_keywords
            )

        except Exception as e:
            logger.error(f"Failed to convert output to TerminologyMap: {e}")
            return None
