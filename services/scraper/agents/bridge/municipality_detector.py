"""
Municipality Detector Agent (BR-1)

Detects and normalizes municipality information from uploaded document content.
Part of the Bridge Layer connecting HOTDOG AI to the CityScraper pipeline.

Responsibilities:
- Analyze document content for location information
- Detect address blocks, letterheads, and geographic patterns
- Normalize municipality names and states
- Provide confidence ratings based on evidence strength
- Handle multi-location documents by identifying primary location
"""

import json
import logging
import re
import time
from typing import Dict, Any, List, Optional

from services.scraper.agents.base import BaseAgent
from services.scraper.models import (
    AgentRequest,
    AgentResponse
)
from services.scraper.prompts.br1_municipality_detector import get_prompt

logger = logging.getLogger(__name__)


class MunicipalityDetectorAgent(BaseAgent):
    """
    BR-1: Municipality Detector Agent

    Analyzes uploaded document content to extract municipality information,
    then normalizes it for the scraper pipeline.

    This agent is the entry point for the Bridge Layer, taking HOTDOG AI
    document analysis output and preparing it for CityScraper processing.
    """

    AGENT_ID = "br-1"
    AGENT_NAME = "Municipality Detector"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-04"

    # Maximum characters to analyze from document
    MAX_EXCERPT_LENGTH = 8000
    # Minimum excerpt ratio to keep when finding clean break points
    MIN_EXCERPT_RATIO = 0.8

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt("{{document_excerpt}}", "{{document_filename}}")

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

    def _prepare_document_excerpt(self, document_content: str) -> str:
        """
        Prepare document excerpt for analysis.

        Extracts the first portion of the document, which typically contains
        the most relevant location information (letterheads, headers, addresses).

        Args:
            document_content: Full document text content

        Returns:
            Excerpt suitable for LLM analysis
        """
        if not document_content:
            return ""

        # Take first MAX_EXCERPT_LENGTH characters
        excerpt = document_content[:self.MAX_EXCERPT_LENGTH]

        # If we cut mid-word or mid-sentence, try to find a clean break
        if len(document_content) > self.MAX_EXCERPT_LENGTH:
            # Look for last paragraph break, sentence end, or word boundary
            for break_char in ['\n\n', '\n', '. ', ' ']:
                last_break = excerpt.rfind(break_char)
                if last_break > self.MAX_EXCERPT_LENGTH * self.MIN_EXCERPT_RATIO:
                    excerpt = excerpt[:last_break + len(break_char)]
                    break

            excerpt += "\n\n[... document continues ...]"

        return excerpt

    def _extract_filename_hints(self, filename: str) -> List[str]:
        """
        Extract potential location hints from filename.

        Args:
            filename: Original document filename

        Returns:
            List of potential location tokens from filename
        """
        if not filename:
            return []

        hints = []

        # Remove common extensions
        name = filename.lower()
        for ext in ['.pdf', '.doc', '.docx', '.txt', '.html', '.htm']:
            if name.endswith(ext):
                name = name[:-len(ext)]
                break

        # Split on common delimiters
        tokens = re.split(r'[_\-\s]+', name)

        # Also handle camelCase
        for token in tokens[:]:
            camel_parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', token)
            if len(camel_parts) > 1:
                tokens.extend(camel_parts)

        # Filter out common non-location words
        noise_words = {
            'rfp', 'bid', 'spec', 'specs', 'document', 'doc', 'final',
            'draft', 'v1', 'v2', 'v3', '2024', '2025', '2026', 'copy',
            'attachment', 'exhibit', 'appendix', 'addendum', 'rev',
            'revised', 'updated', 'new', 'old', 'the', 'and', 'for'
        }

        for token in tokens:
            token_clean = token.strip().lower()
            if token_clean and len(token_clean) >= 2 and token_clean not in noise_words:
                hints.append(token_clean)

        return hints

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process municipality detection request.

        Expected input_data:
        - document_content: str - Raw text content from uploaded document
        - document_filename: str - Original filename (may contain location hints)
        - document_metadata: dict - Any metadata from HOTDOG analysis (optional)

        Returns AgentResponse with:
        - municipality_name: str - Detected city/municipality name
        - state: str - Full state name (normalized)
        - confidence: str - HIGH/MEDIUM/LOW
        - detection_method: str - How it was detected
        - evidence: list[str] - Verbatim quotes showing the detection
        - alternate_locations: list - Other locations mentioned (if any)
        """
        start_time = time.time()
        content = ''  # Initialize before any operation
        json_str = ''  # Initialize before any operation

        document_content = request.input_data.get('document_content', '')
        document_filename = request.input_data.get('document_filename', 'unknown')
        document_metadata = request.input_data.get('document_metadata', {})

        # Type validation for document_content
        if not isinstance(document_content, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"document_content must be string, got {type(document_content).__name__}"]
            )

        # Type validation for document_filename
        if not isinstance(document_filename, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"document_filename must be string, got {type(document_filename).__name__}"]
            )

        # Type validation for optional document_metadata
        if document_metadata is not None and not isinstance(document_metadata, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"document_metadata must be dict or null, got {type(document_metadata).__name__}"]
            )

        document_content = document_content.strip()
        document_filename = document_filename.strip() or 'unknown'

        # Required field validation
        if not document_content:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["document_content is required and cannot be empty"]
            )

        # Content length validation
        if len(document_content) < 50:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"document_content too short ({len(document_content)} chars, minimum 50)"]
            )

        try:
            # Emit event for UI activity feed
            self.emit_event(
                "processing",
                f"Analyzing document: {document_filename[:50]}{'...' if len(document_filename) > 50 else ''}"
            )

            # Prepare document excerpt
            excerpt = self._prepare_document_excerpt(document_content)

            # Extract filename hints for logging/context
            filename_hints = self._extract_filename_hints(document_filename)
            if filename_hints:
                logger.debug(f"BR-1 filename hints: {filename_hints}")

            # Get the prompt with input substituted
            prompt = get_prompt(excerpt, document_filename)

            # Build user message
            user_message = f"""Analyze this document to detect the municipality it pertains to.

