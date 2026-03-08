"""Add title_entities, title_action, title_district, title_country for Palantir-grade blocking.

Revision ID: 009
Revises: 008
Create Date: 2026-01-28

CRITICAL: These columns enable entity-based hard blocking.
- Stories about different people (Oli vs Karki) should NEVER cluster together.
- Stories about different actions (meeting vs clarification) by same person should be separate.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add title_district column for geographic hard blocking
    op.add_column(
        'story_features',
        sa.Column(
            'title_district',
            sa.String(100),
            nullable=True,
            comment='Primary Nepal district in title for hard blocking'
        )
    )

    # Add title_country column for international story blocking
    op.add_column(
        'story_features',
        sa.Column(
            'title_country',
            sa.String(100),
            nullable=True,
            comment='Primary international country in title for hard blocking'
        )
    )

    # Add title_entities column - CRITICAL for entity-based blocking
    # Stories about Oli should NEVER cluster with stories about Karki
    op.add_column(
        'story_features',
        sa.Column(
            'title_entities',
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment='Canonical named entities in title (e.g., [oli], [karki])'
        )
    )

    # Add title_action column for event-type blocking
    # "Oli clarification" != "Oli meets ambassador"
    op.add_column(
        'story_features',
        sa.Column(
            'title_action',
            sa.String(50),
            nullable=True,
            comment='Canonical action type (meeting, clarification, arrest, etc.)'
        )
    )

    # Create indexes for efficient lookups
    op.create_index(
        'idx_story_features_title_district',
        'story_features',
        ['title_district']
    )

    op.create_index(
        'idx_story_features_title_country',
        'story_features',
        ['title_country']
    )

    op.create_index(
        'idx_story_features_title_action',
        'story_features',
        ['title_action']
    )

    # GIN index for array column (title_entities)
    op.execute(
        'CREATE INDEX idx_story_features_title_entities ON story_features USING GIN (title_entities)'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS idx_story_features_title_entities')
    op.drop_index('idx_story_features_title_action', table_name='story_features')
    op.drop_index('idx_story_features_title_country', table_name='story_features')
    op.drop_index('idx_story_features_title_district', table_name='story_features')
    op.drop_column('story_features', 'title_action')
    op.drop_column('story_features', 'title_entities')
    op.drop_column('story_features', 'title_country')
    op.drop_column('story_features', 'title_district')
