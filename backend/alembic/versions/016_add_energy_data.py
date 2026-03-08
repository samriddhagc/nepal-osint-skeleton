"""Add energy_data table for NEA power grid data.

Revision ID: 016
Revises: 015
Create Date: 2026-01-29

Stores energy data from Nepal Electricity Authority (NEA):
- NEA Subsidiary Companies (MWh) - NEA owned power plants
- IPP (Independent Power Producers) (MWh)
- Import from India (MWh)
- Interruption/Outages (MWh)
- Total Energy Demand (MWh)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'energy_data',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Data type identifier (using string enum for flexibility)
        sa.Column('data_type', sa.Enum(
            'nea_subsidiary', 'ipp', 'import', 'interruption', 'total_demand',
            name='energydatatype',
            native_enum=False,
        ), nullable=False),

        # Value and unit
        sa.Column('value', sa.Numeric(precision=12, scale=2), nullable=False, comment='Energy value'),
        sa.Column('unit', sa.String(20), nullable=False, server_default='MWh', comment='Unit of measurement'),

        # Change from previous value
        sa.Column('previous_value', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('change_amount', sa.Numeric(precision=12, scale=2), nullable=True, comment='Absolute change'),
        sa.Column('change_percent', sa.Numeric(precision=8, scale=4), nullable=True, comment='Percentage change'),

        # Source info
        sa.Column('source_name', sa.String(100), nullable=False, server_default='Nepal Electricity Authority', comment='Data source name'),
        sa.Column('source_url', sa.String(500), nullable=True, server_default='https://www.nea.org.np', comment='Source URL'),

        # Timestamps
        sa.Column('data_date', sa.DateTime(timezone=True), nullable=False, comment='Date this data is for'),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indexes for efficient queries
    op.create_index('ix_energy_data_type_date', 'energy_data', ['data_type', 'data_date'])
    op.create_index('ix_energy_data_fetched', 'energy_data', ['fetched_at'])


def downgrade() -> None:
    op.drop_index('ix_energy_data_fetched', table_name='energy_data')
    op.drop_index('ix_energy_data_type_date', table_name='energy_data')
    op.drop_table('energy_data')

    # Drop the enum type
    op.execute('DROP TYPE IF EXISTS energydatatype')
