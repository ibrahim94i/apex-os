"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_bars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_bars_symbol", "price_bars", ["symbol"])
    op.create_index("ix_price_bars_symbol_timestamp", "price_bars", ["symbol", "timestamp"], unique=True)

    op.create_table(
        "indicator_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rsi", sa.Float(), nullable=True),
        sa.Column("macd", sa.Float(), nullable=True),
        sa.Column("macd_signal", sa.Float(), nullable=True),
        sa.Column("macd_histogram", sa.Float(), nullable=True),
        sa.Column("ema_9", sa.Float(), nullable=True),
        sa.Column("ema_21", sa.Float(), nullable=True),
        sa.Column("ema_50", sa.Float(), nullable=True),
        sa.Column("atr", sa.Float(), nullable=True),
        sa.Column("bb_upper", sa.Float(), nullable=True),
        sa.Column("bb_middle", sa.Float(), nullable=True),
        sa.Column("bb_lower", sa.Float(), nullable=True),
        sa.Column("adx", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_indicator_snapshots_symbol", "indicator_snapshots", ["symbol"])

    op.create_table(
        "regime_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("regime", sa.Enum("TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE", "UNKNOWN", name="regime_type"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("adx_value", sa.Float(), nullable=True),
        sa.Column("volatility_pct", sa.Float(), nullable=True),
        sa.Column("trend_strength", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_regime_snapshots_symbol", "regime_snapshots", ["symbol"])

    op.create_table(
        "trading_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.Enum("LONG", "SHORT", "NEUTRAL", name="signal_direction"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Float(), nullable=False),
        sa.Column("position_size", sa.Float(), nullable=False),
        sa.Column("regime", sa.Enum("TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE", "UNKNOWN", name="regime_type_signal"), nullable=False),
        sa.Column("degraded", sa.Boolean(), nullable=False),
        sa.Column("degradation_reason", sa.Text(), nullable=True),
        sa.Column("kill_switch_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trading_signals_symbol", "trading_signals", ["symbol"])

    op.create_table(
        "kill_switch_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "INACTIVE", name="kill_switch_status"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drawdown_pct", sa.Float(), nullable=True),
        sa.Column("daily_loss_pct", sa.Float(), nullable=True),
        sa.Column("consecutive_losses", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "trade_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.Enum("LONG", "SHORT", "NEUTRAL", name="signal_direction_trade"), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=False),
        sa.Column("pnl", sa.Float(), nullable=False),
        sa.Column("pnl_pct", sa.Float(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("trade_results")
    op.drop_table("kill_switch_events")
    op.drop_index("ix_trading_signals_symbol", table_name="trading_signals")
    op.drop_table("trading_signals")
    op.drop_index("ix_regime_snapshots_symbol", table_name="regime_snapshots")
    op.drop_table("regime_snapshots")
    op.drop_index("ix_indicator_snapshots_symbol", table_name="indicator_snapshots")
    op.drop_table("indicator_snapshots")
    op.drop_index("ix_price_bars_symbol_timestamp", table_name="price_bars")
    op.drop_index("ix_price_bars_symbol", table_name="price_bars")
    op.drop_table("price_bars")
    op.execute("DROP TYPE IF EXISTS signal_direction_trade")
    op.execute("DROP TYPE IF EXISTS kill_switch_status")
    op.execute("DROP TYPE IF EXISTS regime_type_signal")
    op.execute("DROP TYPE IF EXISTS signal_direction")
    op.execute("DROP TYPE IF EXISTS regime_type")
