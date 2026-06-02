"""Market Analyst Agent — technical & regime analysis."""

import time

from app.agents.market_analyst.prompt import SYSTEM_PROMPT, build_user_prompt
from app.schemas.agent import AgentLLMOutput, AgentRole, AgentVerdict, MarketSnapshot
from app.schemas import SignalDirection
from app.utils.llm_client import LLMClient, LLMClientError, llm_client


AGENT_NAME_AR = "محلل السوق"
WEIGHT = 0.40


def _rule_based(snapshot: MarketSnapshot) -> AgentLLMOutput:
    reasoning: list[str] = []
    score = 0.0

    ind = snapshot.indicators
    regime = snapshot.regime

    if ind.rsi is not None:
        if ind.rsi < 35:
            score += 1.0
            reasoning.append(f"مؤشر RSI عند {ind.rsi:.1f} — منطقة تشبع بيعي محتمل")
        elif ind.rsi > 65:
            score -= 1.0
            reasoning.append(f"مؤشر RSI عند {ind.rsi:.1f} — منطقة تشبع شرائي محتمل")
        else:
            reasoning.append(f"مؤشر RSI عند {ind.rsi:.1f} — محايد")

    if ind.macd is not None and ind.macd_signal is not None:
        if ind.macd > ind.macd_signal:
            score += 0.8
            reasoning.append("MACD فوق خط الإشارة — زخم صعودي")
        else:
            score -= 0.8
            reasoning.append("MACD تحت خط الإشارة — زخم هبوطي")

    if ind.ema_9 is not None and ind.ema_21 is not None:
        if ind.ema_9 > ind.ema_21:
            score += 0.6
            reasoning.append("EMA9 فوق EMA21 — اتجاه قصير المدى صاعد")
        else:
            score -= 0.6
            reasoning.append("EMA9 تحت EMA21 — اتجاه قصير المدى هابط")

    reasoning.append(f"حالة السوق: {regime.regime.value} بثقة {regime.confidence:.0%}")

    if snapshot.memory_patterns:
        top = snapshot.memory_patterns[0]
        wr = float(top.get("win_rate", 0))
        if wr >= 0.6:
            score += 0.3 if score > 0 else -0.1
            reasoning.append(
                f"نمط ذاكرة قوي: فوز تاريخي {wr:.0%} في {top.get('regime')}"
            )
        elif wr <= 0.4:
            score *= 0.85
            reasoning.append(
                f"نمط ذاكرة ضعيف: فوز تاريخي {wr:.0%} — حذر"
            )

    if score > 0.4:
        direction = SignalDirection.LONG
    elif score < -0.4:
        direction = SignalDirection.SHORT
    else:
        direction = SignalDirection.NEUTRAL

    confidence = min(abs(score) / 2.4, 1.0)
    return AgentLLMOutput(direction=direction, confidence=round(confidence, 4), reasoning=reasoning)


class MarketAnalystAgent:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or llm_client

    async def analyze(self, snapshot: MarketSnapshot) -> AgentVerdict:
        start = time.monotonic()
        used_llm = False
        error: str | None = None

        try:
            if self.client.is_configured:
                output, response = await self.client.structured_completion(
                    SYSTEM_PROMPT,
                    build_user_prompt(snapshot),
                    AgentLLMOutput,
                    symbol=snapshot.symbol,
                )
                used_llm = True
                latency_ms = response.latency_ms
            else:
                output = _rule_based(snapshot)
                latency_ms = (time.monotonic() - start) * 1000
        except LLMClientError as exc:
            error = str(exc)
            output = _rule_based(snapshot)
            latency_ms = (time.monotonic() - start) * 1000

        return AgentVerdict(
            agent_id=AgentRole.MARKET_ANALYST,
            agent_name_ar=AGENT_NAME_AR,
            direction=output.direction,
            confidence=output.confidence,
            reasoning=output.reasoning,
            weight=WEIGHT,
            latency_ms=round(latency_ms, 2),
            used_llm=used_llm,
            error=error,
        )
