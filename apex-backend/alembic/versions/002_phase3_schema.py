"""Phase 3: outcomes, memory patterns, agent weight logs

Revision ID: 002
Revises: 001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trading_signals", sa.Column("outcome", sa.String(length=16), nullable=True))
    op.add_column("trading_signals", sa.Column("actual_exit_price", sa.Float(), nullable=True))
    op.add_column("trading_signals", sa.Column("rr_achieved", sa.Float(), nullable=True))
    op.create_index("ix_trading_signals_outcome", "trading_signals", ["outcome"])

    op.create_table(
        "memory_patterns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("regime", sa.String(length=32), nullable=False),
        sa.Column("time_of_day", sa.String(length=16), nullable=False),
        sa.Column("agent_id", sa.String(length=32), nullable=True),
        sa.Column("win_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_rr", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_patterns_symbol", "memory_patterns", ["symbol"])
    op.create_index("ix_memory_patterns_regime", "memory_patterns", ["regime"])
    op.create_index("ix_memory_patterns_agent_id", "memory_patterns", ["agent_id"])
    op.create_index(
        "ix_memory_patterns_unique",
        "memory_patterns",
        ["symbol", "regime", "time_of_day", "agent_id"],
        unique=True,
    )

    op.create_table(
        "agent_weight_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("regime", sa.String(length=32), nullable=False),
        sa.Column("market_weight", sa.Float(), nullable=False),
        sa.Column("risk_weight", sa.Float(), nullable=False),
        sa.Column("news_weight", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("agent_weight_logs")
    op.drop_index("ix_memory_patterns_unique", table_name="memory_patterns")
    op.drop_index("ix_memory_patterns_regime", table_name="memory_patterns")
    op.drop_index("ix_memory_patterns_symbol", table_name="memory_patterns")
    op.drop_table("memory_patterns")
    op.drop_index("ix_trading_signals_outcome", table_name="trading_signals")
    op.drop_column("trading_signals", "rr_achieved")
    op.drop_column("trading_signals", "actual_exit_price")
    op.drop_column("trading_signals", "outcome")
