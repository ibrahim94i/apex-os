"""Risk Agent — portfolio & drawdown risk assessment."""

import time

from app.agents.risk.prompt import SYSTEM_PROMPT, build_user_prompt
from app.schemas.agent import AgentLLMOutput, AgentRole, AgentVerdict, MarketSnapshot
from app.schemas import SignalDirection
from app.utils.llm_client import LLMClient, LLMClientError, llm_client


AGENT_NAME_AR = "وكيل المخاطر"
WEIGHT = 0.35


def _rule_based(snapshot: MarketSnapshot) -> AgentLLMOutput:
    reasoning: list[str] = []
    risk_score = 1.0

    ks = snapshot.kill_switch
    if ks.status.value == "ACTIVE":
        reasoning.append("مفتاح الأمان نشط — يُنصح بعدم التداول")
        return AgentLLMOutput(
            direction=SignalDirection.NEUTRAL,
            confidence=0.9,
            reasoning=reasoning,
        )

    if snapshot.daily_loss_pct >= snapshot.max_drawdown_pct * 0.5:
        risk_score -= 0.3
        reasoning.append(
            f"الخسارة اليومية {snapshot.daily_loss_pct:.2f}% — اقتراب من الحد"
        )

    if snapshot.consecutive_losses >= 2:
        risk_score -= 0.25
        reasoning.append(f"{snapshot.consecutive_losses} خسائر متتالية — تقليل المخاطرة")

    atr = snapshot.indicators.atr
    if atr and snapshot.price > 0:
        atr_pct = (atr / snapshot.price) * 100
        if atr_pct > 1.5:
            risk_score -= 0.2
            reasoning.append(f"ATR مرتفع ({atr_pct:.2f}%) — تذبذب يزيد المخاطرة")

    reasoning.append(f"رصيد الحساب: ${snapshot.account_balance:,.0f}")
    reasoning.append(f"الحد الأقصى للمخاطرة: {snapshot.max_risk_pct}% لكل صفقة")

    if risk_score >= 0.7:
        direction = SignalDirection.LONG if snapshot.regime.regime.value == "TRENDING_UP" else SignalDirection.NEUTRAL
        if snapshot.regime.regime.value == "TRENDING_DOWN":
            direction = SignalDirection.SHORT
    elif risk_score >= 0.4:
        direction = SignalDirection.NEUTRAL
    else:
        direction = SignalDirection.NEUTRAL

    return AgentLLMOutput(
        direction=direction,
        confidence=round(max(risk_score, 0.1), 4),
        reasoning=reasoning,
    )


class RiskAgent:
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
            agent_id=AgentRole.RISK,
            agent_name_ar=AGENT_NAME_AR,
            direction=output.direction,
            confidence=output.confidence,
            reasoning=output.reasoning,
            weight=WEIGHT,
            latency_ms=round(latency_ms, 2),
            used_llm=used_llm,
            error=error,
        )
