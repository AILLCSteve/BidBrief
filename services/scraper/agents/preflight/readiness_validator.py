"""
Readiness Validator Agent (PF-5)

Aggregates all pre-flight results and determines if extraction can proceed.
This is the final pre-flight agent that gates the extraction phase.

Responsibilities:
- Aggregate results from PF-1 through PF-4
- Determine PASS/PARTIAL/FAIL status
- List gaps and provide remediation recommendations
- Provide extraction guidance based on source completeness
- Gate extraction phase based on readiness assessment
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    PreflightResult,
    PreflightStatus,
    Municipality,
    TableMode,
    JurisdictionInfo,
    SourceMap,
    TerminologyMap,
    SourceURL
)
from services.scraper.prompts.pf5_readiness_validator import get_prompt

logger = logging.getLogger(__name__)


class ReadinessValidatorAgent(BaseAgent):
    """
    PF-5: Readiness Validator Agent

    Aggregates all pre-flight results from PF-1 through PF-4 and determines
    if the extraction phase can proceed. This agent does NOT perform Tavily
    searches - it evaluates the completeness of pre-flight data.
    """

    AGENT_ID = "pf-5"
    AGENT_NAME = "Readiness Validator"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-03"

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt("{{municipality_name}}", "{{state}}", "{{table_mode}}")

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

    def _build_preflight_summary(
        self,
        pf1_result: Dict[str, Any],
        pf2_result: Dict[str, Any],
        pf3_result: Dict[str, Any],
        pf4_result: Dict[str, Any]
    ) -> str:
        """
        Compile results from PF-1 through PF-4 into a summary for evaluation.

        Args:
            pf1_result: Municipality normalization result
            pf2_result: Jurisdiction mapping result
            pf3_result: Source discovery result
            pf4_result: Terminology extraction result

        Returns:
            Formatted summary string for LLM evaluation
        """
        summary_parts = ["## PRE-FLIGHT RESULTS SUMMARY\n"]

        # PF-1: Municipality Normalizer
        summary_parts.append("### PF-1: Municipality Normalizer")
        if pf1_result:
            normalized_name = pf1_result.get('normalized_name', 'NOT PROVIDED')
            state = pf1_result.get('state', 'NOT PROVIDED')
            confidence = pf1_result.get('confidence', 'UNKNOWN')
            validation_status = pf1_result.get('validation_status', 'unknown')
            summary_parts.append(f"- Normalized Name: {normalized_name}")
            summary_parts.append(f"- State: {state}")
            summary_parts.append(f"- Confidence: {confidence}")
            summary_parts.append(f"- Validation Status: {validation_status}")
            if pf1_result.get('population'):
                summary_parts.append(f"- Population: {pf1_result['population']}")
            if pf1_result.get('county'):
                summary_parts.append(f"- County: {pf1_result['county']}")
        else:
            summary_parts.append("- **STATUS: NOT COMPLETED**")
        summary_parts.append("")

        # PF-2: Jurisdiction Mapper
        summary_parts.append("### PF-2: Jurisdiction Mapper")
        if pf2_result:
            sanitary_owner = pf2_result.get('sanitary_sewer_owner', 'NOT FOUND')
            sanitary_operator = pf2_result.get('sanitary_sewer_operator', 'NOT FOUND')
            storm_owner = pf2_result.get('storm_drain_owner', 'NOT FOUND')
            storm_operator = pf2_result.get('storm_drain_operator', 'NOT FOUND')
            confidence = pf2_result.get('confidence', 'UNKNOWN')
            summary_parts.append(f"- Sanitary Sewer Owner: {sanitary_owner}")
            summary_parts.append(f"- Sanitary Sewer Operator: {sanitary_operator}")
            summary_parts.append(f"- Storm Drain Owner: {storm_owner}")
            summary_parts.append(f"- Storm Drain Operator: {storm_operator}")
            summary_parts.append(f"- Confidence: {confidence}")
            if pf2_result.get('sources'):
                summary_parts.append(f"- Sources Found: {len(pf2_result['sources'])}")
        else:
            summary_parts.append("- **STATUS: NOT COMPLETED**")
        summary_parts.append("")

        # PF-3: Source Discovery
        summary_parts.append("### PF-3: Source Discovery")
        if pf3_result:
            source_map = pf3_result.get('source_map', {})
            sources_found = []
            sources_missing = []

            # Check each source type
            source_types = [
                ('official_website', 'Official Website'),
                ('public_works_page', 'Public Works Page'),
                ('sewer_utility_page', 'Sewer Utility Page'),
                ('stormwater_page', 'Stormwater Page'),
                ('procurement_page', 'Procurement Page'),
                ('gis_portal', 'GIS Portal')
            ]

            for key, label in source_types:
                if source_map.get(key):
                    sources_found.append(label)
                else:
                    sources_missing.append(label)

            # Check document sources
            cip_docs = source_map.get('cip_documents', [])
            compliance_sources = source_map.get('compliance_sources', [])

            summary_parts.append(f"- Sources Found: {', '.join(sources_found) if sources_found else 'None'}")
            summary_parts.append(f"- Sources Missing: {', '.join(sources_missing) if sources_missing else 'None'}")
            summary_parts.append(f"- CIP Documents: {len(cip_docs)}")
            summary_parts.append(f"- Compliance Sources: {len(compliance_sources)}")
            confidence = pf3_result.get('confidence', 'UNKNOWN')
            summary_parts.append(f"- Confidence: {confidence}")
        else:
            summary_parts.append("- **STATUS: NOT COMPLETED**")
        summary_parts.append("")

        # PF-4: Terminology Extractor
        summary_parts.append("### PF-4: Terminology Extractor")
        if pf4_result:
            terminology = pf4_result.get('terminology', {})
            bid_keywords = pf4_result.get('bid_portal_keywords', {})
            confidence = pf4_result.get('confidence', 'UNKNOWN')

            # Check terminology categories
            sanitary_locked = bool(terminology.get('sanitary_sewer', {}).get('primary_term'))
            storm_locked = bool(terminology.get('stormwater', {}).get('primary_term'))
            equipment_locked = bool(terminology.get('equipment'))

            summary_parts.append(f"- Sanitary Sewer Terms: {'LOCKED' if sanitary_locked else 'NOT FOUND'}")
            summary_parts.append(f"- Stormwater Terms: {'LOCKED' if storm_locked else 'NOT FOUND'}")
            summary_parts.append(f"- Equipment Terms: {'LOCKED' if equipment_locked else 'NOT FOUND'}")

            # Check bid keywords
            infra_keywords = bid_keywords.get('infrastructure', [])
            service_keywords = bid_keywords.get('services', [])
            summary_parts.append(f"- Infrastructure Keywords: {len(infra_keywords)}")
            summary_parts.append(f"- Service Keywords: {len(service_keywords)}")
            summary_parts.append(f"- Confidence: {confidence}")

            if pf4_result.get('terminology_gaps'):
                summary_parts.append(f"- Gaps: {', '.join(pf4_result['terminology_gaps'])}")
        else:
            summary_parts.append("- **STATUS: NOT COMPLETED**")
        summary_parts.append("")

        return "\n".join(summary_parts)

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process readiness validation request.

        Expected input_data:
        - municipality_name: str - Normalized municipality name
        - state: str - Full state name
        - table_mode: str - "Municipal Systems Information" or "Municipal Public Bids"
        - pf1_result: dict - Municipality normalization result
        - pf2_result: dict - Jurisdiction mapping result
        - pf3_result: dict - Source discovery result
        - pf4_result: dict - Terminology extraction result

        Returns AgentResponse with:
        - status: PASS/PARTIAL/FAIL
        - source_assessment: Critical/Important/Optional source evaluation
        - gaps: List of identified gaps with severity and remediation
        - recommendations: Actionable recommendations
        - extraction_guidance: Guidance for extraction phase
        - risk_assessment: Overall risk evaluation
        - preflight_summary: Summary of all PF agent results
        """
        start_time = time.time()
        content = ''  # Initialize before any operation
        json_str = ''  # Initialize before any operation

        municipality_name = request.input_data.get('municipality_name', '')
        state = request.input_data.get('state', '')
        table_mode = request.input_data.get('table_mode', 'Municipal Systems Information')
        pf1_result = request.input_data.get('pf1_result', {})
        pf2_result = request.input_data.get('pf2_result', {})
        pf3_result = request.input_data.get('pf3_result', {})
        pf4_result = request.input_data.get('pf4_result', {})

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

        # Validate table_mode
        valid_table_modes = ["Municipal Systems Information", "Municipal Public Bids"]
        if table_mode not in valid_table_modes:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"Invalid table_mode: {table_mode}. Must be one of: {valid_table_modes}"]
            )

        try:
            # Emit event for UI activity feed
            self.emit_event("processing", f"Validating readiness for {municipality_name}, {state}")

            # Build summary of all pre-flight results
            preflight_summary = self._build_preflight_summary(
                pf1_result, pf2_result, pf3_result, pf4_result
            )

            # Get the prompt with input substituted
            prompt = get_prompt(municipality_name, state, table_mode)

            # Build user message with pre-flight summary
            user_message = f"""Validate extraction readiness for: {municipality_name}, {state}
Table Mode: {table_mode}

{preflight_summary}

Based on these pre-flight results, determine:
1. Overall readiness status (PASS/PARTIAL/FAIL)
2. Source assessment by category (critical/important/optional)
3. Identified gaps with severity and remediation
4. Actionable recommendations
5. Extraction guidance
6. Risk assessment

Return the JSON readiness assessment as specified in your instructions."""

            self.emit_event("processing", "Analyzing pre-flight completeness...")

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
                logger.warning(f"PF-5 validation failed: {errors}")
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
            status = output_data.get('status', 'UNKNOWN')
            can_proceed = output_data.get('extraction_guidance', {}).get('can_proceed', False)
            gaps_count = len(output_data.get('gaps', []))

            self.emit_event(
                "completed",
                f"Readiness: {status} | Can Proceed: {can_proceed} | Gaps: {gaps_count}",
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
            logger.error(f"PF-5 JSON extraction failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'extraction_error': str(e), 'raw_response': content[:1000] if content else ''},
                errors=[f"JSON extraction error: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )
        except json.JSONDecodeError as e:
            logger.error(f"PF-5 JSON parse failed: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'parse_error': str(e), 'attempted_json': json_str[:500] if json_str else ''},
                errors=[f"JSON parse error at position {e.pos}: {e.msg}"],
                processing_time_seconds=time.time() - start_time
            )
        except Exception as e:
            logger.exception(f"PF-5 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate readiness assessment output against spec."""
        errors = []

        # Check required status field
        status = output.get('status')
        if not status:
            errors.append("Missing required 'status' field")
        elif status not in ['PASS', 'PARTIAL', 'FAIL']:
            errors.append(f"Invalid status: {status}. Must be PASS, PARTIAL, or FAIL")

        # Check source_assessment section
        if 'source_assessment' not in output:
            errors.append("Missing required 'source_assessment' section")
        else:
            sa = output['source_assessment']
            if 'critical' not in sa:
                errors.append("source_assessment missing 'critical' subsection")
            else:
                critical = sa['critical']
                if 'required' not in critical:
                    errors.append("critical sources missing 'required' list")
                if 'found' not in critical:
                    errors.append("critical sources missing 'found' list")
                if 'missing' not in critical:
                    errors.append("critical sources missing 'missing' list")

            if 'important' not in sa:
                errors.append("source_assessment missing 'important' subsection")

        # Check gaps section
        if 'gaps' not in output:
            errors.append("Missing required 'gaps' section")
        elif not isinstance(output['gaps'], list):
            errors.append("'gaps' must be a list")
        else:
            for i, gap in enumerate(output['gaps']):
                if not isinstance(gap, dict):
                    errors.append(f"Gap {i} must be a dictionary")
                    continue
                if 'source' not in gap:
                    errors.append(f"Gap {i} missing 'source' field")
                if 'severity' not in gap:
                    errors.append(f"Gap {i} missing 'severity' field")
                elif gap['severity'] not in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
                    errors.append(f"Gap {i} has invalid severity: {gap['severity']}")

        # Check recommendations section
        if 'recommendations' not in output:
            errors.append("Missing required 'recommendations' section")
        elif not isinstance(output['recommendations'], list):
            errors.append("'recommendations' must be a list")

        # Check extraction_guidance section
        if 'extraction_guidance' not in output:
            errors.append("Missing required 'extraction_guidance' section")
        else:
            eg = output['extraction_guidance']
            if 'can_proceed' not in eg:
                errors.append("extraction_guidance missing 'can_proceed' field")
            elif not isinstance(eg['can_proceed'], bool):
                errors.append("'can_proceed' must be a boolean")
            if 'confidence_level' not in eg:
                errors.append("extraction_guidance missing 'confidence_level' field")

        # Check risk_assessment section
        if 'risk_assessment' not in output:
            errors.append("Missing required 'risk_assessment' section")
        else:
            ra = output['risk_assessment']
            if 'overall_risk' not in ra:
                errors.append("risk_assessment missing 'overall_risk' field")
            elif ra['overall_risk'] not in ['LOW', 'MEDIUM', 'HIGH']:
                errors.append(f"Invalid overall_risk: {ra['overall_risk']}")

        # Check preflight_summary section
        if 'preflight_summary' not in output:
            errors.append("Missing required 'preflight_summary' section")

        # Validate FAIL status logic
        if status == 'FAIL':
            eg = output.get('extraction_guidance', {})
            if eg.get('can_proceed', False):
                errors.append("FAIL status cannot have can_proceed=true")

        return errors

    def to_preflight_result(
        self,
        output: Dict[str, Any],
        municipality_name: str,
        state: str,
        table_mode: str,
        pf2_result: Optional[Dict[str, Any]] = None,
        pf3_result: Optional[Dict[str, Any]] = None,
        pf4_result: Optional[Dict[str, Any]] = None
    ) -> Optional[PreflightResult]:
        """
        Convert validated output to PreflightResult model object.

        Args:
            output: Validated output from process()
            municipality_name: Normalized municipality name
            state: Full state name
            table_mode: Table mode string
            pf2_result: Jurisdiction mapping result (optional)
            pf3_result: Source discovery result (optional)
            pf4_result: Terminology extraction result (optional)

        Returns:
            PreflightResult object or None if conversion fails
        """
        try:
            # Create Municipality object
            municipality = Municipality(city=municipality_name, state=state)

            # Determine TableMode enum
            if table_mode == "Municipal Public Bids":
                mode = TableMode.MUNICIPAL_PUBLIC_BIDS
            else:
                mode = TableMode.MUNICIPAL_SYSTEMS_INFO

            # Determine PreflightStatus enum
            status_str = output.get('status', 'FAIL')
            if status_str == 'PASS':
                status = PreflightStatus.PASS
            elif status_str == 'PARTIAL':
                status = PreflightStatus.PARTIAL
            else:
                status = PreflightStatus.FAIL

            # Build JurisdictionInfo from PF-2 result if available
            jurisdiction = None
            if pf2_result:
                jurisdiction = JurisdictionInfo(
                    sanitary_sewer_owner=pf2_result.get('sanitary_sewer_owner', 'NOT FOUND'),
                    sanitary_sewer_operator=pf2_result.get('sanitary_sewer_operator', 'NOT FOUND'),
                    storm_drain_owner=pf2_result.get('storm_drain_owner', 'NOT FOUND'),
                    storm_drain_operator=pf2_result.get('storm_drain_operator', 'NOT FOUND'),
                    notes=pf2_result.get('notes', ''),
                    sources=[]
                )

            # Build SourceMap from PF-3 result if available
            source_map = None
            if pf3_result:
                sm = pf3_result.get('source_map', {})
                source_map = SourceMap(
                    official_website=self._url_to_source(sm.get('official_website')),
                    public_works_page=self._url_to_source(sm.get('public_works_page')),
                    sewer_utility_page=self._url_to_source(sm.get('sewer_utility_page')),
                    stormwater_page=self._url_to_source(sm.get('stormwater_page')),
                    procurement_page=self._url_to_source(sm.get('procurement_page')),
                    gis_portal=self._url_to_source(sm.get('gis_portal')),
                    cip_documents=[],
                    compliance_sources=[]
                )

            # Build TerminologyMap from PF-4 result if available
            terminology = None
            if pf4_result:
                term = pf4_result.get('terminology', {})
                bid_kw = pf4_result.get('bid_portal_keywords', {})

                # Extract sanitary terms
                sanitary_terms = []
                sanitary = term.get('sanitary_sewer', {})
                if sanitary.get('primary_term'):
                    sanitary_terms.append(sanitary['primary_term'])
                sanitary_terms.extend(sanitary.get('alternate_terms', []))

                # Extract storm terms
                storm_terms = []
                storm = term.get('stormwater', {})
                if storm.get('primary_term'):
                    storm_terms.append(storm['primary_term'])
                storm_terms.extend(storm.get('alternate_terms', []))

                # Extract lift station terms
                lift_station_terms = []
                lift = term.get('lift_stations', {})
                if lift.get('primary_term'):
                    lift_station_terms.append(lift['primary_term'])
                lift_station_terms.extend(lift.get('alternate_terms', []))

                # Extract bid portal keywords
                bid_portal_keywords = []
                bid_portal_keywords.extend(bid_kw.get('infrastructure', []))
                bid_portal_keywords.extend(bid_kw.get('services', []))
                bid_portal_keywords.extend(bid_kw.get('methods', []))

                terminology = TerminologyMap(
                    sanitary_terms=sanitary_terms,
                    storm_terms=storm_terms,
                    lift_station_terms=lift_station_terms,
                    bid_portal_keywords=bid_portal_keywords
                )

            # Extract gaps as string list
            gaps = []
            for gap in output.get('gaps', []):
                gap_str = f"[{gap.get('severity', 'UNKNOWN')}] {gap.get('source', 'Unknown')}: {gap.get('impact', 'No impact specified')}"
                gaps.append(gap_str)

            # Get recommendations
            recommendations = output.get('recommendations', [])

            return PreflightResult(
                municipality=municipality,
                table_mode=mode,
                status=status,
                jurisdiction=jurisdiction,
                source_map=source_map,
                terminology=terminology,
                gaps=gaps,
                recommendations=recommendations
            )

        except Exception as e:
            logger.error(f"Failed to convert output to PreflightResult: {e}")
            return None

    def _url_to_source(self, url_data: Optional[Any]) -> Optional[SourceURL]:
        """Convert URL data to SourceURL object."""
        if not url_data:
            return None

        if isinstance(url_data, str):
            return SourceURL(url=url_data, title="", source_type="official")
        elif isinstance(url_data, dict):
            return SourceURL(
                url=url_data.get('url', ''),
                title=url_data.get('title', ''),
                source_type=url_data.get('source_type', 'official')
            )
        return None
