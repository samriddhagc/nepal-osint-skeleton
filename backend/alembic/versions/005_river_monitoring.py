"""River monitoring tables.

Revision ID: 005
Revises: 004
Create Date: 2026-01-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # River monitoring stations
    op.create_table(
        'river_stations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('bipad_id', sa.Integer, unique=True, nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('basin', sa.String(100)),
        sa.Column('description', sa.Text),
        sa.Column('longitude', sa.Float),
        sa.Column('latitude', sa.Float),
        sa.Column('danger_level', sa.Float),
        sa.Column('warning_level', sa.Float),
        sa.Column('image_url', sa.String(500)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # River water level readings (time-series)
    op.create_table(
        'river_readings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('station_id', UUID(as_uuid=True), sa.ForeignKey('river_stations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('bipad_reading_id', sa.BigInteger, unique=True, nullable=False),
        sa.Column('water_level', sa.Float, nullable=False),
        sa.Column('status', sa.String(50)),  # BELOW WARNING LEVEL, WARNING, DANGER
        sa.Column('trend', sa.String(20)),   # STEADY, RISING, FALLING
        sa.Column('reading_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes for efficient queries
    op.create_index('idx_river_stations_basin', 'river_stations', ['basin'])
    op.create_index('idx_river_stations_active', 'river_stations', ['is_active'])
    op.create_index('idx_river_readings_station_time', 'river_readings', ['station_id', 'reading_at'])
    op.create_index('idx_river_readings_status', 'river_readings', ['status'])
    op.create_index('idx_river_readings_reading_at', 'river_readings', ['reading_at'])


def downgrade() -> None:
    op.drop_table('river_readings')
    op.drop_table('river_stations')
