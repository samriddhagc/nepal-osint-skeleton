"""manifesto promises table

Revision ID: 063
Revises: 062_election_results_2082
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manifesto_promises",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("promise_id", sa.String(10), unique=True, nullable=False),
        sa.Column("party", sa.String(20), nullable=False, server_default="RSP"),
        sa.Column("election_year", sa.String(10), nullable=False, server_default="2082"),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("promise", sa.Text, nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="not_started"),
        sa.Column("status_detail", sa.Text, nullable=True),
        sa.Column("evidence_urls", sa.Text, nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_manifesto_promises_party_year", "manifesto_promises", ["party", "election_year"])
    op.create_index("ix_manifesto_promises_status", "manifesto_promises", ["status"])


def downgrade() -> None:
    op.drop_table("manifesto_promises")
