"""
Maintenance Extractor Agent (EX-3)

Extracts cleaning and maintenance practice data from web sources for municipal systems.
Focuses on cleaning frequency, scope, service delivery model, and formal maintenance programs.

Responsibilities:
- Extract cleaning program data (frequency, scope, method)
- Extract CCTV/televising practices
- Determine in-house vs contractor service model
- Identify CMOM/FOG/I&I programs
- Require verbatim citations for all data points
- Use source map from PF-3 and terminology from PF-4
- Maps to schema column 7: "Cleaning/televising/maintenance practices"
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
from services.scraper.prompts.ex3_maintenance import get_prompt

logger = logging.getLogger(__name__)


class MaintenanceExtractorAgent(BaseAgent):
    """
    EX-3: Maintenance Extractor Agent

    Extracts municipal maintenance practice data including:
    - Cleaning program (frequency, scope, method, footage targets)
    - CCTV/televising practices (frequency, scope, PACP compliance)
    - Service model (in-house vs contracted operations)
    - Formal maintenance programs (CMOM, FOG, I&I)

    All data points require verbatim citations from sources.
    Maps to schema column 7: "Cleaning/televising/maintenance practices"
    """

    AGENT_ID = "ex-3"
    AGENT_NAME = "Maintenance Extractor"
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
        Build search queries for maintenance practice data.

        Returns list of (query, max_results) tuples.
        """
        queries = []

        # Core maintenance practice searches - increased limits
        queries.extend([
            # Cleaning program focused (PRIMARY)
            (f"{municipality_name} {state} sewer cleaning program frequency", 15),
            (f"{municipality_name} {state} sewer cleaning schedule annual", 15),
            (f"{municipality_name} {state} preventive maintenance sewer", 10),

            # CCTV/Televising focused
            (f"{municipality_name} {state} CCTV inspection sewer televising", 15),
            (f"{municipality_name} {state} sewer video inspection program", 10),
            (f"{municipality_name} {state} NASSCO PACP sewer inspection", 10),

            # CMOM/FOG program focused
            (f"{municipality_name} {state} CMOM program maintenance", 15),
            (f"{municipality_name} {state} FOG program grease", 10),
            (f"{municipality_name} {state} SSO reduction program sewer", 10),

            # I&I program focused
            (f"{municipality_name} {state} inflow infiltration I&I program", 10),
            (f"{municipality_name} {state} I&I reduction sewer", 10),

            # Service model focused
            (f"{municipality_name} {state} sewer maintenance contract", 15),
            (f"{municipality_name} {state} sewer cleaning contractor", 10),
            (f"{municipality_name} {state} wastewater collection maintenance", 10),

            # Master plan / engineering focused
            (f"{municipality_name} {state} collection system master plan maintenance", 10),
            (f"{municipality_name} {state} sewer system evaluation study", 10),
        ])

        # Add terminology-based searches if provided - use more terms
        if terminology:
            sanitary_terms = terminology.get('sanitary_terms', [])

            for term in sanitary_terms[:5]:  # Increased from 2 to 5 terms
                queries.append(
                    (f"{municipality_name} {state} {term} cleaning maintenance", 10)
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
        Execute Tavily searches for maintenance practice data.

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
            for key in ['official_website', 'sewer_utility_page', 'public_works_page',
                        'procurement_page', 'stormwater_page']:
                source = source_map.get(key)
                if source and isinstance(source, dict) and source.get('url'):
                    url = source['url']
                    # Extract domain from URL
                    if '://' in url:
                        domain = url.split('://')[1].split('/')[0]
                        if domain not in priority_domains:
                            priority_domains.append(domain)

            # Add compliance source domains (likely CMOM documents)
            compliance_sources = source_map.get('compliance_sources', [])
            if isinstance(compliance_sources, list):
                for source in compliance_sources[:3]:
                    if isinstance(source, dict) and source.get('url'):
                        url = source['url']
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
            (f"{municipality_name} {state} sewer maintenance program cleaning CCTV", 5),
            (f"{municipality_name} {state} wastewater CMOM FOG program", 4),
        ]

        for query, max_results in broader_queries:
            self.emit_event("searching", f"Broad search: {query[:50]}...")
            results = await self.search_tavily(query, max_results=max_results)
            if not results:
                continue
            for r in results:
                r['query'] = query
            all_results.extend(results)

        logger.debug(f"EX-3 collected {len(all_results)} total search results")
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

        context_parts = ["## SEARCH RESULTS FOR MAINTENANCE PRACTICE DATA\n"]
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
            return "Search returned no useful results for maintenance practice data."

        # Add source map context if available
        if source_map:
            context_parts.append("## PRIORITY SOURCES FROM PRE-FLIGHT (PF-3)\n")

            for key, label in [
                ('sewer_utility_page', 'Sewer Utility Page'),
                ('public_works_page', 'Public Works Page'),
                ('procurement_page', 'Procurement Page'),
                ('stormwater_page', 'Stormwater Page')
            ]:
                source = source_map.get(key)
                if source and isinstance(source, dict) and source.get('url'):
                    context_parts.append(f"- **{label}:** {source.get('url')}")

            # Add compliance sources (often have CMOM info)
            compliance_sources = source_map.get('compliance_sources', [])
            if compliance_sources:
                context_parts.append("- **Compliance Sources:**")
                for source in compliance_sources[:5]:
                    if isinstance(source, dict) and source.get('url'):
                        context_parts.append(f"  - {source.get('title', 'Untitled')}: {source.get('url')}")

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
        Process maintenance practice extraction request.

        Expected input_data:
        - municipality_name: str - Normalized municipality name
        - state: str - Full state name
        - source_map: dict - Source map from PF-3 (optional)
        - terminology: dict - Terminology map from PF-4 (optional)

        Returns AgentResponse with:
        - maintenance_practices: Dict with all maintenance categories
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
            self.emit_event("processing", f"Extracting maintenance practice data for {municipality_name}, {state}")

            # Search for maintenance practice data using Tavily
            search_results = await self._search_sources(
                municipality_name, state, source_map, terminology
            )

            # Build context from search results
            context = self._build_context(search_results, source_map)

            # Get the prompt with input substituted
            prompt = get_prompt(municipality_name, state)

            # Build user message with search context
            user_message = f"""Extract maintenance practice data for: {municipality_name}, {state}

SEARCH RESULTS AND SOURCE CONTEXT:
{context}

Based on these search results, extract:
1. **Cleaning Program Data:**
   - Frequency (annual, semi-annual, quarterly, as-needed)
   - Scope (full system, zone-based, footage targets)
   - Method (hydro cleaning, mechanical, combination)
   - Annual footage target if available
   - Preventive vs reactive breakdown
   - Verbatim citation from source

2. **CCTV/Televising Practices:**
   - Inspection frequency
   - Scope and annual footage targets
   - NASSCO PACP compliance status
   - Prioritization method
   - Verbatim citation from source

3. **Service Delivery Model:**
   - In-house vs Contracted vs Both
   - In-house capabilities and staffing
   - Contractor names and scope
   - Verbatim citation from source

4. **Formal Maintenance Programs:**
   - CMOM program status
   - FOG program status
   - I&I reduction program status
   - Program names and descriptions
   - Verbatim citation from source

CRITICAL REQUIREMENTS:
- Every data point MUST have a verbatim citation (exact quote from source)
- Use "NOT FOUND" if data cannot be located
- Use "NOT FOUND (program mentioned but details not specified)" when mentioned without details
- Rate confidence based on source type and age
- Do NOT infer programs exist without explicit source mention
- Capture contractor names if mentioned

Return the JSON output as specified in your instructions."""

            self.emit_event("processing", "Analyzing search results for maintenance practice data...")

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
                logger.warning(f"EX-3 validation failed: {errors}")
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
                f"Extracted {data_points_found} maintenance practice data points",
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
            logger.error(f"EX-3 JSON extraction failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'extraction_error': str(e), 'raw_response': content[:1000] if content else ''},
                errors=[f"JSON extraction error: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )
        except json.JSONDecodeError as e:
            logger.error(f"EX-3 JSON parse failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'parse_error': str(e), 'attempted_json': json_str[:500] if json_str else ''},
                errors=[f"JSON parse error at position {e.pos}: {e.msg}"],
                processing_time_seconds=time.time() - start_time
            )
        except Exception as e:
            logger.exception(f"EX-3 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def _count_data_points_found(self, output_data: Dict[str, Any]) -> int:
        """Count the number of maintenance data points with actual data."""
        count = 0
        practices = output_data.get('maintenance_practices', {})

        # Check cleaning_program
        cleaning = practices.get('cleaning_program', {})
        if isinstance(cleaning, dict):
            if cleaning.get('frequency') and not str(cleaning.get('frequency', '')).startswith('NOT FOUND'):
                count += 1
            if cleaning.get('scope') and not str(cleaning.get('scope', '')).startswith('NOT FOUND'):
                count += 1
            if cleaning.get('method') and not str(cleaning.get('method', '')).startswith('NOT FOUND'):
                count += 1

        # Check cctv_inspection
        cctv = practices.get('cctv_inspection', {})
        if isinstance(cctv, dict):
            if cctv.get('frequency') and not str(cctv.get('frequency', '')).startswith('NOT FOUND'):
                count += 1
            if cctv.get('scope') and not str(cctv.get('scope', '')).startswith('NOT FOUND'):
                count += 1

        # Check service_model
        service = practices.get('service_model', {})
        if isinstance(service, dict):
            if service.get('type') and not str(service.get('type', '')).startswith('NOT FOUND'):
                count += 1

        # Check maintenance_schedule
        schedule = practices.get('maintenance_schedule', {})
        if isinstance(schedule, dict):
            if schedule.get('has_formal_program') is True:
                count += 1
            if schedule.get('cmom_status') and not str(schedule.get('cmom_status', '')).startswith('NOT FOUND'):
                count += 1
            if schedule.get('fog_status') and not str(schedule.get('fog_status', '')).startswith('NOT FOUND'):
                count += 1

        return count

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate maintenance practice extraction output against spec."""
        errors = []

        # Check required top-level field
        if 'maintenance_practices' not in output:
            errors.append("Missing 'maintenance_practices' section")
            return errors  # Early return if missing main section

        practices = output.get('maintenance_practices', {})
        if not isinstance(practices, dict):
            errors.append("'maintenance_practices' must be a dictionary")
            return errors

        # Validate each maintenance category
        required_categories = [
            'cleaning_program',
            'cctv_inspection',
            'service_model',
            'maintenance_schedule'
        ]

        for category in required_categories:
            if category not in practices:
                errors.append(f"Missing maintenance category: {category}")
            else:
                cat_data = practices.get(category, {})
                if not isinstance(cat_data, dict):
                    errors.append(f"'{category}' must be a dictionary")
                else:
                    cat_errors = self._validate_maintenance_category(cat_data, category)
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

    def _validate_maintenance_category(self, category: Dict[str, Any], category_name: str) -> List[str]:
        """Validate a maintenance category section."""
        errors = []

        # Required fields vary by category
        if category_name == 'cleaning_program':
            required_fields = ['frequency', 'confidence']
        elif category_name == 'cctv_inspection':
            required_fields = ['frequency', 'confidence']
        elif category_name == 'service_model':
            required_fields = ['type', 'confidence']
        elif category_name == 'maintenance_schedule':
            required_fields = ['has_formal_program', 'confidence']
        else:
            required_fields = ['confidence']

        for field in required_fields:
            if field not in category:
                errors.append(f"{category_name} missing required field: {field}")

        # Validate confidence value
        confidence = category.get('confidence')
        if confidence and confidence not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append(f"{category_name} invalid confidence: {confidence}")

        # Validate service_model type values
        if category_name == 'service_model':
            service_type = category.get('type', '')
            valid_types = ['In-house', 'Contracted', 'Both', 'NOT FOUND']
            if service_type and not any(vt in service_type for vt in valid_types):
                errors.append(f"{category_name} invalid type: {service_type[:50]}")

        # If data was found (not "NOT FOUND"), require verbatim citation
        primary_field = None
        if category_name == 'cleaning_program':
            primary_field = category.get('frequency', '')
        elif category_name == 'cctv_inspection':
            primary_field = category.get('frequency', '')
        elif category_name == 'service_model':
            primary_field = category.get('type', '')
        elif category_name == 'maintenance_schedule':
            primary_field = 'has_program' if category.get('has_formal_program') else ''

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

        practices = output.get('maintenance_practices', {})

        # Convert each maintenance category
        for category in ['cleaning_program', 'cctv_inspection', 'service_model', 'maintenance_schedule']:
            cat_data = practices.get(category, {})
            if cat_data:
                data_points[category] = ExtractedDataPoint(
                    field_name=category,
                    value=self._format_category_value(cat_data, category),
                    raw_source_value=cat_data.get('description') or cat_data.get('scope'),
                    source_url=cat_data.get('source_url', ''),
                    verbatim_quote=cat_data.get('verbatim_citation', ''),
                    confidence=confidence_str_to_enum(cat_data.get('confidence', 'MEDIUM')),
                    confidence_rationale=cat_data.get('confidence_rationale', ''),
                    notes=self._get_category_notes(cat_data, category)
                )

        # Create combined maintenance_practices data point for schema column 7
        combined_value = self._format_combined_practices(output)
        combined_source = self._get_best_source(practices)

        data_points['maintenance_practices'] = ExtractedDataPoint(
            field_name='maintenance_practices',
            value=combined_value,
            raw_source_value=None,
            source_url=combined_source.get('url', ''),
            verbatim_quote=combined_source.get('citation', ''),
            confidence=confidence_str_to_enum(combined_source.get('confidence', 'MEDIUM')),
            confidence_rationale=f"Combined from {self._count_data_points_found(output)} maintenance data points",
            notes=self._get_service_model_summary(practices)
        )

        return data_points

    def _format_category_value(self, cat_data: Dict[str, Any], category_name: str) -> str:
        """Format category data into a single display value."""
        if category_name == 'cleaning_program':
            frequency = cat_data.get('frequency', 'NOT FOUND')
            scope = cat_data.get('scope', '')
            method = cat_data.get('method', '')

            if frequency == 'NOT FOUND':
                return 'NOT FOUND'

            parts = [f"Frequency: {frequency}"]
            if scope and scope != 'NOT FOUND':
                parts.append(f"Scope: {scope}")
            if method and method != 'NOT FOUND':
                parts.append(f"Method: {method}")
            return "; ".join(parts)

        elif category_name == 'cctv_inspection':
            frequency = cat_data.get('frequency', 'NOT FOUND')
            scope = cat_data.get('scope', '')
            footage = cat_data.get('footage_per_year', '')

            if frequency == 'NOT FOUND':
                return 'NOT FOUND'

            parts = [f"Frequency: {frequency}"]
            if scope and scope != 'NOT FOUND':
                parts.append(f"Scope: {scope}")
            if footage:
                parts.append(f"Annual footage: {footage}")
            return "; ".join(parts)

        elif category_name == 'service_model':
            service_type = cat_data.get('type', 'NOT FOUND')
            if service_type == 'NOT FOUND':
                return 'NOT FOUND'

            parts = [service_type]
            if cat_data.get('in_house_details'):
                parts.append(f"In-house: {cat_data['in_house_details'][:100]}")
            if cat_data.get('contractor_names'):
                contractors = cat_data['contractor_names']
                if isinstance(contractors, list):
                    parts.append(f"Contractors: {', '.join(contractors[:3])}")
            return "; ".join(parts)

        elif category_name == 'maintenance_schedule':
            has_program = cat_data.get('has_formal_program', False)
            if not has_program:
                return 'No formal program identified'

            parts = []
            if cat_data.get('program_name'):
                parts.append(cat_data['program_name'])
            if cat_data.get('cmom_status') and not str(cat_data.get('cmom_status', '')).startswith('NOT FOUND'):
                parts.append(f"CMOM: {cat_data['cmom_status'][:50]}")
            if cat_data.get('fog_status') and not str(cat_data.get('fog_status', '')).startswith('NOT FOUND'):
                parts.append(f"FOG: {cat_data['fog_status'][:50]}")
            return "; ".join(parts) if parts else 'Formal program (details limited)'

        return 'NOT FOUND'

    def _get_category_notes(self, cat_data: Dict[str, Any], category_name: str) -> Optional[str]:
        """Get notes for a category."""
        if category_name == 'cleaning_program':
            parts = []
            if cat_data.get('annual_footage_target'):
                parts.append(f"Target: {cat_data['annual_footage_target']}")
            if cat_data.get('preventive_vs_reactive'):
                parts.append(cat_data['preventive_vs_reactive'])
            return "; ".join(parts) if parts else None

        elif category_name == 'cctv_inspection':
            parts = []
            if cat_data.get('pacp_compliant'):
                parts.append("NASSCO PACP compliant")
            if cat_data.get('prioritization_method'):
                parts.append(f"Priority: {cat_data['prioritization_method']}")
            return "; ".join(parts) if parts else None

        elif category_name == 'service_model':
            return cat_data.get('contract_scope')

        elif category_name == 'maintenance_schedule':
            return cat_data.get('ii_status')

        return None

    def _format_combined_practices(self, output: Dict[str, Any]) -> str:
        """Format all maintenance practices into a combined value for schema column 7."""
        practices = output.get('maintenance_practices', {})
        parts = []

        # Cleaning summary
        cleaning = practices.get('cleaning_program', {})
        if isinstance(cleaning, dict):
            freq = cleaning.get('frequency', 'NOT FOUND')
            if freq and not str(freq).startswith('NOT FOUND'):
                parts.append(f"Cleaning: {freq}")

        # CCTV summary
        cctv = practices.get('cctv_inspection', {})
        if isinstance(cctv, dict):
            freq = cctv.get('frequency', 'NOT FOUND')
            if freq and not str(freq).startswith('NOT FOUND'):
                parts.append(f"CCTV: {freq}")

        # Service model summary
        service = practices.get('service_model', {})
        if isinstance(service, dict):
            stype = service.get('type', 'NOT FOUND')
            if stype and not str(stype).startswith('NOT FOUND'):
                parts.append(f"Service: {stype}")

        # Programs summary
        schedule = practices.get('maintenance_schedule', {})
        if isinstance(schedule, dict):
            programs = []
            if schedule.get('cmom_status') and not str(schedule.get('cmom_status', '')).startswith('NOT FOUND'):
                programs.append("CMOM")
            if schedule.get('fog_status') and not str(schedule.get('fog_status', '')).startswith('NOT FOUND'):
                programs.append("FOG")
            if schedule.get('ii_status') and not str(schedule.get('ii_status', '')).startswith('NOT FOUND'):
                programs.append("I&I")
            if programs:
                parts.append(f"Programs: {', '.join(programs)}")

        if not parts:
            return 'NOT FOUND'

        return "; ".join(parts)

    def _get_service_model_summary(self, practices: Dict[str, Any]) -> Optional[str]:
        """Get service model summary for notes."""
        service = practices.get('service_model', {})
        if isinstance(service, dict):
            contractors = service.get('contractor_names', [])
            if isinstance(contractors, list) and contractors:
                return f"Contractors: {', '.join(contractors[:5])}"
        return None

    def _get_best_source(self, practices: Dict[str, Any]) -> Dict[str, Any]:
        """Get the best source/citation from maintenance practices."""
        best = {'url': '', 'citation': '', 'confidence': 'LOW'}

        confidence_rank = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}

        for category in ['cleaning_program', 'cctv_inspection', 'service_model', 'maintenance_schedule']:
            cat_data = practices.get(category, {})
            if isinstance(cat_data, dict):
                conf = cat_data.get('confidence', 'LOW')
                if confidence_rank.get(conf, 0) > confidence_rank.get(best['confidence'], 0):
                    best = {
                        'url': cat_data.get('source_url', ''),
                        'citation': cat_data.get('verbatim_citation', ''),
                        'confidence': conf
                    }

        return best
