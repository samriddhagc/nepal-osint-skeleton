"""Create aircraft_positions table for ADS-B aviation monitoring.

Revision ID: 057
Revises: 056
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aircraft_positions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("hex_code", sa.String(6), nullable=False, comment="ICAO 24-bit address e.g. 70A001"),
        sa.Column("callsign", sa.String(10), nullable=True),
        sa.Column("registration", sa.String(20), nullable=True, comment="e.g. 9N-AMA"),
        sa.Column("aircraft_type", sa.String(10), nullable=True, comment="ICAO type designator e.g. A320, H125"),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("altitude_ft", sa.Integer, nullable=True, comment="Barometric altitude in feet"),
        sa.Column("ground_speed_kts", sa.Float, nullable=True),
        sa.Column("track_deg", sa.Float, nullable=True, comment="Heading in degrees"),
        sa.Column("vertical_rate_fpm", sa.Integer, nullable=True, comment="Vertical rate in feet per minute"),
        sa.Column("squawk", sa.String(4), nullable=True),
        sa.Column("is_military", sa.Boolean, default=False),
        sa.Column("is_on_ground", sa.Boolean, default=False),
        sa.Column("category", sa.String(4), nullable=True, comment="ADS-B emitter category"),
        sa.Column("nearest_airport_icao", sa.String(4), nullable=True, comment="Nearest Nepal airport ICAO code"),
        sa.Column("source", sa.String(20), default="adsb_lol"),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False, comment="When ADS-B signal was received"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_aircraft_positions_hex_seen", "aircraft_positions", ["hex_code", "seen_at"])
    op.create_index("ix_aircraft_positions_seen_at", "aircraft_positions", ["seen_at"])


def downgrade() -> None:
    op.drop_index("ix_aircraft_positions_seen_at", table_name="aircraft_positions")
    op.drop_index("ix_aircraft_positions_hex_seen", table_name="aircraft_positions")
    op.drop_table("aircraft_positions")
