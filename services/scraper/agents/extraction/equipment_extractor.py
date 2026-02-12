"""
Equipment Extractor Agent (EX-2)

Extracts municipal maintenance equipment data from web sources.
Focuses on CCTV/camera trucks, cleaning equipment, and related fleet assets.

Responsibilities:
- Extract CCTV/camera truck inventory (mainline, push, crawler, lateral)
- Extract cleaning equipment (combo units, jetters, flush trucks)
- Extract hydro-vac/excavation equipment
- Determine in-house vs contracted service model
- Require verbatim citations for all equipment counts
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
from services.scraper.prompts.ex2_equipment import get_prompt

logger = logging.getLogger(__name__)


class EquipmentExtractorAgent(BaseAgent):
    """
    EX-2: Equipment Extractor Agent

    Extracts municipal maintenance equipment data including:
    - Camera trucks (CCTV inspection vehicles)
    - Hydro/flush trucks
    - Hydro-vac trucks
    - Combo units (combination sewer cleaners)
    - Jetter equipment
    - Other relevant maintenance equipment

    All data points require verbatim citations from sources.
    Maps to schema column 6: "Owned equipment for cleaning/maintenance/CCTV"
    """

    AGENT_ID = "ex-2"
    AGENT_NAME = "Equipment Extractor"
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
        Build search queries for equipment data.

        Returns list of (query, max_results) tuples.
        """
        queries = []

        # Core equipment searches - increased limits for comprehensive data
        queries.extend([
            # CCTV/Camera equipment focused (PRIMARY)
            (f"{municipality_name} {state} sewer equipment fleet CCTV", 15),
            (f"{municipality_name} {state} CCTV inspection truck camera", 15),
            (f"{municipality_name} {state} sewer camera inspection equipment", 10),

            # Cleaning equipment focused
            (f"{municipality_name} {state} vactor truck jetter combination", 15),
            (f"{municipality_name} {state} combination sewer cleaner", 10),
            (f"{municipality_name} {state} sewer cleaning equipment fleet", 10),

            # Fleet/inventory focused
            (f"{municipality_name} {state} public works equipment inventory", 15),
            (f"{municipality_name} {state} fleet services sewer storm", 10),
            (f"{municipality_name} {state} wastewater maintenance vehicles", 10),

            # CIP/budget focused
            (f"{municipality_name} {state} equipment replacement CIP", 10),
            (f"{municipality_name} {state} fleet replacement sewer equipment", 10),
            (f"{municipality_name} {state} capital equipment public works", 10),

            # Hydro-vac specific
            (f"{municipality_name} {state} hydrovac hydro excavator truck", 10),
        ])

        # Add terminology-based searches if provided - use more terms
        if terminology:
            sanitary_terms = terminology.get('sanitary_terms', [])

            for term in sanitary_terms[:5]:  # Increased from 2 to 5 terms
                queries.append(
                    (f"{municipality_name} {state} {term} equipment fleet", 10)
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
        Execute Tavily searches for equipment data.

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
            for key in ['official_website', 'public_works_page', 'procurement_page',
                        'sewer_utility_page', 'gis_portal']:
                source = source_map.get(key)
                if source and isinstance(source, dict) and source.get('url'):
                    url = source['url']
                    # Extract domain from URL
                    if '://' in url:
                        domain = url.split('://')[1].split('/')[0]
                        if domain not in priority_domains:
                            priority_domains.append(domain)

            # Add CIP document domains (often have equipment sections)
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
            (f"{municipality_name} {state} sewer CCTV equipment owned", 5),
            (f"{municipality_name} {state} public works fleet vactor jetter", 4),
        ]

        for query, max_results in broader_queries:
            self.emit_event("searching", f"Broad search: {query[:50]}...")
            results = await self.search_tavily(query, max_results=max_results)
            if not results:
                continue
            for r in results:
                r['query'] = query
            all_results.extend(results)

        logger.debug(f"EX-2 collected {len(all_results)} total search results")
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

        context_parts = ["## SEARCH RESULTS FOR EQUIPMENT DATA\n"]
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
            return "Search returned no useful results for equipment data."

        # Add source map context if available
        if source_map:
            context_parts.append("## PRIORITY SOURCES FROM PRE-FLIGHT (PF-3)\n")

            for key, label in [
                ('public_works_page', 'Public Works Page'),
                ('sewer_utility_page', 'Sewer Utility Page'),
                ('procurement_page', 'Procurement Page'),
                ('gis_portal', 'GIS Portal')
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

        # Limit to top 40 unique results to avoid context overflow
        for i, result in enumerate(unique_results[:40], 1):
            title = result.get('title', 'Untitled').strip()
            url = result.get('url', '')
            content = result.get('content', '')
            query = result.get('query', '')

            context_parts.append(f"### Result {i}: {title}")
            context_parts.append(f"**URL:** {url}")
            if query:
                context_parts.append(f"**Query:** {query}")
            # Truncate content to avoid excessive context
            context_parts.append(f"**Content:**\n{content[:2500]}\n")

        return "\n".join(context_parts)

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process equipment extraction request.

        Expected input_data:
        - municipality_name: str - Normalized municipality name
        - state: str - Full state name
        - source_map: dict - Source map from PF-3 (optional)
        - terminology: dict - Terminology map from PF-4 (optional)

        Returns AgentResponse with:
        - equipment_inventory: Dict with all equipment categories
        - total_equipment_pieces: Count of confirmed equipment
        - in_house_vs_contract: Service model determination
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
            self.emit_event("processing", f"Extracting equipment data for {municipality_name}, {state}")

            # Search for equipment data using Tavily
            search_results = await self._search_sources(
                municipality_name, state, source_map, terminology
            )

            # Build context from search results
            context = self._build_context(search_results, source_map)

            # Get the prompt with input substituted
            prompt = get_prompt(municipality_name, state)

            # Build user message with search context
            user_message = f"""Extract maintenance equipment data for: {municipality_name}, {state}

SEARCH RESULTS AND SOURCE CONTEXT:
{context}

Based on these search results, extract:
1. **Camera Trucks/CCTV Equipment:**
   - Count, description, makes/models
   - Stated uses
   - Verbatim citation from source

2. **Hydro/Flush Trucks:**
   - Count, description, makes/models
   - Stated uses
   - Verbatim citation from source

3. **Hydro-Vac Trucks:**
   - Count, description, makes/models
   - Stated uses
   - Verbatim citation from source

4. **Combo Units (Combination Sewer Cleaners):**
   - Count, description, makes/models
   - Stated uses
   - Verbatim citation from source

5. **Jetter Equipment:**
   - Count, description, makes/models
   - Stated uses
   - Verbatim citation from source

6. **Other Relevant Equipment:**
   - Any other sewer/storm maintenance equipment found

7. **Service Model:**
   - In-house vs contracted determination
   - Supporting citation

CRITICAL REQUIREMENTS:
- Every equipment count MUST have a verbatim citation (exact quote from source)
- Use "NOT FOUND" if equipment data cannot be located
- Use "NOT FOUND (equipment type mentioned but count not specified)" when equipment is mentioned without count
- Rate confidence based on source type and age
- Do NOT infer equipment exists without explicit source mention

Return the JSON output as specified in your instructions."""

            self.emit_event("processing", "Analyzing search results for equipment data...")

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
                logger.warning(f"EX-2 validation failed: {errors}")
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

            # Count equipment pieces found
            equipment_count = self._count_equipment_found(output_data)

            # Emit completion event with summary
            self.emit_event(
                "completed",
                f"Extracted {equipment_count} equipment pieces",
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
            logger.error(f"EX-2 JSON extraction failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'extraction_error': str(e), 'raw_response': content[:1000] if content else ''},
                errors=[f"JSON extraction error: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )
        except json.JSONDecodeError as e:
            logger.error(f"EX-2 JSON parse failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'parse_error': str(e), 'attempted_json': json_str[:500] if json_str else ''},
                errors=[f"JSON parse error at position {e.pos}: {e.msg}"],
                processing_time_seconds=time.time() - start_time
            )
        except Exception as e:
            logger.exception(f"EX-2 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def _count_equipment_found(self, output_data: Dict[str, Any]) -> int:
        """Count the number of equipment pieces with confirmed counts."""
        count = 0
        inventory = output_data.get('equipment_inventory', {})

        # Check main equipment categories
        for category in ['camera_trucks', 'hydro_flush_trucks', 'hydro_vac_trucks',
                         'combo_units', 'jetter_equipment']:
            cat_data = inventory.get(category, {})
            if isinstance(cat_data, dict):
                count_val = cat_data.get('count', '')
                if count_val and count_val != 'NOT FOUND' and not count_val.startswith('NOT FOUND'):
                    # Try to parse the count
                    try:
                        count += int(count_val)
                    except (ValueError, TypeError):
                        # Count mentioned but not numeric, count as 1
                        count += 1

        # Check other_equipment
        other = inventory.get('other_equipment', [])
        if isinstance(other, list):
            for item in other:
                if isinstance(item, dict):
                    count_val = item.get('count', '')
                    if count_val and count_val != 'NOT FOUND' and not str(count_val).startswith('NOT FOUND'):
                        try:
                            count += int(count_val)
                        except (ValueError, TypeError):
                            count += 1

        return count

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate equipment extraction output against spec."""
        errors = []

        # Check required top-level field
        if 'equipment_inventory' not in output:
            errors.append("Missing 'equipment_inventory' section")
            return errors  # Early return if missing main section

        inventory = output.get('equipment_inventory', {})
        if not isinstance(inventory, dict):
            errors.append("'equipment_inventory' must be a dictionary")
            return errors

        # Validate each equipment category
        required_categories = [
            'camera_trucks',
            'hydro_flush_trucks',
            'hydro_vac_trucks',
            'combo_units',
            'jetter_equipment'
        ]

        for category in required_categories:
            if category not in inventory:
                errors.append(f"Missing equipment category: {category}")
            else:
                cat_data = inventory.get(category, {})
                if not isinstance(cat_data, dict):
                    errors.append(f"'{category}' must be a dictionary")
                else:
                    cat_errors = self._validate_equipment_category(cat_data, category)
                    errors.extend(cat_errors)

        # Validate other_equipment is a list if present
        other = inventory.get('other_equipment')
        if other is not None and not isinstance(other, list):
            errors.append("'other_equipment' must be a list")

        # Validate in_house_vs_contract
        service_model = output.get('in_house_vs_contract')
        if service_model:
            valid_models = ['In-house', 'Contracted', 'Both', 'NOT FOUND']
            # Allow partial matches (e.g., "Both - In-house for routine...")
            if not any(model in service_model for model in valid_models):
                errors.append(f"Invalid in_house_vs_contract value: {service_model[:50]}")

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

    def _validate_equipment_category(self, category: Dict[str, Any], category_name: str) -> List[str]:
        """Validate an equipment category section."""
        errors = []

        # Required fields
        required_fields = ['count', 'confidence']

        for field in required_fields:
            if field not in category:
                errors.append(f"{category_name} missing required field: {field}")

        # Validate confidence value
        confidence = category.get('confidence')
        if confidence and confidence not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append(f"{category_name} invalid confidence: {confidence}")

        # If equipment was found (not "NOT FOUND"), require verbatim citation
        count = category.get('count', '')
        if count and count != 'NOT FOUND' and not str(count).startswith('NOT FOUND'):
            verbatim = category.get('verbatim_citation')
            if not verbatim:
                errors.append(f"{category_name} has count but missing verbatim_citation")

            source_url = category.get('source_url')
            if not source_url:
                errors.append(f"{category_name} has count but missing source_url")

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

        inventory = output.get('equipment_inventory', {})

        # Convert each equipment category
        for category in ['camera_trucks', 'hydro_flush_trucks', 'hydro_vac_trucks',
                         'combo_units', 'jetter_equipment']:
            cat_data = inventory.get(category, {})
            if cat_data:
                data_points[category] = ExtractedDataPoint(
                    field_name=category,
                    value=self._format_equipment_value(cat_data),
                    raw_source_value=cat_data.get('description'),
                    source_url=cat_data.get('source_url', ''),
                    verbatim_quote=cat_data.get('verbatim_citation', ''),
                    confidence=confidence_str_to_enum(cat_data.get('confidence', 'MEDIUM')),
                    confidence_rationale=cat_data.get('confidence_rationale', ''),
                    notes=cat_data.get('stated_uses')
                )

        # Create combined equipment_owned data point for schema column 6
        combined_value = self._format_combined_equipment(output)
        combined_source = self._get_best_source(inventory)

        data_points['equipment_owned'] = ExtractedDataPoint(
            field_name='equipment_owned',
            value=combined_value,
            raw_source_value=None,
            source_url=combined_source.get('url', ''),
            verbatim_quote=combined_source.get('citation', ''),
            confidence=confidence_str_to_enum(combined_source.get('confidence', 'MEDIUM')),
            confidence_rationale=f"Combined from {self._count_equipment_found(output)} equipment entries",
            notes=output.get('in_house_vs_contract')
        )

        return data_points

    def _format_equipment_value(self, equip_data: Dict[str, Any]) -> str:
        """Format equipment data into a single display value."""
        count = equip_data.get('count', 'NOT FOUND')
        description = equip_data.get('description', '')
        makes_models = equip_data.get('makes_models', '')

        if count == 'NOT FOUND':
            return 'NOT FOUND'

        parts = []
        if count:
            parts.append(f"Count: {count}")
        if description and description != 'NOT FOUND':
            parts.append(description)
        if makes_models:
            parts.append(f"({makes_models})")

        return "; ".join(parts) if parts else 'NOT FOUND'

    def _format_combined_equipment(self, output: Dict[str, Any]) -> str:
        """Format all equipment into a combined value for schema column 6."""
        inventory = output.get('equipment_inventory', {})
        equipment_parts = []

        # Map categories to display names
        category_names = {
            'camera_trucks': 'CCTV/Camera',
            'hydro_flush_trucks': 'Flush Trucks',
            'hydro_vac_trucks': 'Hydro-Vac',
            'combo_units': 'Combo Units',
            'jetter_equipment': 'Jetters'
        }

        for category, display_name in category_names.items():
            cat_data = inventory.get(category, {})
            if isinstance(cat_data, dict):
                count = cat_data.get('count', 'NOT FOUND')
                if count and count != 'NOT FOUND' and not str(count).startswith('NOT FOUND'):
                    equipment_parts.append(f"{display_name}: {count}")

        # Add other equipment
        other = inventory.get('other_equipment', [])
        if isinstance(other, list) and other:
            other_count = len(other)
            equipment_parts.append(f"Other: {other_count} types")

        if not equipment_parts:
            return 'NOT FOUND'

        # Add service model
        service_model = output.get('in_house_vs_contract', 'NOT FOUND')
        result = "; ".join(equipment_parts)
        if service_model and service_model != 'NOT FOUND':
            # Truncate long service model descriptions
            if len(service_model) > 30:
                service_model = service_model[:30] + "..."
            result += f" | Service: {service_model}"

        return result

    def _get_best_source(self, inventory: Dict[str, Any]) -> Dict[str, Any]:
        """Get the best source/citation from equipment inventory."""
        best = {'url': '', 'citation': '', 'confidence': 'LOW'}

        confidence_rank = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}

        for category in ['camera_trucks', 'hydro_flush_trucks', 'hydro_vac_trucks',
                         'combo_units', 'jetter_equipment']:
            cat_data = inventory.get(category, {})
            if isinstance(cat_data, dict):
                conf = cat_data.get('confidence', 'LOW')
                if confidence_rank.get(conf, 0) > confidence_rank.get(best['confidence'], 0):
                    best = {
                        'url': cat_data.get('source_url', ''),
                        'citation': cat_data.get('verbatim_citation', ''),
                        'confidence': conf
                    }

        return best
