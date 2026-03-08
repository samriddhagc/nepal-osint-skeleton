"""Add topic column to story_features for hard blocking.

Revision ID: 008
Revises: 007
Create Date: 2026-01-28

Stories with different topics should NEVER cluster together.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add topic column to story_features
    op.add_column(
        'story_features',
        sa.Column(
            'topic',
            sa.String(50),
            nullable=True,
            comment='Topic classification (election, weather, sports, stock_market, etc.)'
        )
    )

    # Add index for topic-based queries
    op.create_index(
        'idx_story_features_topic',
        'story_features',
        ['topic']
    )


def downgrade() -> None:
    op.drop_index('idx_story_features_topic', table_name='story_features')
    op.drop_column('story_features', 'topic')
