"""Add weather_forecasts table for DHM Nepal weather data.

Revision ID: 010
Revises: 009
Create Date: 2026-01-28

Stores daily weather forecasts from DHM (Department of Hydrology and Meteorology)
Nepal API. Supports bilingual forecasts (English/Nepali) and historical tracking.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'weather_forecasts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('dhm_id', sa.String(50), unique=True, nullable=False, comment='DHM forecast ID'),
        sa.Column('issue_date', sa.DateTime(timezone=True), nullable=False, comment='Forecast issue date'),

        # Bilingual analysis
        sa.Column('analysis_en', sa.Text(), nullable=True, comment='Weather analysis in English'),
        sa.Column('analysis_np', sa.Text(), nullable=True, comment='Weather analysis in Nepali'),

        # Today's forecast
        sa.Column('forecast_en_1', sa.Text(), nullable=True, comment='Today forecast in English'),
        sa.Column('forecast_np_1', sa.Text(), nullable=True, comment='Today forecast in Nepali'),

        # Tomorrow's forecast
        sa.Column('forecast_en_2', sa.Text(), nullable=True, comment='Tomorrow forecast in English'),
        sa.Column('forecast_np_2', sa.Text(), nullable=True, comment='Tomorrow forecast in Nepali'),

        # Special notice
        sa.Column('special_notice', sa.Text(), nullable=True, comment='Special weather warning'),

        # Meteorologist info
        sa.Column('issued_by', sa.String(255), nullable=True, comment='Meteorologist name'),
        sa.Column('updated_by', sa.String(255), nullable=True, comment='Last updater name'),

        # Timestamps
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Index for efficient latest forecast lookup
    op.create_index(
        'idx_weather_forecasts_issue_date',
        'weather_forecasts',
        ['issue_date'],
    )


def downgrade() -> None:
    op.drop_index('idx_weather_forecasts_issue_date', table_name='weather_forecasts')
    op.drop_table('weather_forecasts')
