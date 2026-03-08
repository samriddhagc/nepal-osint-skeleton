"""Add airspace_category column to aircraft_positions.

Revision ID: 059
Revises: 058
"""

from alembic import op
import sqlalchemy as sa

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "aircraft_positions",
        sa.Column(
            "airspace_category",
            sa.String(20),
            nullable=True,
            comment="in_nepal, near_nepal, nepal_carrier, overflight",
        ),
    )
    op.create_index(
        "ix_aircraft_positions_airspace_cat_seen",
        "aircraft_positions",
        ["airspace_category", "seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_aircraft_positions_airspace_cat_seen", "aircraft_positions")
    op.drop_column("aircraft_positions", "airspace_category")
