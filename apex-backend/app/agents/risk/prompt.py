"""Prompts for Risk Agent."""

from app.agents.prompt_utils import AGENT_JSON_RULES, AGENT_JSON_SCHEMA, asset_header
from app.schemas.agent import MarketSnapshot

SYSTEM_PROMPT = f"""أنت وكيل مخاطر مؤسسي في نظام تداول.
قيّم المخاطر لأي أصل (BTCUSDT, XAUUSD, EURUSD, USDJPY, GBPUSD) وأعد JSON فقط:
{AGENT_JSON_SCHEMA}
{AGENT_JSON_RULES}
إذا كان مفتاح الأمان نشطاً، يجب أن تكون الإشارة NEUTRAL."""


def build_user_prompt(snapshot: MarketSnapshot) -> str:
    ks = snapshot.kill_switch
    patterns_text = ""
    if snapshot.memory_patterns:
        lines = []
        for p in snapshot.memory_patterns[:3]:
            lines.append(
                f"- {p.get('regime')}: فوز {p.get('win_rate', 0):.0%}, RR {p.get('avg_rr', 0):.1f}"
            )
        patterns_text = "\nأنماط الذاكرة:\n" + "\n".join(lines)
    return f"""{asset_header(snapshot)}
السعر: {snapshot.price}
رصيد الحساب: {snapshot.account_balance}
حد المخاطرة/صفقة: {snapshot.max_risk_pct}%
حد الهبوط: {snapshot.max_drawdown_pct}%
الخسارة اليومية: {snapshot.daily_loss_pct}%
خسائر متتالية: {snapshot.consecutive_losses}
مفتاح الأمان: {ks.status.value}
سبب المفتاح: {ks.reason or 'لا يوجد'}
ATR: {snapshot.indicators.atr}
حالة السوق: {snapshot.regime.regime.value}{patterns_text}"""
