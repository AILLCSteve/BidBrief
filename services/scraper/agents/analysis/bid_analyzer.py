"""
Bid Analyzer Agent (AN-4)

Provides detailed bid/opportunity analysis with cost estimates and PM considerations.
Based on commsdev Mode B functionality.

Part of the Analysis Layer for CityScraper.

Analysis Outputs:
- bid_summary: Key bid information and dates
- cost_estimates: 3 scenarios (conservative, moderate, aggressive)
- pm_considerations: Resource, timeline, technical, compliance, subcontracting
- competitive_positioning: Strengths, weaknesses, win themes
- go_no_go_factors: Recommendation with rationale
- confidence: Overall analysis confidence level
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
from services.scraper.prompts.an4_bid_analyzer import get_prompt

logger = logging.getLogger(__name__)


class BidAnalyzerAgent(BaseAgent):
    """
    AN-4: Bid Analyzer Agent

    Provides detailed bid/opportunity analysis with cost estimates,
    PM considerations checklist, and go/no-go recommendations.

    This agent transforms bid data from CityScraper extractions into
    actionable intelligence for bid/no-bid decisions.
    """

    AGENT_ID = "an-4"
    AGENT_NAME = "Bid Analyzer"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-04"

    # Valid confidence levels
    VALID_CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")

    # Valid recommendation values
    VALID_RECOMMENDATIONS = ("GO", "NO_GO", "CONDITIONAL")

    # Valid cost estimate scenarios
    VALID_SCENARIOS = ("conservative", "moderate", "aggressive")

    # Required number of cost estimates
    REQUIRED_COST_ESTIMATES = 3

    # Required fields in cost_estimates
    COST_ESTIMATE_REQUIRED_FIELDS = (
        "scenario",
        "estimate_range",
        "rationale",
        "assumptions",
        "risk_factors"
    )

    # Required fields in pm_considerations
    PM_CONSIDERATIONS_FIELDS = (
        "resource_requirements",
        "timeline_risks",
        "technical_challenges",
        "compliance_requirements",
        "subcontracting_needs"
    )

    # Required fields in competitive_positioning
    COMPETITIVE_POSITIONING_FIELDS = (
        "strengths_to_leverage",
        "weaknesses_to_address",
        "win_themes"
    )

    # Required fields in go_no_go_factors
    GO_NO_GO_FIELDS = (
        "go_factors",
        "no_go_factors",
        "recommendation",
        "recommendation_rationale"
    )

    # Required fields in bid_summary.key_dates
    KEY_DATES_FIELDS = (
        "due_date",
        "pre_bid_meeting",
        "questions_deadline",
        "contract_start",
        "contract_end"
    )

    # Minimum items in list fields
    MIN_ASSUMPTIONS = 2
    MIN_RISK_FACTORS = 2
    MIN_RESOURCE_REQUIREMENTS = 3
    MIN_TIMELINE_RISKS = 2
    MIN_TECHNICAL_CHALLENGES = 2
    MIN_COMPLIANCE_REQUIREMENTS = 2
    MIN_SUBCONTRACTING_NEEDS = 1
    MIN_STRENGTHS = 2
    MIN_WEAKNESSES = 2
    MIN_WIN_THEMES = 2
    MIN_GO_FACTORS = 2
    MIN_NO_GO_FACTORS = 1

    # Display limits for LLM context
    MAX_BID_DATA_LENGTH = 6000
    MAX_EXTRACTION_DATA_LENGTH = 4000

    # String truncation limits for formatting bid data
    MAX_SCOPE_LENGTH = 2000
    MAX_TIMELINE_LENGTH = 500
    MAX_TECHNICAL_REQS_LENGTH = 1000
    MAX_QUALIFICATIONS_LENGTH = 500
    MAX_BONDING_LENGTH = 300
    MAX_BUDGET_LENGTH = 300
    MAX_CONTACT_LENGTH = 200
    MAX_ADDITIONAL_FIELD_LENGTH = 200
    MAX_ADDITIONAL_FIELDS_COUNT = 10

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt(
            "{{bid_title}}",
            "{{issuing_agency}}",
            "{{analysis_focus}}"
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

    def _format_bid_data(self, bid_data: Dict[str, Any]) -> str:
        """
        Format bid data for the user message.

        Args:
            bid_data: Bid information from extraction

        Returns:
            Formatted string for prompt
        """
        # Type validation - ensure bid_data is dict
        if not isinstance(bid_data, dict):
            return "Invalid bid data type."

        if not bid_data:
            return "No bid data provided."

        parts = []

        # Extract title
        title = bid_data.get('bid_contract_title', bid_data.get('title', ''))
        if title:
            if isinstance(title, dict):
                title = title.get('value', str(title))
            parts.append(f"## Bid Title: {title}")

        # Extract agency
        agency = bid_data.get('issuing_agency', bid_data.get('agency', ''))
        if agency:
            if isinstance(agency, dict):
                agency = agency.get('value', str(agency))
            parts.append(f"## Issuing Agency: {agency}")

        # Extract status
        status = bid_data.get('status', '')
        if status:
            if isinstance(status, dict):
                status = status.get('value', str(status))
            parts.append(f"## Status: {status}")

        # Extract scope
        scope = bid_data.get('scope', bid_data.get('scope_of_work', ''))
        if scope:
            if isinstance(scope, dict):
                scope = scope.get('value', str(scope))
            parts.append(f"\n## Scope of Work:\n{str(scope)[:self.MAX_SCOPE_LENGTH]}")

        # Extract dates
        parts.append("\n## Key Dates:")
        date_fields = [
            ('due_date', 'Due Date'),
            ('submission_deadline', 'Submission Deadline'),
            ('pre_bid_meeting', 'Pre-Bid Meeting'),
            ('pre_bid_conference', 'Pre-Bid Conference'),
            ('questions_deadline', 'Questions Deadline'),
            ('contract_start', 'Contract Start'),
            ('contract_end', 'Contract End'),
            ('project_duration', 'Project Duration')
        ]
        for field_name, label in date_fields:
            value = bid_data.get(field_name, '')
            if value:
                if isinstance(value, dict):
                    value = value.get('value', str(value))
                parts.append(f"  - {label}: {value}")

        # Extract timeline requirements
        timeline = bid_data.get('timeline_requirements', '')
        if timeline:
            if isinstance(timeline, dict):
                timeline = timeline.get('value', str(timeline))
            parts.append(f"\n## Timeline Requirements:\n{str(timeline)[:self.MAX_TIMELINE_LENGTH]}")

        # Extract technical requirements
        tech_reqs = bid_data.get('technical_requirements', bid_data.get('requirements', ''))
        if tech_reqs:
            if isinstance(tech_reqs, dict):
                tech_reqs = tech_reqs.get('value', str(tech_reqs))
            parts.append(f"\n## Technical Requirements:\n{str(tech_reqs)[:self.MAX_TECHNICAL_REQS_LENGTH]}")

        # Extract qualifications
        qualifications = bid_data.get('qualifications', bid_data.get('required_qualifications', ''))
        if qualifications:
            if isinstance(qualifications, dict):
                qualifications = qualifications.get('value', str(qualifications))
            parts.append(f"\n## Required Qualifications:\n{str(qualifications)[:self.MAX_QUALIFICATIONS_LENGTH]}")

        # Extract bonding requirements
        bonding = bid_data.get('bonding_requirements', bid_data.get('bonding', ''))
        if bonding:
            if isinstance(bonding, dict):
                bonding = bonding.get('value', str(bonding))
            parts.append(f"\n## Bonding Requirements:\n{str(bonding)[:self.MAX_BONDING_LENGTH]}")

        # Extract budget/cost info
        budget = bid_data.get('budget', bid_data.get('estimated_cost', bid_data.get('cost_range', '')))
        if budget:
            if isinstance(budget, dict):
                budget = budget.get('value', str(budget))
            parts.append(f"\n## Budget/Cost Information:\n{str(budget)[:self.MAX_BUDGET_LENGTH]}")

        # Extract contact info
        contact = bid_data.get('contact', bid_data.get('procurement_contact', ''))
        if contact:
            if isinstance(contact, dict):
                contact = contact.get('value', str(contact))
            parts.append(f"\n## Contact:\n{str(contact)[:self.MAX_CONTACT_LENGTH]}")

        # Include any additional fields not already processed
        processed_fields = {
            'bid_contract_title', 'title', 'issuing_agency', 'agency', 'status',
            'scope', 'scope_of_work', 'due_date', 'submission_deadline',
            'pre_bid_meeting', 'pre_bid_conference', 'questions_deadline',
            'contract_start', 'contract_end', 'project_duration',
            'timeline_requirements', 'technical_requirements', 'requirements',
            'qualifications', 'required_qualifications', 'bonding_requirements',
            'bonding', 'budget', 'estimated_cost', 'cost_range', 'contact',
            'procurement_contact', 'source_urls', 'verbatim_citations'
        }
        additional = []
        for key, value in bid_data.items():
            if key not in processed_fields and value:
                if isinstance(value, dict):
                    value = value.get('value', str(value))
                additional.append(f"  - {key}: {str(value)[:self.MAX_ADDITIONAL_FIELD_LENGTH]}")

        if additional:
            parts.append("\n## Additional Information:")
            parts.extend(additional[:self.MAX_ADDITIONAL_FIELDS_COUNT])  # Limit additional fields

        result = "\n".join(parts)

        # Truncate if too long
        if len(result) > self.MAX_BID_DATA_LENGTH:
            result = result[:self.MAX_BID_DATA_LENGTH] + "\n\n[... data truncated ...]"

        return result if result else "Minimal bid data available."

    def _format_extraction_context(self, extraction_result: Dict[str, Any]) -> str:
        """
        Format extraction context for additional background.

        Args:
            extraction_result: Full CityScraper extraction

        Returns:
            Formatted context string
        """
        # Type validation
        if not isinstance(extraction_result, dict):
            return ""

        if not extraction_result:
            return ""

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

        # Include relevant extracted fields (not bid data)
        extracted_data = extraction_result.get('extracted_data', {})
        if extracted_data:
            relevant_fields = [
                'procurement_contact', 'budget_info', 'capital_improvement_program',
                'prevailing_wage', 'local_preference', 'mbe_wbe_requirements'
            ]
            for field_name in relevant_fields:
                if field_name in extracted_data:
                    field_data = extracted_data[field_name]
                    if isinstance(field_data, dict):
                        value = field_data.get('value', '')
                        if value:
                            parts.append(f"{field_name}: {str(value)[:200]}")

        result = "\n".join(parts)

        # Truncate if too long
        if len(result) > self.MAX_EXTRACTION_DATA_LENGTH:
            result = result[:self.MAX_EXTRACTION_DATA_LENGTH] + "\n[... truncated ...]"

        return result

    def _get_bid_title(self, bid_data: Dict[str, Any]) -> str:
        """
        Extract bid title from bid data.

        Args:
            bid_data: Bid data dict

        Returns:
            Bid title string
        """
        if not isinstance(bid_data, dict):
            return "Unknown Bid"

        title = bid_data.get('bid_contract_title', bid_data.get('title', ''))
        if isinstance(title, dict):
            title = title.get('value', '')

        return str(title) if title else "Unknown Bid"

    def _get_issuing_agency(self, bid_data: Dict[str, Any]) -> str:
        """
        Extract issuing agency from bid data.

        Args:
            bid_data: Bid data dict

        Returns:
            Agency name string
        """
        if not isinstance(bid_data, dict):
            return "Unknown Agency"

        agency = bid_data.get('issuing_agency', bid_data.get('agency', ''))
        if isinstance(agency, dict):
            agency = agency.get('value', '')

        return str(agency) if agency else "Unknown Agency"

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process bid analysis request.

        Expected input_data:
        - bid_data: dict - Bid information from extraction (from public_bid_rows)
        - extraction_result: dict - Full CityScraper extraction for context (optional)
        - analysis_focus: str - Optional focus (cost_estimation, timeline, requirements, etc.)

        Returns AgentResponse with:
        - bid_summary: dict with title, agency, status, key_dates
        - cost_estimates: list of 3 scenario dicts
        - pm_considerations: dict with resource, timeline, technical, compliance, subcontracting
        - competitive_positioning: dict with strengths, weaknesses, win_themes
        - go_no_go_factors: dict with go, no_go, recommendation, rationale
        - confidence: str - HIGH/MEDIUM/LOW
        """
        start_time = time.time()
        content = ''  # Initialize before any operation
        json_str = ''  # Initialize before any operation

        # Extract input data
        bid_data = request.input_data.get('bid_data', {})
        extraction_result = request.input_data.get('extraction_result', {})
        analysis_focus = request.input_data.get('analysis_focus', '')

        # Type validation for bid_data
        if not isinstance(bid_data, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"bid_data must be dict, got {type(bid_data).__name__}"]
            )

        # Type validation for extraction_result (optional, can be dict or None)
        if extraction_result is not None and not isinstance(extraction_result, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"extraction_result must be dict or None, got {type(extraction_result).__name__}"]
            )

        # Type validation for analysis_focus (optional, must be string or None)
        if analysis_focus is None:
            analysis_focus = ''
        elif not isinstance(analysis_focus, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"analysis_focus must be string or None, got {type(analysis_focus).__name__}"]
            )

        # Handle empty bid data
        if not bid_data:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["No bid data provided. Cannot analyze bid without data."],
                processing_time_seconds=time.time() - start_time
            )

        try:
            # Get bid title and agency for prompt
            bid_title = self._get_bid_title(bid_data)
            issuing_agency = self._get_issuing_agency(bid_data)

            # Emit event for UI activity feed
            self.emit_event(
                "processing",
                f"Analyzing bid: {bid_title[:50]}..."
            )

            # Format bid data for prompt
            bid_text = self._format_bid_data(bid_data)

            # Format extraction context if available
            context_text = ""
            if extraction_result:
                context_text = self._format_extraction_context(extraction_result)

            # Get the prompt with inputs substituted
            prompt = get_prompt(
                bid_title=bid_title,
                issuing_agency=issuing_agency,
                analysis_focus=analysis_focus
            )

            # Build user message
            focus_instruction = ""
            if analysis_focus:
                focus_instruction = f"\n\n**Analysis Focus:** {analysis_focus}\nProvide extra detail in this area."

            context_section = ""
            if context_text:
                context_section = f"\n\n---\n\n## ADDITIONAL CONTEXT\n\n{context_text}"

            user_message = f"""Analyze the following bid opportunity and provide comprehensive analysis.

**CRITICAL**: Base all estimates on industry benchmarks and available data. Ground recommendations in facts.
{focus_instruction}

---

## BID DATA

{bid_text}
{context_section}

---

Generate complete analysis including:
1. Bid summary with key dates
2. Three cost estimate scenarios (conservative, moderate, aggressive) with rationale
3. PM considerations checklist (resources, timeline, technical, compliance, subcontracting)
4. Competitive positioning (strengths, weaknesses, win themes)
5. Go/No-Go recommendation with detailed rationale

Return the complete JSON output as specified in your instructions."""

            self.emit_event(
                "processing",
                f"Building cost estimates and PM checklist..."
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
            errors = self.validate_output(output_data)

            if errors:
                logger.warning(f"AN-4 validation failed: {errors}")
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
            recommendation = output_data.get('go_no_go_factors', {}).get('recommendation', 'UNKNOWN')
            cost_estimates = output_data.get('cost_estimates', [])
            moderate_estimate = next(
                (e.get('estimate_range', 'N/A') for e in cost_estimates if e.get('scenario') == 'moderate'),
                'N/A'
            )

            completion_msg = (
                f"Bid analysis complete: {recommendation} recommendation, "
                f"moderate estimate {moderate_estimate}, "
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
            logger.error(f"AN-4 JSON parse failed: {e}")
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
            logger.error(f"AN-4 JSON extraction failed: {e}")
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
            logger.error(f"AN-4 data structure error: {e}")
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
            logger.exception(f"AN-4 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """
        Validate bid analyzer output against spec.

        Args:
            output: The output data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required top-level fields
        required_fields = [
            'bid_summary',
            'cost_estimates',
            'pm_considerations',
            'competitive_positioning',
            'go_no_go_factors',
            'confidence'
        ]

        for field_name in required_fields:
            if field_name not in output:
                errors.append(f"Missing required field: '{field_name}'")

        # Return early if missing required fields
        if errors:
            return errors

        # Validate bid_summary structure
        bid_summary = output.get('bid_summary')
        if not isinstance(bid_summary, dict):
            errors.append("'bid_summary' must be a dict")
        else:
            # Check required fields in bid_summary
            for field in ('title', 'issuing_agency', 'status', 'key_dates'):
                if field not in bid_summary:
                    errors.append(f"bid_summary missing '{field}'")

            # Validate key_dates if present
            key_dates = bid_summary.get('key_dates')
            if key_dates is not None:
                if not isinstance(key_dates, dict):
                    errors.append("bid_summary.key_dates must be a dict")
                else:
                    for date_field in self.KEY_DATES_FIELDS:
                        if date_field not in key_dates:
                            errors.append(f"bid_summary.key_dates missing '{date_field}'")

        # Validate cost_estimates structure
        cost_estimates = output.get('cost_estimates')
        if not isinstance(cost_estimates, list):
            errors.append("'cost_estimates' must be a list")
        elif len(cost_estimates) != self.REQUIRED_COST_ESTIMATES:
            errors.append(
                f"'cost_estimates' must have exactly {self.REQUIRED_COST_ESTIMATES} items, "
                f"got {len(cost_estimates)}"
            )
        else:
            scenarios_found = set()
            for i, estimate in enumerate(cost_estimates):
                if not isinstance(estimate, dict):
                    errors.append(f"cost_estimates[{i}] must be a dict")
                    continue

                # Check required fields in each estimate
                for field in self.COST_ESTIMATE_REQUIRED_FIELDS:
                    if field not in estimate:
                        errors.append(f"cost_estimates[{i}] missing '{field}'")

                # Validate scenario value
                scenario = estimate.get('scenario')
                if scenario not in self.VALID_SCENARIOS:
                    errors.append(
                        f"cost_estimates[{i}].scenario must be one of {self.VALID_SCENARIOS}, "
                        f"got '{scenario}'"
                    )
                else:
                    scenarios_found.add(scenario)

                # Validate estimate_range is a string
                estimate_range = estimate.get('estimate_range')
                if not isinstance(estimate_range, str) or len(estimate_range.strip()) < 3:
                    errors.append(f"cost_estimates[{i}].estimate_range must be a non-empty string")

                # Validate rationale is meaningful
                rationale = estimate.get('rationale')
                if not isinstance(rationale, str) or len(rationale.strip()) < 20:
                    errors.append(
                        f"cost_estimates[{i}].rationale must be a meaningful string (min 20 chars)"
                    )

                # Validate assumptions list
                assumptions = estimate.get('assumptions')
                if not isinstance(assumptions, list):
                    errors.append(f"cost_estimates[{i}].assumptions must be a list")
                elif len(assumptions) < self.MIN_ASSUMPTIONS:
                    errors.append(
                        f"cost_estimates[{i}].assumptions should have at least "
                        f"{self.MIN_ASSUMPTIONS} items, got {len(assumptions)}"
                    )

                # Validate risk_factors list
                risk_factors = estimate.get('risk_factors')
                if not isinstance(risk_factors, list):
                    errors.append(f"cost_estimates[{i}].risk_factors must be a list")
                elif len(risk_factors) < self.MIN_RISK_FACTORS:
                    errors.append(
                        f"cost_estimates[{i}].risk_factors should have at least "
                        f"{self.MIN_RISK_FACTORS} items, got {len(risk_factors)}"
                    )

            # Check all scenarios are present
            if scenarios_found != set(self.VALID_SCENARIOS):
                missing = set(self.VALID_SCENARIOS) - scenarios_found
                errors.append(f"cost_estimates missing scenarios: {missing}")

        # Validate pm_considerations structure
        pm_considerations = output.get('pm_considerations')
        if not isinstance(pm_considerations, dict):
            errors.append("'pm_considerations' must be a dict")
        else:
            # Check required fields with minimum counts
            field_mins = {
                'resource_requirements': self.MIN_RESOURCE_REQUIREMENTS,
                'timeline_risks': self.MIN_TIMELINE_RISKS,
                'technical_challenges': self.MIN_TECHNICAL_CHALLENGES,
                'compliance_requirements': self.MIN_COMPLIANCE_REQUIREMENTS,
                'subcontracting_needs': self.MIN_SUBCONTRACTING_NEEDS
            }

            for field, min_count in field_mins.items():
                if field not in pm_considerations:
                    errors.append(f"pm_considerations missing '{field}'")
                else:
                    value = pm_considerations[field]
                    if not isinstance(value, list):
                        errors.append(f"pm_considerations.{field} must be a list")
                    elif len(value) < min_count:
                        errors.append(
                            f"pm_considerations.{field} should have at least "
                            f"{min_count} items, got {len(value)}"
                        )

        # Validate competitive_positioning structure
        competitive_positioning = output.get('competitive_positioning')
        if not isinstance(competitive_positioning, dict):
            errors.append("'competitive_positioning' must be a dict")
        else:
            field_mins = {
                'strengths_to_leverage': self.MIN_STRENGTHS,
                'weaknesses_to_address': self.MIN_WEAKNESSES,
                'win_themes': self.MIN_WIN_THEMES
            }

            for field, min_count in field_mins.items():
                if field not in competitive_positioning:
                    errors.append(f"competitive_positioning missing '{field}'")
                else:
                    value = competitive_positioning[field]
                    if not isinstance(value, list):
                        errors.append(f"competitive_positioning.{field} must be a list")
                    elif len(value) < min_count:
                        errors.append(
                            f"competitive_positioning.{field} should have at least "
                            f"{min_count} items, got {len(value)}"
                        )

        # Validate go_no_go_factors structure
        go_no_go_factors = output.get('go_no_go_factors')
        if not isinstance(go_no_go_factors, dict):
            errors.append("'go_no_go_factors' must be a dict")
        else:
            # Check required fields
            for field in self.GO_NO_GO_FIELDS:
                if field not in go_no_go_factors:
                    errors.append(f"go_no_go_factors missing '{field}'")

            # Validate go_factors list
            go_factors = go_no_go_factors.get('go_factors')
            if go_factors is not None:
                if not isinstance(go_factors, list):
                    errors.append("go_no_go_factors.go_factors must be a list")
                elif len(go_factors) < self.MIN_GO_FACTORS:
                    errors.append(
                        f"go_no_go_factors.go_factors should have at least "
                        f"{self.MIN_GO_FACTORS} items, got {len(go_factors)}"
                    )

            # Validate no_go_factors list
            no_go_factors = go_no_go_factors.get('no_go_factors')
            if no_go_factors is not None:
                if not isinstance(no_go_factors, list):
                    errors.append("go_no_go_factors.no_go_factors must be a list")
                elif len(no_go_factors) < self.MIN_NO_GO_FACTORS:
                    errors.append(
                        f"go_no_go_factors.no_go_factors should have at least "
                        f"{self.MIN_NO_GO_FACTORS} items, got {len(no_go_factors)}"
                    )

            # Validate recommendation
            recommendation = go_no_go_factors.get('recommendation')
            if recommendation not in self.VALID_RECOMMENDATIONS:
                errors.append(
                    f"go_no_go_factors.recommendation must be one of "
                    f"{self.VALID_RECOMMENDATIONS}, got '{recommendation}'"
                )

            # Validate recommendation_rationale is meaningful
            rationale = go_no_go_factors.get('recommendation_rationale')
            if not isinstance(rationale, str) or len(rationale.strip()) < 30:
                errors.append(
                    "go_no_go_factors.recommendation_rationale must be a meaningful string "
                    "(min 30 chars)"
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
        bid_summary = output.get('bid_summary', {})
        cost_estimates = output.get('cost_estimates', [])
        pm_considerations = output.get('pm_considerations', {})
        competitive_positioning = output.get('competitive_positioning', {})
        go_no_go_factors = output.get('go_no_go_factors', {})

        # Format cost estimates with scenario labels
        formatted_estimates = []
        scenario_labels = {
            'conservative': 'Conservative (Higher Risk Allowance)',
            'moderate': 'Moderate (Most Likely)',
            'aggressive': 'Aggressive (Optimal Conditions)'
        }
        for estimate in cost_estimates:
            scenario = estimate.get('scenario', '')
            formatted_estimates.append({
                'scenario': scenario,
                'scenario_label': scenario_labels.get(scenario, scenario.title()),
                'estimate_range': estimate.get('estimate_range', 'N/A'),
                'rationale': estimate.get('rationale', ''),
                'assumptions': estimate.get('assumptions', []),
                'risk_factors': estimate.get('risk_factors', [])
            })

        # Sort estimates: conservative, moderate, aggressive
        scenario_order = {'conservative': 0, 'moderate': 1, 'aggressive': 2}
        formatted_estimates.sort(key=lambda x: scenario_order.get(x['scenario'], 99))

        # Format recommendation with visual indicator
        recommendation = go_no_go_factors.get('recommendation', 'UNKNOWN')
        recommendation_style = {
            'GO': {'color': 'green', 'icon': 'check'},
            'NO_GO': {'color': 'red', 'icon': 'x'},
            'CONDITIONAL': {'color': 'yellow', 'icon': 'alert'}
        }

        return {
            'bid_summary': {
                'title': bid_summary.get('title', 'Unknown'),
                'issuing_agency': bid_summary.get('issuing_agency', 'Unknown'),
                'status': bid_summary.get('status', 'Unknown'),
                'key_dates': bid_summary.get('key_dates', {})
            },
            'cost_estimates': formatted_estimates,
            'moderate_estimate': next(
                (e['estimate_range'] for e in formatted_estimates if e['scenario'] == 'moderate'),
                'N/A'
            ),
            'pm_considerations': {
                'resource_requirements': pm_considerations.get('resource_requirements', []),
                'timeline_risks': pm_considerations.get('timeline_risks', []),
                'technical_challenges': pm_considerations.get('technical_challenges', []),
                'compliance_requirements': pm_considerations.get('compliance_requirements', []),
                'subcontracting_needs': pm_considerations.get('subcontracting_needs', [])
            },
            'competitive_positioning': {
                'strengths_to_leverage': competitive_positioning.get('strengths_to_leverage', []),
                'weaknesses_to_address': competitive_positioning.get('weaknesses_to_address', []),
                'win_themes': competitive_positioning.get('win_themes', [])
            },
            'go_no_go': {
                'go_factors': go_no_go_factors.get('go_factors', []),
                'no_go_factors': go_no_go_factors.get('no_go_factors', []),
                'recommendation': recommendation,
                'recommendation_style': recommendation_style.get(recommendation, {}),
                'recommendation_rationale': go_no_go_factors.get('recommendation_rationale', '')
            },
            'confidence': output.get('confidence', 'UNKNOWN'),
            'agent_id': self.AGENT_ID,
            'agent_name': self.AGENT_NAME
        }
