"""
Municipality Normalizer Agent (PF-1)

Validates and normalizes municipality identifiers.
First step in pre-flight validation.

Responsibilities:
- Validate municipality exists
- Normalize name to official form
- Determine state and county
- Flag ambiguities for user clarification
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse,
    Municipality
)
from services.scraper.prompts.pf1_municipality_normalizer import get_prompt

logger = logging.getLogger(__name__)


class MunicipalityNormalizerAgent(BaseAgent):
    """
    PF-1: Municipality Normalizer Agent

    Validates and normalizes municipality input before any research begins.
    """

    AGENT_ID = "pf-1"
    AGENT_NAME = "Municipality Normalizer"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-03"

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt("{{municipality_input}}")

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

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process municipality normalization request.

        Expected input_data:
        - municipality_input: str - Raw municipality input (e.g., "springfield IL")

        Returns AgentResponse with:
        - normalized: Municipality data if valid
        - ambiguities: List of ambiguities if any
        - clarification_needed: Question for user if ambiguous
        """
        start_time = time.time()

        municipality_input = request.input_data.get('municipality_input', '')

        # Type validation
        if not isinstance(municipality_input, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"municipality_input must be string, got {type(municipality_input).__name__}"]
            )

        municipality_input = municipality_input.strip()

        if not municipality_input:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["municipality_input is required"]
            )

        # Length check
        if len(municipality_input) > 200:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"municipality_input too long ({len(municipality_input)} chars, max 200)"]
            )

        try:
            content = ''  # Initialize before any operation

            # Emit event for UI activity feed
            self.emit_event("processing", f"Normalizing municipality: {municipality_input}")

            # Get the prompt with input substituted
            prompt = get_prompt(municipality_input)

            # Call OpenAI
            result = await self.call_openai(
                user_message=f"Normalize this municipality: {municipality_input}",
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
                logger.warning(f"PF-1 validation failed: {errors}")
                self.emit_event(f"Validation errors: {'; '.join(errors)}")
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
            status = output_data.get('validation_status', 'UNKNOWN')
            self.emit_event("completed", f"Normalization complete: {status}", is_completed=True)

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
            logger.error(f"PF-1 failed to parse JSON response: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content},
                errors=[f"JSON parse error: {e}"]
            )
        except Exception as e:
            logger.error(f"PF-1 processing error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content} if content else {},
                errors=[str(e)]
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate normalizer output against spec."""
        errors = []

        # Check required top-level fields
        if 'normalized' not in output:
            errors.append("Missing 'normalized' field")

        if 'validation_status' not in output:
            errors.append("Missing 'validation_status' field")
        elif output['validation_status'] not in ['VALID', 'AMBIGUOUS', 'INVALID']:
            errors.append(f"Invalid validation_status: {output['validation_status']}")

        # AMBIGUOUS status requires clarification
        if output.get('validation_status') == 'AMBIGUOUS':
            if not output.get('clarification_needed') and not output.get('ambiguities'):
                errors.append("AMBIGUOUS status requires 'clarification_needed' or 'ambiguities'")

        normalized = output.get('normalized', {})

        # Required normalized fields
        if not normalized.get('city'):
            errors.append("Missing normalized city name")

        if not normalized.get('state'):
            errors.append("Missing normalized state name")

        # municipality_type validation
        valid_types = ['city', 'town', 'village', 'borough', 'township', 'consolidated']
        mtype = normalized.get('municipality_type')
        if mtype and mtype not in valid_types:
            errors.append(f"Invalid municipality_type: {mtype}")

        # Confidence validation
        confidence = output.get('confidence')
        if confidence and confidence not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append(f"Invalid confidence: {confidence}")

        return errors

    def to_municipality(self, output: Dict[str, Any]) -> Optional[Municipality]:
        """Convert validated output to Municipality object."""
        if output.get('validation_status') != 'VALID':
            return None

        normalized = output.get('normalized', {})

        return Municipality(
            city=normalized.get('city', ''),
            state=normalized.get('state', ''),
            county=normalized.get('county')
        )
