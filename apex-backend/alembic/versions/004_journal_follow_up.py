"""Add follow_up_status for Telegram signal journal tracking."""

from alembic import op
import sqlalchemy as sa

revision = "004_journal_follow_up"
down_revision = "003_journal_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "journal_entries",
        sa.Column("follow_up_status", sa.String(16), nullable=False, server_default="entered"),
    )
    op.add_column(
        "journal_entries",
        sa.Column("signal_confidence", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_journal_entries_follow_up_status",
        "journal_entries",
        ["follow_up_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_journal_entries_follow_up_status", table_name="journal_entries")
    op.drop_column("journal_entries", "signal_confidence")
    op.drop_column("journal_entries", "follow_up_status")
