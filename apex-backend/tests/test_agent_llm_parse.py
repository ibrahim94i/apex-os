"""Tests for AgentLLMOutput parsing across all assets."""

import json

import pytest

from app.schemas.agent import AgentLLMOutput
from app.schemas.enums import SignalDirection
from app.utils.agent_llm_parse import normalize_agent_llm_payload, parse_agent_llm_json


def test_parse_flat_json() -> None:
    raw = {
        "direction": "LONG",
        "confidence": 0.82,
        "reasoning": ["سبب 1", "سبب 2"],
    }
    out = AgentLLMOutput.model_validate(normalize_agent_llm_payload(raw, symbol="BTCUSDT"))
    assert out.direction == SignalDirection.LONG
    assert out.confidence == 0.82
    assert len(out.reasoning) == 2


def test_parse_eurusd_wrapped_by_symbol() -> None:
    raw = {
        "EURUSD": {
            "direction": "SHORT",
            "confidence": 0.71,
            "reasoning": ["ضغط هبوطي على اليورو"],
        }
    }
    out = AgentLLMOutput.model_validate(normalize_agent_llm_payload(raw, symbol="EURUSD"))
    assert out.direction == SignalDirection.SHORT
    assert out.confidence == 0.71


def test_parse_nested_analysis_key() -> None:
    raw = {
        "analysis": {
            "direction": "NEUTRAL",
            "confidence": 55,
            "reasons": ["تذبذب عالي"],
        }
    }
    out = AgentLLMOutput.model_validate(normalize_agent_llm_payload(raw, symbol="XAUUSD"))
    assert out.direction == SignalDirection.NEUTRAL
    assert out.confidence == 0.55


def test_parse_missing_fields_get_defaults() -> None:
    raw = {"note": "empty"}
    out = AgentLLMOutput.model_validate(normalize_agent_llm_payload(raw, symbol="EURUSD"))
    assert out.direction == SignalDirection.NEUTRAL
    assert 0.0 <= out.confidence <= 1.0
    assert len(out.reasoning) >= 1


def test_parse_agent_llm_json_string() -> None:
    content = json.dumps(
        {
            "result": {
                "signal": "BUY",
                "confidence_score": 0.68,
                "reasoning": ["اتجاه صاعد"],
            }
        }
    )
    out = parse_agent_llm_json(content, symbol="EURUSD")
    assert out.direction == SignalDirection.LONG
    assert out.confidence == 0.68


@pytest.mark.parametrize("symbol", ["BTCUSDT", "XAUUSD", "EURUSD"])
def test_all_assets_same_schema(symbol: str) -> None:
    raw = {
        "direction": "LONG",
        "confidence": 0.75,
        "reasoning": [f"اختبار {symbol}"],
    }
    out = AgentLLMOutput.model_validate(normalize_agent_llm_payload(raw, symbol=symbol))
    assert out.direction == SignalDirection.LONG
