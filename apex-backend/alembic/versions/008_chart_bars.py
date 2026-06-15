"""Chart bars table for MetaTrader multi-timeframe candles."""

from alembic import op
import sqlalchemy as sa

revision = "008_chart_bars"
down_revision = "007_auto_outcome_tracker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chart_bars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chart_bars_symbol", "chart_bars", ["symbol"], unique=False)
    op.create_index(
        "ix_chart_bars_symbol_timeframe_timestamp",
        "chart_bars",
        ["symbol", "timeframe", "timestamp"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_chart_bars_symbol_timeframe_timestamp", table_name="chart_bars")
    op.drop_index("ix_chart_bars_symbol", table_name="chart_bars")
    op.drop_table("chart_bars")
