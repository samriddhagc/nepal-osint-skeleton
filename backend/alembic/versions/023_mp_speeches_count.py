"""Add speeches_count to mp_performance

Revision ID: 023
Revises: 022
Create Date: 2026-02-01

Tracks the number of times an MP has spoken in parliament
(scraped from video archives at hr.parliament.gov.np/en/videos)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '023'
down_revision: Union[str, None] = '022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add speeches_count column to mp_performance
    op.add_column(
        'mp_performance',
        sa.Column('speeches_count', sa.Integer(), nullable=False, server_default='0')
    )


def downgrade() -> None:
    op.drop_column('mp_performance', 'speeches_count')
