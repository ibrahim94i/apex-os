"""Auto outcome tracker fields on trading signals and journal entries."""

from alembic import op
import sqlalchemy as sa

revision = "007_auto_outcome_tracker"
down_revision = "006_snr_signal_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trading_signals",
        sa.Column("max_favorable_excursion", sa.Float(), nullable=True),
    )
    op.add_column(
        "trading_signals",
        sa.Column("max_adverse_excursion", sa.Float(), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("trading_signal_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("auto_outcome", sa.String(16), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("time_to_outcome", sa.Float(), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("max_favorable_excursion", sa.Float(), nullable=True),
    )
    op.add_column(
        "journal_entries",
        sa.Column("max_adverse_excursion", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_journal_entries_auto_outcome",
        "journal_entries",
        ["auto_outcome"],
    )
    op.create_index(
        "ix_journal_entries_trading_signal_id",
        "journal_entries",
        ["trading_signal_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_journal_entries_trading_signal_id", table_name="journal_entries")
    op.drop_index("ix_journal_entries_auto_outcome", table_name="journal_entries")
    op.drop_column("journal_entries", "max_adverse_excursion")
    op.drop_column("journal_entries", "max_favorable_excursion")
    op.drop_column("journal_entries", "time_to_outcome")
    op.drop_column("journal_entries", "auto_outcome")
    op.drop_column("journal_entries", "trading_signal_id")
    op.drop_column("trading_signals", "max_adverse_excursion")
    op.drop_column("trading_signals", "max_favorable_excursion")
