"""Daily position budget — how many trades left today."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.cache import get_latest_regime
from app.services.account_service import account_service
from app.models.journal import JournalEntry
from app.schemas.journal import PositionManagerSchema

REGIME_AR = {
    "TRENDING_UP": "اتجاه صاعد",
    "TRENDING_DOWN": "اتجاه هابط",
    "RANGING": "سوق جانبي",
    "VOLATILE": "تذبذب عالي",
    "UNKNOWN": "غير معروف",
}


class PositionManagerService:
    async def get_status(
        self, session: AsyncSession, symbol: str = "XAUUSD"
    ) -> PositionManagerSchema:
        balance = await account_service.get_balance()
        daily_limit = balance * (settings.max_daily_loss_pct / 100.0)
        risk_per_trade = balance * (settings.max_risk_per_trade_pct / 100.0)

        today = datetime.now(timezone.utc).date()
        result = await session.execute(select(JournalEntry))
        today_entries = [
            e for e in result.scalars().all() if e.closed_at.date() == today
        ]

        daily_loss_used = sum(abs(e.pnl) for e in today_entries if e.result == "loss")
        losing_today = sum(1 for e in today_entries if e.result == "loss")
        daily_loss_used = min(daily_loss_used, daily_limit)
        remaining = max(daily_limit - daily_loss_used, 0.0)

        additional = int(remaining // risk_per_trade) if risk_per_trade > 0 else 0

        regime_data = await get_latest_regime(symbol)
        regime = regime_data.get("regime", "UNKNOWN") if regime_data else "UNKNOWN"
        market_state_ar = REGIME_AR.get(regime, regime)

        if regime == "VOLATILE":
            additional = max(additional - 1, 0)
            market_state_ar += " — حذر"

        can_trade = remaining > 0 and additional > 0

        if not can_trade:
            message = "توقف التداول اليوم — استأنف غداً"
        elif additional == 1:
            message = (
                f"يمكنك فتح صفقة إضافية واحدة اليوم — "
                f"لديك ${remaining:.2f} متبقية من حد المخاطرة اليومي"
            )
        else:
            message = (
                f"يمكنك فتح {additional} صفقات إضافية اليوم — "
                f"لديك ${remaining:.2f} متبقية من حد المخاطرة اليومي"
            )

        return PositionManagerSchema(
            account_balance=balance,
            daily_loss_limit_usd=round(daily_limit, 2),
            daily_loss_used_usd=round(daily_loss_used, 2),
            daily_loss_remaining_usd=round(remaining, 2),
            risk_per_trade_usd=round(risk_per_trade, 2),
            losing_trades_today=losing_today,
            additional_trades_allowed=additional,
            market_state_ar=market_state_ar,
            can_trade=can_trade,
            message_ar=message,
        )


position_manager_service = PositionManagerService()
