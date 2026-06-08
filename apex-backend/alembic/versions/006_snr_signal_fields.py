"""Add SNR state and penalty to trading signals and journal entries."""

from alembic import op
import sqlalchemy as sa

revision = "006_snr_signal_fields"
down_revision = "005_journal_follow_up"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trading_signals",
        sa.Column("snr_state", sa.String(32), nullable=True),
    )
    op.add_column(
        "trading_signals",
        sa.Column("snr_penalty", sa.Integer(), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("snr_state", sa.String(32), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("snr_penalty", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("journal_entries", "snr_penalty")
    op.drop_column("journal_entries", "snr_state")
    op.drop_column("trading_signals", "snr_penalty")
    op.drop_column("trading_signals", "snr_state")
