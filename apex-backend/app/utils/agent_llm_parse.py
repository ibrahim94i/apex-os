"""Normalize LLM JSON into AgentLLMOutput — same contract for all assets."""

from __future__ import annotations

import json
from typing import Any

from app.schemas.enums import SignalDirection

_WRAPPER_KEYS = (
    "result",
    "analysis",
    "output",
    "response",
    "data",
    "signal",
    "verdict",
    "agent_output",
    "recommendation",
)

_DIRECTION_MAP = {
    "LONG": SignalDirection.LONG,
    "SHORT": SignalDirection.SHORT,
    "NEUTRAL": SignalDirection.NEUTRAL,
    "BUY": SignalDirection.LONG,
    "SELL": SignalDirection.SHORT,
    "WAIT": SignalDirection.NEUTRAL,
    "HOLD": SignalDirection.NEUTRAL,
    "NONE": SignalDirection.NEUTRAL,
    "شراء": SignalDirection.LONG,
    "بيع": SignalDirection.SHORT,
    "محايد": SignalDirection.NEUTRAL,
    "انتظار": SignalDirection.NEUTRAL,
}


def _has_core_fields(data: dict[str, Any]) -> bool:
    return any(k in data for k in ("direction", "confidence", "reasoning", "reasons"))


def _unwrap_payload(raw: dict[str, Any], symbol: str | None) -> dict[str, Any]:
    if _has_core_fields(raw):
        return raw

    if symbol:
        asset = None
        try:
            from app.config.assets import get_asset

            asset = get_asset(symbol)
        except Exception:
            asset = None

        keys = {symbol, symbol.upper(), symbol.lower()}
        if asset and asset.twelvedata_symbol:
            keys.add(asset.twelvedata_symbol)
            keys.add(asset.twelvedata_symbol.replace("/", ""))
        if asset and asset.alphavantage_from_symbol and asset.alphavantage_to_symbol:
            pair = f"{asset.alphavantage_from_symbol}/{asset.alphavantage_to_symbol}"
            keys.add(pair)
            keys.add(pair.replace("/", ""))

        for key in keys:
            inner = raw.get(key)
            if isinstance(inner, dict):
                return inner

    for key in _WRAPPER_KEYS:
        inner = raw.get(key)
        if isinstance(inner, dict):
            return inner

    for val in raw.values():
        if isinstance(val, dict) and _has_core_fields(val):
            return val

    return raw


def _coerce_direction(value: Any) -> SignalDirection:
    if value is None:
        return SignalDirection.NEUTRAL
    if isinstance(value, SignalDirection):
        return value
    text = str(value).strip().upper()
    if text in _DIRECTION_MAP:
        return _DIRECTION_MAP[text]
    if text in _DIRECTION_MAP:
        return _DIRECTION_MAP[text]
    # Arabic case-sensitive keys
    for key, direction in _DIRECTION_MAP.items():
        if str(value).strip() == key:
            return direction
    return SignalDirection.NEUTRAL


def _coerce_confidence(value: Any) -> float:
    if value is None:
        return 0.5
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.5
    if conf > 1.0:
        conf = conf / 100.0
    return max(0.0, min(1.0, conf))


def _coerce_reasoning(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, dict):
        items: list[str] = []
        for k, v in value.items():
            items.append(f"{k}: {v}")
        return items
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def normalize_agent_llm_payload(raw: Any, symbol: str | None = None) -> dict[str, Any]:
    """Coerce varied LLM JSON shapes into AgentLLMOutput fields."""
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object, got {type(raw).__name__}")

    data = _unwrap_payload(raw, symbol)

    direction = _coerce_direction(
        data.get("direction")
        or data.get("signal")
        or data.get("signal_direction")
        or data.get("trade_direction")
        or data.get("recommendation")
    )
    confidence = _coerce_confidence(
        data.get("confidence")
        or data.get("confidence_score")
        or data.get("score")
        or data.get("probability")
    )
    reasoning = _coerce_reasoning(
        data.get("reasoning")
        or data.get("reasons")
        or data.get("rationale")
        or data.get("analysis")
        or data.get("explanation")
    )

    if not reasoning:
        asset_label = symbol or "الأصل"
        reasoning = [f"تحليل {asset_label} — لم يُرجع النموذج أسباباً تفصيلية"]

    return {
        "direction": direction.value,
        "confidence": confidence,
        "reasoning": reasoning[:15],
    }


def parse_agent_llm_json(content: str, symbol: str | None = None):
    """Parse raw LLM JSON string into AgentLLMOutput."""
    from app.schemas.agent import AgentLLMOutput

    raw = json.loads(content)
    return AgentLLMOutput.model_validate(normalize_agent_llm_payload(raw, symbol=symbol))


def parse_combined_agent_llm_json(content: str, symbol: str | None = None):
    """Parse combined multi-agent LLM JSON."""
    from app.schemas.agent import AgentLLMOutput, CombinedAgentLLMOutput

    raw = json.loads(content)
    if not isinstance(raw, dict):
        raise ValueError("Expected JSON object")

    agents_raw = raw
    for key in _WRAPPER_KEYS:
        inner = raw.get(key)
        if isinstance(inner, dict) and any(k in inner for k in ("market_analyst", "risk", "news")):
            agents_raw = inner
            break

    def _parse_agent(key: str, alt_keys: tuple[str, ...] = ()) -> dict[str, Any]:
        block = agents_raw.get(key)
        for alt in alt_keys:
            if block is None:
                block = agents_raw.get(alt)
        if isinstance(block, dict):
            return normalize_agent_llm_payload(block, symbol=symbol)
        return normalize_agent_llm_payload({}, symbol=symbol)

    return CombinedAgentLLMOutput(
        market_analyst=AgentLLMOutput.model_validate(
            _parse_agent("market_analyst", ("market", "analyst", "technical"))
        ),
        risk=AgentLLMOutput.model_validate(_parse_agent("risk", ("risk_agent",))),
        news=AgentLLMOutput.model_validate(_parse_agent("news", ("news_agent",))),
    )


def _parse_round_opinion(block: Any, symbol: str | None) -> dict[str, Any]:
    if isinstance(block, dict):
        return normalize_agent_llm_payload(block, symbol=symbol)
    return normalize_agent_llm_payload({}, symbol=symbol)


def parse_team_discussion_json(content: str, symbol: str | None = None):
    """Parse three-round team discussion LLM JSON."""
    from app.schemas.agent import TeamDiscussionLLMOutput, TeamRoundOpinion

    raw = json.loads(content)
    if not isinstance(raw, dict):
        raise ValueError("Expected JSON object")

    def _round(section_key: str) -> dict[str, TeamRoundOpinion]:
        section = raw.get(section_key, {})
        if not isinstance(section, dict):
            section = {}
        out: dict[str, TeamRoundOpinion] = {}
        for key in ("market_analyst", "risk", "news"):
            if key in section:
                out[key] = TeamRoundOpinion.model_validate(_parse_round_opinion(section[key], symbol))
        return out

    final_raw = raw.get("round3_final") or raw.get("final") or {}
    final = TeamRoundOpinion.model_validate(_parse_round_opinion(final_raw, symbol))

    return TeamDiscussionLLMOutput(
        round1_initial=_round("round1_initial"),
        round2_responses=_round("round2_responses"),
        round3_final=final,
        agreements=_coerce_reasoning(raw.get("agreements") or []),
        disagreements=_coerce_reasoning(raw.get("disagreements") or []),
        discussion_summary=_coerce_reasoning(raw.get("discussion_summary") or []),
    )
