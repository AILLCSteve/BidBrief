"""Tests for the central model tier registry + parameter adapter."""
import os

import pytest

from services.ai_models import (
    chat_payload,
    completion_params,
    default_effort,
    high_power_model,
    is_reasoning_model,
    model_tier,
    resolve_model,
    standard_model,
)


def test_default_tiers(monkeypatch):
    # Delete the overrides first: a machine that sets these in its own env
    # would otherwise fail a test about the built-in defaults.
    monkeypatch.delenv('BIDBRIEF_MODEL_STANDARD', raising=False)
    monkeypatch.delenv('BIDBRIEF_MODEL_HIGH_POWER', raising=False)
    assert standard_model() == 'gpt-5.6-terra'
    assert high_power_model() == 'gpt-5.6-sol'
    assert resolve_model(False) == 'gpt-5.6-terra'
    assert resolve_model(True) == 'gpt-5.6-sol'
    assert model_tier('gpt-5.6-sol') == 'high_power'
    assert model_tier('gpt-5.6-terra') == 'standard'


def test_env_override(monkeypatch):
    monkeypatch.setenv('BIDBRIEF_MODEL_STANDARD', 'gpt-4o')
    monkeypatch.setenv('BIDBRIEF_MODEL_HIGH_POWER', 'gpt-5.4')
    assert resolve_model(False) == 'gpt-4o'
    assert resolve_model(True) == 'gpt-5.4'


def test_reasoning_detection():
    assert is_reasoning_model('gpt-5.4')
    assert is_reasoning_model('gpt-5.5')
    # The 5.6 family keeps the gpt-5 prefix, so the named tiers must still be
    # routed to max_completion_tokens/reasoning_effort - never temperature.
    assert is_reasoning_model('gpt-5.6-sol')
    assert is_reasoning_model('gpt-5.6-terra')
    assert is_reasoning_model('gpt-5.6-luna')
    assert is_reasoning_model('o3')
    assert not is_reasoning_model('gpt-4o')
    assert not is_reasoning_model('gpt-4o-mini')


def test_reasoning_params_drop_temperature_and_use_completion_tokens():
    p = completion_params('gpt-5.4', 5000, temperature=0.3)
    assert 'temperature' not in p
    assert 'max_tokens' not in p
    assert p['max_completion_tokens'] == 5000 + 4096  # low-effort headroom
    assert p['reasoning_effort'] == 'low'


def test_legacy_params_keep_temperature_and_max_tokens():
    p = completion_params('gpt-4o', 5000, temperature=0.3)
    assert p == {'model': 'gpt-4o', 'temperature': 0.3, 'max_tokens': 5000}


def test_reasoning_headroom_scales_with_effort_and_caps():
    low = completion_params('gpt-5.4', 4000, reasoning_effort='low')
    high = completion_params('gpt-5.5', 4000, reasoning_effort='high')
    assert high['max_completion_tokens'] > low['max_completion_tokens']
    capped = completion_params('gpt-5.5', 999999, reasoning_effort='xhigh')
    assert capped['max_completion_tokens'] == 128000


def test_no_token_budget_omits_limit():
    p = completion_params('gpt-5.4', temperature=0.5)
    assert 'max_completion_tokens' not in p
    assert 'max_tokens' not in p


def test_default_effort_tiers():
    assert default_effort(False) == 'low'
    assert default_effort(True) == 'high'


def test_chat_payload_shape():
    msgs = [{'role': 'user', 'content': 'hi'}]
    p = chat_payload('gpt-5.4', msgs, max_output_tokens=1000,
                     temperature=0.3, response_format={'type': 'json_object'})
    assert p['messages'] == msgs
    assert p['model'] == 'gpt-5.4'
    assert 'temperature' not in p
    assert p['response_format'] == {'type': 'json_object'}


def test_token_optimizer_detects_gpt5():
    from services.hotdog.token_optimizer import TokenOptimizer
    limits = TokenOptimizer.detect_model_limits('gpt-5.4')
    assert limits.context_window == 400000
    assert limits.max_completion_tokens_api == 128000
    # window sizing stays stable vs the gpt-4o era
    assert limits.recommended_completion_tokens == 16384
    legacy = TokenOptimizer.detect_model_limits('gpt-4o')
    assert legacy.context_window == 128000
