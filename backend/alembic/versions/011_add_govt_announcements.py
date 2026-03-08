"""Add govt_announcements table for government announcements.

Revision ID: 011
Revises: 010
Create Date: 2026-01-28

Stores government announcements from various ministries (MoHA, etc.)
with support for attachments, bilingual content, and Bikram Sambat dates.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'govt_announcements',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('external_id', sa.String(50), unique=True, nullable=False, comment='Hash of URL for deduplication'),

        # Source info
        sa.Column('source', sa.String(100), nullable=False, comment='Source domain (e.g., moha.gov.np)'),
        sa.Column('source_name', sa.String(255), nullable=False, comment='Human-readable source name'),

        # Content
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('category', sa.String(100), nullable=False, comment='press-release, notice, circular'),

        # Dates
        sa.Column('date_bs', sa.String(20), nullable=True, comment='Bikram Sambat date'),
        sa.Column('date_ad', sa.DateTime(timezone=True), nullable=True, comment='Gregorian date'),

        # Attachments (JSON array)
        sa.Column('attachments', postgresql.JSON(), nullable=True, default=list, comment='[{name, url}]'),
        sa.Column('has_attachments', sa.Boolean(), default=False),

        # Full content
        sa.Column('content', sa.Text(), nullable=True, comment='Full content from detail page'),
        sa.Column('content_fetched', sa.Boolean(), default=False),

        # Metadata
        sa.Column('is_read', sa.Boolean(), default=False),
        sa.Column('is_important', sa.Boolean(), default=False),

        # Timestamps
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Indexes for efficient queries
    op.create_index('idx_govt_announcements_source', 'govt_announcements', ['source'])
    op.create_index('idx_govt_announcements_category', 'govt_announcements', ['category'])
    op.create_index('idx_govt_announcements_fetched_at', 'govt_announcements', ['fetched_at'])
    op.create_index('idx_govt_announcements_is_read', 'govt_announcements', ['is_read'])
    op.create_index('idx_govt_announcements_has_attachments', 'govt_announcements', ['has_attachments'])


def downgrade() -> None:
    op.drop_index('idx_govt_announcements_has_attachments', table_name='govt_announcements')
    op.drop_index('idx_govt_announcements_is_read', table_name='govt_announcements')
    op.drop_index('idx_govt_announcements_fetched_at', table_name='govt_announcements')
    op.drop_index('idx_govt_announcements_category', table_name='govt_announcements')
    op.drop_index('idx_govt_announcements_source', table_name='govt_announcements')
    op.drop_table('govt_announcements')
