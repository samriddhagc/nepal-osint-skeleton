"""Add curfew_alerts table for tracking active curfew orders.

Revision ID: 013
Revises: 012
Create Date: 2026-01-28

Stores curfew alerts detected from DAO and provincial government
announcements. Alerts automatically expire after 24 hours and
trigger map highlighting for affected districts.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'curfew_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),

        # District info
        sa.Column('district', sa.String(100), nullable=False, comment='Affected district name'),
        sa.Column('province', sa.String(100), nullable=True, comment='Province name'),

        # Link to source announcement
        sa.Column('announcement_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('govt_announcements.id', ondelete='SET NULL'),
                  nullable=True, comment='Source announcement ID'),

        # Curfew details
        sa.Column('title', sa.Text(), nullable=False, comment='Announcement title'),
        sa.Column('source', sa.String(255), nullable=False, comment='Source domain'),
        sa.Column('source_name', sa.String(255), nullable=True, comment='Human-readable source'),

        # Detection metadata
        sa.Column('matched_keywords', postgresql.JSONB(), nullable=True,
                  comment='Keywords that triggered detection'),

        # Time bounds
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False, comment='When curfew was detected'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False,
                  comment='When alert expires (24h after detection by default)'),

        # Status
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False,
                  comment='Whether alert is currently active'),
        sa.Column('is_confirmed', sa.Boolean(), default=False, nullable=False,
                  comment='Manual confirmation flag'),

        # Severity
        sa.Column('severity', sa.String(20), default='high', nullable=False,
                  comment='Alert severity: low, medium, high, critical'),

        # Additional context
        sa.Column('notes', sa.Text(), nullable=True, comment='Admin notes'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )

    # Indexes for efficient queries
    op.create_index('idx_curfew_alerts_district', 'curfew_alerts', ['district'])
    op.create_index('idx_curfew_alerts_is_active', 'curfew_alerts', ['is_active'])
    op.create_index('idx_curfew_alerts_expires_at', 'curfew_alerts', ['expires_at'])
    op.create_index('idx_curfew_alerts_severity', 'curfew_alerts', ['severity'])

    # Composite index for active alerts query
    op.create_index(
        'idx_curfew_alerts_active_district',
        'curfew_alerts',
        ['is_active', 'district'],
        postgresql_where=sa.text('is_active = true')
    )


def downgrade() -> None:
    op.drop_index('idx_curfew_alerts_active_district', table_name='curfew_alerts')
    op.drop_index('idx_curfew_alerts_severity', table_name='curfew_alerts')
    op.drop_index('idx_curfew_alerts_expires_at', table_name='curfew_alerts')
    op.drop_index('idx_curfew_alerts_is_active', table_name='curfew_alerts')
    op.drop_index('idx_curfew_alerts_district', table_name='curfew_alerts')
    op.drop_table('curfew_alerts')
