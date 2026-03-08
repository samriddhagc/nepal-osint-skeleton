"""Add indexes for aviation analytics queries.

Revision ID: 058
Revises: 057
"""
from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_aircraft_positions_military_seen",
        "aircraft_positions",
        ["is_military", "seen_at"],
    )
    op.create_index(
        "ix_aircraft_positions_airport_seen",
        "aircraft_positions",
        ["nearest_airport_icao", "seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_aircraft_positions_airport_seen", table_name="aircraft_positions")
    op.drop_index("ix_aircraft_positions_military_seen", table_name="aircraft_positions")
