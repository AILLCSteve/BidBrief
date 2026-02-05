"""
Gap Analyzer Agent (BR-2)

Analyzes HOTDOG document analysis results to identify questions/gaps that
CityScraper's municipal research could potentially answer.
Part of the Bridge Layer connecting HOTDOG AI to the CityScraper pipeline.

Responsibilities:
- Analyze unanswered questions from HOTDOG analysis
- Categorize gaps as answerable or unanswerable by CityScraper
- Map answerable gaps to specific data sources (table.column)
- Prioritize gaps based on value to the user
- Recommend enrichment strategy and table mode
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
from services.scraper.prompts.br2_gap_analyzer import get_prompt

logger = logging.getLogger(__name__)


class GapAnalyzerAgent(BaseAgent):
    """
    BR-2: Gap Analyzer Agent

    Analyzes HOTDOG document analysis output to identify which unanswered
    questions could be addressed by CityScraper's municipal research.

    This agent bridges HOTDOG AI analysis with CityScraper by determining
    what additional value municipal research can provide.
    """

    AGENT_ID = "br-2"
    AGENT_NAME = "Gap Analyzer"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-04"

    # Valid priority values
    VALID_PRIORITIES = ("HIGH", "MEDIUM", "LOW")
    # Valid enrichment recommendations
    VALID_ENRICHMENT_RECOMMENDATIONS = ("FULL", "PARTIAL", "NONE")
    # Valid table modes
    VALID_TABLE_MODES = ("systems_info", "public_bids", "both")
    # Valid confidence levels
    VALID_CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")

    # Maximum length for HOTDOG analysis summary sent to LLM
    MAX_HOTDOG_SUMMARY_LENGTH = 4000
    # Maximum questions to analyze
    MAX_QUESTIONS_TO_ANALYZE = 50

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt(
            "{{document_type}}",
            "{{municipality_info}}",
            "{{hotdog_summary}}",
            "{{unanswered_questions}}"
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

    def _format_municipality_info(self, municipality: Optional[Dict[str, Any]]) -> str:
        """
        Format municipality info for prompt.

        Args:
            municipality: Municipality detection result from BR-1

        Returns:
            Formatted string for prompt
        """
        if not municipality:
            return "Municipality: Not detected"

        parts = []
        name = municipality.get('municipality_name')
        state = municipality.get('state')
        confidence = municipality.get('confidence', 'UNKNOWN')

        if name and state:
            parts.append(f"Municipality: {name}, {state}")
        elif name:
            parts.append(f"Municipality: {name} (state unknown)")
        else:
            parts.append("Municipality: Not detected")

        parts.append(f"Detection Confidence: {confidence}")

        if municipality.get('is_county_level'):
            parts.append("Note: County-level document")

        if municipality.get('county_if_known'):
            parts.append(f"County: {municipality.get('county_if_known')}")

        return "\n".join(parts)

    def _format_hotdog_summary(self, hotdog_analysis: Dict[str, Any]) -> str:
        """
        Format HOTDOG analysis results for prompt.

        Args:
            hotdog_analysis: Results from HOTDOG document analysis

        Returns:
            Formatted summary string
        """
        if not hotdog_analysis:
            return "No HOTDOG analysis available."

        parts = []

        # Include document summary if available
        if hotdog_analysis.get('summary'):
            parts.append(f"Document Summary: {hotdog_analysis['summary'][:500]}")

        # Include key findings
        if hotdog_analysis.get('key_findings'):
            findings = hotdog_analysis['key_findings']
            if isinstance(findings, list):
                parts.append("Key Findings:")
                for finding in findings[:15]:  # Increased from 5
                    parts.append(f"  - {finding}")

        # Include extracted data points if available
        if hotdog_analysis.get('extracted_data'):
            data = hotdog_analysis['extracted_data']
            parts.append(f"Extracted Data Points: {len(data) if isinstance(data, (list, dict)) else 'N/A'}")

        # Include answered questions count if available
        if hotdog_analysis.get('answered_questions'):
            answered = hotdog_analysis['answered_questions']
            parts.append(f"Questions Answered: {len(answered) if isinstance(answered, list) else 'N/A'}")

        # Include confidence score if available
        if hotdog_analysis.get('confidence_score'):
            parts.append(f"Overall Confidence: {hotdog_analysis['confidence_score']}")

        result = "\n".join(parts) if parts else "Minimal analysis data available."

        # Truncate if too long
        if len(result) > self.MAX_HOTDOG_SUMMARY_LENGTH:
            result = result[:self.MAX_HOTDOG_SUMMARY_LENGTH] + "\n[... truncated ...]"

        return result

    def _format_unanswered_questions(self, questions: List[str]) -> str:
        """
        Format unanswered questions for prompt.

        Args:
            questions: List of unanswered question strings

        Returns:
            Formatted numbered list of questions
        """
        if not questions:
            return "No unanswered questions provided."

        # Limit to MAX_QUESTIONS_TO_ANALYZE
        limited_questions = questions[:self.MAX_QUESTIONS_TO_ANALYZE]

        parts = []
        for i, question in enumerate(limited_questions, 1):
            # Clean up question text
            question_clean = question.strip()
            if question_clean:
                parts.append(f"{i}. {question_clean}")

        if len(questions) > self.MAX_QUESTIONS_TO_ANALYZE:
            parts.append(f"\n[... {len(questions) - self.MAX_QUESTIONS_TO_ANALYZE} additional questions truncated ...]")

        return "\n".join(parts) if parts else "No valid questions provided."

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process gap analysis request.

        Expected input_data:
        - hotdog_analysis: dict - Results from HOTDOG document analysis
        - unanswered_questions: list[str] - Questions HOTDOG couldn't answer
        - document_type: str - Type of document (rfp, bid_document, contract, etc.)
        - municipality: dict - Detected municipality info from BR-1

        Returns AgentResponse with:
        - answerable_gaps: list[dict] - Gaps CityScraper CAN address
        - unanswerable_gaps: list[dict] - Gaps CityScraper CANNOT address
        - enrichment_recommendation: str - FULL/PARTIAL/NONE
        - recommended_table_mode: str - systems_info/public_bids/both
        - confidence: str - HIGH/MEDIUM/LOW
        """
        start_time = time.time()
        content = ''  # Initialize before any operation
        json_str = ''  # Initialize before any operation

        # Extract input data
        hotdog_analysis = request.input_data.get('hotdog_analysis', {})
        unanswered_questions = request.input_data.get('unanswered_questions', [])
        document_type = request.input_data.get('document_type', 'unknown')
        municipality = request.input_data.get('municipality', {})

        # Type validation for hotdog_analysis
        if not isinstance(hotdog_analysis, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"hotdog_analysis must be dict, got {type(hotdog_analysis).__name__}"]
            )

        # Type validation for unanswered_questions
        if not isinstance(unanswered_questions, list):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"unanswered_questions must be list, got {type(unanswered_questions).__name__}"]
            )

        # Validate list contents are strings
        for i, q in enumerate(unanswered_questions):
            if not isinstance(q, str):
                return AgentResponse(
                    agent_id=self.AGENT_ID,
                    task=request.task,
                    success=False,
                    output_data={},
                    errors=[f"unanswered_questions[{i}] must be string, got {type(q).__name__}"]
                )

        # Type validation for document_type
        if not isinstance(document_type, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"document_type must be string, got {type(document_type).__name__}"]
            )

        # Type validation for municipality (can be dict or None)
        if municipality is not None and not isinstance(municipality, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"municipality must be dict or null, got {type(municipality).__name__}"]
            )

        # Handle empty questions list
        if not unanswered_questions:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=True,
                output_data={
                    'answerable_gaps': [],
                    'unanswerable_gaps': [],
                    'enrichment_recommendation': 'NONE',
                    'enrichment_rationale': 'No unanswered questions provided for analysis.',
                    'recommended_table_mode': 'systems_info',
                    'table_mode_rationale': 'Default mode; no gaps to analyze.',
                    'confidence': 'HIGH',
                    'confidence_rationale': 'No questions to analyze means no uncertainty.',
                    'analysis_notes': 'No unanswered questions provided. HOTDOG analysis appears complete.'
                },
                errors=[],
                processing_time_seconds=time.time() - start_time
            )

        try:
            # Emit event for UI activity feed
            self.emit_event(
                "processing",
                f"Analyzing {len(unanswered_questions)} unanswered questions..."
            )

            # Format inputs for prompt
            municipality_info = self._format_municipality_info(municipality)
            hotdog_summary = self._format_hotdog_summary(hotdog_analysis)
            questions_text = self._format_unanswered_questions(unanswered_questions)

            # Get the prompt with inputs substituted
            prompt = get_prompt(
                document_type=document_type,
                municipality_info=municipality_info,
                hotdog_summary=hotdog_summary,
                unanswered_questions=questions_text
            )

            # Build user message
            user_message = f"""Analyze these unanswered questions from HOTDOG document analysis.

**Document Type:** {document_type}

**Municipality:**
{municipality_info}

**HOTDOG Analysis Summary:**
{hotdog_summary}

**Unanswered Questions:**
{questions_text}

Categorize each question as answerable or unanswerable by CityScraper.
Provide enrichment recommendations.
Return the complete JSON output as specified in your instructions."""

            self.emit_event("processing", "Categorizing gaps and mapping data sources...")

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
                logger.warning(f"BR-2 validation failed: {errors}")
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
            answerable_count = len(output_data.get('answerable_gaps', []))
            unanswerable_count = len(output_data.get('unanswerable_gaps', []))
            recommendation = output_data.get('enrichment_recommendation', 'UNKNOWN')
            table_mode = output_data.get('recommended_table_mode', 'unknown')

            completion_msg = (
                f"Analysis complete: {answerable_count} answerable, "
                f"{unanswerable_count} unanswerable gaps. "
                f"Recommend: {recommendation} enrichment ({table_mode} mode)"
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

        except ValueError as e:
            # JSON extraction failed
            logger.error(f"BR-2 JSON extraction failed: {e}")
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
            logger.error(f"BR-2 JSON parse failed: {e}")
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
        except (TypeError, AttributeError, KeyError) as e:
            # Handle data structure issues
            logger.error(f"BR-2 data structure error: {e}")
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
            logger.exception(f"BR-2 unexpected error: {e}")
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
        Validate gap analyzer output against spec.

        Args:
            output: The output data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required top-level fields
        required_fields = [
            'answerable_gaps', 'unanswerable_gaps',
            'enrichment_recommendation', 'recommended_table_mode', 'confidence'
        ]

        for field_name in required_fields:
            if field_name not in output:
                errors.append(f"Missing required field: '{field_name}'")

        # Return early if missing required fields
        if errors:
            return errors

        # Validate answerable_gaps is a list
        answerable_gaps = output.get('answerable_gaps')
        if not isinstance(answerable_gaps, list):
            errors.append("'answerable_gaps' must be a list")
        else:
            # Validate each answerable gap
            for i, gap in enumerate(answerable_gaps):
                if not isinstance(gap, dict):
                    errors.append(f"answerable_gaps[{i}] must be a dict")
                    continue

                # Required fields in each gap
                if 'question' not in gap:
                    errors.append(f"answerable_gaps[{i}] missing 'question'")
                if 'data_source' not in gap:
                    errors.append(f"answerable_gaps[{i}] missing 'data_source'")
                if 'priority' not in gap:
                    errors.append(f"answerable_gaps[{i}] missing 'priority'")
                elif gap.get('priority') not in self.VALID_PRIORITIES:
                    errors.append(f"answerable_gaps[{i}] has invalid priority: {gap.get('priority')}")
                if 'rationale' not in gap:
                    errors.append(f"answerable_gaps[{i}] missing 'rationale'")

        # Validate unanswerable_gaps is a list
        unanswerable_gaps = output.get('unanswerable_gaps')
        if not isinstance(unanswerable_gaps, list):
            errors.append("'unanswerable_gaps' must be a list")
        else:
            # Validate each unanswerable gap
            for i, gap in enumerate(unanswerable_gaps):
                if not isinstance(gap, dict):
                    errors.append(f"unanswerable_gaps[{i}] must be a dict")
                    continue

                # Required fields in each gap
                if 'question' not in gap:
                    errors.append(f"unanswerable_gaps[{i}] missing 'question'")
                if 'reason' not in gap:
                    errors.append(f"unanswerable_gaps[{i}] missing 'reason'")

        # Validate enrichment_recommendation
        enrichment = output.get('enrichment_recommendation')
        if enrichment not in self.VALID_ENRICHMENT_RECOMMENDATIONS:
            errors.append(f"Invalid enrichment_recommendation: {enrichment}")

        # Validate recommended_table_mode
        table_mode = output.get('recommended_table_mode')
        if table_mode not in self.VALID_TABLE_MODES:
            errors.append(f"Invalid recommended_table_mode: {table_mode}")

        # Validate confidence
        confidence = output.get('confidence')
        if confidence not in self.VALID_CONFIDENCE_LEVELS:
            errors.append(f"Invalid confidence: {confidence}")

        return errors

    def to_enrichment_config(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert validated output to enrichment configuration for CityScraper.

        This format can be passed to the scraper orchestrator to run
        targeted enrichment based on gap analysis.

        Args:
            output: Validated output from process()

        Returns:
            Dict suitable for configuring scraper enrichment run
        """
        recommendation = output.get('enrichment_recommendation', 'NONE')

        if recommendation == 'NONE':
            return {
                'should_enrich': False,
                'reason': output.get('enrichment_rationale', 'No enrichment recommended')
            }

        # Extract HIGH priority answerable gaps for targeted search
        high_priority_gaps = [
            gap for gap in output.get('answerable_gaps', [])
            if gap.get('priority') == 'HIGH'
        ]

        # Determine which data sources to query
        data_sources = set()
        for gap in output.get('answerable_gaps', []):
            source = gap.get('data_source', '')
            if '.' in source:
                table = source.split('.')[0]
                data_sources.add(table)

        return {
            'should_enrich': True,
            'enrichment_level': recommendation,
            'table_mode': output.get('recommended_table_mode', 'systems_info'),
            'priority_gaps': high_priority_gaps,
            'data_sources': list(data_sources),
            'total_answerable_gaps': len(output.get('answerable_gaps', [])),
            'total_unanswerable_gaps': len(output.get('unanswerable_gaps', [])),
            'analysis_confidence': output.get('confidence'),
            'rationale': output.get('enrichment_rationale')
        }
