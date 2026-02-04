"""
Source Discovery Agent (PF-3)

Builds baseline source map for a municipality before extraction.
Identifies official websites, department pages, portals, and document repositories.

Responsibilities:
- Discover official municipal web presence
- Find sewer/wastewater sources (PRIMARY - 70% effort)
- Locate procurement portals and GIS systems
- Identify CIP and compliance document sources
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    SourceMap,
    SourceURL
)
from services.scraper.prompts.pf3_source_discovery import get_prompt

logger = logging.getLogger(__name__)


class SourceDiscoveryAgent(BaseAgent):
    """
    PF-3: Source Discovery Agent

    Builds comprehensive source map for municipal data extraction.
    Sewer/wastewater sources are the PRIMARY focus (70% of effort).
    """

    AGENT_ID = "pf-3"
    AGENT_NAME = "Source Discovery"
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

    async def _discover_sources(
        self,
        municipality_name: str,
        state: str
    ) -> List[Dict[str, Any]]:
        """
        Execute Tavily searches for source discovery.

        Follows the 70/30 effort split: sewer/wastewater (primary) vs other sources (secondary).

        Args:
            municipality_name: Normalized municipality name
            state: Full state name

        Returns:
            List of search result dictionaries
        """
        all_results = []

        # Search queries organized by priority with (query, max_results)
        # Sewer/Wastewater is PRIMARY - 70% effort (more queries, more results)
        search_configs = [
            # 1. Official Website (required baseline)
            (f"{municipality_name} {state} official website city government", 3),

            # 2. Public Works Department
            (f"{municipality_name} {state} public works utilities department", 3),

            # 3. Sewer/Wastewater (PRIMARY - 70% effort, more results)
            (f"{municipality_name} {state} sewer utility wastewater", 5),
            (f"{municipality_name} {state} sanitary sewer service department", 5),
            (f"{municipality_name} {state} wastewater treatment utility", 4),

            # 4. Stormwater (secondary)
            (f"{municipality_name} {state} stormwater drainage MS4", 3),
            (f"{municipality_name} {state} storm drain utility", 3),

            # 5. Procurement/Bid Portal
            (f"{municipality_name} {state} bid portal procurement RFP", 4),
            (f"{municipality_name} {state} public bids contracts purchasing", 3),

            # 6. GIS Portal
            (f"{municipality_name} {state} GIS map interactive viewer", 3),
            (f"{municipality_name} {state} ArcGIS infrastructure map", 3),

            # 7. CIP/Budget Documents
            (f"{municipality_name} {state} capital improvement plan CIP budget", 4),
            (f"{municipality_name} {state} infrastructure master plan", 3),

            # 8. Compliance Sources
            (f"{municipality_name} {state} SSO CMOM EPA compliance sewer", 3),
            (f"{municipality_name} {state} NPDES permit wastewater", 2),
        ]

        for query, max_results in search_configs:
            self.emit_event("searching", f"Searching: {query[:50]}...")
            results = await self.search_tavily(query, max_results=max_results)
            # Tag results with their query for context
            for r in results:
                r['query'] = query
            all_results.extend(results)

        logger.debug(f"PF-3 discovered {len(all_results)} total search results")
        return all_results

    def _build_context(self, search_results: List[Dict[str, Any]]) -> str:
        """Build context string from search results with validation and deduplication."""
        if not search_results:
            return "No search results available."

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
        Process source discovery request.

        Expected input_data:
        - municipality_name: str - Normalized municipality name (e.g., "Springfield")
        - state: str - Full state name (e.g., "Illinois")

        Returns AgentResponse with:
        - source_map: Discovered sources organized by category
        - sources_discovered_count: Counts by category
        - confidence: Overall confidence rating
        - gaps: Source categories not found
        - recommendations: Suggestions for finding missing sources
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
            self.emit_event("processing", f"Discovering sources for {municipality_name}, {state}")

            # Discover sources via Tavily searches
            search_results = await self._discover_sources(municipality_name, state)

            # Build context from search results
            context = self._build_context(search_results)

            # Get the prompt with input substituted
            prompt = get_prompt(municipality_name, state)

            # Build user message with search context
            user_message = f"""Discover and map data sources for: {municipality_name}, {state}

SEARCH RESULTS TO ANALYZE:
{context}

Based on these search results, build a comprehensive source map identifying:
- Official website
- Public works/utilities pages
- Sewer/wastewater utility pages (PRIMARY FOCUS)
- Stormwater pages
- Procurement/bid portal
- GIS portal
- CIP/budget documents
- Compliance sources

