"""Add ministerial positions table for executive branch tracking.

Revision ID: 024
Revises: 023
Create Date: 2026-02-01

Tracks cabinet positions (Ministers, Deputy PM, State Ministers) for political figures.
This complements parliamentary data to give a complete picture of a candidate's
political experience - both legislative AND executive.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ministerial_positions table."""
    op.create_table(
        "ministerial_positions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Person identification
        sa.Column("person_name_en", sa.String(255), nullable=False),
        sa.Column("person_name_ne", sa.String(255), nullable=True),
        # Optional links to other tables
        sa.Column(
            "linked_candidate_id",
            UUID(as_uuid=True),
            sa.ForeignKey("candidates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "linked_mp_id",
            UUID(as_uuid=True),
            sa.ForeignKey("mp_performance.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Position details
        sa.Column("position_type", sa.String(50), nullable=False),  # prime_minister, deputy_pm, minister, state_minister
        sa.Column("ministry", sa.String(255), nullable=True),
        sa.Column("ministry_ne", sa.String(255), nullable=True),
        sa.Column("position_title", sa.String(255), nullable=True),
        # Tenure
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), default=False, nullable=False),
        # Context
        sa.Column("government_name", sa.String(255), nullable=True),
        sa.Column("prime_minister", sa.String(255), nullable=True),
        sa.Column("appointment_order", sa.Integer(), nullable=True),
        sa.Column("party_at_appointment", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # Metadata
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # Create indexes for efficient lookups
    op.create_index(
        "idx_ministerial_positions_person",
        "ministerial_positions",
        ["person_name_en"],
    )
    op.create_index(
        "idx_ministerial_positions_candidate",
        "ministerial_positions",
        ["linked_candidate_id"],
    )
    op.create_index(
        "idx_ministerial_positions_mp",
        "ministerial_positions",
        ["linked_mp_id"],
    )
    op.create_index(
        "idx_ministerial_positions_ministry",
        "ministerial_positions",
        ["ministry"],
    )
    op.create_index(
        "idx_ministerial_positions_type",
        "ministerial_positions",
        ["position_type"],
    )
    op.create_index(
        "idx_ministerial_positions_current",
        "ministerial_positions",
        ["is_current"],
    )
    op.create_index(
        "idx_ministerial_positions_dates",
        "ministerial_positions",
        ["start_date", "end_date"],
    )


def downgrade() -> None:
    """Drop ministerial_positions table and indexes."""
    op.drop_index("idx_ministerial_positions_dates", table_name="ministerial_positions")
    op.drop_index("idx_ministerial_positions_current", table_name="ministerial_positions")
    op.drop_index("idx_ministerial_positions_type", table_name="ministerial_positions")
    op.drop_index("idx_ministerial_positions_ministry", table_name="ministerial_positions")
    op.drop_index("idx_ministerial_positions_mp", table_name="ministerial_positions")
    op.drop_index("idx_ministerial_positions_candidate", table_name="ministerial_positions")
    op.drop_index("idx_ministerial_positions_person", table_name="ministerial_positions")
    op.drop_table("ministerial_positions")
