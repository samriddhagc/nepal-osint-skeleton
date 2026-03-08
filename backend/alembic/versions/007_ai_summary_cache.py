"""Add AI summary cache columns.

Revision ID: 007
Revises: 006
Create Date: 2026-01-28

Stores AI-generated summaries to avoid repeated API calls.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add AI summary cache to stories table
    op.add_column(
        'stories',
        sa.Column(
            'ai_summary',
            JSONB,
            nullable=True,
            comment='Cached AI-generated summary JSON'
        )
    )
    op.add_column(
        'stories',
        sa.Column(
            'ai_summary_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When AI summary was generated'
        )
    )

    # Add index for faster lookup of uncached stories
    op.create_index(
        'idx_stories_ai_summary_null',
        'stories',
        ['id'],
        postgresql_where=sa.text('ai_summary IS NULL')
    )


def downgrade() -> None:
    op.drop_index('idx_stories_ai_summary_null', table_name='stories')
    op.drop_column('stories', 'ai_summary_at')
    op.drop_column('stories', 'ai_summary')