Return the JSON source map as specified in your instructions."""

            self.emit_event("processing", "Analyzing search results...")

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
                logger.warning(f"PF-3 validation failed: {errors}")
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
            sources_count = output_data.get('sources_discovered_count', {})
            total_count = sources_count.get('total', 0) if isinstance(sources_count, dict) else sources_count
            confidence = output_data.get('confidence', 'UNKNOWN')

            self.emit_event(
                "completed",
                f"Discovered {total_count} sources ({confidence} confidence)",
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
            logger.error(f"PF-3 JSON extraction failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'extraction_error': str(e), 'raw_response': content[:1000] if content else ''},
                errors=[f"JSON extraction error: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )
        except json.JSONDecodeError as e:
            logger.error(f"PF-3 JSON parse failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'parse_error': str(e), 'attempted_json': json_str[:500] if json_str else ''},
                errors=[f"JSON parse error at position {e.pos}: {e.msg}"],
                processing_time_seconds=time.time() - start_time
            )
        except Exception as e:
            logger.exception(f"PF-3 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate source discovery output against spec."""
        errors = []

        # Check source_map exists
        if 'source_map' not in output:
            errors.append("Missing 'source_map' section")
            return errors

        source_map = output['source_map']

        # Check key source categories exist (can be null if not found)
        required_categories = ['official_website', 'sewer_utility_page']
        for cat in required_categories:
            if cat not in source_map:
                errors.append(f"Missing required source category: {cat}")

        # Validate official_website has URL if not null
        official = source_map.get('official_website')
        if official is not None and not official.get('url'):
            errors.append("official_website present but missing 'url' field")

        # Validate sewer_utility_page (PRIMARY focus)
        sewer = source_map.get('sewer_utility_page')
        if sewer is not None and not isinstance(sewer, dict):
            errors.append("sewer_utility_page must be a dictionary or null")

        # Validate confidence
        confidence = output.get('confidence')
        if not confidence:
            errors.append("Missing required 'confidence' field")
        elif confidence not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append(f"Invalid confidence: {confidence}")

        # Validate sources_discovered_count is present
        if 'sources_discovered_count' not in output:
            errors.append("Missing 'sources_discovered_count' field")

        # Validate gaps and recommendations are lists
        gaps = output.get('gaps')
        if gaps is not None and not isinstance(gaps, list):
            errors.append("'gaps' must be a list")

        recommendations = output.get('recommendations')
        if recommendations is not None and not isinstance(recommendations, list):
            errors.append("'recommendations' must be a list")

        # Validate cip_documents is a list if present
        cip_docs = source_map.get('cip_documents')
        if cip_docs is not None and not isinstance(cip_docs, list):
            errors.append("'cip_documents' must be a list")

        # Validate compliance_sources is a list if present
        compliance = source_map.get('compliance_sources')
        if compliance is not None and not isinstance(compliance, list):
            errors.append("'compliance_sources' must be a list")

        return errors

    def to_source_map(self, output: Dict[str, Any]) -> Optional[SourceMap]:
        """
        Convert validated output to SourceMap model object.

        Args:
            output: Validated output from process()

        Returns:
            SourceMap object or None if conversion fails
        """
        try:
            source_map_data = output.get('source_map', {})

            def make_source_url(data: Optional[Dict], source_type: str) -> Optional[SourceURL]:
                """Helper to create SourceURL from data dict."""
                if not data or not data.get('url'):
                    return None
                return SourceURL(
                    url=data['url'],
                    title=data.get('title', ''),
                    source_type=source_type,
                    relevance_score=1.0
                )

            # Build SourceMap from output
            return SourceMap(
                official_website=make_source_url(
                    source_map_data.get('official_website'), 'official'
                ),
                public_works_page=make_source_url(
                    source_map_data.get('public_works_page'), 'public_works'
                ),
                sewer_utility_page=make_source_url(
                    source_map_data.get('sewer_utility_page'), 'sewer'
                ),
                stormwater_page=make_source_url(
                    source_map_data.get('stormwater_page'), 'stormwater'
                ),
                procurement_page=make_source_url(
                    source_map_data.get('procurement_portal'), 'procurement'
                ),
                gis_portal=make_source_url(
                    source_map_data.get('gis_portal'), 'gis'
                ),
                cip_documents=[
                    SourceURL(
                        url=doc.get('url', ''),
                        title=doc.get('title', ''),
                        source_type='cip',
                        relevance_score=1.0
                    )
                    for doc in source_map_data.get('cip_documents', [])
                    if doc.get('url')
                ],
                compliance_sources=[
                    SourceURL(
                        url=src.get('url', ''),
                        title=src.get('title', ''),
                        source_type=src.get('source_type', 'compliance'),
                        relevance_score=1.0
                    )
                    for src in source_map_data.get('compliance_sources', [])
                    if src.get('url')
                ]
            )

        except Exception as e:
            logger.error(f"Failed to convert output to SourceMap: {e}")
            return None
