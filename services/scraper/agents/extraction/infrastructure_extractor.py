"""
Infrastructure Extractor Agent (EX-1)

Extracts pipe infrastructure data from web sources for municipal systems.
Focuses on sanitary sewer and storm drain pipe networks.

Responsibilities:
- Extract sanitary sewer pipe data (total feet, sizes, materials)
- Extract storm drain pipe data (total feet, sizes, materials)
- Handle unit conversions (miles/km to feet)
- Require verbatim citations for all data points
- Use source map from PF-3 and terminology from PF-4
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    ExtractedDataPoint,
    ConfidenceRating
)
from services.scraper.prompts.ex1_infrastructure import get_prompt

logger = logging.getLogger(__name__)


class InfrastructureExtractorAgent(BaseAgent):
    """
    EX-1: Infrastructure Extractor Agent

    Extracts pipe infrastructure data including:
    - Sanitary sewer pipe: total length, sizes, materials
    - Storm drain pipe: total length, sizes, materials

    All data points require verbatim citations from sources.
    """

    AGENT_ID = "ex-1"
    AGENT_NAME = "Infrastructure Extractor"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-03"

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt("{{municipality_name}}", "{{state}}")

    def _extract_json_from_response(self, content: str) -> str:
        """Safely extract JSON from LLM response with validation.

        Tries multiple extraction strategies:
        1. Markdown JSON block (```json ... ```)
        2. Generic markdown block (``` ... ```)
        3. Raw JSON (first { to last })

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

    def _build_search_queries(
        self,
        municipality_name: str,
        state: str,
        terminology: Optional[Dict[str, Any]] = None
    ) -> List[tuple]:
        """
        Build search queries for infrastructure data.

        Returns list of (query, max_results) tuples.
        """
        queries = []

        # Core infrastructure searches - increased limits for comprehensive data
        queries.extend([
            # Sanitary sewer focused (PRIMARY)
            (f"{municipality_name} {state} sanitary sewer system miles feet total", 15),
            (f"{municipality_name} {state} sewer infrastructure asset inventory", 15),
            (f"{municipality_name} {state} GIS sewer pipe data", 10),
            (f"{municipality_name} {state} wastewater master plan infrastructure", 10),
            (f"{municipality_name} {state} sewer collection system miles", 10),

            # Storm drain focused
            (f"{municipality_name} {state} stormwater system miles feet total", 10),
            (f"{municipality_name} {state} storm drain infrastructure inventory", 10),
            (f"{municipality_name} {state} MS4 stormwater pipe system", 10),
            (f"{municipality_name} {state} drainage master plan", 10),

            # Combined infrastructure searches
            (f"{municipality_name} {state} utility infrastructure report", 10),
            (f"{municipality_name} {state} capital improvement plan sewer storm", 10),
            (f"{municipality_name} {state} public works infrastructure assets", 10),
        ])

        # Add terminology-based searches if provided - use all terms
        if terminology:
            sanitary_terms = terminology.get('sanitary_terms', [])
            storm_terms = terminology.get('storm_terms', [])

            for term in sanitary_terms[:10]:  # Increased from 3 to use more terms
                queries.append(
                    (f"{municipality_name} {state} {term} system miles feet", 10)
                )

            for term in storm_terms[:10]:  # Increased from 3 to use more terms
                queries.append(
                    (f"{municipality_name} {state} {term} miles feet", 10)
                )

        return queries

    async def _search_sources(
        self,
        municipality_name: str,
        state: str,
        source_map: Optional[Dict[str, Any]] = None,
        terminology: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute Tavily searches for infrastructure data.

        Uses PF-3 source map to prioritize domain searches when available.

        Args:
            municipality_name: Normalized municipality name
            state: Full state name
            source_map: Source map from PF-3 (optional)
            terminology: Terminology map from PF-4 (optional)

        Returns:
            List of search result dictionaries
        """
        all_results = []

        # Check if Tavily is configured
        if not self.config.tavily or not self.config.tavily.api_key:
            logger.warning(f"{self.AGENT_ID}: Tavily not configured — will use AI knowledge only")
            return all_results

        # Extract priority domains from source map
        priority_domains = []
        if source_map:
            # Extract domains from source map URLs
            for key in ['official_website', 'sewer_utility_page', 'stormwater_page',
                        'public_works_page', 'gis_portal']:
                source = source_map.get(key)
                if source and isinstance(source, dict) and source.get('url'):
                    url = source['url']
                    # Extract domain from URL
                    if '://' in url:
                        domain = url.split('://')[1].split('/')[0]
                        if domain not in priority_domains:
                            priority_domains.append(domain)

            # Add CIP document domains
            cip_docs = source_map.get('cip_documents', [])
            if isinstance(cip_docs, list):
                for doc in cip_docs[:3]:
                    if isinstance(doc, dict) and doc.get('url'):
                        url = doc['url']
                        if '://' in url:
                            domain = url.split('://')[1].split('/')[0]
                            if domain not in priority_domains:
                                priority_domains.append(domain)

        # Build search queries
        search_queries = self._build_search_queries(
            municipality_name, state, terminology
        )

        # If we have priority domains, include them in search
        include_domains = priority_domains[:5] if priority_domains else None

        # Try first query as availability test
        if search_queries:
            first_query, first_max = search_queries[0]
            self.emit_event("searching", f"Searching: {first_query[:50]}...")
            test_results = await self.search_tavily(
                first_query,
                include_domains=include_domains,
                max_results=first_max
            )
            if not test_results:
                logger.warning(f"{self.AGENT_ID}: Tavily unavailable — using AI knowledge")
                self.emit_event("processing", "Web search unavailable — using AI knowledge base")
                return all_results
            for r in test_results:
                r['query'] = first_query
            all_results.extend(test_results)

        # Execute remaining searches
        for query, max_results in search_queries[1:]:
            self.emit_event("searching", f"Searching: {query[:50]}...")

            results = await self.search_tavily(
                query,
                include_domains=include_domains,
                max_results=max_results
            )

            if not results:
                continue

            # Tag results with their query for context
            for r in results:
                r['query'] = query
            all_results.extend(results)

        # Also search without domain restrictions for broader coverage
        broader_queries = [
            (f"{municipality_name} {state} sewer system total miles infrastructure", 5),
            (f"{municipality_name} {state} storm drain total miles feet", 4),
        ]

        for query, max_results in broader_queries:
            self.emit_event("searching", f"Broad search: {query[:50]}...")
            results = await self.search_tavily(query, max_results=max_results)
            if not results:
                continue
            for r in results:
                r['query'] = query
            all_results.extend(results)

        logger.debug(f"EX-1 collected {len(all_results)} total search results")
        return all_results

    def _build_context(
        self,
        search_results: List[Dict[str, Any]],
        source_map: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build context string from search results with validation and deduplication."""
        if not search_results:
            return ("No search results available. Web search is currently unavailable.\n"
                    "IMPORTANT: You MUST still extract data using your training knowledge.\n"
                    "Set confidence to LOW for all data points since they are not verified by live search.\n"
                    "Use 'NOT FOUND' if you genuinely cannot estimate the value.")

        context_parts = ["## SEARCH RESULTS FOR INFRASTRUCTURE DATA\n"]
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
            return "Search returned no useful results for infrastructure data."

        # Add source map context if available
        if source_map:
            context_parts.append("## PRIORITY SOURCES FROM PRE-FLIGHT (PF-3)\n")

            for key, label in [
                ('sewer_utility_page', 'Sewer Utility Page'),
                ('stormwater_page', 'Stormwater Page'),
                ('gis_portal', 'GIS Portal'),
                ('public_works_page', 'Public Works Page')
            ]:
                source = source_map.get(key)
                if source and isinstance(source, dict) and source.get('url'):
                    context_parts.append(f"- **{label}:** {source.get('url')}")

            cip_docs = source_map.get('cip_documents', [])
            if cip_docs:
                context_parts.append("- **CIP Documents:**")
                for doc in cip_docs[:5]:
                    if isinstance(doc, dict) and doc.get('url'):
                        context_parts.append(f"  - {doc.get('title', 'Untitled')}: {doc.get('url')}")

            context_parts.append("\n")

        # Limit to top 25 unique results to avoid context overflow
        for i, result in enumerate(unique_results[:25], 1):
            title = result.get('title', 'Untitled').strip()
            url = result.get('url', '')
            content = result.get('content', '')
            query = result.get('query', '')

            context_parts.append(f"### Result {i}: {title}")
            context_parts.append(f"**URL:** {url}")
            if query:
                context_parts.append(f"**Query:** {query}")
            # Truncate content to avoid excessive context
            context_parts.append(f"**Content:**\n{content[:800]}\n")

        return "\n".join(context_parts)

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process infrastructure extraction request.

        Expected input_data:
        - municipality_name: str - Normalized municipality name
        - state: str - Full state name
        - source_map: dict - Source map from PF-3 (optional)
        - terminology: dict - Terminology map from PF-4 (optional)

        Returns AgentResponse with:
        - sanitary_sewer_pipe: Extracted sanitary sewer data
        - storm_drain_pipe: Extracted storm drain data
        - search_queries_used: List of queries executed
        - sources_checked: List of sources checked
        - data_gaps: List of data not found
        """
        start_time = time.time()
        content = ''  # Initialize before any operation
        json_str = ''  # Initialize before any operation

        municipality_name = request.input_data.get('municipality_name', '')
        state = request.input_data.get('state', '')
        source_map = request.input_data.get('source_map')
        terminology = request.input_data.get('terminology')

        # Type validation for municipality_name
        if not isinstance(municipality_name, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"municipality_name must be string, got {type(municipality_name).__name__}"]
            )

        # Type validation for state
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

        # Required field validation
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

        # Type validation for optional source_map
        if source_map is not None and not isinstance(source_map, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"source_map must be dict or null, got {type(source_map).__name__}"]
            )

        # Type validation for optional terminology
        if terminology is not None and not isinstance(terminology, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"terminology must be dict or null, got {type(terminology).__name__}"]
            )

        try:
            # Emit event for UI activity feed
            self.emit_event("processing", f"Extracting infrastructure data for {municipality_name}, {state}")

            # Search for infrastructure data using Tavily
            search_results = await self._search_sources(
                municipality_name, state, source_map, terminology
            )

            # Build context from search results
            context = self._build_context(search_results, source_map)

            # Get the prompt with input substituted
            prompt = get_prompt(municipality_name, state)

            # Build user message with search context
            user_message = f"""Extract pipe infrastructure data for: {municipality_name}, {state}

SEARCH RESULTS AND SOURCE CONTEXT:
{context}

Based on these search results, extract:
1. **Sanitary Sewer Pipe Data:**
   - Total length in feet (convert from miles/km if needed, show work)
   - Pipe size range (diameters)
   - Pipe material types
   - Verbatim citation from source

2. **Storm Drain Pipe Data:**
   - Total length in feet (convert from miles/km if needed, show work)
   - Pipe size range (diameters)
   - Pipe material types
   - Verbatim citation from source

CRITICAL REQUIREMENTS:
- Every data point MUST have a verbatim citation (exact quote from source)
- Show all unit conversion calculations
- Use "NOT FOUND" if data cannot be located
- Rate confidence based on source type and age

Return the JSON output as specified in your instructions."""

            self.emit_event("processing", "Analyzing search results for infrastructure data...")

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
                logger.warning(f"EX-1 validation failed: {errors}")
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

            # Count data points found
            data_points_found = 0
            sanitary = output_data.get('sanitary_sewer_pipe', {})
            storm = output_data.get('storm_drain_pipe', {})

            if sanitary.get('total_feet') and sanitary.get('total_feet') != 'NOT FOUND':
                data_points_found += 1
            if sanitary.get('pipe_sizes') and sanitary.get('pipe_sizes') != 'NOT FOUND':
                data_points_found += 1
            if sanitary.get('pipe_types') and sanitary.get('pipe_types') != 'NOT FOUND':
                data_points_found += 1
            if storm.get('total_feet') and storm.get('total_feet') != 'NOT FOUND':
                data_points_found += 1
            if storm.get('pipe_sizes') and storm.get('pipe_sizes') != 'NOT FOUND':
                data_points_found += 1
            if storm.get('pipe_types') and storm.get('pipe_types') != 'NOT FOUND':
                data_points_found += 1

            # Emit completion event with summary
            self.emit_event(
                "completed",
                f"Extracted {data_points_found} infrastructure data points",
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
            logger.error(f"EX-1 JSON extraction failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'extraction_error': str(e), 'raw_response': content[:1000] if content else ''},
                errors=[f"JSON extraction error: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )
        except json.JSONDecodeError as e:
            logger.error(f"EX-1 JSON parse failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'parse_error': str(e), 'attempted_json': json_str[:500] if json_str else ''},
                errors=[f"JSON parse error at position {e.pos}: {e.msg}"],
                processing_time_seconds=time.time() - start_time
            )
        except Exception as e:
            logger.exception(f"EX-1 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate infrastructure extraction output against spec."""
        errors = []

        # Check required top-level fields
        if 'sanitary_sewer_pipe' not in output:
            errors.append("Missing 'sanitary_sewer_pipe' section")

        if 'storm_drain_pipe' not in output:
            errors.append("Missing 'storm_drain_pipe' section")

        # Return early if missing required sections
        if errors:
            return errors

        # Validate sanitary_sewer_pipe structure
        sanitary = output.get('sanitary_sewer_pipe', {})
        if not isinstance(sanitary, dict):
            errors.append("'sanitary_sewer_pipe' must be a dictionary")
        else:
            sanitary_errors = self._validate_pipe_section(sanitary, 'sanitary_sewer_pipe')
            errors.extend(sanitary_errors)

        # Validate storm_drain_pipe structure
        storm = output.get('storm_drain_pipe', {})
        if not isinstance(storm, dict):
            errors.append("'storm_drain_pipe' must be a dictionary")
        else:
            storm_errors = self._validate_pipe_section(storm, 'storm_drain_pipe')
            errors.extend(storm_errors)

        # Validate data_gaps is a list if present
        data_gaps = output.get('data_gaps')
        if data_gaps is not None and not isinstance(data_gaps, list):
            errors.append("'data_gaps' must be a list")

        # Validate sources_checked is a list if present
        sources_checked = output.get('sources_checked')
        if sources_checked is not None and not isinstance(sources_checked, list):
            errors.append("'sources_checked' must be a list")

        # Validate search_queries_used is a list if present
        search_queries = output.get('search_queries_used')
        if search_queries is not None and not isinstance(search_queries, list):
            errors.append("'search_queries_used' must be a list")

        return errors

    def _validate_pipe_section(self, section: Dict[str, Any], section_name: str) -> List[str]:
        """Validate a pipe data section (sanitary or storm)."""
        errors = []

        # Required fields
        required_fields = ['total_feet', 'pipe_sizes', 'pipe_types', 'confidence']

        for field in required_fields:
            if field not in section:
                errors.append(f"{section_name} missing required field: {field}")

        # Validate confidence value
        confidence = section.get('confidence')
        if confidence and confidence not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append(f"{section_name} invalid confidence: {confidence}")

        # If data was found (not "NOT FOUND"), require verbatim citation
        total_feet = section.get('total_feet', '')
        if total_feet and total_feet != 'NOT FOUND':
            verbatim = section.get('verbatim_citation')
            if not verbatim:
                errors.append(f"{section_name} has data but missing verbatim_citation")

            source_url = section.get('source_url')
            if not source_url:
                errors.append(f"{section_name} has data but missing source_url")

        return errors

    def to_extracted_data_points(self, output: Dict[str, Any]) -> Dict[str, ExtractedDataPoint]:
        """
        Convert validated output to ExtractedDataPoint model objects.

        Args:
            output: Validated output from process()

        Returns:
            Dict mapping field names to ExtractedDataPoint objects
        """
        data_points = {}

        def confidence_str_to_enum(conf_str: str) -> ConfidenceRating:
            """Convert confidence string to enum."""
            mapping = {
                'HIGH': ConfidenceRating.HIGH,
                'MEDIUM': ConfidenceRating.MEDIUM,
                'LOW': ConfidenceRating.LOW
            }
            return mapping.get(conf_str, ConfidenceRating.MEDIUM)

        # Convert sanitary sewer pipe
        sanitary = output.get('sanitary_sewer_pipe', {})
        if sanitary:
            data_points['sanitary_sewer_pipe'] = ExtractedDataPoint(
                field_name='sanitary_sewer_pipe',
                value=self._format_pipe_value(sanitary),
                raw_source_value=sanitary.get('raw_data_found'),
                conversion_applied=sanitary.get('conversion_applied'),
                source_url=sanitary.get('source_url', ''),
                verbatim_quote=sanitary.get('verbatim_citation', ''),
                confidence=confidence_str_to_enum(sanitary.get('confidence', 'MEDIUM')),
                confidence_rationale=sanitary.get('confidence_rationale', ''),
                notes=sanitary.get('notes')
            )

        # Convert storm drain pipe
        storm = output.get('storm_drain_pipe', {})
        if storm:
            data_points['storm_drain_pipe'] = ExtractedDataPoint(
                field_name='storm_drain_pipe',
                value=self._format_pipe_value(storm),
                raw_source_value=storm.get('raw_data_found'),
                conversion_applied=storm.get('conversion_applied'),
                source_url=storm.get('source_url', ''),
                verbatim_quote=storm.get('verbatim_citation', ''),
                confidence=confidence_str_to_enum(storm.get('confidence', 'MEDIUM')),
                confidence_rationale=storm.get('confidence_rationale', ''),
                notes=storm.get('notes')
            )

        return data_points

    def _format_pipe_value(self, pipe_data: Dict[str, Any]) -> str:
        """Format pipe data into a single display value."""
        total = pipe_data.get('total_feet', 'NOT FOUND')
        sizes = pipe_data.get('pipe_sizes', 'NOT FOUND')
        types = pipe_data.get('pipe_types', 'NOT FOUND')

        if total == 'NOT FOUND' and sizes == 'NOT FOUND' and types == 'NOT FOUND':
            return 'NOT FOUND'

        parts = []
        if total and total != 'NOT FOUND':
            parts.append(f"Total: {total}")
        if sizes and sizes != 'NOT FOUND':
            parts.append(f"Sizes: {sizes}")
        if types and types != 'NOT FOUND':
            parts.append(f"Types: {types}")

        return "; ".join(parts) if parts else 'NOT FOUND'