**Filename:** {document_filename}

**Document Excerpt:**
{excerpt}

Based on the document content and filename, identify:
1. The PRIMARY municipality this document is about
2. The state (normalized to full name)
3. Evidence supporting your detection (verbatim quotes)
4. Any alternate locations mentioned
5. Your confidence level (HIGH/MEDIUM/LOW)

Return the JSON output as specified in your instructions."""

            self.emit_event("processing", "Detecting municipality from document content...")

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
                logger.warning(f"BR-1 validation failed: {errors}")
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
            municipality = output_data.get('municipality_name')
            state = output_data.get('state')
            confidence = output_data.get('confidence', 'UNKNOWN')

            if municipality and state:
                completion_msg = f"Detected: {municipality}, {state} ({confidence} confidence)"
            elif municipality:
                completion_msg = f"Detected: {municipality} (state unknown, {confidence} confidence)"
            else:
                completion_msg = "No municipality detected in document"

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

        except ValueError as e:
            # JSON extraction failed
            logger.error(f"BR-1 JSON extraction failed: {e}")
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
        except json.JSONDecodeError as e:
            logger.error(f"BR-1 JSON parse failed: {e}")
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
        except Exception as e:
            logger.exception(f"BR-1 unexpected error: {e}")
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
        Validate municipality detector output against spec.

        Args:
            output: The output data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required top-level fields
        required_fields = [
            'municipality_name', 'state', 'state_abbreviation',
            'confidence', 'detection_method', 'evidence'
        ]

        for field in required_fields:
            if field not in output:
                errors.append(f"Missing required field: '{field}'")

        # Return early if missing required fields
        if errors:
            return errors

        # Validate confidence value
        confidence = output.get('confidence')
        if confidence and confidence not in ['HIGH', 'MEDIUM', 'LOW']:
            errors.append(f"Invalid confidence value: {confidence}")

        # Validate detection_method value
        valid_methods = [
            'address_block', 'letterhead', 'header', 'city_of_pattern',
            'content_mention', 'filename', 'county_level_document',
            'multiple_signals', 'none'
        ]
        detection_method = output.get('detection_method')
        if detection_method and detection_method not in valid_methods:
            errors.append(f"Invalid detection_method: {detection_method}")

        # Validate evidence is a list
        evidence = output.get('evidence')
        if evidence is not None and not isinstance(evidence, list):
            errors.append("'evidence' must be a list")

        # Validate alternate_locations is a list if present
        alt_locations = output.get('alternate_locations')
        if alt_locations is not None and not isinstance(alt_locations, list):
            errors.append("'alternate_locations' must be a list")

        # If municipality was detected, evidence should be provided (unless method is 'none')
        municipality = output.get('municipality_name')
        if municipality and detection_method != 'none':
            if not evidence or len(evidence) == 0:
                errors.append("Municipality detected but no evidence provided")

        # Validate state abbreviation format (2 uppercase letters or null)
        state_abbrev = output.get('state_abbreviation')
        if state_abbrev is not None:
            if not isinstance(state_abbrev, str):
                errors.append("'state_abbreviation' must be a string or null")
            elif len(state_abbrev) != 2 or not state_abbrev.isupper():
                errors.append(f"Invalid state_abbreviation format: {state_abbrev}")

        # Validate is_county_level is boolean if present
        is_county = output.get('is_county_level')
        if is_county is not None and not isinstance(is_county, bool):
            errors.append("'is_county_level' must be a boolean")

        return errors

    def to_normalized_result(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert validated output to normalized format for downstream processing.

        This format is compatible with the PF-1 Municipality Normalizer input.

        Args:
            output: Validated output from process()

        Returns:
            Dict suitable for passing to PF-1 or downstream agents
        """
        municipality = output.get('municipality_name')
        state = output.get('state')
        state_abbrev = output.get('state_abbreviation')

        if not municipality:
            return {
                'detected': False,
                'municipality_input': None,
                'confidence': output.get('confidence', 'LOW'),
                'detection_method': output.get('detection_method', 'none'),
                'notes': output.get('detection_notes', 'No municipality detected')
            }

        # Build municipality input string for PF-1
        if state:
            municipality_input = f"{municipality}, {state}"
        elif state_abbrev:
            municipality_input = f"{municipality}, {state_abbrev}"
        else:
            municipality_input = municipality

        return {
            'detected': True,
            'municipality_input': municipality_input,
            'municipality_name': municipality,
            'state': state,
            'state_abbreviation': state_abbrev,
            'confidence': output.get('confidence'),
            'detection_method': output.get('detection_method'),
            'evidence': output.get('evidence', []),
            'alternate_locations': output.get('alternate_locations', []),
            'is_county_level': output.get('is_county_level', False),
            'county_if_known': output.get('county_if_known'),
            'detection_notes': output.get('detection_notes')
        }
