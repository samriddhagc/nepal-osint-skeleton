"""Add market_data table for NEPSE, forex, gold/silver, and fuel prices.

Revision ID: 012
Revises: 011
Create Date: 2026-01-28

Stores market data from various sources:
- NEPSE index from Nepal Stock Exchange
- USD/NPR forex rate from Nepal Rastra Bank
- Gold/Silver prices from FENEGOSIDA
- Fuel prices from Nepal Oil Corporation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum for market data types
    market_data_type = postgresql.ENUM(
        'nepse', 'forex_usd', 'gold', 'silver', 'petrol', 'diesel', 'kerosene', 'lpg',
        name='marketdatatype',
        create_type=True
    )
    market_data_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'market_data',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # Data type identifier
        sa.Column('data_type', sa.Enum(
            'nepse', 'forex_usd', 'gold', 'silver', 'petrol', 'diesel', 'kerosene', 'lpg',
            name='marketdatatype',
            native_enum=False,
        ), nullable=False),

        # Value and unit
        sa.Column('value', sa.Numeric(precision=12, scale=4), nullable=False, comment='Current value'),
        sa.Column('unit', sa.String(50), nullable=False, comment='NPR, NPR/tola, NPR/litre, points'),

        # Change from previous value
        sa.Column('previous_value', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('change_amount', sa.Numeric(precision=12, scale=4), nullable=True, comment='Absolute change'),
        sa.Column('change_percent', sa.Numeric(precision=8, scale=4), nullable=True, comment='Percentage change'),

        # Source info
        sa.Column('source_name', sa.String(100), nullable=False, comment='Data source name'),
        sa.Column('source_url', sa.String(500), nullable=True, comment='Source URL'),

        # Timestamps
        sa.Column('data_date', sa.DateTime(timezone=True), nullable=False, comment='Date this data is for'),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indexes for efficient queries
    op.create_index('ix_market_data_type_date', 'market_data', ['data_type', 'data_date'])
    op.create_index('ix_market_data_fetched', 'market_data', ['fetched_at'])


def downgrade() -> None:
    op.drop_index('ix_market_data_fetched', table_name='market_data')
    op.drop_index('ix_market_data_type_date', table_name='market_data')
    op.drop_table('market_data')

    # Drop the enum type
    op.execute('DROP TYPE IF EXISTS marketdatatype')
