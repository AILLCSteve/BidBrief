"""
Incident Extractor Agent (EX-4) [PRIORITY]

Extracts incident and compliance data from web sources for municipal systems.
Focuses on SSOs, stoppages, pipe breaks, flooding, costs/fines, and environmental impacts.

This is a PRIORITY agent per schema spec - requires EXTRA search effort.

Responsibilities:
- Extract SSO (Sanitary Sewer Overflow) events with counts and dates
- Extract stoppage and pipe break incidents
- Extract storm drain flooding and clogged drain incidents
- Extract costs, fines, consent decrees
- Extract environmental impacts, waterways affected, volumes
- Extract customer complaints
- Search CMOM/SSO reports, consent orders, EPA ECHO, news
- Maps to schema columns 8 AND 9 (sewage and storm incidents)
- Requires verbatim citations for all data points
- EXTRA THOROUGH SEARCHING - more queries than typical agents (20+)
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
from services.scraper.prompts.ex4_incident import get_prompt

logger = logging.getLogger(__name__)


class IncidentExtractorAgent(BaseAgent):
    """
    EX-4: Incident Extractor Agent [PRIORITY]

    Extracts municipal incident and compliance data including:
    - SSO (Sanitary Sewer Overflow) events
    - Stoppages and pipe break incidents
    - Storm drain flooding and clogged drain events
    - Costs, fines, and consent decrees
    - Environmental impacts and complaints

    This agent performs EXTRA THOROUGH searching per schema priority.
    All data points require verbatim citations from sources.
    Maps to schema columns 8 (sewage incidents) and 9 (storm incidents).
    """

    AGENT_ID = "ex-4"
    AGENT_NAME = "Incident Extractor"
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
        Build search queries for incident and compliance data.

        PRIORITY: This agent executes MORE searches than typical agents (20+).

        Returns list of (query, max_results) tuples.
        """
        queries = []

        # ==============================================================
        # SEWAGE INCIDENT SEARCHES (Schema Column 8) - PRIMARY PRIORITY
        # ==============================================================

        # SSO/Overflow focused (HIGHEST PRIORITY)
        queries.extend([
            (f"{municipality_name} {state} SSO sanitary sewer overflow report", 5),
            (f"{municipality_name} {state} sewer overflow incident spill", 5),
            (f"{municipality_name} {state} sewage spill discharge release", 5),
            (f"{municipality_name} {state} sewer overflow EPA violation", 4),
            (f"{municipality_name} {state} SSO annual report count", 4),
        ])

        # Regulatory and compliance focused
        queries.extend([
            (f"{municipality_name} {state} EPA ECHO enforcement wastewater", 5),
            (f"{municipality_name} {state} NPDES violation sewer wastewater", 5),
            (f"{municipality_name} {state} consent decree sewer EPA", 5),
            (f"{municipality_name} {state} consent order wastewater violation", 4),
            (f"{state} environmental agency {municipality_name} sewer violation", 4),
        ])

        # CMOM/Compliance reporting focused
        queries.extend([
            (f"{municipality_name} {state} CMOM SSO report overflow", 5),
            (f"{municipality_name} {state} sewer overflow compliance report", 4),
            (f"{municipality_name} {state} wastewater compliance annual report", 4),
        ])

        # Stoppage and pipe break focused
        queries.extend([
            (f"{municipality_name} {state} sewer stoppage blockage backup", 5),
            (f"{municipality_name} {state} sewer main break emergency", 4),
            (f"{municipality_name} {state} pipe break sewer collapse", 4),
            (f"{municipality_name} {state} sewer backup flooding basement", 4),
        ])

        # Costs and fines focused
        queries.extend([
            (f"{municipality_name} {state} sewer fine penalty EPA", 5),
            (f"{municipality_name} {state} environmental fine sewer violation", 4),
            (f"{municipality_name} {state} consent decree penalty wastewater", 4),
        ])

        # Environmental impact focused
        queries.extend([
            (f"{municipality_name} {state} sewage release waterway river creek", 4),
            (f"{municipality_name} {state} sewer overflow environmental impact", 4),
            (f"{municipality_name} {state} raw sewage discharge gallons", 4),
        ])

        # ==============================================================
        # STORM DRAIN INCIDENT SEARCHES (Schema Column 9) - PRIORITY
        # ==============================================================

        # Flooding events focused
        queries.extend([
            (f"{municipality_name} {state} street flooding storm drain", 5),
            (f"{municipality_name} {state} storm drain overflow flooding", 5),
            (f"{municipality_name} {state} flash flood drainage problem", 4),
            (f"{municipality_name} {state} flooding complaint storm sewer", 4),
        ])

        # Clogged drains focused
        queries.extend([
            (f"{municipality_name} {state} clogged storm drain debris", 4),
            (f"{municipality_name} {state} storm drain blockage maintenance", 4),
            (f"{municipality_name} {state} drainage infrastructure problem", 4),
        ])

        # Storm system costs/fines
        queries.extend([
            (f"{municipality_name} {state} stormwater violation fine MS4", 4),
            (f"{municipality_name} {state} storm drain damage costs repair", 3),
        ])

        # ==============================================================
        # NEWS AND PUBLIC RECORDS SEARCHES
        # ==============================================================

        queries.extend([
            (f"{municipality_name} {state} sewer overflow news recent", 4),
            (f"{municipality_name} {state} sewage spill news report", 4),
            (f"{municipality_name} {state} flooding complaint resident", 3),
            (f"{municipality_name} {state} sewer problem complaint citizen", 3),
        ])

        # Add terminology-based searches if provided
        if terminology:
            sanitary_terms = terminology.get('sanitary_terms', [])
            storm_terms = terminology.get('storm_terms', [])

            for term in sanitary_terms[:2]:  # Limit to top 2 terms
                queries.append(
                    (f"{municipality_name} {state} {term} overflow incident", 3)
                )

            for term in storm_terms[:2]:
                queries.append(
                    (f"{municipality_name} {state} {term} flooding problem", 3)
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
        Execute Tavily searches for incident and compliance data.

        PRIORITY: This agent performs EXTRA THOROUGH searching.

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

        # Extract priority domains from source map
        priority_domains = []
        if source_map:
            # Extract domains from source map URLs
            for key in ['official_website', 'sewer_utility_page', 'public_works_page',
                        'stormwater_page', 'environmental_page']:
                source = source_map.get(key)
                if source and isinstance(source, dict) and source.get('url'):
                    url = source['url']
                    # Extract domain from URL
                    if '://' in url:
                        domain = url.split('://')[1].split('/')[0]
                        if domain not in priority_domains:
                            priority_domains.append(domain)

            # Add compliance source domains (CMOM, SSO reports)
            compliance_sources = source_map.get('compliance_sources', [])
            if isinstance(compliance_sources, list):
                for source in compliance_sources[:5]:
                    if isinstance(source, dict) and source.get('url'):
                        url = source['url']
                        if '://' in url:
                            domain = url.split('://')[1].split('/')[0]
                            if domain not in priority_domains:
                                priority_domains.append(domain)

        # Build search queries - EXTRA THOROUGH for PRIORITY agent
        search_queries = self._build_search_queries(
            municipality_name, state, terminology
        )

        self.emit_event("processing", f"PRIORITY: Executing {len(search_queries)} thorough incident searches...")

        # Execute searches
        for query, max_results in search_queries:
            self.emit_event("searching", f"Searching: {query[:50]}...")

            # If we have priority domains, include them in search
            include_domains = priority_domains[:5] if priority_domains else None

            results = await self.search_tavily(
                query,
                include_domains=include_domains,
                max_results=max_results
            )

            # Tag results with their query for context
            for r in results:
                r['query'] = query
            all_results.extend(results)

        # ==============================================================
        # ADDITIONAL BROAD SEARCHES - EXTRA EFFORT for PRIORITY agent
        # ==============================================================

        broader_queries = [
            (f"{municipality_name} {state} sewer system emergency incident history", 5),
            (f"{municipality_name} {state} stormwater flooding problems complaints", 5),
            (f"{municipality_name} {state} EPA enforcement action sewer", 4),
            (f"site:epa.gov {municipality_name} {state} wastewater enforcement", 4),
            (f"{municipality_name} {state} sanitary sewer overflow notification", 4),
        ]

        for query, max_results in broader_queries:
            self.emit_event("searching", f"Broad search: {query[:50]}...")
            results = await self.search_tavily(query, max_results=max_results)
            for r in results:
                r['query'] = query
            all_results.extend(results)

        logger.debug(f"EX-4 PRIORITY collected {len(all_results)} total search results")
        return all_results

    def _build_context(
        self,
        search_results: List[Dict[str, Any]],
        source_map: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build context string from search results with validation and deduplication."""
        if not search_results:
            return "No search results available."

        context_parts = ["## SEARCH RESULTS FOR INCIDENT AND COMPLIANCE DATA\n"]
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
            return "Search returned no useful results for incident data."

        # Add source map context if available
        if source_map:
            context_parts.append("## PRIORITY SOURCES FROM PRE-FLIGHT (PF-3)\n")

            for key, label in [
                ('sewer_utility_page', 'Sewer Utility Page'),
                ('stormwater_page', 'Stormwater Page'),
                ('public_works_page', 'Public Works Page'),
                ('environmental_page', 'Environmental Page')
            ]:
                source = source_map.get(key)
                if source and isinstance(source, dict) and source.get('url'):
                    context_parts.append(f"- **{label}:** {source.get('url')}")

            # Add compliance sources (often have SSO/incident info)
            compliance_sources = source_map.get('compliance_sources', [])
            if compliance_sources:
                context_parts.append("- **Compliance Sources:**")
                for source in compliance_sources[:5]:
                    if isinstance(source, dict) and source.get('url'):
                        context_parts.append(f"  - {source.get('title', 'Untitled')}: {source.get('url')}")

            context_parts.append("\n")

        # Limit to top 30 unique results (more than other agents due to PRIORITY)
        for i, result in enumerate(unique_results[:30], 1):
            title = result.get('title', 'Untitled').strip()
            url = result.get('url', '')
            content = result.get('content', '')
            query = result.get('query', '')

            context_parts.append(f"### Result {i}: {title}")
            context_parts.append(f"**URL:** {url}")
            if query:
                context_parts.append(f"**Query:** {query}")
            # Truncate content to avoid excessive context
            context_parts.append(f"**Content:**\n{content[:900]}\n")

        return "\n".join(context_parts)

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process incident and compliance extraction request.

        PRIORITY AGENT: Performs extra thorough searching.

        Expected input_data:
        - municipality_name: str - Normalized municipality name
        - state: str - Full state name
        - source_map: dict - Source map from PF-3 (optional)
        - terminology: dict - Terminology map from PF-4 (optional)

        Returns AgentResponse with:
        - sewage_incidents: Dict with SSO, stoppage, pipe break, cost, impact data
        - storm_incidents: Dict with flooding, clogged drain, cost data
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
            # Emit event for UI activity feed - PRIORITY emphasis
            self.emit_event("processing", f"[PRIORITY] Extracting incident data for {municipality_name}, {state}")

            # Search for incident data using Tavily - EXTRA THOROUGH
            search_results = await self._search_sources(
                municipality_name, state, source_map, terminology
            )

            # Build context from search results
            context = self._build_context(search_results, source_map)

            # Get the prompt with input substituted
            prompt = get_prompt(municipality_name, state)

            # Build user message with search context
            user_message = f"""Extract incident and compliance data for: {municipality_name}, {state}

SEARCH RESULTS AND SOURCE CONTEXT:
{context}

Based on these search results, extract:

1. **SEWAGE INCIDENTS (Schema Column 8):**
   - SSO Events: count, frequency, recent events with dates
   - Stoppages: count, causes (FOG, roots, debris)
   - Pipe Breaks: count, locations
   - Costs/Fines: total costs, fines/penalties, consent decree status
   - Environmental Impacts: waterways affected, volume released
   - Complaints: count, types
   - Verbatim citations for ALL data points

2. **STORM INCIDENTS (Schema Column 9):**
   - Flooding Events: count, locations, frequency
   - Clogged Drains: count, problem areas
   - Costs/Fines: damage costs, fines
   - Complaints: count, types
   - Verbatim citations for ALL data points

CRITICAL REQUIREMENTS:
- Every data point MUST have a verbatim citation (exact quote from source)
- Capture DATES for all incidents when available
- QUANTIFY: Number of SSOs, gallons released, fine amounts
- Use "NOT FOUND" if data cannot be located
- Rate confidence based on source type: EPA ECHO/consent decrees = HIGH, CMOM = MEDIUM, news = LOW
- Do NOT infer incidents - only report explicitly documented events

Return the JSON output as specified in your instructions."""

            self.emit_event("processing", "[PRIORITY] Analyzing search results for incident data...")

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
                logger.warning(f"EX-4 validation failed: {errors}")
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
            data_points_found = self._count_data_points_found(output_data)

            # Emit completion event with summary
            self.emit_event(
                "completed",
                f"[PRIORITY] Extracted {data_points_found} incident data points",
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
            logger.error(f"EX-4 JSON extraction failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'extraction_error': str(e), 'raw_response': content[:1000] if content else ''},
                errors=[f"JSON extraction error: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )
        except json.JSONDecodeError as e:
            logger.error(f"EX-4 JSON parse failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'parse_error': str(e), 'attempted_json': json_str[:500] if json_str else ''},
                errors=[f"JSON parse error at position {e.pos}: {e.msg}"],
                processing_time_seconds=time.time() - start_time
            )
        except Exception as e:
            logger.exception(f"EX-4 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def _count_data_points_found(self, output_data: Dict[str, Any]) -> int:
        """Count the number of incident data points with actual data."""
        count = 0

        # Count sewage incidents
        sewage = output_data.get('sewage_incidents', {})
        if isinstance(sewage, dict):
            for category in ['sso_events', 'stoppages', 'pipe_breaks', 'costs_fines',
                           'environmental_impacts', 'complaints']:
                cat_data = sewage.get(category, {})
                if isinstance(cat_data, dict):
                    # Check primary field for data
                    primary = cat_data.get('count') or cat_data.get('total_costs') or cat_data.get('description')
                    if primary and not str(primary).startswith('NOT FOUND'):
                        count += 1

        # Count storm incidents
        storm = output_data.get('storm_incidents', {})
        if isinstance(storm, dict):
            for category in ['flooding_events', 'clogged_drains', 'costs_fines', 'complaints']:
                cat_data = storm.get(category, {})
                if isinstance(cat_data, dict):
                    # Check primary field for data
                    primary = cat_data.get('count') or cat_data.get('damage_costs')
                    if primary and not str(primary).startswith('NOT FOUND'):
                        count += 1

        return count

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate incident extraction output against spec."""
        errors = []

        # Check required top-level fields
        if 'sewage_incidents' not in output:
            errors.append("Missing 'sewage_incidents' section")

        if 'storm_incidents' not in output:
            errors.append("Missing 'storm_incidents' section")

        # Return early if missing required sections
        if errors:
            return errors

        # Validate sewage_incidents structure
        sewage = output.get('sewage_incidents', {})
        if not isinstance(sewage, dict):
            errors.append("'sewage_incidents' must be a dictionary")
        else:
            sewage_categories = ['sso_events', 'stoppages', 'pipe_breaks',
                               'costs_fines', 'environmental_impacts', 'complaints']
            for category in sewage_categories:
                if category not in sewage:
                    errors.append(f"sewage_incidents missing category: {category}")
                else:
                    cat_data = sewage.get(category, {})
                    if not isinstance(cat_data, dict):
                        errors.append(f"sewage_incidents.{category} must be a dictionary")
                    else:
                        cat_errors = self._validate_incident_category(cat_data, f"sewage_incidents.{category}")
                        errors.extend(cat_errors)

        # Validate storm_incidents structure
        storm = output.get('storm_incidents', {})
        if not isinstance(storm, dict):
            errors.append("'storm_incidents' must be a dictionary")
        else:
            storm_categories = ['flooding_events', 'clogged_drains', 'costs_fines', 'complaints']
            for category in storm_categories:
                if category not in storm:
                    errors.append(f"storm_incidents missing category: {category}")
                else:
                    cat_data = storm.get(category, {})
                    if not isinstance(cat_data, dict):
                        errors.append(f"storm_incidents.{category} must be a dictionary")
                    else:
                        cat_errors = self._validate_incident_category(cat_data, f"storm_incidents.{category}")
                        errors.extend(cat_errors)

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

    def _validate_incident_category(self, category: Dict[str, Any], category_name: str) -> List[str]:
        """Validate an incident category section."""
        errors = []

        # Validate confidence value
        confidence = category.get('confidence')
        if confidence and confidence not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append(f"{category_name} invalid confidence: {confidence}")

        # Determine primary data field based on category
        primary_field = None
        if 'count' in category:
            primary_field = category.get('count', '')
        elif 'total_costs' in category:
            primary_field = category.get('total_costs', '')
        elif 'damage_costs' in category:
            primary_field = category.get('damage_costs', '')
        elif 'description' in category:
            primary_field = category.get('description', '')

        # If data was found (not "NOT FOUND"), require verbatim citation
        if primary_field and not str(primary_field).startswith('NOT FOUND'):
            verbatim = category.get('verbatim_citation')
            if not verbatim:
                errors.append(f"{category_name} has data but missing verbatim_citation")

            source_url = category.get('source_url')
            if not source_url:
                errors.append(f"{category_name} has data but missing source_url")

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

        # Convert sewage_incidents (Schema Column 8)
        sewage = output.get('sewage_incidents', {})
        if sewage:
            data_points['sewage_incidents'] = ExtractedDataPoint(
                field_name='sewage_incidents',
                value=self._format_sewage_incidents(sewage),
                raw_source_value=self._get_primary_citation(sewage),
                source_url=self._get_best_source_url(sewage),
                verbatim_quote=self._get_best_citation(sewage),
                confidence=confidence_str_to_enum(self._get_best_confidence(sewage)),
                confidence_rationale=f"Sewage incident data from {self._count_sewage_sources(sewage)} sources",
                notes=self._get_sewage_notes(sewage)
            )

        # Convert storm_incidents (Schema Column 9)
        storm = output.get('storm_incidents', {})
        if storm:
            data_points['storm_incidents'] = ExtractedDataPoint(
                field_name='storm_incidents',
                value=self._format_storm_incidents(storm),
                raw_source_value=self._get_primary_citation(storm),
                source_url=self._get_best_source_url(storm),
                verbatim_quote=self._get_best_citation(storm),
                confidence=confidence_str_to_enum(self._get_best_confidence(storm)),
                confidence_rationale=f"Storm incident data from {self._count_storm_sources(storm)} sources",
                notes=self._get_storm_notes(storm)
            )

        return data_points

    def _format_sewage_incidents(self, sewage: Dict[str, Any]) -> str:
        """Format sewage incident data into a combined value for schema column 8."""
        parts = []

        # SSO events
        sso = sewage.get('sso_events', {})
        if isinstance(sso, dict):
            count = sso.get('count', 'NOT FOUND')
            if count and not str(count).startswith('NOT FOUND'):
                freq = sso.get('frequency', '')
                if freq:
                    parts.append(f"SSOs: {count} ({freq})")
                else:
                    parts.append(f"SSOs: {count}")

        # Stoppages
        stoppages = sewage.get('stoppages', {})
        if isinstance(stoppages, dict):
            count = stoppages.get('count', 'NOT FOUND')
            if count and not str(count).startswith('NOT FOUND'):
                parts.append(f"Stoppages: {count}")

        # Pipe breaks
        breaks = sewage.get('pipe_breaks', {})
        if isinstance(breaks, dict):
            count = breaks.get('count', 'NOT FOUND')
            if count and not str(count).startswith('NOT FOUND'):
                parts.append(f"Pipe breaks: {count}")

        # Costs/fines
        costs = sewage.get('costs_fines', {})
        if isinstance(costs, dict):
            fines = costs.get('fines_penalties', 'NOT FOUND')
            consent = costs.get('consent_decree', 'NOT FOUND')
            if fines and not str(fines).startswith('NOT FOUND'):
                parts.append(f"Fines: {fines}")
            if consent and consent not in ['NOT FOUND', 'No']:
                parts.append(f"Consent decree: {consent[:50]}")

        # Environmental impacts
        env = sewage.get('environmental_impacts', {})
        if isinstance(env, dict):
            volume = env.get('volume_released', 'NOT FOUND')
            if volume and not str(volume).startswith('NOT FOUND'):
                parts.append(f"Volume released: {volume}")

        if not parts:
            return 'NOT FOUND'

        return "; ".join(parts)

    def _format_storm_incidents(self, storm: Dict[str, Any]) -> str:
        """Format storm incident data into a combined value for schema column 9."""
        parts = []

        # Flooding events
        flooding = storm.get('flooding_events', {})
        if isinstance(flooding, dict):
            count = flooding.get('count', 'NOT FOUND')
            if count and not str(count).startswith('NOT FOUND'):
                freq = flooding.get('frequency', '')
                if freq:
                    parts.append(f"Flooding events: {count} ({freq})")
                else:
                    parts.append(f"Flooding events: {count}")

        # Clogged drains
        clogged = storm.get('clogged_drains', {})
        if isinstance(clogged, dict):
            count = clogged.get('count', 'NOT FOUND')
            if count and not str(count).startswith('NOT FOUND'):
                parts.append(f"Clogged drains: {count}")

        # Costs/fines
        costs = storm.get('costs_fines', {})
        if isinstance(costs, dict):
            damage = costs.get('damage_costs', 'NOT FOUND')
            if damage and not str(damage).startswith('NOT FOUND'):
                parts.append(f"Damage costs: {damage}")

        # Complaints
        complaints = storm.get('complaints', {})
        if isinstance(complaints, dict):
            count = complaints.get('count', 'NOT FOUND')
            if count and not str(count).startswith('NOT FOUND'):
                parts.append(f"Complaints: {count}")

        if not parts:
            return 'NOT FOUND'

        return "; ".join(parts)

    def _get_primary_citation(self, incidents: Dict[str, Any]) -> Optional[str]:
        """Get the primary citation from incident data."""
        for category in incidents.values():
            if isinstance(category, dict):
                citation = category.get('verbatim_citation')
                if citation:
                    return citation
        return None

    def _get_best_source_url(self, incidents: Dict[str, Any]) -> str:
        """Get the best source URL from incident data."""
        confidence_rank = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
        best_url = ''
        best_conf = 0

        for category in incidents.values():
            if isinstance(category, dict):
                conf = category.get('confidence', 'LOW')
                conf_rank = confidence_rank.get(conf, 0)
                if conf_rank > best_conf and category.get('source_url'):
                    best_url = category['source_url']
                    best_conf = conf_rank

        return best_url

    def _get_best_citation(self, incidents: Dict[str, Any]) -> str:
        """Get the best verbatim citation from incident data."""
        confidence_rank = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
        best_citation = ''
        best_conf = 0

        for category in incidents.values():
            if isinstance(category, dict):
                conf = category.get('confidence', 'LOW')
                conf_rank = confidence_rank.get(conf, 0)
                if conf_rank > best_conf and category.get('verbatim_citation'):
                    best_citation = category['verbatim_citation']
                    best_conf = conf_rank

        return best_citation

    def _get_best_confidence(self, incidents: Dict[str, Any]) -> str:
        """Get the best confidence level from incident data."""
        confidence_rank = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
        best_conf = 'LOW'
        best_rank = 0

        for category in incidents.values():
            if isinstance(category, dict):
                conf = category.get('confidence', 'LOW')
                conf_rank = confidence_rank.get(conf, 0)
                if conf_rank > best_rank:
                    best_conf = conf
                    best_rank = conf_rank

        return best_conf

    def _count_sewage_sources(self, sewage: Dict[str, Any]) -> int:
        """Count unique sources in sewage incidents."""
        urls = set()
        for category in sewage.values():
            if isinstance(category, dict) and category.get('source_url'):
                urls.add(category['source_url'])
        return len(urls)

    def _count_storm_sources(self, storm: Dict[str, Any]) -> int:
        """Count unique sources in storm incidents."""
        urls = set()
        for category in storm.values():
            if isinstance(category, dict) and category.get('source_url'):
                urls.add(category['source_url'])
        return len(urls)

    def _get_sewage_notes(self, sewage: Dict[str, Any]) -> Optional[str]:
        """Get notes for sewage incidents."""
        notes = []

        # Check for consent decree
        costs = sewage.get('costs_fines', {})
        if isinstance(costs, dict):
            consent = costs.get('consent_decree', '')
            if consent and consent not in ['NOT FOUND', 'No', 'None']:
                notes.append(f"Consent decree: {consent[:100]}")

        # Check for environmental impacts
        env = sewage.get('environmental_impacts', {})
        if isinstance(env, dict):
            waterways = env.get('waterways_affected', [])
            if waterways and isinstance(waterways, list):
                notes.append(f"Waterways affected: {', '.join(waterways[:5])}")

        # Check for recent events
        sso = sewage.get('sso_events', {})
        if isinstance(sso, dict):
            recent = sso.get('recent_events', [])
            if recent and isinstance(recent, list) and len(recent) > 0:
                notes.append(f"Recent SSO events: {len(recent)}")

        return "; ".join(notes) if notes else None

    def _get_storm_notes(self, storm: Dict[str, Any]) -> Optional[str]:
        """Get notes for storm incidents."""
        notes = []

        # Check for problem areas
        clogged = storm.get('clogged_drains', {})
        if isinstance(clogged, dict):
            areas = clogged.get('problem_areas', [])
            if areas and isinstance(areas, list):
                notes.append(f"Problem areas: {', '.join(areas[:5])}")

        # Check for flooding locations
        flooding = storm.get('flooding_events', {})
        if isinstance(flooding, dict):
            locations = flooding.get('locations', [])
            if locations and isinstance(locations, list):
                notes.append(f"Flooding locations: {', '.join(locations[:5])}")

        return "; ".join(notes) if notes else None
