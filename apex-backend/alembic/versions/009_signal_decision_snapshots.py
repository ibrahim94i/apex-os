"""Immutable decision snapshots linked to emitted trading signals."""

from alembic import op
import sqlalchemy as sa

revision = "009_signal_decision_snapshots"
down_revision = "008_chart_bars"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_decision_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trading_signal_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("candle_close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["trading_signal_id"],
            ["trading_signals.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trading_signal_id"),
    )
    op.create_index(
        "ix_signal_decision_snapshots_symbol",
        "signal_decision_snapshots",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_signal_decision_snapshots_candle_close_time",
        "signal_decision_snapshots",
        ["candle_close_time"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_signal_decision_snapshots_candle_close_time",
        table_name="signal_decision_snapshots",
    )
    op.drop_index("ix_signal_decision_snapshots_symbol", table_name="signal_decision_snapshots")
    op.drop_table("signal_decision_snapshots")
