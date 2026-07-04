"""
Central OpenAI model configuration for BidBrief.

Two tiers:
  STANDARD   — the general-purpose workhorse every feature uses by default.
  HIGH POWER — the flagship model, enabled per-request by admins / bonus users
               via a `high_power: true` body flag on the AI feature endpoints.

Both are env-overridable so model bumps or rollbacks are a Render env change:
  BIDBRIEF_MODEL_STANDARD    (default: gpt-5.4)
  BIDBRIEF_MODEL_HIGH_POWER  (default: gpt-5.5)

Why this module exists (do not bypass it):
GPT-5.x are reasoning models. In Chat Completions they REJECT `max_tokens`,
`temperature`, and `top_p`; they require `max_completion_tokens` and accept
`reasoning_effort` (none/low/medium/high/xhigh). Reasoning tokens bill as
output tokens and consume the completion budget, so budgets need headroom.
Legacy models (gpt-4o and earlier) still take `max_tokens` + `temperature`.
`completion_params()` maps one intent onto whichever family is in play.
"""

import os
from typing import Any, Dict, List, Optional

# Prefixes that mark OpenAI reasoning models (no temperature, max_completion_tokens).
_REASONING_PREFIXES = ('gpt-5', 'o1', 'o3', 'o4')

# Extra completion budget consumed by hidden reasoning tokens, by effort level.
_REASONING_HEADROOM = {
    'none': 0,
    'low': 4096,
    'medium': 8192,
    'high': 16384,
    'xhigh': 32768,
}

# Absolute completion-token ceiling for gpt-5.x requests.
_MAX_COMPLETION_CAP = 128000


def standard_model() -> str:
    return os.environ.get('BIDBRIEF_MODEL_STANDARD', 'gpt-5.4')


def high_power_model() -> str:
    return os.environ.get('BIDBRIEF_MODEL_HIGH_POWER', 'gpt-5.5')


def resolve_model(high_power: bool = False) -> str:
    return high_power_model() if high_power else standard_model()


def model_tier(model: str) -> str:
    """Human-readable tier label for API responses / logs."""
    return 'high_power' if model == high_power_model() else 'standard'


def default_effort(high_power: bool = False) -> str:
    """Reasoning effort used when the caller does not specify one."""
    return 'high' if high_power else 'low'


def is_reasoning_model(model: str) -> bool:
    m = (model or '').lower()
    return any(m.startswith(p) for p in _REASONING_PREFIXES)


def completion_params(
    model: str,
    max_output_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the model + sampling/limit kwargs for chat.completions.create().

    max_output_tokens is the DESIRED visible output budget; for reasoning
    models the wire value is padded with headroom for hidden reasoning tokens.
    temperature is applied only on legacy models (reasoning models reject it).
    """
    params: Dict[str, Any] = {'model': model}
    if is_reasoning_model(model):
        effort = reasoning_effort or 'low'
        params['reasoning_effort'] = effort
        if max_output_tokens is not None:
            budget = max_output_tokens + _REASONING_HEADROOM.get(effort, 8192)
            params['max_completion_tokens'] = min(budget, _MAX_COMPLETION_CAP)
    else:
        if temperature is not None:
            params['temperature'] = temperature
        if max_output_tokens is not None:
            params['max_tokens'] = max_output_tokens
    return params


def chat_payload(
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
    response_format: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """JSON body for raw HTTP POSTs to /v1/chat/completions (app.py question gen)."""
    payload = completion_params(model, max_output_tokens, temperature, reasoning_effort)
    payload['messages'] = messages
    if response_format is not None:
        payload['response_format'] = response_format
    return payload
