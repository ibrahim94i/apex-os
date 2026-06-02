"""Add calibration fields to trading_signals and indicator columns."""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trading_signals",
        sa.Column("max_drawdown_during_trade", sa.Float(), nullable=True),
    )
    op.add_column(
        "trading_signals",
        sa.Column("time_in_trade_hours", sa.Float(), nullable=True),
    )
    op.add_column(
        "trading_signals",
        sa.Column("profit_loss_amount", sa.Float(), nullable=True),
    )
    op.add_column(
        "indicator_snapshots",
        sa.Column("ema_200", sa.Float(), nullable=True),
    )
    op.add_column(
        "indicator_snapshots",
        sa.Column("atr_avg_20", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("indicator_snapshots", "atr_avg_20")
    op.drop_column("indicator_snapshots", "ema_200")
    op.drop_column("trading_signals", "profit_loss_amount")
    op.drop_column("trading_signals", "time_in_trade_hours")
    op.drop_column("trading_signals", "max_drawdown_during_trade")
