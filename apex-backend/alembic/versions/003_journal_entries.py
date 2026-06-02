"""Add journal_entries table."""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("emotion", sa.String(length=16), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pnl_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("closed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journal_entries_symbol", "journal_entries", ["symbol"])
    op.create_index("ix_journal_entries_result", "journal_entries", ["result"])
    op.create_index("ix_journal_entries_closed_at", "journal_entries", ["closed_at"])


def downgrade() -> None:
    op.drop_index("ix_journal_entries_closed_at", table_name="journal_entries")
    op.drop_index("ix_journal_entries_result", table_name="journal_entries")
    op.drop_index("ix_journal_entries_symbol", table_name="journal_entries")
    op.drop_table("journal_entries")
