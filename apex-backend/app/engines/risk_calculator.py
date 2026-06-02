"""Position sizing based on account risk parameters."""

from dataclasses import dataclass

from app.config import settings


@dataclass
class PositionSizeResult:
    position_size: float
    risk_amount: float
    risk_pct: float
    units: float


class RiskCalculator:
    def __init__(
        self,
        account_balance: float | None = None,
        max_risk_pct: float | None = None,
    ) -> None:
        self.account_balance = account_balance or settings.account_balance
        self.max_risk_pct = max_risk_pct or settings.max_risk_per_trade_pct

    def calculate(
        self,
        entry_price: float,
        stop_loss: float,
        direction: str,
    ) -> PositionSizeResult:
        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            return PositionSizeResult(
                position_size=0.0,
                risk_amount=0.0,
                risk_pct=0.0,
                units=0.0,
            )

        risk_amount = self.account_balance * (self.max_risk_pct / 100.0)
        units = risk_amount / risk_per_unit
        position_size = units * entry_price

        return PositionSizeResult(
            position_size=round(position_size, 2),
            risk_amount=round(risk_amount, 2),
            risk_pct=self.max_risk_pct,
            units=round(units, 6),
        )
