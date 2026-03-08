"""Add disaster tables (incidents, alerts) with coordinate storage.

Revision ID: 004
Revises: 003
Create Date: 2026-01-27

Note: Uses simple float columns for coordinates instead of PostGIS geometry
for compatibility with pgvector image.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create disaster_incidents table
    op.create_table(
        "disaster_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bipad_id", sa.Integer, nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("title_ne", sa.Text, nullable=True),
        sa.Column(
            "hazard_type",
            sa.String(30),
            nullable=False,
            comment="flood|landslide|earthquake|fire|lightning|drought|avalanche|windstorm|cold_wave|epidemic|other",
        ),
        sa.Column("hazard_id", sa.Integer, nullable=True),
        # Coordinates as simple floats (compatible with pgvector image)
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("street_address", sa.String(500), nullable=True),
        sa.Column("ward_ids", postgresql.JSONB, nullable=True),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("province", sa.Integer, nullable=True),
        sa.Column("deaths", sa.Integer, default=0, nullable=False),
        sa.Column("injured", sa.Integer, default=0, nullable=False),
        sa.Column("missing", sa.Integer, default=0, nullable=False),
        sa.Column("affected_families", sa.Integer, default=0, nullable=False),
        sa.Column("estimated_loss", sa.Float, default=0.0, nullable=False, comment="Loss in NPR"),
        sa.Column("verified", sa.Boolean, default=False),
        sa.Column(
            "severity",
            sa.String(20),
            nullable=True,
            comment="critical|high|medium|low",
        ),
        sa.Column("incident_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create disaster_alerts table
    op.create_table(
        "disaster_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bipad_id", sa.Integer, nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "alert_type",
            sa.String(50),
            nullable=False,
            comment="earthquake|river_alert|early_warning|weather_warning",
        ),
        sa.Column(
            "alert_level",
            sa.String(20),
            nullable=False,
            comment="critical|high|medium|low",
        ),
        # Coordinates as simple floats
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("location_name", sa.String(255), nullable=True),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("province", sa.Integer, nullable=True),
        sa.Column("magnitude", sa.Float, nullable=True, comment="For earthquakes"),
        sa.Column("depth_km", sa.Float, nullable=True, comment="Earthquake depth in km"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create indexes for incidents
    op.create_index("idx_incidents_bipad_id", "disaster_incidents", ["bipad_id"])
    op.create_index("idx_incidents_hazard_date", "disaster_incidents", ["hazard_type", "incident_on"])
    op.create_index("idx_incidents_severity", "disaster_incidents", ["severity"])
    op.create_index("idx_incidents_district", "disaster_incidents", ["district"])
    op.create_index("idx_incidents_incident_on", "disaster_incidents", ["incident_on"])
    op.create_index("idx_incidents_deaths", "disaster_incidents", ["deaths"])
    op.create_index("idx_incidents_coords", "disaster_incidents", ["longitude", "latitude"])

    # Create indexes for alerts
    op.create_index("idx_alerts_bipad_id", "disaster_alerts", ["bipad_id"])
    op.create_index("idx_alerts_active_issued", "disaster_alerts", ["is_active", "issued_at"])
    op.create_index("idx_alerts_type_level", "disaster_alerts", ["alert_type", "alert_level"])
    op.create_index("idx_alerts_district", "disaster_alerts", ["district"])
    op.create_index("idx_alerts_coords", "disaster_alerts", ["longitude", "latitude"])


def downgrade() -> None:
    # Drop indexes for alerts
    op.drop_index("idx_alerts_coords", table_name="disaster_alerts")
    op.drop_index("idx_alerts_district", table_name="disaster_alerts")
    op.drop_index("idx_alerts_type_level", table_name="disaster_alerts")
    op.drop_index("idx_alerts_active_issued", table_name="disaster_alerts")
    op.drop_index("idx_alerts_bipad_id", table_name="disaster_alerts")

    # Drop indexes for incidents
    op.drop_index("idx_incidents_coords", table_name="disaster_incidents")
    op.drop_index("idx_incidents_deaths", table_name="disaster_incidents")
    op.drop_index("idx_incidents_incident_on", table_name="disaster_incidents")
    op.drop_index("idx_incidents_district", table_name="disaster_incidents")
    op.drop_index("idx_incidents_severity", table_name="disaster_incidents")
    op.drop_index("idx_incidents_hazard_date", table_name="disaster_incidents")
    op.drop_index("idx_incidents_bipad_id", table_name="disaster_incidents")

    # Drop tables
    op.drop_table("disaster_alerts")
    op.drop_table("disaster_incidents")
