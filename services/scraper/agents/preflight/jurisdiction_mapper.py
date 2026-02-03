"""
Jurisdiction Mapper Agent (PF-2)

Determines ownership and operation responsibilities for sanitary sewer
and stormwater systems in a municipality.

Responsibilities:
- Identify who OWNS sanitary sewer infrastructure
- Identify who OPERATES sanitary sewer (may differ from owner)
- Identify stormwater owner and operator
- Detect regional authorities, special districts, JPAs
- Gather verbatim evidence for all claims

Key Insight: Ownership and operation are often DIFFERENT entities.
A city may own pipes but a regional district operates treatment.
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    JurisdictionInfo,
    SourceURL
)
from services.scraper.prompts.pf2_jurisdiction_mapper import get_prompt

logger = logging.getLogger(__name__)


class JurisdictionMapperAgent(BaseAgent):
    """
    PF-2: Jurisdiction Mapper Agent

    Determines who owns and operates sanitary sewer and stormwater systems.
    Critical for understanding the municipal utility landscape before extraction.
    """

    AGENT_ID = "pf-2"
    AGENT_NAME = "Jurisdiction Mapper"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-03"

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt("{{municipality_name}}", "{{state}}")

    def _extract_json_from_response(self, content: str) -> str:
        """Safely extract JSON from LLM response."""
        try:
            # Try markdown JSON block
            if '```json' in content:
                parts = content.split('```json', 1)
                if len(parts) > 1:
                    end_parts = parts[1].split('```', 1)
                    if len(end_parts) > 0:
                        return end_parts[0].strip()

            # Try generic markdown block
            if '```' in content:
                parts = content.split('```', 2)
                if len(parts) >= 3:
                    return parts[1].strip()

            # Try raw JSON (find first { and last })
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end > start:
                return content[start:end+1]

            return content.strip()
        except (IndexError, AttributeError) as e:
            logger.error(f"Failed to extract JSON structure: {e}")
            raise ValueError(f"LLM response did not contain valid JSON structure: {str(e)}")

    async def _gather_jurisdiction_info(
        self,
        municipality_name: str,
        state: str
    ) -> List[Dict[str, Any]]:
        """
        Execute Tavily searches to gather jurisdiction information.

        Follows the 70/30 effort split: sanitary sewer (primary) vs stormwater (secondary).

        Args:
            municipality_name: Normalized municipality name
            state: Full state name

        Returns:
            List of search result dictionaries
        """
        all_results = []

        # Primary searches - Sanitary Sewer (70% effort)
        sanitary_queries = [
            f"{municipality_name} {state} sanitary sewer district owner",
            f"{municipality_name} {state} wastewater utility operator",
            f"{municipality_name} {state} sewer system regional authority",
            f"{municipality_name} wastewater treatment plant operator",
        ]

        # Secondary searches - Stormwater (30% effort)
        stormwater_queries = [
            f"{municipality_name} {state} stormwater management",
            f"{municipality_name} {state} storm drain owner MS4",
        ]

        # Execute sanitary sewer searches
        for query in sanitary_queries:
            self.emit_event("searching", f"Searching: {query[:50]}...")
            results = await self.search_tavily(query, max_results=5)
            all_results.extend(results)

        # Execute stormwater searches
        for query in stormwater_queries:
            self.emit_event("searching", f"Searching: {query[:50]}...")
            results = await self.search_tavily(query, max_results=3)
            all_results.extend(results)

        logger.debug(f"PF-2 gathered {len(all_results)} total search results")
        return all_results

    def _build_context(self, search_results: List[Dict[str, Any]]) -> str:
        """
        Build context string from search results for LLM consumption.

        Args:
            search_results: List of Tavily search results

        Returns:
            Formatted context string
        """
        if not search_results:
            return "No search results available. Use general knowledge with LOW confidence."

        context_parts = ["## SEARCH RESULTS\n"]

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for result in search_results:
            url = result.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)

        for i, result in enumerate(unique_results[:15], 1):  # Limit to top 15 unique
            title = result.get('title', 'Untitled')
            url = result.get('url', '')
            content = result.get('content', '')
            query = result.get('query', '')

            context_parts.append(f"### Result {i}: {title}")
            context_parts.append(f"**URL:** {url}")
            context_parts.append(f"**Query:** {query}")
            context_parts.append(f"**Content:**\n{content}\n")

        return "\n".join(context_parts)

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process jurisdiction mapping request.

        Expected input_data:
        - municipality_name: str - Normalized municipality name (e.g., "Springfield")
        - state: str - Full state name (e.g., "Illinois")

        Returns AgentResponse with:
        - sanitary_sewer: Owner and operator info
        - stormwater: Owner and operator info
        - regional_authorities: Any regional entities discovered
        - confidence: Overall confidence rating
        """
        start_time = time.time()

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

        # Length checks
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
            content = ''  # Initialize before any operation

            # Emit event for UI activity feed
            self.emit_event("processing", f"Mapping jurisdiction: {municipality_name}, {state}")

            # Gather jurisdiction information via Tavily searches
            search_results = await self._gather_jurisdiction_info(municipality_name, state)

            # Build context from search results
            context = self._build_context(search_results)

            # Get the prompt with input substituted
            prompt = get_prompt(municipality_name, state)

            # Build user message with search context
            user_message = f"""Determine utility jurisdiction for: {municipality_name}, {state}

{context}

Based on these search results, identify the owners and operators for sanitary sewer
and stormwater systems. Use VERBATIM quotes from the search results as evidence.
Return the JSON output as specified."""

            # Call OpenAI
            result = await self.call_openai(
                user_message=user_message,
                system_prompt=prompt
            )

            # Parse JSON from response
            content = result.get('content', '')

            # Extract JSON from response (handle markdown code blocks)
            json_str = self._extract_json_from_response(content)

            output_data = json.loads(json_str)

            # Validate output
            errors = self.validate_output(output_data)

            if errors:
                logger.warning(f"PF-2 validation failed: {errors}")
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

            # Emit completion event
            confidence = output_data.get('confidence', 'UNKNOWN')
            complexity = output_data.get('jurisdiction_complexity', 'unknown')
            self.emit_event(
                "completed",
                f"Jurisdiction mapped: {complexity} complexity, {confidence} confidence",
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

        except json.JSONDecodeError as e:
            logger.error(f"PF-2 failed to parse JSON response: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content},
                errors=[f"JSON parse error: {e}"]
            )
        except Exception as e:
            logger.error(f"PF-2 processing error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content} if content else {},
                errors=[str(e)]
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """
        Validate jurisdiction mapper output against spec.

        Checks:
        - sanitary_sewer section exists with owner
        - stormwater section exists
        - confidence is valid enum
        - Owner has entity_name (or explicit null with data_gaps)
        """
        errors = []

        # Check required top-level sections
        if 'sanitary_sewer' not in output:
            errors.append("Missing 'sanitary_sewer' section")
        else:
            sanitary = output['sanitary_sewer']
            if 'owner' not in sanitary:
                errors.append("Missing 'sanitary_sewer.owner' section")
            else:
                owner = sanitary['owner']
                # entity_name can be null if data_gaps explains why
                if owner.get('entity_name') is None:
                    # Check if this is documented in data_gaps
                    data_gaps = output.get('data_gaps', [])
                    if not any('sanitary' in gap.lower() or 'sewer' in gap.lower() for gap in data_gaps):
                        errors.append("sanitary_sewer.owner.entity_name is null but not documented in data_gaps")

        if 'stormwater' not in output:
            errors.append("Missing 'stormwater' section")

        # Confidence validation
        confidence = output.get('confidence')
        if confidence and confidence not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append(f"Invalid confidence: {confidence} (must be HIGH, MEDIUM, or LOW)")

        # Complexity validation
        complexity = output.get('jurisdiction_complexity')
        if complexity and complexity not in ['simple', 'moderate', 'complex']:
            errors.append(f"Invalid jurisdiction_complexity: {complexity}")

        # Validate regional_authorities if present
        regional = output.get('regional_authorities', [])
        if not isinstance(regional, list):
            errors.append("regional_authorities must be a list")

        return errors

    def to_jurisdiction_info(self, output: Dict[str, Any]) -> Optional[JurisdictionInfo]:
        """
        Convert validated output to JurisdictionInfo model object.

        Args:
            output: Validated output from process()

        Returns:
            JurisdictionInfo object or None if conversion fails
        """
        try:
            sanitary = output.get('sanitary_sewer', {})
            stormwater = output.get('stormwater', {})
            sources_data = output.get('sources_consulted', [])

            # Extract entity names with fallbacks
            sanitary_owner = sanitary.get('owner', {}).get('entity_name') or 'NOT FOUND'
            sanitary_operator = sanitary.get('operator', {}).get('entity_name') or sanitary_owner

            storm_owner = stormwater.get('owner', {}).get('entity_name') or 'NOT FOUND'
            storm_operator = stormwater.get('operator', {}).get('entity_name') or storm_owner

            # Build notes from various sources
            notes_parts = []
            if sanitary.get('notes'):
                notes_parts.append(f"Sanitary: {sanitary['notes']}")
            if stormwater.get('notes'):
                notes_parts.append(f"Stormwater: {stormwater['notes']}")
            if output.get('complexity_rationale'):
                notes_parts.append(f"Complexity: {output['complexity_rationale']}")

            # Convert sources
            sources = []
            for src in sources_data:
                if src.get('url'):
                    sources.append(SourceURL(
                        url=src['url'],
                        title=src.get('title', ''),
                        source_type='jurisdiction_research',
                        relevance_score=1.0
                    ))

            return JurisdictionInfo(
                sanitary_sewer_owner=sanitary_owner,
                sanitary_sewer_operator=sanitary_operator,
                storm_drain_owner=storm_owner,
                storm_drain_operator=storm_operator,
                notes='; '.join(notes_parts) if notes_parts else '',
                sources=sources
            )

        except Exception as e:
            logger.error(f"Failed to convert output to JurisdictionInfo: {e}")
            return None
