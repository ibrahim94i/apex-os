"""Tests for team discussion JSON parsing."""

import json

from app.schemas.enums import SignalDirection
from app.utils.agent_llm_parse import parse_team_discussion_json


def test_parse_team_discussion_json() -> None:
    raw = {
        "round1_initial": {
            "market_analyst": {
                "direction": "LONG",
                "confidence": 0.8,
                "reasoning": ["اتجاه صاعد"],
            },
            "risk": {"direction": "LONG", "confidence": 0.7, "reasoning": ["مخاطر مقبولة"]},
            "news": {"direction": "NEUTRAL", "confidence": 0.5, "reasoning": ["لا أخبار"]},
        },
        "round2_responses": {
            "market_analyst": {
                "direction": "LONG",
                "confidence": 0.85,
                "reasoning": ["أوافق المخاطر"],
            },
            "risk": {"direction": "LONG", "confidence": 0.75, "reasoning": ["أوافق المحلل"]},
            "news": {"direction": "NEUTRAL", "confidence": 0.5, "reasoning": ["محايد"]},
        },
        "round3_final": {
            "direction": "LONG",
            "confidence": 0.78,
            "reasoning": ["قرار نهائي: شراء"],
        },
        "agreements": ["اتفاق على الصعود"],
        "disagreements": ["الأخبار محايدة"],
        "discussion_summary": ["ملخص النقاش"],
    }
    result = parse_team_discussion_json(json.dumps(raw), symbol="BTCUSDT")
    assert result.round3_final.direction == SignalDirection.LONG
    assert result.round3_final.confidence == 0.78
    assert len(result.agreements) == 1
    assert "market_analyst" in result.round1_initial
