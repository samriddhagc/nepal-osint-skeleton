"""Add election_sync_runs operational metadata table.

Revision ID: 048
Revises: 047
Create Date: 2026-02-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "048"
down_revision: Union[str, None] = "047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "election_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("years", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("import_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("link_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("override_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reconciliation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_election_sync_runs_started_at", "election_sync_runs", ["started_at"], unique=False)
    op.create_index("idx_election_sync_runs_status", "election_sync_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_election_sync_runs_status", table_name="election_sync_runs")
    op.drop_index("idx_election_sync_runs_started_at", table_name="election_sync_runs")
    op.drop_table("election_sync_runs")

