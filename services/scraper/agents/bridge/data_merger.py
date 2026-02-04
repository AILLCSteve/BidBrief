"""
Data Merger Agent (BR-3)

Merges HOTDOG document analysis results with CityScraper-sourced municipal data,
maintaining clear attribution for external research.

Part of the Bridge Layer connecting HOTDOG AI to the CityScraper pipeline.

CRITICAL REQUIREMENT: External research data MUST be clearly marked as
[External Research] - never blend with document-sourced answers without
clear distinction. This is NON-NEGOTIABLE.

Responsibilities:
- Combine HOTDOG document answers with CityScraper external research
- Maintain clear [From Document] and [External Research] source tags
- Reconcile confidence levels between sources
- Track which gaps were filled vs. remain unanswered
- Handle both "supplement" and "standalone" merge modes
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
from services.scraper.prompts.br3_data_merger import get_prompt

logger = logging.getLogger(__name__)


class DataMergerAgent(BaseAgent):
    """
    BR-3: Data Merger Agent

    Merges HOTDOG document analysis output with CityScraper external research,
    maintaining clear source attribution for all data.

    This agent is the final bridge component that produces enriched answers
    with transparent sourcing for downstream consumption.
    """

    AGENT_ID = "br-3"
    AGENT_NAME = "Data Merger"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "3.0.0"
    PROMPT_LAST_REFINED = "2026-02-04"

    # Valid source types for merged answers
    VALID_SOURCE_TYPES = ("document", "external_research", "combined")
    # Valid confidence levels
    VALID_CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW")
    # Valid merge modes
    VALID_MERGE_MODES = ("supplement", "standalone")

    # Maximum length for gap analysis summary sent to LLM
    MAX_GAP_ANALYSIS_LENGTH = 3000
    # Maximum questions to process
    MAX_QUESTIONS_TO_MERGE = 100

    def get_system_prompt(self) -> str:
        """Get base system prompt (without input substitution)."""
        return get_prompt(
            "{{gap_analysis}}",
            "{{merge_mode}}"
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

    def _format_gap_analysis(self, gap_analysis: Optional[Dict[str, Any]]) -> str:
        """
        Format gap analysis results for prompt.

        Args:
            gap_analysis: BR-2 gap analysis output

        Returns:
            Formatted summary string
        """
        if not gap_analysis:
            return "No gap analysis provided."

        parts = []

        # Include enrichment recommendation
        recommendation = gap_analysis.get('enrichment_recommendation', 'UNKNOWN')
        parts.append(f"Enrichment Recommendation: {recommendation}")

        # Include table mode
        table_mode = gap_analysis.get('recommended_table_mode', 'unknown')
        parts.append(f"Recommended Table Mode: {table_mode}")

        # Include answerable gaps summary
        answerable = gap_analysis.get('answerable_gaps', [])
        if answerable:
            parts.append(f"\nAnswerable Gaps ({len(answerable)} questions):")
            for i, gap in enumerate(answerable[:10], 1):  # Limit to 10 for prompt
                question = gap.get('question', 'Unknown question')
                priority = gap.get('priority', 'UNKNOWN')
                source = gap.get('data_source', 'unknown')
                parts.append(f"  {i}. [{priority}] {question}")
                parts.append(f"     Source: {source}")

            if len(answerable) > 10:
                parts.append(f"  ... and {len(answerable) - 10} more")

        # Include unanswerable gaps summary
        unanswerable = gap_analysis.get('unanswerable_gaps', [])
        if unanswerable:
            parts.append(f"\nUnanswerable Gaps ({len(unanswerable)} questions):")
            for i, gap in enumerate(unanswerable[:5], 1):  # Limit to 5
                question = gap.get('question', 'Unknown question')
                reason = gap.get('reason', 'No reason given')
                parts.append(f"  {i}. {question}")
                parts.append(f"     Reason: {reason[:100]}")

            if len(unanswerable) > 5:
                parts.append(f"  ... and {len(unanswerable) - 5} more")

        # Include analysis notes if available
        if gap_analysis.get('analysis_notes'):
            parts.append(f"\nAnalysis Notes: {gap_analysis['analysis_notes'][:200]}")

        result = "\n".join(parts)

        # Truncate if too long
        if len(result) > self.MAX_GAP_ANALYSIS_LENGTH:
            result = result[:self.MAX_GAP_ANALYSIS_LENGTH] + "\n[... truncated ...]"

        return result

    def _format_hotdog_results(self, hotdog_results: Dict[str, Any]) -> str:
        """
        Format HOTDOG results for the user message.

        Args:
            hotdog_results: HOTDOG document analysis results

        Returns:
            Formatted string for prompt
        """
        if not hotdog_results:
            return "No HOTDOG results provided."

        parts = []

        # Include answered questions
        answered = hotdog_results.get('answered_questions', [])
        if answered:
            parts.append(f"Document-Answered Questions ({len(answered)}):")
            for item in answered[:20]:  # Limit for prompt size
                if isinstance(item, dict):
                    q = item.get('question', 'Unknown')
                    a = item.get('answer', 'No answer')
                    citation = item.get('citation', '')
                    confidence = item.get('confidence', 'UNKNOWN')
                    parts.append(f"\nQ: {q}")
                    parts.append(f"A: {a[:300]}{'...' if len(str(a)) > 300 else ''}")
                    if citation:
                        parts.append(f"Citation: {citation}")
                    parts.append(f"Confidence: {confidence}")
                elif isinstance(item, str):
                    parts.append(f"- {item}")

            if len(answered) > 20:
                parts.append(f"\n... and {len(answered) - 20} more answered questions")

        # Include unanswered questions
        unanswered = hotdog_results.get('unanswered_questions', [])
        if unanswered:
            parts.append(f"\nDocument-Unanswered Questions ({len(unanswered)}):")
            for i, q in enumerate(unanswered[:20], 1):
                if isinstance(q, str):
                    parts.append(f"  {i}. {q}")
                elif isinstance(q, dict):
                    parts.append(f"  {i}. {q.get('question', 'Unknown')}")

            if len(unanswered) > 20:
                parts.append(f"  ... and {len(unanswered) - 20} more")

        # Include summary if available
        if hotdog_results.get('summary'):
            parts.append(f"\nDocument Summary: {hotdog_results['summary'][:500]}")

        return "\n".join(parts) if parts else "Minimal HOTDOG data available."

    def _format_scraper_results(self, scraper_results: Dict[str, Any]) -> str:
        """
        Format CityScraper results for the user message.

        Args:
            scraper_results: CityScraper extraction results (PR-3 packaged format)

        Returns:
            Formatted string for prompt
        """
        if not scraper_results:
            return "No CityScraper results provided."

        parts = []

        # Include municipality info
        municipality = scraper_results.get('municipality', {})
        if municipality:
            city = municipality.get('city', 'Unknown')
            state = municipality.get('state', 'Unknown')
            parts.append(f"Municipality: {city}, {state}")

        # Include extracted data
        extracted_data = scraper_results.get('extracted_data', {})
        if extracted_data:
            parts.append(f"\nExtracted Data Fields ({len(extracted_data)}):")
            for field_name, field_data in list(extracted_data.items())[:15]:
                if isinstance(field_data, dict):
                    value = field_data.get('value', 'NOT FOUND')
                    source = field_data.get('source_url', '')
                    confidence = field_data.get('confidence', 'UNKNOWN')
                    parts.append(f"\n  {field_name}:")
                    parts.append(f"    Value: {str(value)[:200]}")
                    if source:
                        parts.append(f"    Source: {source}")
                    parts.append(f"    Confidence: {confidence}")
                else:
                    parts.append(f"\n  {field_name}: {str(field_data)[:200]}")

            if len(extracted_data) > 15:
                parts.append(f"\n  ... and {len(extracted_data) - 15} more fields")

        # Include sources used
        sources = scraper_results.get('sources', [])
        if sources:
            parts.append(f"\nSources Used ({len(sources)}):")
            for source in sources[:10]:
                if isinstance(source, dict):
                    title = source.get('title', 'Unknown')
                    url = source.get('url', '')
                    parts.append(f"  - {title}")
                    if url:
                        parts.append(f"    URL: {url}")
                elif isinstance(source, str):
                    parts.append(f"  - {source}")

        # Include data gaps if reported
        gaps = scraper_results.get('data_gaps', [])
        if gaps:
            parts.append(f"\nData Gaps Reported: {len(gaps)}")
            for gap in gaps[:5]:
                parts.append(f"  - {gap}")

        return "\n".join(parts) if parts else "Minimal CityScraper data available."

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process data merge request.

        Expected input_data:
        - hotdog_results: dict - Original HOTDOG document analysis results
        - scraper_results: dict - CityScraper extraction results (from PR-3)
        - gap_analysis: dict - BR-2 output showing which gaps were targeted
        - merge_mode: str - "supplement" (default) or "standalone"

        Returns AgentResponse with:
        - merged_answers: list[dict] - Combined answers with source tags
        - source_summary: dict - Counts of document vs external sources
        - enrichment_success: bool - Whether gaps were successfully filled
        - gaps_filled: list[str] - Questions answered by scraper
        - gaps_remaining: list[str] - Questions still unanswered
        """
        start_time = time.time()
        content = ''  # Initialize before any operation
        json_str = ''  # Initialize before any operation

        # Extract input data
        hotdog_results = request.input_data.get('hotdog_results', {})
        scraper_results = request.input_data.get('scraper_results', {})
        gap_analysis = request.input_data.get('gap_analysis', {})
        merge_mode = request.input_data.get('merge_mode', 'supplement')

        # Type validation for hotdog_results
        if not isinstance(hotdog_results, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"hotdog_results must be dict, got {type(hotdog_results).__name__}"]
            )

        # Type validation for scraper_results
        if not isinstance(scraper_results, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"scraper_results must be dict, got {type(scraper_results).__name__}"]
            )

        # Type validation for gap_analysis
        if not isinstance(gap_analysis, dict):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"gap_analysis must be dict, got {type(gap_analysis).__name__}"]
            )

        # Type validation for merge_mode
        if not isinstance(merge_mode, str):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"merge_mode must be string, got {type(merge_mode).__name__}"]
            )

        # Validate merge_mode value
        if merge_mode not in self.VALID_MERGE_MODES:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=[f"merge_mode must be one of {self.VALID_MERGE_MODES}, got '{merge_mode}'"]
            )

        # Handle empty inputs
        if not hotdog_results and not scraper_results:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=True,
                output_data={
                    'merged_answers': [],
                    'source_summary': {
                        'total_questions': 0,
                        'document_only_answers': 0,
                        'external_only_answers': 0,
                        'combined_answers': 0,
                        'unanswered': 0,
                        'document_sources_used': [],
                        'external_sources_used': []
                    },
                    'enrichment_success': False,
                    'gaps_filled': [],
                    'gaps_remaining': [],
                    'merge_notes': 'No data provided for merge. Both HOTDOG and CityScraper results are empty.'
                },
                errors=[],
                processing_time_seconds=time.time() - start_time
            )

        try:
            # Emit event for UI activity feed
            self.emit_event(
                "processing",
                f"Merging data sources ({merge_mode} mode)..."
            )

            # Format inputs for prompt
            gap_analysis_text = self._format_gap_analysis(gap_analysis)
            hotdog_text = self._format_hotdog_results(hotdog_results)
            scraper_text = self._format_scraper_results(scraper_results)

            # Get the prompt with inputs substituted
            prompt = get_prompt(
                gap_analysis=gap_analysis_text,
                merge_mode=merge_mode
            )

            # Build user message
            user_message = f"""Merge the following data sources according to the {merge_mode} mode.

**CRITICAL**: All external research data MUST be tagged with [External Research - CityScraper].
Document data should be tagged with [From Document]. Never blend sources without clear tags.

---

## HOTDOG DOCUMENT ANALYSIS RESULTS

{hotdog_text}

---

## CITYSCRAPER EXTERNAL RESEARCH RESULTS

{scraper_text}

---

## GAP ANALYSIS (from BR-2)

{gap_analysis_text}

---

Merge these sources following the {merge_mode} mode rules.
Ensure every answer has proper source attribution tags.
Return the complete JSON output as specified in your instructions."""

            self.emit_event("processing", "Reconciling sources and attributing data...")

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
                logger.warning(f"BR-3 validation failed: {errors}")
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

            # Validate source attribution tags in answers
            attribution_warnings = self._validate_source_attribution(output_data)
            if attribution_warnings:
                logger.warning(f"BR-3 attribution warnings: {attribution_warnings}")
                # Add warnings but don't fail - just note them
                if 'merge_notes' in output_data:
                    output_data['merge_notes'] += f" Attribution warnings: {'; '.join(attribution_warnings)}"

            elapsed = time.time() - start_time

            # Build completion message
            merged_count = len(output_data.get('merged_answers', []))
            gaps_filled = len(output_data.get('gaps_filled', []))
            gaps_remaining = len(output_data.get('gaps_remaining', []))
            enrichment_success = output_data.get('enrichment_success', False)

            completion_msg = (
                f"Merge complete: {merged_count} answers merged, "
                f"{gaps_filled} gaps filled, {gaps_remaining} gaps remaining. "
                f"Enrichment {'successful' if enrichment_success else 'limited'}."
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
            logger.error(f"BR-3 JSON extraction failed: {e}")
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
            logger.error(f"BR-3 JSON parse failed: {e}")
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
            logger.error(f"BR-3 data structure error: {e}")
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
            logger.exception(f"BR-3 unexpected error: {e}")
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={'raw_response': content[:500] if content else ''},
                errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
                processing_time_seconds=time.time() - start_time
            )

    def _validate_source_attribution(self, output: Dict[str, Any]) -> List[str]:
        """
        Validate that source attribution tags are present in merged answers.

        This is a CRITICAL requirement - external research must ALWAYS be tagged.

        Args:
            output: The validated output data

        Returns:
            List of attribution warnings (empty if all properly attributed)
        """
        warnings = []

        merged_answers = output.get('merged_answers', [])
        for i, answer in enumerate(merged_answers):
            if not isinstance(answer, dict):
                continue

            answer_text = answer.get('answer', '')
            source_type = answer.get('source_type', '')

            # Check external research tagging
            if source_type == 'external_research':
                if '[External Research' not in answer_text:
                    warnings.append(
                        f"Answer {i+1} is external_research but missing [External Research] tag"
                    )

            # Check combined answers have both tags
            elif source_type == 'combined':
                if '[From Document]' not in answer_text:
                    warnings.append(
                        f"Answer {i+1} is combined but missing [From Document] tag"
                    )
                if '[External Research' not in answer_text:
                    warnings.append(
                        f"Answer {i+1} is combined but missing [External Research] tag"
                    )

            # Check document answers
            elif source_type == 'document':
                if '[From Document]' not in answer_text:
                    warnings.append(
                        f"Answer {i+1} is document but missing [From Document] tag"
                    )

        return warnings

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """
        Validate data merger output against spec.

        Args:
            output: The output data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required top-level fields
        required_fields = [
            'merged_answers', 'source_summary', 'enrichment_success',
            'gaps_filled', 'gaps_remaining'
        ]

        for field_name in required_fields:
            if field_name not in output:
                errors.append(f"Missing required field: '{field_name}'")

        # Return early if missing required fields
        if errors:
            return errors

        # Validate merged_answers is a list
        merged_answers = output.get('merged_answers')
        if not isinstance(merged_answers, list):
            errors.append("'merged_answers' must be a list")
        else:
            # Validate each merged answer
            for i, answer in enumerate(merged_answers):
                if not isinstance(answer, dict):
                    errors.append(f"merged_answers[{i}] must be a dict")
                    continue

                # Required fields in each answer
                if 'question' not in answer:
                    errors.append(f"merged_answers[{i}] missing 'question'")
                if 'answer' not in answer:
                    errors.append(f"merged_answers[{i}] missing 'answer'")
                if 'source_type' not in answer:
                    errors.append(f"merged_answers[{i}] missing 'source_type'")
                elif answer.get('source_type') not in self.VALID_SOURCE_TYPES:
                    errors.append(
                        f"merged_answers[{i}] has invalid source_type: {answer.get('source_type')}"
                    )
                if 'confidence' not in answer:
                    errors.append(f"merged_answers[{i}] missing 'confidence'")
                elif answer.get('confidence') not in self.VALID_CONFIDENCE_LEVELS:
                    errors.append(
                        f"merged_answers[{i}] has invalid confidence: {answer.get('confidence')}"
                    )

                # Validate citation fields exist (can be empty strings)
                if 'document_citation' not in answer:
                    errors.append(f"merged_answers[{i}] missing 'document_citation'")
                if 'external_citation' not in answer:
                    errors.append(f"merged_answers[{i}] missing 'external_citation'")

        # Validate source_summary
        source_summary = output.get('source_summary')
        if not isinstance(source_summary, dict):
            errors.append("'source_summary' must be a dict")
        else:
            summary_fields = [
                'total_questions', 'document_only_answers', 'external_only_answers',
                'combined_answers', 'unanswered', 'document_sources_used',
                'external_sources_used'
            ]
            for field_name in summary_fields:
                if field_name not in source_summary:
                    errors.append(f"source_summary missing '{field_name}'")

            # Validate numeric fields
            for numeric_field in ['total_questions', 'document_only_answers',
                                  'external_only_answers', 'combined_answers', 'unanswered']:
                val = source_summary.get(numeric_field)
                if val is not None and not isinstance(val, int):
                    errors.append(f"source_summary.{numeric_field} must be integer")

            # Validate list fields
            for list_field in ['document_sources_used', 'external_sources_used']:
                val = source_summary.get(list_field)
                if val is not None and not isinstance(val, list):
                    errors.append(f"source_summary.{list_field} must be list")

        # Validate enrichment_success is boolean
        enrichment_success = output.get('enrichment_success')
        if not isinstance(enrichment_success, bool):
            errors.append("'enrichment_success' must be boolean")

        # Validate gaps_filled is a list
        gaps_filled = output.get('gaps_filled')
        if not isinstance(gaps_filled, list):
            errors.append("'gaps_filled' must be a list")

        # Validate gaps_remaining is a list
        gaps_remaining = output.get('gaps_remaining')
        if not isinstance(gaps_remaining, list):
            errors.append("'gaps_remaining' must be a list")

        return errors

    def to_enriched_hotdog_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert validated output to enriched HOTDOG output format.

        This format can be used to replace/supplement the original HOTDOG
        analysis with CityScraper-enriched data.

        Args:
            output: Validated output from process()

        Returns:
            Dict formatted for HOTDOG-compatible consumption
        """
        merged_answers = output.get('merged_answers', [])
        source_summary = output.get('source_summary', {})

        # Group answers by source type
        document_answers = []
        external_answers = []
        combined_answers = []

        for answer in merged_answers:
            source_type = answer.get('source_type', '')
            formatted_answer = {
                'question': answer.get('question', ''),
                'answer': answer.get('answer', ''),
                'confidence': answer.get('confidence', 'MEDIUM'),
                'citations': {
                    'document': answer.get('document_citation', ''),
                    'external': answer.get('external_citation', '')
                }
            }

            if source_type == 'document':
                document_answers.append(formatted_answer)
            elif source_type == 'external_research':
                external_answers.append(formatted_answer)
            elif source_type == 'combined':
                combined_answers.append(formatted_answer)

        return {
            'enriched': True,
            'enrichment_source': 'CityScraper',
            'document_answers': document_answers,
            'external_answers': external_answers,
            'combined_answers': combined_answers,
            'gaps_filled': output.get('gaps_filled', []),
            'gaps_remaining': output.get('gaps_remaining', []),
            'source_summary': source_summary,
            'merge_notes': output.get('merge_notes', '')
        }
