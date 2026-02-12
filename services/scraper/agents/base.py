"""
Base Agent class for Municipal Scraper (CityScraper) system.

All agents inherit from this base class which provides:
- OpenAI API integration
- Tavily search integration
- Prompt management with version tracking
- Response validation
- Error handling and retries
- Logging and metrics

Design Philosophy:
- Each agent is a domain EXPERT with detailed persona
- NO token-limiting mindset - accuracy and precision paramount
- Small context windows for focused, accurate responses
- Prompts refined through critique cycles
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime

import httpx
from openai import AsyncOpenAI

from services.scraper.config import get_config, ScraperConfig
from services.scraper.models import AgentRequest, AgentResponse, AgentActivityEvent

logger = logging.getLogger(__name__)


@dataclass
class AgentMetrics:
    """Metrics tracking for an agent."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens_used: int = 0
    total_processing_time: float = 0.0
    average_response_time: float = 0.0
    last_request_at: Optional[datetime] = None


class BaseAgent(ABC):
    """
    Abstract base class for all CityScraper agents.

    Each agent is a specialized expert with:
    - Deep domain knowledge encoded in system prompt
    - Specific extraction/analysis responsibilities
    - Validation requirements for outputs
    - Small context window for accuracy

    Prompt Development Process (for each agent):
    1. Draft initial prompt
    2. Self-critique: Identify issues (persona depth, reasoning framework,
       validation criteria, conflict resolution, citation requirements)
    3. Revise prompt addressing all critiques
    4. Second critique cycle
    5. Final refined prompt
    """

    # Override in subclasses
    AGENT_ID: str = "base"
    AGENT_NAME: str = "Base Agent"
    AGENT_VERSION: str = "1.0.0"
    PROMPT_VERSION: str = "1.0.0"
    PROMPT_LAST_REFINED: str = "2026-02-03"

    # Shared Tavily rate-limiting state (class-level, shared across all agent instances)
    _tavily_last_call_time: float = 0.0
    _tavily_consecutive_failures: int = 0
    _tavily_circuit_open_until: float = 0.0
    _tavily_min_interval: float = 2.0  # Enforces ~30 calls/min across all agents

    def __init__(
        self,
        config: Optional[ScraperConfig] = None,
        openai_client: Optional[AsyncOpenAI] = None,
        event_callback: Optional[callable] = None
    ):
        """
        Initialize the agent.

        Args:
            config: Scraper configuration (uses global if not provided)
            openai_client: OpenAI client (creates new if not provided)
            event_callback: Callback for agent activity events (for UI feed)
        """
        self.config = config or get_config()
        self.event_callback = event_callback

        if openai_client:
            self.openai_client = openai_client
        elif self.config.openai:
            self.openai_client = AsyncOpenAI(api_key=self.config.openai.api_key)
        else:
            self.openai_client = None
            logger.warning(f"Agent {self.AGENT_ID} initialized without OpenAI client")

        self.metrics = AgentMetrics()
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info(f"Initialized agent: {self.AGENT_NAME} v{self.AGENT_VERSION}")
        logger.debug(f"  Prompt version: {self.PROMPT_VERSION} (refined {self.PROMPT_LAST_REFINED})")

    # ═══════════════════════════════════════════════════════════════════════
    # ABSTRACT METHODS - Must be implemented by each agent
    # ═══════════════════════════════════════════════════════════════════════

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get the detailed system prompt for this agent.

        This prompt should include:
        - Expert persona with domain background
        - Specific extraction/analysis task
        - Required data points with formats
        - Source hierarchy and trust ordering
        - Confidence rating criteria
        - Output format specification
        - Critical rules (no inference, no blanks, verbatim quotes)

        Returns:
            Complete system prompt string
        """
        pass

    @abstractmethod
    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process a request and return response.

        Args:
            request: The agent request with task and input data

        Returns:
            AgentResponse with results or errors
        """
        pass

    @abstractmethod
    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """
        Validate the agent's output.

        Args:
            output: The output data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        pass

    # ═══════════════════════════════════════════════════════════════════════
    # EVENT EMISSION (for UI agent activity feed)
    # ═══════════════════════════════════════════════════════════════════════

    def emit_event(self, status: str, message: str, is_completed: bool = False):
        """Emit an event for the UI agent activity feed."""
        if self.event_callback:
            event = AgentActivityEvent(
                agent_id=self.AGENT_ID,
                agent_name=self.AGENT_NAME,
                status=status,
                message=message,
                is_active=not is_completed,
                is_completed=is_completed
            )
            self.event_callback(event)

    # ═══════════════════════════════════════════════════════════════════════
    # OPENAI INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════

    async def call_openai(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Make an OpenAI API call with the agent's persona.

        Args:
            user_message: The user/task message
            system_prompt: Override system prompt (uses agent's default if None)
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            Dict with 'content', 'tokens_used', 'model' keys
        """
        if not self.openai_client:
            raise RuntimeError(f"Agent {self.AGENT_ID} has no OpenAI client")

        system = system_prompt or self.get_system_prompt()
        temp = temperature if temperature is not None else self.config.openai.temperature
        tokens = max_tokens or self.config.openai.max_tokens

        start_time = time.time()
        self.emit_event("processing", f"Calling GPT-4o...")

        try:
            response = await self.openai_client.chat.completions.create(
                model=self.config.openai.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message}
                ],
                temperature=temp,
                max_tokens=tokens
            )

            elapsed = time.time() - start_time
            tokens_used = response.usage.total_tokens if response.usage else 0

            # Update metrics
            self.metrics.total_requests += 1
            self.metrics.successful_requests += 1
            self.metrics.total_tokens_used += tokens_used
            self.metrics.total_processing_time += elapsed
            self.metrics.average_response_time = (
                self.metrics.total_processing_time / self.metrics.total_requests
            )
            self.metrics.last_request_at = datetime.now()

            logger.debug(f"Agent {self.AGENT_ID} OpenAI call: {tokens_used} tokens, {elapsed:.2f}s")

            return {
                'content': response.choices[0].message.content,
                'tokens_used': tokens_used,
                'model': response.model,
                'elapsed_seconds': elapsed
            }

        except Exception as e:
            self.metrics.total_requests += 1
            self.metrics.failed_requests += 1
            logger.error(f"Agent {self.AGENT_ID} OpenAI call failed: {e}")
            self.emit_event("failed", f"OpenAI error: {str(e)[:100]}")
            raise

    # ═══════════════════════════════════════════════════════════════════════
    # TAVILY SEARCH INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════

    async def search_tavily(
        self,
        query: str,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        max_results: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a Tavily search query with rate limiting, exponential backoff,
        and circuit breaker protection.

        Args:
            query: Search query string
            include_domains: Only include these domains
            exclude_domains: Exclude these domains
            max_results: Override max results

        Returns:
            List of search results with 'title', 'url', 'content', 'score'
        """
        if not self.config.tavily:
            logger.warning(f"Agent {self.AGENT_ID} attempted search without Tavily config")
            return []

        tavily_cfg = self.config.tavily
        max_retries = tavily_cfg.max_retries_per_query
        initial_backoff = tavily_cfg.initial_backoff_seconds
        max_backoff = tavily_cfg.max_backoff_seconds
        cb_threshold = tavily_cfg.circuit_breaker_threshold
        cb_cooldown = tavily_cfg.circuit_breaker_cooldown

        # ── CIRCUIT BREAKER CHECK ──────────────────────────────────────
        now = time.monotonic()
        if BaseAgent._tavily_circuit_open_until > now:
            wait_remaining = BaseAgent._tavily_circuit_open_until - now
            logger.warning(
                f"Agent {self.AGENT_ID} Tavily circuit breaker OPEN. "
                f"Waiting {wait_remaining:.1f}s before retrying query: {query[:60]}"
            )
            self.emit_event("rate_limited", f"Circuit breaker open, waiting {wait_remaining:.0f}s...")
            await asyncio.sleep(wait_remaining)
            # After waiting, reset the circuit breaker so we can try again
            BaseAgent._tavily_circuit_open_until = 0.0
            BaseAgent._tavily_consecutive_failures = 0
            logger.info(f"Agent {self.AGENT_ID} Tavily circuit breaker CLOSED after cooldown")

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=tavily_cfg.timeout_seconds)

        # Use preferred domains if none specified
        if include_domains is None:
            include_domains = tavily_cfg.preferred_domains

        request_data = {
            "api_key": tavily_cfg.api_key,
            "query": query,
            "search_depth": tavily_cfg.search_depth,
            "max_results": max_results or tavily_cfg.max_results_per_query,
            "include_answer": tavily_cfg.include_answer,
            "include_raw_content": tavily_cfg.include_raw_content
        }

        if include_domains:
            request_data["include_domains"] = include_domains
        if exclude_domains:
            request_data["exclude_domains"] = exclude_domains

        # ── RETRY LOOP WITH EXPONENTIAL BACKOFF ────────────────────────
        for attempt in range(max_retries + 1):
            try:
                # ── RATE LIMITER: enforce min interval between calls ───
                now = time.monotonic()
                elapsed_since_last = now - BaseAgent._tavily_last_call_time
                if elapsed_since_last < BaseAgent._tavily_min_interval:
                    sleep_time = BaseAgent._tavily_min_interval - elapsed_since_last
                    logger.debug(
                        f"Agent {self.AGENT_ID} rate limiter: sleeping {sleep_time:.2f}s"
                    )
                    await asyncio.sleep(sleep_time)
                BaseAgent._tavily_last_call_time = time.monotonic()

                self.emit_event("searching", f"Searching: {query[:50]}...")
                logger.debug(
                    f"Agent {self.AGENT_ID} searching (attempt {attempt + 1}/{max_retries + 1}): {query}"
                )

                response = await self._http_client.post(
                    "https://api.tavily.com/search",
                    json=request_data
                )

                # ── SUCCESS ────────────────────────────────────────────
                if response.status_code == 200:
                    BaseAgent._tavily_consecutive_failures = 0

                    data = response.json()
                    results = []
                    for item in data.get('results', []):
                        results.append({
                            'title': item.get('title', ''),
                            'url': item.get('url', ''),
                            'content': item.get('content', ''),
                            'raw_content': item.get('raw_content', ''),
                            'score': item.get('score', 0),
                            'query': query
                        })

                    # Include AI summary if available
                    if data.get('answer'):
                        results.append({
                            'title': 'Tavily AI Summary',
                            'url': 'tavily:ai-summary',
                            'content': data['answer'],
                            'score': 1.0,
                            'query': query,
                            'is_ai_summary': True
                        })

                    logger.debug(f"Agent {self.AGENT_ID} found {len(results)} results")
                    return results

                # ── RATE LIMITED (429 / 432) ───────────────────────────
                if response.status_code in (429, 432):
                    BaseAgent._tavily_consecutive_failures += 1
                    failures = BaseAgent._tavily_consecutive_failures
                    logger.warning(
                        f"Agent {self.AGENT_ID} Tavily rate limited "
                        f"(HTTP {response.status_code}), "
                        f"consecutive failures: {failures}/{cb_threshold}, "
                        f"attempt {attempt + 1}/{max_retries + 1}"
                    )

                    # Check circuit breaker threshold
                    if failures >= cb_threshold:
                        BaseAgent._tavily_circuit_open_until = (
                            time.monotonic() + cb_cooldown
                        )
                        logger.error(
                            f"Agent {self.AGENT_ID} Tavily circuit breaker OPENED "
                            f"after {failures} consecutive failures. "
                            f"Cooldown: {cb_cooldown}s"
                        )
                        self.emit_event(
                            "circuit_breaker",
                            f"Circuit breaker opened after {failures} failures"
                        )
                        return []

                    # Exponential backoff with jitter-free cap
                    if attempt < max_retries:
                        backoff = min(
                            initial_backoff * (2 ** attempt),
                            max_backoff
                        )
                        logger.info(
                            f"Agent {self.AGENT_ID} backing off {backoff:.1f}s "
                            f"before retry"
                        )
                        self.emit_event(
                            "rate_limited",
                            f"Rate limited, retrying in {backoff:.0f}s..."
                        )
                        await asyncio.sleep(backoff)
                        continue

                    # Exhausted retries
                    logger.error(
                        f"Agent {self.AGENT_ID} Tavily rate limited, "
                        f"exhausted {max_retries + 1} attempts for: {query[:60]}"
                    )
                    return []

                # ── OTHER HTTP ERRORS (don't retry) ────────────────────
                logger.error(
                    f"Agent {self.AGENT_ID} Tavily API error: "
                    f"{response.status_code} - {response.text[:200]}"
                )
                return []

            except Exception as e:
                logger.error(
                    f"Agent {self.AGENT_ID} Tavily search exception "
                    f"(attempt {attempt + 1}/{max_retries + 1}): {e}"
                )
                if attempt < max_retries:
                    backoff = min(
                        initial_backoff * (2 ** attempt),
                        max_backoff
                    )
                    logger.info(
                        f"Agent {self.AGENT_ID} retrying after exception, "
                        f"backoff {backoff:.1f}s"
                    )
                    await asyncio.sleep(backoff)
                    continue

                # Exhausted retries on exceptions
                logger.error(
                    f"Agent {self.AGENT_ID} Tavily search failed after "
                    f"{max_retries + 1} attempts: {e}"
                )
                return []

        # Should not reach here, but safety net
        return []

    # ═══════════════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ═══════════════════════════════════════════════════════════════════════

    async def cleanup(self):
        """Clean up resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def get_metrics(self) -> Dict[str, Any]:
        """Get agent metrics as dictionary."""
        return {
            'agent_id': self.AGENT_ID,
            'agent_name': self.AGENT_NAME,
            'version': self.AGENT_VERSION,
            'prompt_version': self.PROMPT_VERSION,
            'total_requests': self.metrics.total_requests,
            'successful_requests': self.metrics.successful_requests,
            'failed_requests': self.metrics.failed_requests,
            'success_rate': (
                self.metrics.successful_requests / self.metrics.total_requests
                if self.metrics.total_requests > 0 else 0
            ),
            'total_tokens_used': self.metrics.total_tokens_used,
            'average_response_time': self.metrics.average_response_time,
            'last_request_at': (
                self.metrics.last_request_at.isoformat()
                if self.metrics.last_request_at else None
            )
        }

    def __repr__(self) -> str:
        return f"<{self.AGENT_NAME} v{self.AGENT_VERSION}>"
