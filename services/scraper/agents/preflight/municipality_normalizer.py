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

        if not municipality_input:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["municipality_input is required"]
            )

        try:
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
            content = result['content']

            # Extract JSON from response (handle markdown code blocks)
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                json_str = content.split('```')[1].split('```')[0].strip()
            else:
                json_str = content.strip()

            output_data = json.loads(json_str)

            # Validate output
            errors = self.validate_output(output_data)

            elapsed = time.time() - start_time

            # Emit completion event
            status = output_data.get('validation_status', 'UNKNOWN')
            self.emit_event("completed", f"Normalization complete: {status}", is_completed=True)

            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=len(errors) == 0,
                output_data=output_data,
                errors=errors,
                tokens_used=result.get('tokens_used', 0),
                processing_time_seconds=elapsed
            )

        except json.JSONDecodeError as e:
            logger.error(f"PF-1 failed to parse JSON response: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content if 'content' in dir() else ''},
                errors=[f"JSON parse error: {e}"]
            )
        except Exception as e:
            logger.error(f"PF-1 processing error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[str(e)]
            )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """Validate normalizer output."""
        errors = []

        # Check required fields
        if 'normalized' not in output:
            errors.append("Missing 'normalized' field")
            return errors

        normalized = output['normalized']

        if not normalized.get('city'):
            errors.append("Missing normalized city name")

        if not normalized.get('state'):
            errors.append("Missing normalized state name")

        if output.get('validation_status') not in ['VALID', 'AMBIGUOUS', 'INVALID']:
            errors.append("Invalid validation_status")

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
