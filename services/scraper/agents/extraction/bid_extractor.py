"""
Bid Extractor Agent (EX-5)

Extracts municipal public bid data from web sources for sewer/storm projects.
Finds open/closed/awarded bids, extracts timelines, requirements, and contacts.

Responsibilities:
- Find bids/RFPs/contracts related to sewer and storm drain work
- Apply INCLUSION FILTER: Only include bids with sewer/storm keywords
- Extract bid timelines: due dates, pre-bid meetings, question deadlines
- Extract qualification requirements and submission details
- Extract contacts: name, phone, email, title, addresses
- Identify downloadable document URLs for EX-6
- Maps to "Municipal Public Bids" table schema
- Requires verbatim citations for all data points

INCLUSION FILTER (from schema):
"Include a bid/contract ONLY if the source text explicitly contains at least
one of: sewer, sanitary sewer, storm sewer, storm drain"
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
from services.scraper.prompts.ex5_bid import get_prompt

logger = logging.getLogger(__name__)


class BidExtractorAgent(BaseAgent):
    """
    EX-5: Bid Extractor Agent

    Extracts municipal public bid data including:
    - Bid title, number, and agency
    - Sewer/storm keyword validation (INCLUSION FILTER)
    - Scope: description, budget, work type, quantities
    - Timeline: due date, pre-bid meeting, questions deadline
    - Requirements: qualifications, bonds, insurance
    - Contacts: name, title, phone, email
    - Downloadable documents for EX-6

    All data points require verbatim citations from sources.
    Maps to "Municipal Public Bids" table schema.
    """

    AGENT_ID = "ex-5"
    AGENT_NAME = "Bid Extractor"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-03"

    # Inclusion filter keywords - bid MUST contain at least one
    INCLUSION_KEYWORDS = [
        'sewer', 'sanitary sewer', 'storm sewer', 'storm drain',
        'stormwater', 'wastewater', 'collection system', 'lift station',
        'manhole', 'CCTV inspection', 'pipe lining', 'sewer rehabilitation',
        'SSO', 'I&I', 'inflow and infiltration'
    ]

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
        Build search queries for municipal public bids.

        Returns list of (query, max_results) tuples.
        """
        queries = []

        # ==============================================================
        # PHASE 1: BID PORTAL SEARCHES - PRIMARY (increased limits)
        # ==============================================================

        queries.extend([
            (f"{municipality_name} {state} bid RFP sewer", 15),
            (f"{municipality_name} {state} public bid sanitary sewer", 15),
            (f"{municipality_name} {state} procurement storm drain", 15),
            (f"{municipality_name} {state} contract award sewer", 10),
            (f"{municipality_name} bid opportunities sewer storm", 10),
        ])

        # ==============================================================
        # PHASE 2: PORTAL-SPECIFIC SEARCHES (increased limits)
        # ==============================================================

        queries.extend([
            (f"site:bidsync.com {municipality_name} sewer", 10),
            (f"site:ionwave.net {municipality_name} sewer", 10),
            (f"site:bidnet.com {municipality_name} sewer", 10),
            (f"site:planetbids.com {municipality_name} sewer", 10),
            (f"site:gobonfire.com {municipality_name} sewer storm", 10),
            (f"site:publicpurchase.com {municipality_name} sewer", 10),
        ])

        # ==============================================================
        # PHASE 3: MUNICIPAL WEBSITE SEARCHES (increased limits)
        # ==============================================================

        # Format municipality name for URL patterns
        muni_slug = municipality_name.lower().replace(' ', '')
        state_abbr = self._get_state_abbr(state)

        queries.extend([
            (f"site:{muni_slug}.gov bid sewer", 10),
            (f"{municipality_name} {state} purchasing sewer services", 10),
            (f"{municipality_name} {state} RFQ sewer inspection", 10),
            (f"{municipality_name} {state} ITB storm drain", 10),
        ])

        # ==============================================================
        # PHASE 4: RECENT/ACTIVE SEARCHES (increased limits)
        # ==============================================================

        queries.extend([
            (f"{municipality_name} {state} current bids sewer 2024 2025 2026", 15),
            (f"{municipality_name} {state} upcoming projects sewer storm", 10),
            (f"{municipality_name} {state} awarded contract sewer 2024", 10),
            (f"{municipality_name} {state} awarded contract sewer 2025", 10),
        ])

        # ==============================================================
        # PHASE 5: SPECIFIC WORK TYPE SEARCHES (increased limits)
        # ==============================================================

        queries.extend([
            (f"{municipality_name} {state} CCTV sewer inspection bid", 10),
            (f"{municipality_name} {state} sewer lining rehabilitation bid", 10),
            (f"{municipality_name} {state} storm drain cleaning bid", 10),
            (f"{municipality_name} {state} sewer cleaning jetting bid", 10),
            (f"{municipality_name} {state} manhole rehabilitation bid", 3),
        ])

        # ==============================================================
        # PHASE 6: COUNCIL/AWARD SEARCHES
        # ==============================================================

        queries.extend([
            (f"{municipality_name} {state} council agenda sewer contract award", 4),
            (f"{municipality_name} {state} city council sewer bid approval", 3),
        ])

        # Add terminology-based searches if provided
        if terminology:
            bid_terms = terminology.get('bid_portal_keywords', [])
            sanitary_terms = terminology.get('sanitary_terms', [])

            for term in bid_terms[:2]:
                queries.append(
                    (f"{municipality_name} {state} {term} bid sewer", 3)
                )

            for term in sanitary_terms[:2]:
                queries.append(
                    (f"{municipality_name} {state} {term} bid RFP", 3)
                )

        return queries

    def _get_state_abbr(self, state: str) -> str:
        """Get state abbreviation from full name."""
        state_abbrevs = {
            'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
            'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
            'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
            'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
            'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
            'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
            'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
            'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
            'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
            'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
            'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
            'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
            'wisconsin': 'WI', 'wyoming': 'WY'
        }
        return state_abbrevs.get(state.lower(), state[:2].upper())

    async def _search_sources(
        self,
        municipality_name: str,
        state: str,
        source_map: Optional[Dict[str, Any]] = None,
        terminology: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute Tavily searches for municipal public bids.

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
            # Extract procurement/bid-related domains
            for key in ['official_website', 'procurement_page', 'public_works_page']:
                source = source_map.get(key)
                if source and isinstance(source, dict) and source.get('url'):
                    url = source['url']
                    if '://' in url:
                        domain = url.split('://')[1].split('/')[0]
                        if domain not in priority_domains:
                            priority_domains.append(domain)

        # Build search queries
        search_queries = self._build_search_queries(
            municipality_name, state, terminology
        )

        self.emit_event("processing", f"Executing {len(search_queries)} bid searches...")

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

        logger.debug(f"EX-5 collected {len(all_results)} total search results")
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

        context_parts = ["## SEARCH RESULTS FOR MUNICIPAL PUBLIC BIDS\n"]
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
            return "Search returned no useful results for bid data."

        # Add source map context if available
        if source_map:
            context_parts.append("## PRIORITY SOURCES FROM PRE-FLIGHT (PF-3)\n")

            for key, label in [
                ('procurement_page', 'Procurement Page'),
                ('official_website', 'Official Website'),
                ('public_works_page', 'Public Works Page')
            ]:
                source = source_map.get(key)
                if source and isinstance(source, dict) and source.get('url'):
                    context_parts.append(f"- **{label}:** {source.get('url')}")

            context_parts.append("\n")

        # Limit to top 40 unique results
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
        Process bid extraction request.

        Expected input_data:
        - municipality_name: str - Normalized municipality name
        - state: str - Full state name
        - source_map: dict - Source map from PF-3 (optional)
        - terminology: dict - Terminology map from PF-4 (optional)

        Returns AgentResponse with:
        - bids: List of extracted bids with scope, timeline, requirements, contacts
        - total_bids_found: Count of bids found
        - bids_by_status: Breakdown by open/closed/awarded
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
            self.emit_event("processing", f"Extracting bid data for {municipality_name}, {state}")

            # Search for bid data using Tavily
            search_results = await self._search_sources(
                municipality_name, state, source_map, terminology
            )

            # Build context from search results
            context = self._build_context(search_results, source_map)

            # Get the prompt with input substituted
            prompt = get_prompt(municipality_name, state)

            # Build user message with search context
            user_message = f"""Extract municipal public bid data for: {municipality_name}, {state}

SEARCH RESULTS AND SOURCE CONTEXT:
{context}

Based on these search results, extract:

1. **BIDS** - Find all bids/RFPs/contracts related to sewer and storm drain work
   - APPLY INCLUSION FILTER: Only include bids with explicit sewer/storm keywords
   - Extract bid title, number, agency
   - Identify which keywords triggered inclusion
   - Determine status: open, closed, or awarded

2. **SCOPE** - For each bid:
   - Description of work
   - Budget/estimated amount
   - Work type (CCTV, cleaning, lining, etc.)
   - Quantities (footage, asset counts)
   - Methods specified

3. **TIMELINE** - Extract all dates:
   - Bid due date (with time and timezone)
   - Pre-bid meeting date/time/location
   - Last day for questions
   - Council meeting (for approval)
   - Project start/end dates

4. **REQUIREMENTS** - For each bid:
   - Qualification requirements
   - Certifications needed
   - Submission location and method
   - Bond requirements
   - Insurance requirements

5. **CONTACTS** - Extract:
   - Name, title, phone, email
   - Agency address

6. **DOWNLOADABLE DOCUMENTS** - Identify for EX-6:
   - Document title
   - URL (especially PDFs)
   - File type

CRITICAL REQUIREMENTS:
- INCLUSION FILTER IS MANDATORY - Only include bids with sewer/storm keywords
- Every data point MUST have a verbatim citation (exact quote from source)
- Capture ALL dates in format: "Month Day, Year, Time Timezone"
- Identify ALL downloadable document URLs
- Use "NOT FOUND" if data cannot be located
- Rate confidence based on source type: bid portal = HIGH, news = LOW

Return the JSON output as specified in your instructions."""

            self.emit_event("processing", "Analyzing search results for bid data...")

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
                logger.warning(f"EX-5 validation failed: {errors}")
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

            # Count bids found
            bids_found = output_data.get('total_bids_found', 0)
            bids_by_status = output_data.get('bids_by_status', {})
            open_bids = bids_by_status.get('open', 0)

            # Emit completion event with summary
            self.emit_event(
                "completed",
                f"Found {bids_found} bids ({open_bids} open)",
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
            logger.error(f"EX-5 JSON extraction failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'extraction_error': str(e), 'raw_response': content[:1000] if content else ''},
                errors=[f"JSON extraction error: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )
        except json.JSONDecodeError as e:
            logger.error(f"EX-5 JSON parse failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'parse_error': str(e), 'attempted_json': json_str[:500] if json_str else ''},
                errors=[f"JSON parse error at position {e.pos}: {e.msg}"],
                processing_time_seconds=time.time() - start_time
            )
        except Exception as e:
            logger.exception(f"EX-5 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate bid extraction output against spec."""
        errors = []

        # Check required top-level fields
        if 'bids' not in output:
            errors.append("Missing 'bids' list")

        if 'total_bids_found' not in output:
            errors.append("Missing 'total_bids_found' count")

        # Return early if missing required sections
        if errors:
            return errors

        # Validate bids is a list
        bids = output.get('bids', [])
        if not isinstance(bids, list):
            errors.append("'bids' must be a list")
            return errors

        # Validate each bid
        for i, bid in enumerate(bids):
            if not isinstance(bid, dict):
                errors.append(f"Bid {i} must be a dictionary")
                continue

            bid_errors = self._validate_bid(bid, i)
            errors.extend(bid_errors)

        # Validate bids_by_status if present
        bids_by_status = output.get('bids_by_status')
        if bids_by_status is not None:
            if not isinstance(bids_by_status, dict):
                errors.append("'bids_by_status' must be a dictionary")
            else:
                for status in ['open', 'closed', 'awarded']:
                    if status not in bids_by_status:
                        errors.append(f"'bids_by_status' missing '{status}'")

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

    def _validate_bid(self, bid: Dict[str, Any], index: int) -> List[str]:
        """Validate a single bid entry."""
        errors = []
        prefix = f"Bid {index}"

        # Required fields
        if not bid.get('bid_title'):
            errors.append(f"{prefix} missing 'bid_title'")

        if not bid.get('sewer_storm_keywords'):
            errors.append(f"{prefix} missing 'sewer_storm_keywords' (INCLUSION FILTER)")
        elif not isinstance(bid.get('sewer_storm_keywords'), list):
            errors.append(f"{prefix} 'sewer_storm_keywords' must be a list")
        elif len(bid.get('sewer_storm_keywords', [])) == 0:
            errors.append(f"{prefix} has no sewer_storm_keywords (violates INCLUSION FILTER)")

        if not bid.get('status'):
            errors.append(f"{prefix} missing 'status'")
        elif bid.get('status') not in ['open', 'closed', 'awarded']:
            errors.append(f"{prefix} invalid status: {bid.get('status')}")

        # Validate scope section
        scope = bid.get('scope')
        if scope:
            if not isinstance(scope, dict):
                errors.append(f"{prefix} 'scope' must be a dictionary")
            else:
                scope_errors = self._validate_section_with_citation(scope, f"{prefix}.scope")
                errors.extend(scope_errors)

        # Validate timeline section
        timeline = bid.get('timeline')
        if timeline:
            if not isinstance(timeline, dict):
                errors.append(f"{prefix} 'timeline' must be a dictionary")
            else:
                timeline_errors = self._validate_section_with_citation(timeline, f"{prefix}.timeline")
                errors.extend(timeline_errors)

        # Validate requirements section
        requirements = bid.get('requirements')
        if requirements:
            if not isinstance(requirements, dict):
                errors.append(f"{prefix} 'requirements' must be a dictionary")
            else:
                req_errors = self._validate_section_with_citation(requirements, f"{prefix}.requirements")
                errors.extend(req_errors)

        # Validate contacts section
        contacts = bid.get('contacts')
        if contacts:
            if not isinstance(contacts, dict):
                errors.append(f"{prefix} 'contacts' must be a dictionary")

        # Validate downloadable_documents
        docs = bid.get('downloadable_documents')
        if docs is not None and not isinstance(docs, list):
            errors.append(f"{prefix} 'downloadable_documents' must be a list")

        return errors

    def _validate_section_with_citation(self, section: Dict[str, Any], section_name: str) -> List[str]:
        """Validate a section has required citation fields when data is present."""
        errors = []

        # Check for confidence
        confidence = section.get('confidence')
        if confidence and confidence not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append(f"{section_name} invalid confidence: {confidence}")

        # Check if section has data (not just "NOT FOUND")
        has_data = False
        for key, value in section.items():
            if key not in ['source_url', 'verbatim_citation', 'confidence']:
                if value and not str(value).startswith('NOT FOUND'):
                    has_data = True
                    break

        # If data was found, require verbatim citation
        if has_data:
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
            Dict mapping bid titles to ExtractedDataPoint objects
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

        # Convert each bid to data point
        bids = output.get('bids', [])
        for bid in bids:
            bid_title = bid.get('bid_title', 'Unknown')
            safe_key = bid_title.replace(' ', '_').replace('-', '_')[:50]

            data_points[safe_key] = ExtractedDataPoint(
                field_name=f"bid_{safe_key}",
                value=self._format_bid_summary(bid),
                raw_source_value=self._get_bid_citation(bid),
                source_url=self._get_bid_source_url(bid),
                verbatim_quote=self._get_bid_citation(bid) or '',
                confidence=confidence_str_to_enum(self._get_bid_confidence(bid)),
                confidence_rationale=f"Bid data from {bid.get('status', 'unknown')} bid",
                notes=self._get_bid_notes(bid)
            )

        return data_points

    def _format_bid_summary(self, bid: Dict[str, Any]) -> str:
        """Format bid data into a summary string."""
        parts = []

        title = bid.get('bid_title', 'Unknown')
        status = bid.get('status', 'unknown')
        parts.append(f"{title} [{status}]")

        # Add due date if available
        timeline = bid.get('timeline', {})
        if isinstance(timeline, dict):
            due_date = timeline.get('bid_due_date')
            if due_date and not str(due_date).startswith('NOT FOUND'):
                parts.append(f"Due: {due_date}")

        # Add scope summary if available
        scope = bid.get('scope', {})
        if isinstance(scope, dict):
            work_type = scope.get('work_type')
            if work_type and not str(work_type).startswith('NOT FOUND'):
                parts.append(f"Type: {work_type}")

            budget = scope.get('budget_amount')
            if budget and not str(budget).startswith('NOT FOUND'):
                parts.append(f"Budget: {budget}")

        return "; ".join(parts)

    def _get_bid_citation(self, bid: Dict[str, Any]) -> Optional[str]:
        """Get the primary citation from bid data."""
        # Try scope first
        scope = bid.get('scope', {})
        if isinstance(scope, dict) and scope.get('verbatim_citation'):
            return scope['verbatim_citation']

        # Try timeline
        timeline = bid.get('timeline', {})
        if isinstance(timeline, dict) and timeline.get('verbatim_citation'):
            return timeline['verbatim_citation']

        # Try requirements
        requirements = bid.get('requirements', {})
        if isinstance(requirements, dict) and requirements.get('verbatim_citation'):
            return requirements['verbatim_citation']

        return None

    def _get_bid_source_url(self, bid: Dict[str, Any]) -> str:
        """Get the best source URL from bid data."""
        # Try scope first
        scope = bid.get('scope', {})
        if isinstance(scope, dict) and scope.get('source_url'):
            return scope['source_url']

        # Try timeline
        timeline = bid.get('timeline', {})
        if isinstance(timeline, dict) and timeline.get('source_url'):
            return timeline['source_url']

        # Try requirements
        requirements = bid.get('requirements', {})
        if isinstance(requirements, dict) and requirements.get('source_url'):
            return requirements['source_url']

        # Try contacts
        contacts = bid.get('contacts', {})
        if isinstance(contacts, dict) and contacts.get('source_url'):
            return contacts['source_url']

        return ''

    def _get_bid_confidence(self, bid: Dict[str, Any]) -> str:
        """Get the best confidence level from bid data."""
        confidence_rank = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
        best_conf = 'LOW'
        best_rank = 0

        for section_key in ['scope', 'timeline', 'requirements']:
            section = bid.get(section_key, {})
            if isinstance(section, dict):
                conf = section.get('confidence', 'LOW')
                conf_rank = confidence_rank.get(conf, 0)
                if conf_rank > best_rank:
                    best_conf = conf
                    best_rank = conf_rank

        return best_conf

    def _get_bid_notes(self, bid: Dict[str, Any]) -> Optional[str]:
        """Get notes for a bid."""
        notes = []

        # Keywords that triggered inclusion
        keywords = bid.get('sewer_storm_keywords', [])
        if keywords:
            notes.append(f"Keywords: {', '.join(keywords)}")

        # Agency
        agency = bid.get('agency')
        if agency:
            notes.append(f"Agency: {agency}")

        # Document count
        docs = bid.get('downloadable_documents', [])
        if docs:
            notes.append(f"Documents: {len(docs)}")

        return "; ".join(notes) if notes else None

    def get_downloadable_documents(self, output: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract all downloadable documents from output for EX-6.

        Args:
            output: Validated output from process()

        Returns:
            List of document dicts with title, url, file_type, bid_title
        """
        documents = []

        bids = output.get('bids', [])
        for bid in bids:
            bid_title = bid.get('bid_title', 'Unknown')
            docs = bid.get('downloadable_documents', [])

            if isinstance(docs, list):
                for doc in docs:
                    if isinstance(doc, dict) and doc.get('url'):
                        documents.append({
                            'title': doc.get('title', 'Unknown Document'),
                            'url': doc.get('url'),
                            'file_type': doc.get('file_type', 'Unknown'),
                            'bid_title': bid_title
                        })

        return documents
