"""Kill switch — halts signal generation when risk limits breached."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.cache import get_kill_switch_status, set_kill_switch_status
from app.services.account_service import account_service
from app.models import KillSwitchEvent, KillSwitchStatus as KillSwitchStatusModel, TradeResult
from app.schemas import KillSwitchStatus, KillSwitchStatusSchema


@dataclass
class RiskMetrics:
    drawdown_pct: float = 0.0
    daily_loss_pct: float = 0.0
    consecutive_losses: int = 0
    account_balance: float = field(default_factory=lambda: settings.account_balance)


class KillSwitch:
    def __init__(self) -> None:
        self._status = KillSwitchStatus.INACTIVE
        self._reason: str | None = None
        self._triggered_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self._status == KillSwitchStatus.ACTIVE

    async def load_from_cache(self) -> None:
        cached = await get_kill_switch_status()
        if cached:
            self._status = KillSwitchStatus(cached.get("status", "INACTIVE"))
            self._reason = cached.get("reason")
            ts = cached.get("triggered_at")
            self._triggered_at = datetime.fromisoformat(ts) if ts else None

    async def _persist_status(self, metrics: RiskMetrics | None = None) -> None:
        data = {
            "status": self._status.value,
            "reason": self._reason,
            "triggered_at": self._triggered_at.isoformat() if self._triggered_at else None,
            "drawdown_pct": metrics.drawdown_pct if metrics else None,
            "daily_loss_pct": metrics.daily_loss_pct if metrics else None,
            "consecutive_losses": metrics.consecutive_losses if metrics else None,
        }
        await set_kill_switch_status(data)

    async def compute_metrics(self, session: AsyncSession) -> RiskMetrics:
        result = await session.execute(
            select(TradeResult).order_by(TradeResult.closed_at.desc()).limit(100)
        )
        trades = result.scalars().all()

        balance = await account_service.get_balance()
        metrics = RiskMetrics(account_balance=balance)
        if not trades:
            return metrics

        peak_balance = balance
        running_balance = balance
        max_drawdown = 0.0

        for trade in reversed(trades):
            running_balance += trade.pnl
            if running_balance > peak_balance:
                peak_balance = running_balance
            dd = ((peak_balance - running_balance) / peak_balance) * 100 if peak_balance > 0 else 0
            max_drawdown = max(max_drawdown, dd)

        metrics.drawdown_pct = round(max_drawdown, 4)

        today = datetime.now(timezone.utc).date()
        daily_pnl = sum(t.pnl for t in trades if t.closed_at.date() == today)
        metrics.daily_loss_pct = round(
            abs(min(daily_pnl, 0)) / balance * 100, 4
        )

        consecutive = 0
        for trade in trades:
            if trade.pnl < 0:
                consecutive += 1
            else:
                break
        metrics.consecutive_losses = consecutive

        return metrics

    async def evaluate(self, session: AsyncSession) -> KillSwitchStatusSchema:
        metrics = await self.compute_metrics(session)
        reasons: list[str] = []

        if metrics.drawdown_pct >= settings.max_drawdown_pct:
            reasons.append(f"Max drawdown breached: {metrics.drawdown_pct}%")
        if metrics.daily_loss_pct >= settings.max_daily_loss_pct:
            reasons.append(f"Max daily loss breached: {metrics.daily_loss_pct}%")
        if metrics.consecutive_losses >= settings.max_consecutive_losses:
            reasons.append(f"Consecutive losses: {metrics.consecutive_losses}")

        if reasons:
            self._status = KillSwitchStatus.ACTIVE
            self._reason = "; ".join(reasons)
            self._triggered_at = datetime.now(timezone.utc)

            event = KillSwitchEvent(
                status=KillSwitchStatusModel.ACTIVE,
                reason=self._reason,
                drawdown_pct=metrics.drawdown_pct,
                daily_loss_pct=metrics.daily_loss_pct,
                consecutive_losses=metrics.consecutive_losses,
            )
            session.add(event)
        else:
            if self._status == KillSwitchStatus.ACTIVE:
                event = KillSwitchEvent(
                    status=KillSwitchStatusModel.INACTIVE,
                    reason="Risk metrics normalized",
                    resolved_at=datetime.now(timezone.utc),
                )
                session.add(event)
            self._status = KillSwitchStatus.INACTIVE
            self._reason = None
            self._triggered_at = None

        await self._persist_status(metrics)

        return KillSwitchStatusSchema(
            status=self._status,
            reason=self._reason,
            triggered_at=self._triggered_at,
            drawdown_pct=metrics.drawdown_pct,
            daily_loss_pct=metrics.daily_loss_pct,
            consecutive_losses=metrics.consecutive_losses,
        )

    def to_schema(self) -> KillSwitchStatusSchema:
        return KillSwitchStatusSchema(
            status=self._status,
            reason=self._reason,
            triggered_at=self._triggered_at,
        )


kill_switch = KillSwitch()
